"""CLI for OpenBench - A/B testing platform for Claude agents."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.table import Table
from rich import box

from .storage import ResultStore
from .compare import ResultComparator
from ._tui import make_trial_callback, make_turn_callback

app = typer.Typer(
    name="openbench",
    help="A/B testing platform for Claude agents.",
    add_completion=False,
    pretty_exceptions_show_locals=False,
)

_console = Console()
_err_console = Console(stderr=True, style="bold red")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_experiment(experiment_path: Path):
    """Import an experiment module and return its `experiment` attribute."""
    path = experiment_path.resolve()
    if not path.exists():
        _err_console.print(f"File not found: {path}")
        raise typer.Exit(1)

    spec = importlib.util.spec_from_file_location("_openbench_exp", str(path))
    if spec is None or spec.loader is None:
        _err_console.print(f"Cannot load module from: {path}")
        raise typer.Exit(1)

    module = importlib.util.module_from_spec(spec)
    sys.modules["_openbench_exp"] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        _err_console.print(f"Error loading experiment file: {exc}")
        raise typer.Exit(1) from exc

    if not hasattr(module, "experiment"):
        _err_console.print(
            f"Experiment file must define a top-level `experiment` variable. "
            f"None found in {path}"
        )
        raise typer.Exit(1)

    return module.experiment


def _get_store() -> ResultStore:
    # Results are stored relative to the project root (two levels up from here).
    project_root = Path(__file__).parent.parent.parent
    return ResultStore(results_root=project_root / "results")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.command("run")
def run_experiment(
    experiment_file: Annotated[
        Path,
        typer.Argument(
            help="Path to the experiment Python file (must define `experiment` variable)."
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print experiment details without running it."),
    ] = False,
) -> None:
    """Run an A/B experiment and save the results."""
    from .runner import ExperimentRunner

    experiment = _load_experiment(experiment_file)

    _console.rule(f"[bold cyan]OpenBench Run: {experiment.name}[/bold cyan]")
    _console.print(f"[dim]{experiment.description}[/dim]")
    _console.print(
        f"  Agent A: [green]{experiment.agent_a.name}[/green] ({experiment.agent_a.model})"
    )
    _console.print(
        f"  Agent B: [blue]{experiment.agent_b.name}[/blue] ({experiment.agent_b.model})"
    )
    _console.print(f"  Tasks:   {len(experiment.tasks)}")
    _console.print(f"  Diff:    [yellow]{experiment.diff.field}[/yellow] - {experiment.diff.description}")
    _console.print()

    if dry_run:
        _console.print("[yellow]--dry-run: not executing.[/yellow]")
        raise typer.Exit(0)

    num_tasks = len(experiment.tasks)
    num_samples = experiment.num_samples
    total = num_tasks * num_samples

    runner = ExperimentRunner()
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=_console,
            transient=False,
        ) as progress:
            task_a = progress.add_task(
                f"[green]{experiment.agent_a.name}[/green]", total=total
            )
            task_b = progress.add_task(
                f"[blue]{experiment.agent_b.name}[/blue]", total=total
            )
            cost_acc = [0.0]
            on_trial_done = make_trial_callback(
                progress, task_a, task_b,
                experiment.agent_a.name, experiment.agent_b.name,
                num_tasks, cost_accumulator=cost_acc,
            )
            on_turn = make_turn_callback(
                progress, task_a, task_b,
                experiment.agent_a.name, experiment.agent_b.name,
                num_tasks,
            )
            result = runner.run(experiment, on_trial_done=on_trial_done, on_turn=on_turn)

    except ImportError as exc:
        _err_console.print(str(exc))
        raise typer.Exit(1) from exc
    except Exception as exc:
        _err_console.print(f"Experiment failed: {exc}")
        raise typer.Exit(1) from exc

    store = _get_store()
    saved_path = store.save_result(result)

    _console.print(f"\n[bold green]Done![/bold green] Results saved to: {saved_path}")
    _console.print(f"Run ID: [cyan]{result.run_id}[/cyan]\n")

    # Show comparison
    comparator = ResultComparator(console=_console)
    comparator.compare(result)


@app.command("list")
def list_experiments() -> None:
    """List all stored experiments."""
    store = _get_store()
    experiments = store.list_experiments()

    if not experiments:
        _console.print("[yellow]No experiments found.[/yellow]")
        _console.print(
            "Run an experiment first with:  [bold]openbench run <experiment_file>[/bold]"
        )
        raise typer.Exit(0)

    table = Table(
        title="Stored Experiments",
        box=box.SIMPLE_HEAVY,
        show_header=True,
        header_style="bold",
    )
    table.add_column("Experiment", style="cyan", min_width=25)
    table.add_column("Runs", justify="right", min_width=6)
    table.add_column("Latest Run", min_width=22)
    table.add_column("Tasks", justify="right", min_width=6)

    for exp_name in experiments:
        runs = store.list_runs(exp_name)
        num_runs = len(runs)
        if runs:
            latest = runs[-1]
            latest_at = latest["started_at"][:19].replace("T", " ")
            num_tasks = str(latest.get("num_tasks", "?"))
        else:
            latest_at = "-"
            num_tasks = "-"
        table.add_row(exp_name, str(num_runs), latest_at, num_tasks)

    _console.print(table)


@app.command("compare")
def compare_experiment(
    experiment_name: Annotated[
        str,
        typer.Argument(help="Name of the experiment to compare."),
    ],
    run_id: Annotated[
        Optional[str],
        typer.Option("--run-id", "-r", help="Specific run ID to compare (default: latest)."),
    ] = None,
) -> None:
    """Show an A/B comparison report for an experiment."""
    store = _get_store()

    if run_id:
        result = store.load_by_run_id(experiment_name, run_id)
        if result is None:
            _err_console.print(
                f"Run '{run_id}' not found for experiment '{experiment_name}'."
            )
            raise typer.Exit(1)
    else:
        result = store.load_latest(experiment_name)
        if result is None:
            _err_console.print(
                f"No results found for experiment '{experiment_name}'."
            )
            raise typer.Exit(1)

    comparator = ResultComparator(console=_console)
    comparator.compare(result)


@app.command("show")
def show_experiment(
    experiment_name: Annotated[
        str,
        typer.Argument(help="Name of the experiment."),
    ],
    run_id: Annotated[
        str,
        typer.Argument(help="Run ID to show raw results for."),
    ],
    agent: Annotated[
        Optional[str],
        typer.Option(
            "--agent",
            "-a",
            help="Filter to 'a', 'b', or leave blank for both.",
        ),
    ] = None,
) -> None:
    """Show raw trial results for a specific experiment run."""
    store = _get_store()
    result = store.load_by_run_id(experiment_name, run_id)

    if result is None:
        _err_console.print(
            f"Run '{run_id}' not found for experiment '{experiment_name}'."
        )
        raise typer.Exit(1)

    exp = result.experiment
    _console.rule(f"[bold cyan]{exp.name}[/bold cyan] — run [yellow]{run_id[:8]}...[/yellow]")
    _console.print(f"Started:  {result.started_at}")
    _console.print(f"Finished: {result.finished_at}")
    _console.print()

    def show_trials(trials, label: str, color: str) -> None:
        _console.rule(f"[{color}]{label}[/{color}]")
        for trial in trials:
            m = trial.metrics
            _console.print(
                f"\n[bold]Task {trial.task_index + 1}:[/bold] {trial.task!r}"
            )
            _console.print(f"  Trial ID:  {trial.trial_id}")
            _console.print(f"  Timestamp: {trial.timestamp}")
            _console.print(f"  Stop:      {m.stop_reason}")
            _console.print(f"  Latency:   {m.latency_ms:.0f}ms")
            _console.print(f"  Tokens:    {m.total_tokens} (in={m.input_tokens}, out={m.output_tokens})")
            _console.print(f"  Cost:      ${m.estimated_cost_usd:.6f}")
            _console.print(f"  Turns:     {m.num_turns}")
            _console.print(f"  Tools:     {m.num_tool_calls} — {m.tool_call_names}")
            if m.error:
                _console.print(f"  [red]Error: {m.error}[/red]")
            output_preview = trial.output[:500] if trial.output else "(empty)"
            if len(trial.output) > 500:
                output_preview += f"  [dim]... ({len(trial.output)} chars total)[/dim]"
            _console.print(f"  Output:\n[dim]{output_preview}[/dim]")

    show_a = agent in (None, "a", "agent_a")
    show_b = agent in (None, "b", "agent_b")

    if show_a:
        show_trials(result.trials_a, f"Agent A: {exp.agent_a.name}", "green")
    if show_b:
        show_trials(result.trials_b, f"Agent B: {exp.agent_b.name}", "blue")


@app.command("runs")
def list_runs(
    experiment_name: Annotated[
        str,
        typer.Argument(help="Name of the experiment."),
    ],
) -> None:
    """List all stored runs for an experiment."""
    store = _get_store()
    runs = store.list_runs(experiment_name)

    if not runs:
        _console.print(f"[yellow]No runs found for experiment '{experiment_name}'.[/yellow]")
        raise typer.Exit(0)

    table = Table(
        title=f"Runs for '{experiment_name}'",
        box=box.SIMPLE_HEAVY,
        header_style="bold",
    )
    table.add_column("Run ID", style="cyan", min_width=36)
    table.add_column("Started At", min_width=20)
    table.add_column("Finished At", min_width=20)
    table.add_column("Tasks", justify="right")

    for run in runs:
        table.add_row(
            run["run_id"],
            run["started_at"][:19].replace("T", " "),
            run["finished_at"][:19].replace("T", " "),
            str(run.get("num_tasks", "?")),
        )

    _console.print(table)


@app.command("research")
def auto_research(
    goal: Annotated[
        str,
        typer.Argument(help="Natural language research goal, e.g. 'Find the best system prompt for a coding assistant'"),
    ],
    max_iter: Annotated[int, typer.Option("--max-iter", "-n", help="Maximum iterations")] = 3,
    max_cost: Annotated[float, typer.Option("--max-cost", "-c", help="Max total cost in USD")] = 2.0,
    model: Annotated[str, typer.Option("--model", "-m", help="Model for the agents under test")] = "claude-haiku-4-5",
    max_turns: Annotated[int, typer.Option("--max-turns", help="Max agent turns per trial")] = 3,
    num_samples: Annotated[int, typer.Option("--samples", "-s", help="Trials per (agent, task) pair — use ≥3 for pass@k")] = 1,
    target: Annotated[str, typer.Option("--target", "-t", help="Optimization target: quality,cost,latency")] = "quality",
    domain: Annotated[Optional[str], typer.Option("--domain", "-d", help="Agent domain (auto-detected if not set)")] = None,
    program_file: Annotated[Optional[Path], typer.Option("--program", "-p", help="Load ResearchProgram from JSON file")] = None,
    cn: Annotated[bool, typer.Option("--cn", help="Output final summary in Simplified Chinese.")] = False,
) -> None:
    """Run an automated research loop from a natural language goal.

    Examples:
        openbench research "Find the best system prompt for a coding assistant"
        openbench research "Optimize for customer service quality" --max-iter 5 --model claude-haiku-4-5
        openbench research "Balance speed vs quality for data extraction" --target quality,cost
        openbench research "Find best coding prompt" --samples 5   # enables pass@5
    """
    import json as _json
    from .program import ResearchProgram
    from .autoloop import AutoResearchLoop

    if program_file:
        if not program_file.exists():
            _err_console.print(f"Program file not found: {program_file}")
            raise typer.Exit(1)
        data = _json.loads(program_file.read_text())
        program = ResearchProgram.from_dict(data)
        # Apply CLI overrides
        program.constraints["model"] = model
        program.constraints["max_turns"] = max_turns
        program.constraints["num_samples"] = num_samples
    else:
        targets = [t.strip() for t in target.split(",")]
        program = ResearchProgram.from_natural_language(
            goal,
            domain=domain or "general",
            optimization_targets=targets,
            constraints={
                "model": model,
                "max_turns": max_turns,
                "num_samples": num_samples,
                "allowed_tools": [],
                "max_iterations": max_iter,
                "max_cost_usd": max_cost,
            },
        )

    loop = AutoResearchLoop(store=_get_store())
    loop.run(
        program=program,
        max_iterations=max_iter,
        max_cost_usd=max_cost,
        console=_console,
        lang="zh" if cn else "en",
    )


@app.command("save-program")
def save_program(
    goal: Annotated[str, typer.Argument(help="Natural language research goal")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Output JSON file path")] = Path("program.json"),
    model: Annotated[str, typer.Option("--model")] = "claude-haiku-4-5",
    max_turns: Annotated[int, typer.Option("--max-turns")] = 3,
    target: Annotated[str, typer.Option("--target")] = "quality",
    domain: Annotated[Optional[str], typer.Option("--domain")] = None,
) -> None:
    """Save a ResearchProgram to a JSON file for later use with `research --program`."""
    import json as _json
    from .program import ResearchProgram

    targets = [t.strip() for t in target.split(",")]
    program = ResearchProgram.from_natural_language(
        goal,
        domain=domain or "general",
        optimization_targets=targets,
        constraints={"model": model, "max_turns": max_turns, "allowed_tools": []},
    )
    output.write_text(_json.dumps(program.to_dict(), indent=2, ensure_ascii=False))
    _console.print(f"[green]Saved ResearchProgram to[/green] {output}")
    _console.print(f"[dim]Run with:[/dim] openbench research --program {output}")


@app.command("tui")
def launch_tui() -> None:
    """Launch the interactive history browser (requires: pip install textual)."""
    try:
        from ._history_tui import HistoryApp
    except ImportError:
        _err_console.print(
            "textual is required for the TUI browser.\n"
            "Install it with:  pip install textual"
        )
        raise typer.Exit(1)
    HistoryApp(store=_get_store()).run()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app()


if __name__ == "__main__":
    main()
