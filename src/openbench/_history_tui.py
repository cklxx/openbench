"""Interactive history browser for OpenBench results.

Launch with:  openbench tui
Navigate:     ↑↓ move cursor  Enter select  Esc go back  q quit
"""
from __future__ import annotations

import io

from rich.console import Console
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Label, Static
from textual.containers import Horizontal, VerticalScroll

from .storage import ResultStore


class HistoryApp(App):
    """Two-panel TUI: left = navigation (experiments → runs), right = detail."""

    TITLE = "OpenBench History"
    CSS = """
    #nav {
        width: 42;
        border-right: solid $panel-lighten-2;
    }
    #breadcrumb {
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 2;
    }
    #detail {
        padding: 0 2;
    }
    DataTable {
        height: 1fr;
    }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "back", "Back"),
    ]

    def __init__(self, store: ResultStore) -> None:
        super().__init__()
        self._store = store
        self._current_exp: str | None = None
        self._runs_cache: list[dict] = []

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("  Experiments", id="breadcrumb")
        with Horizontal():
            with VerticalScroll(id="nav"):
                yield DataTable(id="nav-table", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="detail"):
                yield Static("", id="detail-content", markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._show_experiments()

    # ------------------------------------------------------------------
    # Navigation states
    # ------------------------------------------------------------------

    def _show_experiments(self) -> None:
        self._current_exp = None
        self._runs_cache = []

        table = self.query_one("#nav-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Experiment", "Runs", "Latest")

        experiments = self._store.list_experiments()
        for name in experiments:
            runs = self._store.list_runs(name)
            latest = runs[-1]["started_at"][:10] if runs else "—"
            table.add_row(name, str(len(runs)), latest)

        self.query_one("#breadcrumb", Label).update("  Experiments")
        hint = "[dim]↑↓ navigate  Enter select  q quit[/dim]"
        if not experiments:
            hint = "[dim]No experiments found. Run[/dim] [cyan]openbench run[/cyan] [dim]first.[/dim]"
        self.query_one("#detail-content", Static).update(hint)

    def _show_runs(self, exp_name: str) -> None:
        self._current_exp = exp_name
        self._runs_cache = list(reversed(self._store.list_runs(exp_name)))

        table = self.query_one("#nav-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Run ID", "Started", "Tasks")

        for r in self._runs_cache:
            table.add_row(
                r["run_id"][:8] + "…",
                r["started_at"][:16].replace("T", " "),
                str(r.get("num_tasks", "?")),
            )

        self.query_one("#breadcrumb", Label).update(f"  {exp_name}")
        self.query_one("#detail-content", Static).update(
            f"[dim]{len(self._runs_cache)} run(s) — Enter to view comparison[/dim]"
        )

    def _show_comparison(self, run_idx: int) -> None:
        if run_idx >= len(self._runs_cache):
            return
        run = self._runs_cache[run_idx]
        result = self._store.load_by_run_id(self._current_exp, run["run_id"])
        if result is None:
            self.query_one("#detail-content", Static).update("[red]Could not load run.[/red]")
            return

        sio = io.StringIO()
        console = Console(file=sio, force_terminal=True, width=90, highlight=False)
        from .compare import ResultComparator
        ResultComparator(console=console).compare(result)
        self.query_one("#detail-content", Static).update(Text.from_ansi(sio.getvalue()))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = event.cursor_row
        if self._current_exp is None:
            experiments = self._store.list_experiments()
            if idx < len(experiments):
                self._show_runs(experiments[idx])
        else:
            self._show_comparison(idx)

    def action_back(self) -> None:
        if self._current_exp is not None:
            self._show_experiments()
