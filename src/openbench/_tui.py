"""TUI helpers shared between cli.py and autoloop.py."""
from __future__ import annotations

from collections.abc import Callable

from rich.progress import Progress


def make_turn_callback(
    progress: Progress,
    task_a_id: object,
    task_b_id: object,
    agent_a_name: str,
    agent_b_name: str,
    num_tasks: int,
) -> Callable[[str, int, str], None]:
    """Return a closure for ``ExperimentRunner.on_turn``.

    Updates the progress bar description with a live snippet of the agent's
    current turn output — gives real-time visibility into what each agent is
    generating while the trial is still running.

    Args:
        progress:      The rich Progress instance.
        task_a_id:     Task ID from progress.add_task() for agent A.
        task_b_id:     Task ID from progress.add_task() for agent B.
        agent_a_name:  Name of agent A.
        agent_b_name:  Name of agent B.
        num_tasks:     Total task count for "T{i}/{num_tasks}" display.
    """

    def on_turn(agent_name: str, task_index: int, text: str) -> None:
        snippet = text.replace("\n", " ")
        if len(snippet) > 50:
            snippet = snippet[:50] + "…"
        is_a = agent_name == agent_a_name
        task_id = task_a_id if is_a else task_b_id
        color = "green" if is_a else "blue"
        label = agent_a_name if is_a else agent_b_name
        progress.update(
            task_id,
            description=(
                f"[{color}]{label}[/{color}]"
                f" T{task_index + 1}/{num_tasks}"
                f" [dim italic]{snippet}[/dim italic]"
            ),
        )

    return on_turn


def make_trial_callback(
    progress: Progress,
    task_a_id: object,
    task_b_id: object,
    agent_a_name: str,
    agent_b_name: str,
    num_tasks: int,
    cost_accumulator: list[float] | None = None,
) -> Callable[[str, int, bool, float], None]:
    """Return a closure for ``ExperimentRunner.on_trial_done``.

    Advances the appropriate progress bar and updates the description after
    each trial completes.

    Args:
        progress:         The rich Progress instance.
        task_a_id:        Task ID from progress.add_task() for agent A.
        task_b_id:        Task ID from progress.add_task() for agent B.
        agent_a_name:     Name of agent A — routes callback to the right bar.
        agent_b_name:     Name of agent B.
        num_tasks:        Total task count for "T{i}/{num_tasks}" display.
        cost_accumulator: Optional single-element list ``[running_total]``.
                          When provided, cost is summed across all trials and
                          appended to the last-updated bar's description.
    """

    def on_trial_done(
        agent_name: str, task_index: int, ok: bool, cost_usd: float
    ) -> None:
        icon = "" if ok else " [red]✗[/red]"
        cost_str = ""
        if cost_accumulator is not None:
            cost_accumulator[0] += cost_usd
            cost_str = f" [dim]${cost_accumulator[0]:.4f}[/dim]"

        if agent_name == agent_a_name:
            progress.advance(task_a_id)
            progress.update(
                task_a_id,
                description=(
                    f"[green]{agent_a_name}[/green]"
                    f" T{task_index + 1}/{num_tasks}{icon}{cost_str}"
                ),
            )
        else:
            progress.advance(task_b_id)
            progress.update(
                task_b_id,
                description=(
                    f"[blue]{agent_b_name}[/blue]"
                    f" T{task_index + 1}/{num_tasks}{icon}{cost_str}"
                ),
            )

    return on_trial_done
