"""ExperimentRunner - orchestrates A/B agent runs and collects metrics."""

from __future__ import annotations

import time
import uuid
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

async def _run_agent_async(
    config: AgentConfig,
    task: str,
    workdir: str,
) -> tuple[str, list[str], int, int, int, str, str | None, int, float]:
    """Run a single agent asynchronously and return raw collected data.

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

    # Merge extra_options (user-supplied overrides)
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
                # Collect tool use blocks
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        tool_call_names.append(block.name)
                # Accumulate token usage if the SDK exposes it per message
                if message.usage:
                    input_tokens += message.usage.get("input_tokens", 0)
                    output_tokens += message.usage.get("output_tokens", 0)

            elif isinstance(message, ResultMessage):
                output = message.result or ""
                stop_reason = message.stop_reason or "end_turn"
                sdk_duration_ms = message.duration_ms
                if message.is_error:
                    error = output
                    stop_reason = "error"
                # Prefer SDK-reported cost and usage when available
                if message.total_cost_usd is not None:
                    sdk_cost_usd = message.total_cost_usd
                if message.usage:
                    u = message.usage
                    # ResultMessage.usage may contain cumulative totals
                    reported_input = u.get("input_tokens", 0)
                    reported_output = u.get("output_tokens", 0)
                    # Only override our per-message accumulation if the
                    # ResultMessage gives us a larger (cumulative) value.
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

    Usage::

        runner = ExperimentRunner()
        result = runner.run(experiment)
    """

    def run(self, experiment: Experiment) -> ExperimentResult:
        """Run the experiment synchronously and return the full result."""
        _require_sdk()
        return anyio.run(self._run_async, experiment)

    async def _run_async(self, experiment: Experiment) -> ExperimentResult:
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()

        trials_a: list[TrialResult] = []
        trials_b: list[TrialResult] = []

        for task_index, task in enumerate(experiment.tasks):
            # ---- agent_a ----
            trial_a = await self._run_trial(
                experiment.name,
                experiment.agent_a,
                task,
                task_index,
            )
            trials_a.append(trial_a)

            # ---- agent_b ----
            trial_b = await self._run_trial(
                experiment.name,
                experiment.agent_b,
                task,
                task_index,
            )
            trials_b.append(trial_b)

        finished_at = datetime.now(timezone.utc).isoformat()

        return ExperimentResult(
            experiment=experiment,
            trials_a=trials_a,
            trials_b=trials_b,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
        )

    async def _run_trial(
        self,
        experiment_name: str,
        config: AgentConfig,
        task: str,
        task_index: int,
    ) -> TrialResult:
        trial_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        with isolated_workdir() as workdir:
            workdir_str = str(workdir)

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
            ) = await _run_agent_async(config, task, workdir_str)
            wall_elapsed_ms = (time.monotonic() - wall_start) * 1000.0

        # Prefer SDK-reported duration; fall back to wall-clock.
        latency_ms = float(sdk_duration_ms) if sdk_duration_ms > 0 else wall_elapsed_ms

        # If token counts are zero (SDK didn't report them), estimate from text.
        if input_tokens == 0 and output_tokens == 0:
            # Estimate: input ~ task + system_prompt, output ~ response
            input_text = task + (config.system_prompt or "")
            input_tokens = estimate_tokens_from_text(input_text)
            output_tokens = estimate_tokens_from_text(output)

        total_tokens = input_tokens + output_tokens

        # Prefer SDK cost if available, otherwise calculate from token estimates.
        if sdk_cost_usd > 0:
            estimated_cost_usd = sdk_cost_usd
        else:
            estimated_cost_usd = calculate_cost(config.model, input_tokens, output_tokens)

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
            experiment_name=experiment_name,
            agent_name=config.name,
            task=task,
            task_index=task_index,
            output=output,
            metrics=metrics,
            timestamp=timestamp,
            workdir=workdir_str,
        )
