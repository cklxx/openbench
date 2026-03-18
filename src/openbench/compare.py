"""ResultComparator - compare agent A vs agent B and render a report."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from rich.console import Console
from rich.table import Table
from rich import box

from .metrics import pass_at_k
from .types import ExperimentResult, TrialResult

_console = Console()


def _avg(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _delta_pct(a: float, b: float) -> str:
    """Return a formatted percentage-change string (B relative to A)."""
    if a == 0:
        return "N/A"
    pct = (b - a) / a * 100.0
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


def _success(trial: TrialResult) -> bool:
    return trial.metrics.stop_reason != "error" and trial.metrics.error is None


class ResultComparator:
    """Build and print comparison reports for an ExperimentResult."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or _console

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def compare(self, result: ExperimentResult) -> None:
        """Print a full comparison report to the console."""
        exp = result.experiment
        c = self._console

        c.rule(f"[bold cyan]Experiment: {exp.name}[/bold cyan]")
        c.print(f"[dim]{exp.description}[/dim]")
        c.print()

        # Show the diff
        diff = exp.diff
        val_a = self._field_value(exp.agent_a, diff.field)
        val_b = self._field_value(exp.agent_b, diff.field)
        c.print(
            f"[bold]Diff ([yellow]{diff.field}[/yellow]):[/bold] {diff.description}"
        )
        c.print(f"  Agent A ([green]{exp.agent_a.name}[/green]): {self._truncate(val_a)}")
        c.print(f"  Agent B ([blue]{exp.agent_b.name}[/blue]):  {self._truncate(val_b)}")
        c.print()

        # Per-task results (only when num_samples == 1 to avoid flooding output)
        if exp.num_samples == 1:
            for idx, (trial_a, trial_b) in enumerate(
                zip(result.trials_a, result.trials_b)
            ):
                self._print_task(idx + 1, trial_a, trial_b)
        else:
            c.print(
                f"[dim]num_samples={exp.num_samples} — "
                f"{len(result.trials_a)} agent-A trials, "
                f"{len(result.trials_b)} agent-B trials[/dim]"
            )
            c.print()

        # Summary table
        self._print_summary(result)

        # pass@k table (only when num_samples > 1)
        if exp.num_samples > 1:
            self._print_pass_at_k(result)

    # ------------------------------------------------------------------
    # Per-task output
    # ------------------------------------------------------------------

    def _print_task(
        self,
        num: int,
        trial_a: TrialResult,
        trial_b: TrialResult,
    ) -> None:
        c = self._console
        task_preview = trial_a.task if len(trial_a.task) <= 70 else trial_a.task[:67] + "..."
        c.print(f"[bold]Task {num}:[/bold] [italic]\"{task_preview}\"[/italic]")

        def fmt_trial(trial: TrialResult, label: str, color: str) -> str:
            m = trial.metrics
            status = "[green]✓[/green]" if _success(trial) else "[red]✗[/red]"
            latency = f"{m.latency_ms / 1000:.2f}s"
            tokens = f"{m.total_tokens:,} tokens"
            cost = f"${m.estimated_cost_usd:.5f}"
            tools = f"{m.num_tool_calls} tools"
            turns = f"{m.num_turns} turns"
            err = f" [red]ERR: {m.error[:60]}[/red]" if m.error else ""
            return (
                f"  [{color}]{label}[/{color}] {status} "
                f"{latency}, {tokens}, {cost}, {tools}, {turns}{err}"
            )

        c.print(fmt_trial(trial_a, f"Agent A ({trial_a.agent_name})", "green"))
        c.print(fmt_trial(trial_b, f"Agent B ({trial_b.agent_name})", "blue"))
        c.print()

    # ------------------------------------------------------------------
    # Summary table
    # ------------------------------------------------------------------

    def _print_summary(self, result: ExperimentResult) -> None:
        c = self._console
        n = len(result.experiment.tasks)
        ns = result.experiment.num_samples
        label = f"{n} task{'s' if n != 1 else ''}"
        if ns > 1:
            label += f" × {ns} samples"
        c.rule(f"[bold]SUMMARY ({label})[/bold]")

        def collect(trials: list[TrialResult]) -> dict[str, Any]:
            latencies = [t.metrics.latency_ms for t in trials]
            tokens = [float(t.metrics.total_tokens) for t in trials]
            costs = [t.metrics.estimated_cost_usd for t in trials]
            tools = [float(t.metrics.num_tool_calls) for t in trials]
            successes = sum(1 for t in trials if _success(t))
            return {
                "latency_ms": _avg(latencies),
                "tokens": _avg(tokens),
                "cost": _avg(costs),
                "tools": _avg(tools),
                "successes": successes,
                "total": len(trials),
            }

        stats_a = collect(result.trials_a)
        stats_b = collect(result.trials_b)

        table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
        table.add_column("Metric", style="bold", min_width=12)
        table.add_column(
            f"Agent A\n({result.experiment.agent_a.name})",
            style="green",
            justify="right",
            min_width=18,
        )
        table.add_column(
            f"Agent B\n({result.experiment.agent_b.name})",
            style="blue",
            justify="right",
            min_width=18,
        )
        table.add_column("Delta (B vs A)", justify="right", min_width=14)

        def delta_style(a: float, b: float, lower_is_better: bool = True) -> str:
            if a == 0:
                return "N/A"
            pct = (b - a) / a * 100.0
            sign = "+" if pct >= 0 else ""
            s = f"{sign}{pct:.1f}%"
            if lower_is_better:
                color = "green" if pct < 0 else ("red" if pct > 5 else "yellow")
            else:
                color = "green" if pct > 0 else ("red" if pct < -5 else "yellow")
            return f"[{color}]{s}[/{color}]"

        latency_a = stats_a["latency_ms"] / 1000
        latency_b = stats_b["latency_ms"] / 1000
        table.add_row(
            "Latency",
            f"{latency_a:.2f}s",
            f"{latency_b:.2f}s",
            delta_style(latency_a, latency_b, lower_is_better=True),
        )
        table.add_row(
            "Tokens (avg)",
            f"{stats_a['tokens']:,.0f}",
            f"{stats_b['tokens']:,.0f}",
            delta_style(stats_a["tokens"], stats_b["tokens"], lower_is_better=True),
        )
        table.add_row(
            "Cost (avg)",
            f"${stats_a['cost']:.5f}",
            f"${stats_b['cost']:.5f}",
            delta_style(stats_a["cost"], stats_b["cost"], lower_is_better=True),
        )
        table.add_row(
            "Tools (avg)",
            f"{stats_a['tools']:.1f}",
            f"{stats_b['tools']:.1f}",
            delta_style(stats_a["tools"], stats_b["tools"], lower_is_better=True),
        )

        succ_a = f"{stats_a['successes']}/{stats_a['total']}"
        succ_b = f"{stats_b['successes']}/{stats_b['total']}"
        succ_delta = delta_style(
            float(stats_a["successes"]),
            float(stats_b["successes"]),
            lower_is_better=False,
        )
        table.add_row("Successes", succ_a, succ_b, succ_delta)

        c.print(table)

    # ------------------------------------------------------------------
    # pass@k table
    # ------------------------------------------------------------------

    def _print_pass_at_k(self, result: ExperimentResult) -> None:
        """Print per-task pass@k table. Only called when num_samples > 1."""
        c = self._console
        n = result.experiment.num_samples

        # Group trials by task_index.
        by_task_a: dict[int, list[TrialResult]] = defaultdict(list)
        by_task_b: dict[int, list[TrialResult]] = defaultdict(list)
        for t in result.trials_a:
            by_task_a[t.task_index].append(t)
        for t in result.trials_b:
            by_task_b[t.task_index].append(t)

        task_indices = sorted(set(by_task_a) | set(by_task_b))
        # k values to report: always include 1 and n; add midpoint if n >= 4.
        ks = sorted({1, n // 2, n} - {0}) if n >= 4 else sorted({1, n})

        c.rule(f"[bold]PASS@k  (n={n} samples per task)[/bold]")

        table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
        table.add_column("Task", style="bold", min_width=6)
        table.add_column("k", justify="right", min_width=4)
        table.add_column(
            f"Agent A\n({result.experiment.agent_a.name})",
            style="green", justify="right", min_width=14,
        )
        table.add_column(
            f"Agent B\n({result.experiment.agent_b.name})",
            style="blue", justify="right", min_width=14,
        )
        table.add_column("Winner", justify="center", min_width=8)

        for task_idx in task_indices:
            trials_a = by_task_a.get(task_idx, [])
            trials_b = by_task_b.get(task_idx, [])
            n_a = len(trials_a)
            n_b = len(trials_b)
            c_a = sum(1 for t in trials_a if _success(t))
            c_b = sum(1 for t in trials_b if _success(t))

            # One sample of the task text for display
            task_label = f"T{task_idx + 1}"

            first_row = True
            for k in ks:
                p_a = pass_at_k(n_a, c_a, k) if n_a >= k else 0.0
                p_b = pass_at_k(n_b, c_b, k) if n_b >= k else 0.0
                winner = (
                    "[green]A[/green]" if p_a > p_b
                    else "[blue]B[/blue]" if p_b > p_a
                    else "[dim]tie[/dim]"
                )
                table.add_row(
                    task_label if first_row else "",
                    str(k),
                    f"{p_a:.2%}",
                    f"{p_b:.2%}",
                    winner,
                )
                first_row = False

        c.print(table)

        # Overall pass@k (aggregate across all tasks).
        c.print("[bold]Overall pass@k (all tasks, all samples):[/bold]")
        all_a = result.trials_a
        all_b = result.trials_b
        n_all = len(all_a)
        c_all_a = sum(1 for t in all_a if _success(t))
        c_all_b = sum(1 for t in all_b if _success(t))

        for k in ks:
            if n_all >= k:
                p_a = pass_at_k(n_all, c_all_a, k)
                p_b = pass_at_k(n_all, c_all_b, k)
                winner = "A" if p_a > p_b else "B" if p_b > p_a else "tie"
                c.print(f"  pass@{k}: A={p_a:.2%}  B={p_b:.2%}  → {winner}")

        c.print()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _field_value(obj: Any, field: str) -> Any:
        return getattr(obj, field, "<not set>")

    @staticmethod
    def _truncate(val: Any, max_len: int = 80) -> str:
        s = str(val)
        if len(s) > max_len:
            return s[:max_len - 3] + "..."
        return s


def compare(result: ExperimentResult, console: Console | None = None) -> None:
    """Convenience function: print a comparison report for *result*."""
    ResultComparator(console=console).compare(result)
