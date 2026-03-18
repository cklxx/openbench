"""AutoResearchLoop — the main orchestration loop."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.markdown import Markdown
from rich.rule import Rule

from ._sdk_call import sdk_call
from ._tui import make_trial_callback, make_turn_callback
from .evaluator import AutoEvaluator, ExperimentEvaluation
from .planner import ExperimentPlanner, OptimizationStep
from .program import ResearchProgram
from .runner import ExperimentRunner
from .storage import ResultStore
from .types import AgentConfig


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
    _PLAN_COST_EST = 0.12    # two Opus calls: initial plan + adversarial critique
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
        lang: str = "en",
    ) -> AutoResearchResult:
        c = console or Console()
        result = AutoResearchResult(program=program)
        history: list[tuple[OptimizationStep, ExperimentEvaluation]] = []

        # ── Three-layer live display ─────────────────────────────────────────
        # phase_progress: one row per phase (plan/run/eval), spinner while active,
        #                 stopped when done — rows stay visible as history
        phase_progress = Progress(
            SpinnerColumn(),
            TimeElapsedColumn(),
            TextColumn("{task.description}"),
            console=c,
        )
        # trial_progress: A/B bars during running, hidden after each iteration
        trial_progress = Progress(
            TextColumn("  "),
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=c,
        )
        # overall_progress: one bar across all iterations + live budget
        overall_progress = Progress(
            TextColumn("[bold]Overall[/bold]"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            TextColumn("{task.fields[budget]}"),
            console=c,
        )

        live_group = Group(
            Panel(
                Group(phase_progress, trial_progress),
                title="[bold cyan]AutoResearch Loop[/bold cyan]",
                border_style="cyan",
                padding=(0, 1),
            ),
            overall_progress,
        )

        c.print()
        c.print(f"[dim]Objective:[/dim] {program.objective}")
        c.print(f"[dim]Targets:[/dim]   {', '.join(program.optimization_targets)}")
        c.print(f"[dim]Budget:[/dim]    max {max_iterations} iters · ${max_cost_usd:.2f}")
        c.print()

        with Live(live_group, console=c, refresh_per_second=10, transient=False):
            overall_task = overall_progress.add_task(
                "iterations",
                total=max_iterations,
                budget=f"[dim]${result.total_cost_usd:.3f}/${max_cost_usd:.2f}[/dim]",
            )

            for iteration in range(1, max_iterations + 1):
                if result.total_cost_usd >= max_cost_usd:
                    c.print(f"[yellow]Budget exhausted (${result.total_cost_usd:.3f} / ${max_cost_usd:.2f}). Stopping.[/yellow]")
                    break

                c.print(Rule(
                    f"[bold]Iteration {iteration}/{max_iterations}[/bold]",
                    style="dim",
                ))

                # ── 1. Plan ──────────────────────────────────────────────────
                plan_task = phase_progress.add_task(
                    f"[yellow]Iter {iteration}[/yellow]  Planning…"
                )
                try:
                    if iteration == 1:
                        step = self._planner.plan_initial(program)
                    else:
                        step = self._planner.plan_next(program, history)
                except Exception as exc:
                    phase_progress.update(plan_task, description=f"[red]Iter {iteration}  Planning failed: {exc}[/red]")
                    phase_progress.stop_task(plan_task)
                    break

                if iteration > 1 and step is None:
                    phase_progress.update(plan_task, description=f"[green]Iter {iteration}  Converged[/green]")
                    phase_progress.stop_task(plan_task)
                    c.print("[green]✓ Converged — no further improvements to test.[/green]")
                    result.converged = True
                    break

                result.total_cost_usd += self._PLAN_COST_EST
                exp = step.experiment
                phase_progress.update(
                    plan_task,
                    description=f"[dim]Iter {iteration}[/dim]  [bold]Plan[/bold]  {step.hypothesis[:60]}",
                )
                phase_progress.stop_task(plan_task)

                c.print(
                    f"  [bold cyan]Plan[/bold cyan]  {step.hypothesis}\n"
                    f"  diff=[yellow]{exp.diff.field}[/yellow]: {exp.diff.description}\n"
                    f"  [green]{exp.agent_a.name}[/green] vs [blue]{exp.agent_b.name}[/blue]"
                    f"  —  {len(exp.tasks)} task(s)"
                )

                # ── 2. Run ───────────────────────────────────────────────────
                num_tasks = len(exp.tasks)
                total_trials = num_tasks * exp.num_samples

                run_task = phase_progress.add_task(
                    f"[yellow]Iter {iteration}[/yellow]  Running…"
                )
                prog_a = trial_progress.add_task(
                    f"[green]{exp.agent_a.name}[/green]", total=total_trials
                )
                prog_b = trial_progress.add_task(
                    f"[blue]{exp.agent_b.name}[/blue]", total=total_trials
                )
                on_trial_done = make_trial_callback(
                    trial_progress, prog_a, prog_b,
                    exp.agent_a.name, exp.agent_b.name,
                    num_tasks,
                )
                on_turn = make_turn_callback(
                    trial_progress, prog_a, prog_b,
                    exp.agent_a.name, exp.agent_b.name,
                    num_tasks,
                )

                try:
                    exp_result = self._runner.run(exp, on_trial_done=on_trial_done, on_turn=on_turn)
                except Exception as exc:
                    phase_progress.update(run_task, description=f"[red]Iter {iteration}  Run failed: {exc}[/red]")
                    phase_progress.stop_task(run_task)
                    trial_progress.update(prog_a, visible=False)
                    trial_progress.update(prog_b, visible=False)
                    break

                # Hide trial bars; mark phase done
                trial_progress.update(prog_a, visible=False)
                trial_progress.update(prog_b, visible=False)
                phase_progress.update(
                    run_task,
                    description=f"[dim]Iter {iteration}[/dim]  [bold]Run[/bold]  {len(exp.tasks)} tasks complete",
                )
                phase_progress.stop_task(run_task)

                # Per-task text summary (scrolls above the live panel)
                for i, (ta, tb) in enumerate(zip(exp_result.trials_a, exp_result.trials_b)):
                    preview = ta.task[:60] + "…" if len(ta.task) > 60 else ta.task
                    ok_a = "[green]✓[/green]" if not ta.metrics.error else "[red]✗[/red]"
                    ok_b = "[green]✓[/green]" if not tb.metrics.error else "[red]✗[/red]"
                    c.print(
                        f"  T{i+1} "
                        f"{ok_a}[green]{ta.metrics.latency_ms/1000:.1f}s {ta.metrics.total_tokens}tok[/green]"
                        f"  {ok_b}[blue]{tb.metrics.latency_ms/1000:.1f}s {tb.metrics.total_tokens}tok[/blue]"
                        f"  [dim]{preview!r}[/dim]"
                    )

                # Save to store
                try:
                    self._store.save_result(exp_result)
                except Exception:
                    pass  # non-fatal

                trial_cost = sum(t.metrics.estimated_cost_usd for t in exp_result.trials_a + exp_result.trials_b)
                result.total_cost_usd += trial_cost

                # ── 3. Evaluate ──────────────────────────────────────────────
                eval_task = phase_progress.add_task(
                    f"[yellow]Iter {iteration}[/yellow]  Evaluating…"
                )
                try:
                    evaluation = self._evaluator.evaluate(exp_result, program)
                except Exception as exc:
                    phase_progress.update(eval_task, description=f"[red]Iter {iteration}  Eval failed: {exc}[/red]")
                    phase_progress.stop_task(eval_task)
                    break

                eval_cost = len(exp_result.trials_a + exp_result.trials_b) * self._EVAL_COST_EST + 0.003
                result.total_cost_usd += eval_cost

                delta = evaluation.avg_score_b - evaluation.avg_score_a
                delta_str = f"{delta:+.1f}"
                _VERDICT = {
                    "a":   ("green",  "A",   exp.agent_a.name),
                    "b":   ("blue",   "B",   exp.agent_b.name),
                    "tie": ("yellow", "Tie", "—"),
                }
                winner_color, winner_label, winner_name = _VERDICT[evaluation.winner]

                phase_progress.update(
                    eval_task,
                    description=(
                        f"[dim]Iter {iteration}[/dim]  [bold]Eval[/bold]  "
                        f"Winner=[bold {winner_color}]{winner_label}: {winner_name}[/bold {winner_color}]"
                        f" ({delta_str}pts)"
                    ),
                )
                phase_progress.stop_task(eval_task)

                ca = "green" if evaluation.winner == "a" else "dim"
                cb = "blue"  if evaluation.winner == "b" else "dim"
                c.print(
                    f"  [bold cyan]Scores[/bold cyan]  "
                    f"A=[{ca}]{evaluation.avg_score_a:.1f}[/{ca}]  "
                    f"B=[{cb}]{evaluation.avg_score_b:.1f}[/{cb}]  "
                    f"Winner=[bold {winner_color}]{winner_label}: {winner_name}[/bold {winner_color}]"
                    f" ({delta_str}pts, conf={evaluation.confidence:.2f})"
                )
                c.print(f"  [dim]{evaluation.analysis}[/dim]")

                # ── 4. Update best ───────────────────────────────────────────
                use_b = evaluation.winner == "b" or evaluation.avg_score_b >= evaluation.avg_score_a
                winner_config = exp.agent_b if use_b else exp.agent_a
                winner_score = evaluation.avg_score_b if use_b else evaluation.avg_score_a

                if winner_score > result.best_score:
                    result.best_config = winner_config
                    result.best_score = winner_score
                    c.print(f"  [green]★ New best: {winner_config.name} (score={winner_score:.1f})[/green]")

                result.steps.append({"step": step, "result": exp_result, "eval": evaluation})
                history.append((step, evaluation))
                result.total_iterations = iteration

                # Advance overall bar + refresh budget display
                overall_progress.advance(overall_task)
                overall_progress.update(
                    overall_task,
                    budget=f"[dim]${result.total_cost_usd:.3f}/${max_cost_usd:.2f}[/dim]",
                )
                c.print()

        # ── Final summary ────────────────────────────────────────────────────
        c.print(Rule("[bold cyan]Research Complete[/bold cyan]", style="cyan"))
        result.summary = self._generate_summary(result, lang=lang)
        c.print(Markdown(result.summary))
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

    def _generate_summary(self, result: AutoResearchResult, lang: str = "en") -> str:
        if not result.steps:
            return "No experiments completed."

        history_lines = []
        for s in result.steps:
            step: OptimizationStep = s["step"]
            ev: ExperimentEvaluation = s["eval"]
            delta = ev.avg_score_b - ev.avg_score_a
            conclusive = ev.confidence >= 0.6 and abs(delta) >= 2
            history_lines.append(
                f"- Step {step.step_number} (conf={ev.confidence:.2f}, delta={delta:+.1f}pts, "
                f"{'CONCLUSIVE' if conclusive else 'INCONCLUSIVE'}): "
                f"{step.hypothesis[:80]}\n"
                f"  → winner={ev.winner}, A={ev.avg_score_a:.1f}, B={ev.avg_score_b:.1f}\n"
                f"  → analysis: {ev.analysis}"
            )

        prompt = f"""You are summarizing an automated agent research session. Be analytically rigorous.

OBJECTIVE: {result.program.objective}

EXPERIMENT HISTORY (with confidence and conclusiveness flags):
{chr(10).join(history_lines)}

BEST CONFIG SCORE: {result.best_score:.1f}/100
CONVERGED: {result.converged}

Write a 4-6 sentence summary covering:
1. Which changes produced CONCLUSIVE improvements (high confidence, meaningful delta) vs which were noise
2. The best configuration and what specifically made it better
3. Any surprising or counter-intuitive findings
4. Recommended next steps — if results were mostly inconclusive, say so and suggest why

Do NOT blindly declare winners from low-confidence or near-zero-delta results.
Be concrete, honest about uncertainty, and actionable.
{("Reply in Simplified Chinese." if lang == "zh" else "")}"""

        try:
            return sdk_call(prompt, model="claude-opus-4-6").strip()
        except Exception:
            return f"Completed {result.total_iterations} iteration(s). Best score: {result.best_score:.1f}/100."
