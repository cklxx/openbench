"""AutoResearchLoop — the main orchestration loop."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.rule import Rule

from ._sdk_call import sdk_call
from .evaluator import AutoEvaluator, ExperimentEvaluation
from .planner import ExperimentPlanner, OptimizationStep
from .program import ResearchProgram
from .runner import ExperimentRunner
from .storage import ResultStore
from .types import AgentConfig, ExperimentResult


@dataclass
class AutoResearchResult:
    program: ResearchProgram
    steps: list[dict[str, Any]] = field(default_factory=list)
    # Each step: {"step": OptimizationStep, "result": ExperimentResult, "eval": ExperimentEvaluation}
    best_config: AgentConfig | None = None
    best_score: float = 0.0
    total_cost_usd: float = 0.0
    total_iterations: int = 0
    converged: bool = False
    summary: str = ""


class AutoResearchLoop:
    """Orchestrates the full automated research loop."""

    # Approximate overhead costs per LLM call (planning + evaluation)
    _PLAN_COST_EST = 0.06    # opus call ~2k tokens
    _EVAL_COST_EST = 0.003   # haiku call per trial

    def __init__(
        self,
        planner: ExperimentPlanner | None = None,
        runner: ExperimentRunner | None = None,
        evaluator: AutoEvaluator | None = None,
        store: ResultStore | None = None,
    ) -> None:
        self._planner = planner or ExperimentPlanner()
        self._runner = runner or ExperimentRunner()
        self._evaluator = evaluator or AutoEvaluator()
        self._store = store or ResultStore()

    def run(
        self,
        program: ResearchProgram,
        max_iterations: int = 3,
        max_cost_usd: float = 5.0,
        console: Console | None = None,
    ) -> AutoResearchResult:
        c = console or Console()
        result = AutoResearchResult(program=program)
        history: list[tuple[OptimizationStep, ExperimentEvaluation]] = []

        c.print()
        c.print(Rule("[bold cyan]AutoResearch Loop[/bold cyan]", style="cyan"))
        c.print(f"[dim]Objective:[/dim] {program.objective}")
        c.print(f"[dim]Targets:[/dim] {', '.join(program.optimization_targets)}")
        c.print(f"[dim]Budget:[/dim] max {max_iterations} iterations · ${max_cost_usd:.2f} max cost")
        c.print()

        for iteration in range(1, max_iterations + 1):
            if result.total_cost_usd >= max_cost_usd:
                c.print(f"[yellow]Budget exhausted (${result.total_cost_usd:.3f} / ${max_cost_usd:.2f}). Stopping.[/yellow]")
                break

            c.print(Rule(f"[bold]Iteration {iteration}/{max_iterations}[/bold]"))

            # ── 1. Plan ──────────────────────────────────────────────────────
            c.print("[bold cyan]▶ Planning[/bold cyan] — generating experiment hypothesis...")
            try:
                if iteration == 1:
                    step = self._planner.plan_initial(program)
                else:
                    step = self._planner.plan_next(program, history)
                    if step is None:
                        c.print("[green]✓ Converged — planner found no further improvements to test.[/green]")
                        result.converged = True
                        break
            except Exception as exc:
                c.print(f"[red]Planning failed: {exc}[/red]")
                break

            result.total_cost_usd += self._PLAN_COST_EST
            exp = step.experiment
            c.print(f"  Hypothesis: [italic]{step.hypothesis}[/italic]")
            c.print(f"  Experiment: [bold]{exp.name}[/bold]")
            c.print(f"  Diff ([yellow]{exp.diff.field}[/yellow]): {exp.diff.description}")
            c.print(f"  Tasks: {len(exp.tasks)} tasks")
            c.print(f"  Agent A: [green]{exp.agent_a.name}[/green] | Agent B: [blue]{exp.agent_b.name}[/blue]")
            c.print()

            # ── 2. Run ───────────────────────────────────────────────────────
            c.print("[bold cyan]▶ Running[/bold cyan] — executing A/B experiment...")
            try:
                exp_result = self._runner.run(exp)
            except Exception as exc:
                c.print(f"[red]Runner failed: {exc}[/red]")
                break

            # Show per-task progress
            for i, (ta, tb) in enumerate(zip(exp_result.trials_a, exp_result.trials_b)):
                task_preview = ta.task[:55] + "..." if len(ta.task) > 55 else ta.task
                ok_a = "✓" if not ta.metrics.error else "✗"
                ok_b = "✓" if not tb.metrics.error else "✗"
                c.print(f"  Task {i+1}: [dim]{task_preview!r}[/dim]")
                c.print(
                    f"    A [{ok_a}] {ta.metrics.latency_ms/1000:.1f}s {ta.metrics.total_tokens}tok  "
                    f"B [{ok_b}] {tb.metrics.latency_ms/1000:.1f}s {tb.metrics.total_tokens}tok"
                )

            # Save to store
            try:
                self._store.save_result(exp_result)
            except Exception:
                pass  # non-fatal

            # Account for trial costs
            trial_cost = sum(t.metrics.estimated_cost_usd for t in exp_result.trials_a + exp_result.trials_b)
            result.total_cost_usd += trial_cost
            c.print()

            # ── 3. Evaluate ──────────────────────────────────────────────────
            c.print("[bold cyan]▶ Evaluating[/bold cyan] — LLM judge scoring outputs...")
            try:
                evaluation = self._evaluator.evaluate(exp_result, program)
            except Exception as exc:
                c.print(f"[red]Evaluation failed: {exc}[/red]")
                break

            eval_cost = len(exp_result.trials_a + exp_result.trials_b) * self._EVAL_COST_EST + 0.003
            result.total_cost_usd += eval_cost

            is_b_winner = evaluation.winner == "b"
            color_a = "green" if evaluation.winner == "a" else "dim"
            color_b = "blue" if is_b_winner else "dim"
            c.print(f"  Agent A avg score: [{color_a}]{evaluation.avg_score_a:.1f}/100[/{color_a}]")
            c.print(f"  Agent B avg score: [{color_b}]{evaluation.avg_score_b:.1f}/100[/{color_b}]")

            delta = evaluation.avg_score_b - evaluation.avg_score_a
            delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
            winner_label = "Agent B" if is_b_winner else "Agent A"
            winner_color = "blue" if is_b_winner else "green"
            winner_name = exp.agent_b.name if is_b_winner else exp.agent_a.name
            c.print(
                f"  Winner: [bold]{winner_label}[/bold] "
                f"([{winner_color}]{winner_name}[/{winner_color}]) "
                f"({delta_str}pts, confidence={evaluation.confidence:.2f})"
            )
            c.print(f"  [dim]{evaluation.analysis}[/dim]")
            c.print()

            # ── 4. Update best ───────────────────────────────────────────────
            winner_config = exp.agent_b if evaluation.winner == "b" else exp.agent_a
            winner_score = evaluation.avg_score_b if evaluation.winner == "b" else evaluation.avg_score_a

            if winner_score > result.best_score:
                result.best_config = winner_config
                result.best_score = winner_score
                c.print(f"  [green]New best config: {winner_config.name} (score={winner_score:.1f})[/green]")

            # Record step
            result.steps.append({
                "step": step,
                "result": exp_result,
                "eval": evaluation,
            })
            history.append((step, evaluation))
            result.total_iterations = iteration
            c.print(f"  [dim]Cumulative cost: ${result.total_cost_usd:.4f}[/dim]")
            c.print()

        # ── Final summary ────────────────────────────────────────────────────
        c.print(Rule("[bold cyan]Research Complete[/bold cyan]", style="cyan"))
        result.summary = self._generate_summary(result)
        c.print(result.summary)
        c.print()

        if result.best_config:
            c.print("[bold]Best Configuration Found:[/bold]")
            c.print(f"  Name:          [green]{result.best_config.name}[/green]")
            c.print(f"  Model:         {result.best_config.model}")
            sp = result.best_config.system_prompt
            if sp:
                preview = sp[:120] + "..." if len(sp) > 120 else sp
                c.print(f"  System Prompt: [italic]{preview}[/italic]")
            else:
                c.print("  System Prompt: (none)")
            c.print(f"  Score:         {result.best_score:.1f}/100")

        c.print(f"\n[dim]Total iterations: {result.total_iterations} | Total cost: ${result.total_cost_usd:.4f}[/dim]")
        return result

    def _generate_summary(self, result: AutoResearchResult) -> str:
        if not result.steps:
            return "No experiments completed."

        history_lines = []
        for s in result.steps:
            step: OptimizationStep = s["step"]
            ev: ExperimentEvaluation = s["eval"]
            history_lines.append(
                f"- Step {step.step_number}: {step.hypothesis[:80]} → winner={ev.winner}, "
                f"A={ev.avg_score_a:.1f}, B={ev.avg_score_b:.1f}"
            )

        prompt = f"""Summarize the key findings from this automated agent research session.

OBJECTIVE: {result.program.objective}

EXPERIMENT HISTORY:
{chr(10).join(history_lines)}

BEST CONFIG SCORE: {result.best_score:.1f}/100
CONVERGED: {result.converged}

Write a 3-5 sentence summary of:
1. What was discovered (which changes helped and why)
2. The best configuration found
3. Recommended next steps (if not converged)

Be concrete and actionable."""

        try:
            return sdk_call(prompt, model="claude-haiku-4-5").strip()
        except Exception:
            return f"Completed {result.total_iterations} iteration(s). Best score: {result.best_score:.1f}/100."
