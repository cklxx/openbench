"""AutoEvaluator — LLM-as-judge evaluation for A/B agent experiments."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import anyio

from ._sdk_call import sdk_call_async
from ._utils import _parse_json
from .program import ResearchProgram
from .types import ExperimentResult, TrialResult


# ── result types ─────────────────────────────────────────────────────────────

@dataclass
class TaskEvaluation:
    trial_id: str
    task: str
    output: str
    quality_score: float          # 0–100 overall
    dimensions: dict[str, float]  # dimension_name → 0–100
    reasoning: str
    judge_model: str


@dataclass
class ExperimentEvaluation:
    run_id: str
    experiment_name: str
    evals_a: list[TaskEvaluation]
    evals_b: list[TaskEvaluation]
    avg_score_a: float
    avg_score_b: float
    winner: str            # "a", "b", or "tie"
    confidence: float      # 0.0–1.0
    analysis: str          # LLM explanation
    recommendation: str    # what to try next


# ── evaluator ────────────────────────────────────────────────────────────────

class AutoEvaluator:
    """Scores agent outputs using an LLM judge.

    All per-trial evaluations run concurrently (up to *_MAX_CONCURRENT* at once)
    via a single anyio event loop started by evaluate(). This avoids the
    overhead of creating a new event loop for each judge call.
    """

    _MAX_CONCURRENT = 8  # semaphore cap for concurrent LLM judge calls

    def __init__(
        self,
        model: str = "claude-haiku-4-5",
        rubric: str | None = None,
    ) -> None:
        self.model = model
        self.rubric = rubric

    # ── public ───────────────────────────────────────────────────────────────

    def evaluate(
        self,
        result: ExperimentResult,
        program: ResearchProgram,
    ) -> ExperimentEvaluation:
        """Evaluate all trials, compare A vs B, return ExperimentEvaluation.

        Runs all per-trial judge calls concurrently inside a single event loop.
        """
        return anyio.run(self._evaluate_async, result, program)

    # ── private ──────────────────────────────────────────────────────────────

    async def _evaluate_async(
        self,
        result: ExperimentResult,
        program: ResearchProgram,
    ) -> ExperimentEvaluation:
        rubric = self.rubric or program.eval_rubric or self._default_rubric(program)
        sem = anyio.Semaphore(self._MAX_CONCURRENT)

        evals_a: list[TaskEvaluation | None] = [None] * len(result.trials_a)
        evals_b: list[TaskEvaluation | None] = [None] * len(result.trials_b)

        async def _score(
            trial: TrialResult,
            out: list[TaskEvaluation | None],
            idx: int,
        ) -> None:
            async with sem:
                out[idx] = await self._eval_trial_async(trial, program, rubric)

        async with anyio.create_task_group() as tg:
            for i, trial in enumerate(result.trials_a):
                tg.start_soon(_score, trial, evals_a, i)
            for i, trial in enumerate(result.trials_b):
                tg.start_soon(_score, trial, evals_b, i)

        # Cast: all slots filled by the task group above.
        scored_a: list[TaskEvaluation] = evals_a  # type: ignore[assignment]
        scored_b: list[TaskEvaluation] = evals_b  # type: ignore[assignment]

        avg_a = sum(e.quality_score for e in scored_a) / max(len(scored_a), 1)
        avg_b = sum(e.quality_score for e in scored_b) / max(len(scored_b), 1)

        verdict = await self._compare_async(result, program, scored_a, scored_b, avg_a, avg_b)

        return ExperimentEvaluation(
            run_id=result.run_id,
            experiment_name=result.experiment.name,
            evals_a=scored_a,
            evals_b=scored_b,
            avg_score_a=avg_a,
            avg_score_b=avg_b,
            winner=verdict["winner"],
            confidence=verdict["confidence"],
            analysis=verdict["analysis"],
            recommendation=verdict["recommendation"],
        )

    def _default_rubric(self, program: ResearchProgram) -> str:
        targets = ", ".join(program.optimization_targets)
        return (
            f"Evaluate based on: {targets}. "
            "Score task_completion (did the agent finish the task?), "
            "accuracy (is the output correct/helpful?), "
            "and conciseness (is the output appropriately brief?)."
        )

    async def _eval_trial_async(
        self,
        trial: TrialResult,
        program: ResearchProgram,
        rubric: str,
    ) -> TaskEvaluation:
        m = trial.metrics
        prompt = f"""You are evaluating an AI agent's response.

RESEARCH OBJECTIVE: {program.objective}
EVALUATION RUBRIC: {rubric}

TASK: {trial.task}
AGENT OUTPUT:
{trial.output or "(no output)"}

PERFORMANCE METRICS:
- Latency: {m.latency_ms:.0f}ms
- Tokens: {m.total_tokens}
- Cost: ${m.estimated_cost_usd:.5f}
- Tool calls: {m.num_tool_calls}
- Stop reason: {m.stop_reason}
{"- ERROR: " + m.error if m.error else ""}

Score this output. Return ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "quality_score": <0-100 overall>,
  "dimensions": {{
    "task_completion": <0-100>,
    "accuracy": <0-100>,
    "conciseness": <0-100>
  }},
  "reasoning": "<1-2 sentence explanation>"
}}"""

        text = await sdk_call_async(prompt, model=self.model)
        data = _parse_json(text)

        return TaskEvaluation(
            trial_id=trial.trial_id,
            task=trial.task,
            output=trial.output or "",
            quality_score=float(data.get("quality_score", 50)),
            dimensions={k: float(v) for k, v in data.get("dimensions", {}).items()},
            reasoning=data.get("reasoning", ""),
            judge_model=self.model,
        )

    async def _compare_async(
        self,
        result: ExperimentResult,
        program: ResearchProgram,
        evals_a: list[TaskEvaluation],
        evals_b: list[TaskEvaluation],
        avg_a: float,
        avg_b: float,
    ) -> dict[str, Any]:
        exp = result.experiment

        def fmt_evals(evals: list[TaskEvaluation]) -> str:
            lines = []
            for e in evals:
                dims = ", ".join(f"{k}={v:.0f}" for k, v in e.dimensions.items())
                lines.append(
                    f"  Task: {e.task[:60]!r}\n"
                    f"  Score: {e.quality_score:.1f} [{dims}]\n"
                    f"  Reason: {e.reasoning}"
                )
            return "\n".join(lines)

        prompt = f"""You are analyzing A/B agent experiment results.

RESEARCH OBJECTIVE: {program.objective}
OPTIMIZATION TARGETS: {', '.join(program.optimization_targets)}

EXPERIMENT: {exp.name}
DIFF ({exp.diff.field}): {exp.diff.description}
- Agent A ({exp.agent_a.name}): avg_score={avg_a:.1f}/100
- Agent B ({exp.agent_b.name}): avg_score={avg_b:.1f}/100

AGENT A TRIALS:
{fmt_evals(evals_a)}

AGENT B TRIALS:
{fmt_evals(evals_b)}

Determine the winner and recommend the NEXT experiment hypothesis.
Return ONLY valid JSON:
{{
  "winner": "a" or "b" or "tie",
  "confidence": <0.0-1.0>,
  "analysis": "<2-3 sentence analysis of what worked and why>",
  "recommendation": "<specific hypothesis to test next, different from this diff>"
}}"""

        text = await sdk_call_async(prompt, model=self.model)
        return _parse_json(text)
