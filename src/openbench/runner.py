"""ExperimentRunner - orchestrates A/B agent runs and collects metrics."""

from __future__ import annotations

import subprocess
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

import anyio

from .isolation import isolated_workdir
from .metrics import calculate_cost, estimate_tokens_from_text
from .types import (
    AgentConfig,
    Experiment,
    ExperimentResult,
    TrialMetrics,
    TrialResult,
)

# ---------------------------------------------------------------------------
# SDK import with graceful error
# ---------------------------------------------------------------------------

try:
    import claude_agent_sdk
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        ToolUseBlock,
    )
    _SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SDK_AVAILABLE = False
    claude_agent_sdk = None  # type: ignore[assignment]
    AssistantMessage = None  # type: ignore[assignment]
    ClaudeAgentOptions = None  # type: ignore[assignment]
    ResultMessage = None  # type: ignore[assignment]
    ToolUseBlock = None  # type: ignore[assignment]


def _require_sdk() -> None:
    if not _SDK_AVAILABLE:
        raise ImportError(
            "claude-agent-sdk is not installed.\n"
            "Install it with:  pip install claude-agent-sdk\n"
            "See https://github.com/anthropics/claude-agent-sdk-python"
        )


# ---------------------------------------------------------------------------
# Internal async helpers
# ---------------------------------------------------------------------------

async def _run_setup_script(script: str, workdir: str) -> None:
    """Run a shell setup script inside the workdir before the agent starts.

    Uses a thread to avoid blocking the event loop during subprocess execution.
    Raises RuntimeError with stderr output if the script exits non-zero.
    """
    def _run() -> subprocess.CompletedProcess:  # type: ignore[type-arg]
        return subprocess.run(
            script,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
        )

    result = await anyio.to_thread.run_sync(_run)
    if result.returncode != 0:
        raise RuntimeError(
            f"setup_script exited with code {result.returncode}.\n"
            f"stderr: {result.stderr[:500]}"
        )


async def _run_agent_async(
    config: AgentConfig,
    task: str,
    workdir: str,
    on_turn: Callable[[str], None] | None = None,
) -> tuple[str, list[str], int, int, int, str, str | None, int, float]:
    """Run a single agent asynchronously and return raw collected data.

    Args:
        on_turn: Optional callback called after each assistant turn with the
                 text content of that turn. Used for live streaming display.

    Returns:
        Tuple of:
            (output, tool_call_names, num_turns,
             input_tokens, output_tokens,
             stop_reason, error, sdk_duration_ms, sdk_cost_usd)
    """
    options_kwargs: dict = {
        "model": config.model,
        "max_turns": config.max_turns,
        "cwd": workdir,
        "allowed_tools": list(config.allowed_tools),
    }

    if config.system_prompt is not None:
        options_kwargs["system_prompt"] = config.system_prompt

    for k, v in (config.extra_options or {}).items():
        options_kwargs[k] = v

    options = ClaudeAgentOptions(**options_kwargs)

    output: str = ""
    tool_call_names: list[str] = []
    num_turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = "unknown"
    error: str | None = None
    sdk_duration_ms: int = 0
    sdk_cost_usd: float = 0.0

    try:
        async for message in claude_agent_sdk.query(prompt=task, options=options):
            if isinstance(message, AssistantMessage):
                num_turns += 1
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        tool_call_names.append(block.name)
                if message.usage:
                    input_tokens += message.usage.get("input_tokens", 0)
                    output_tokens += message.usage.get("output_tokens", 0)
                if on_turn is not None:
                    text_parts = [
                        getattr(b, "text", "") for b in message.content
                        if not isinstance(b, ToolUseBlock) and getattr(b, "text", "")
                    ]
                    if text_parts:
                        try:
                            on_turn(" ".join(text_parts))
                        except Exception:  # noqa: BLE001
                            pass

            elif isinstance(message, ResultMessage):
                output = message.result or ""
                stop_reason = message.stop_reason or "end_turn"
                sdk_duration_ms = message.duration_ms
                if message.is_error:
                    error = output
                    stop_reason = "error"
                if message.total_cost_usd is not None:
                    sdk_cost_usd = message.total_cost_usd
                if message.usage:
                    u = message.usage
                    reported_input = u.get("input_tokens", 0)
                    reported_output = u.get("output_tokens", 0)
                    if reported_input > input_tokens:
                        input_tokens = reported_input
                    if reported_output > output_tokens:
                        output_tokens = reported_output

    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        stop_reason = "error"
        output = ""

    return (
        output,
        tool_call_names,
        num_turns,
        input_tokens,
        output_tokens,
        stop_reason,
        error,
        sdk_duration_ms,
        sdk_cost_usd,
    )


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------

class ExperimentRunner:
    """Runs an experiment and collects all metrics.

    Agent A and Agent B trials run concurrently per task. When num_samples > 1,
    all samples for both agents run concurrently within the same task group.
    Tasks still execute sequentially to respect API rate limits.

    Usage::

        runner = ExperimentRunner()
        result = runner.run(experiment)
    """

    def run(
        self,
        experiment: Experiment,
        on_trial_done: Callable[[str, int, bool, float], None] | None = None,
        on_turn: Callable[[str, int, str], None] | None = None,
    ) -> ExperimentResult:
        """Run the experiment synchronously and return the full result.

        Args:
            experiment: The experiment to run.
            on_trial_done: Optional callback invoked after each trial completes.
                Signature: ``on_trial_done(agent_name, task_index, ok, cost_usd)``
            on_turn: Optional callback invoked after each assistant turn during
                a trial. Signature: ``on_turn(agent_name, task_index, text)``
                where *text* is the combined text content of that turn.
                Both callbacks swallow exceptions so a UI bug never cancels trials.
        """
        _require_sdk()
        return anyio.run(self._run_async, experiment, on_trial_done, on_turn)

    async def _run_async(
        self,
        experiment: Experiment,
        on_trial_done: Callable[[str, int, bool, float], None] | None,
        on_turn: Callable[[str, int, str], None] | None = None,
    ) -> ExperimentResult:
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()

        trials_a: list[TrialResult] = []
        trials_b: list[TrialResult] = []

        for task_index, task in enumerate(experiment.tasks):
            n = experiment.num_samples

            # Pre-allocate result slots; filled concurrently by the task group.
            slot_a: list[TrialResult | None] = [None] * n
            slot_b: list[TrialResult | None] = [None] * n

            async with anyio.create_task_group() as tg:
                for s in range(n):
                    tg.start_soon(
                        self._run_and_store,
                        experiment, experiment.agent_a, task, task_index, slot_a, s,
                        on_trial_done, on_turn,
                    )
                    tg.start_soon(
                        self._run_and_store,
                        experiment, experiment.agent_b, task, task_index, slot_b, s,
                        on_trial_done, on_turn,
                    )

            trials_a.extend(t for t in slot_a if t is not None)
            trials_b.extend(t for t in slot_b if t is not None)

        finished_at = datetime.now(timezone.utc).isoformat()

        return ExperimentResult(
            experiment=experiment,
            trials_a=trials_a,
            trials_b=trials_b,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
        )

    async def _run_and_store(
        self,
        experiment: Experiment,
        config: AgentConfig,
        task: str,
        task_index: int,
        results: list[TrialResult | None],
        slot: int,
        on_trial_done: Callable[[str, int, bool, float], None] | None = None,
        on_turn: Callable[[str, int, str], None] | None = None,
    ) -> None:
        """Run one trial and store the result at results[slot]."""
        _agent_on_turn: Callable[[str], None] | None = None
        if on_turn is not None:
            def _agent_on_turn(text: str) -> None:
                try:
                    on_turn(config.name, task_index, text)
                except Exception:  # noqa: BLE001
                    pass

        trial = await self._run_trial(experiment, config, task, task_index, on_turn=_agent_on_turn)
        results[slot] = trial
        if on_trial_done is not None:
            ok = trial.metrics.error is None and trial.metrics.stop_reason != "error"
            try:
                on_trial_done(config.name, task_index, ok, trial.metrics.estimated_cost_usd)
            except Exception as exc:  # noqa: BLE001
                import sys
                print(f"[warn] on_trial_done raised: {exc}", file=sys.stderr)

    async def _run_trial(
        self,
        experiment: Experiment,
        config: AgentConfig,
        task: str,
        task_index: int,
        on_turn: Callable[[str], None] | None = None,
    ) -> TrialResult:
        trial_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        with isolated_workdir(setup_files=experiment.setup_files or None) as workdir:
            workdir_str = str(workdir)

            # Run optional setup script before the agent starts.
            if experiment.setup_script:
                try:
                    await _run_setup_script(experiment.setup_script, workdir_str)
                except RuntimeError as exc:
                    # Record setup failure as a trial error; skip running the agent.
                    metrics = TrialMetrics(
                        latency_ms=0.0,
                        total_tokens=0,
                        input_tokens=0,
                        output_tokens=0,
                        estimated_cost_usd=0.0,
                        num_tool_calls=0,
                        tool_call_names=[],
                        num_turns=0,
                        stop_reason="error",
                        error=f"setup_script failed: {exc}",
                    )
                    return TrialResult(
                        trial_id=trial_id,
                        experiment_name=experiment.name,
                        agent_name=config.name,
                        task=task,
                        task_index=task_index,
                        output="",
                        metrics=metrics,
                        timestamp=timestamp,
                        workdir=workdir_str,
                    )

            wall_start = time.monotonic()
            (
                output,
                tool_call_names,
                num_turns,
                input_tokens,
                output_tokens,
                stop_reason,
                error,
                sdk_duration_ms,
                sdk_cost_usd,
            ) = await _run_agent_async(config, task, workdir_str, on_turn=on_turn)
            wall_elapsed_ms = (time.monotonic() - wall_start) * 1000.0

        latency_ms = float(sdk_duration_ms) if sdk_duration_ms > 0 else wall_elapsed_ms

        if input_tokens == 0 and output_tokens == 0:
            input_text = task + (config.system_prompt or "")
            input_tokens = estimate_tokens_from_text(input_text)
            output_tokens = estimate_tokens_from_text(output)

        total_tokens = input_tokens + output_tokens

        estimated_cost_usd = (
            sdk_cost_usd if sdk_cost_usd > 0
            else calculate_cost(config.model, input_tokens, output_tokens)
        )

        metrics = TrialMetrics(
            latency_ms=latency_ms,
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost_usd,
            num_tool_calls=len(tool_call_names),
            tool_call_names=tool_call_names,
            num_turns=num_turns,
            stop_reason=stop_reason,
            error=error,
        )

        return TrialResult(
            trial_id=trial_id,
            experiment_name=experiment.name,
            agent_name=config.name,
            task=task,
            task_index=task_index,
            output=output,
            metrics=metrics,
            timestamp=timestamp,
            workdir=workdir_str,
        )
