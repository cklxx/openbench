"""Result persistence - JSONL storage and loading."""

from __future__ import annotations

import dataclasses
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import (
    AgentConfig,
    DiffSpec,
    Experiment,
    ExperimentResult,
    TrialMetrics,
    TrialResult,
)

# Default results root relative to this file's package location.
_DEFAULT_RESULTS_ROOT = Path(__file__).parent.parent.parent / "results"


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------

def _to_dict(obj: Any) -> Any:
    """Recursively convert dataclasses / lists / dicts to JSON-safe primitives."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, Path):
        return str(obj)
    return obj


def _metrics_from_dict(d: dict[str, Any]) -> TrialMetrics:
    return TrialMetrics(
        latency_ms=d["latency_ms"],
        total_tokens=d["total_tokens"],
        input_tokens=d["input_tokens"],
        output_tokens=d["output_tokens"],
        estimated_cost_usd=d["estimated_cost_usd"],
        num_tool_calls=d["num_tool_calls"],
        tool_call_names=d["tool_call_names"],
        num_turns=d["num_turns"],
        stop_reason=d["stop_reason"],
        error=d.get("error"),
    )


def _trial_from_dict(d: dict[str, Any]) -> TrialResult:
    return TrialResult(
        trial_id=d["trial_id"],
        experiment_name=d["experiment_name"],
        agent_name=d["agent_name"],
        task=d["task"],
        task_index=d["task_index"],
        output=d["output"],
        metrics=_metrics_from_dict(d["metrics"]),
        timestamp=d["timestamp"],
        workdir=d["workdir"],
    )


def _agent_config_from_dict(d: dict[str, Any]) -> AgentConfig:
    return AgentConfig(
        name=d["name"],
        model=d["model"],
        system_prompt=d.get("system_prompt"),
        allowed_tools=d.get("allowed_tools", []),
        max_turns=d.get("max_turns", 10),
        extra_options=d.get("extra_options", {}),
    )


def _experiment_from_dict(d: dict[str, Any]) -> Experiment:
    return Experiment(
        name=d["name"],
        description=d["description"],
        diff=DiffSpec(field=d["diff"]["field"], description=d["diff"]["description"]),
        agent_a=_agent_config_from_dict(d["agent_a"]),
        agent_b=_agent_config_from_dict(d["agent_b"]),
        tasks=d["tasks"],
        tags=d.get("tags", []),
    )


def _experiment_result_from_dict(d: dict[str, Any]) -> ExperimentResult:
    return ExperimentResult(
        experiment=_experiment_from_dict(d["experiment"]),
        trials_a=[_trial_from_dict(t) for t in d["trials_a"]],
        trials_b=[_trial_from_dict(t) for t in d["trials_b"]],
        run_id=d["run_id"],
        started_at=d["started_at"],
        finished_at=d["finished_at"],
    )


# ---------------------------------------------------------------------------
# ResultStore
# ---------------------------------------------------------------------------

class ResultStore:
    """Persist and retrieve experiment results.

    File layout::

        results/
          <experiment_name>/
            <run_id>.jsonl          # one TrialResult per line
            <run_id>_meta.json      # full ExperimentResult (minus individual trials)
    """

    def __init__(self, results_root: str | Path | None = None) -> None:
        if results_root is None:
            results_root = _DEFAULT_RESULTS_ROOT
        self.results_root = Path(results_root)

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def save_result(self, experiment_result: ExperimentResult) -> Path:
        """Persist *experiment_result* to disk.

        Returns the path to the JSONL file.
        """
        exp_dir = self.results_root / experiment_result.experiment.name
        exp_dir.mkdir(parents=True, exist_ok=True)

        run_id = experiment_result.run_id
        jsonl_path = exp_dir / f"{run_id}.jsonl"
        meta_path = exp_dir / f"{run_id}_meta.json"

        # Write each trial as a single JSONL line
        all_trials = experiment_result.trials_a + experiment_result.trials_b
        with jsonl_path.open("w", encoding="utf-8") as fh:
            for trial in all_trials:
                fh.write(json.dumps(_to_dict(trial), ensure_ascii=False) + "\n")

        # Write full metadata (includes experiment definition + summary)
        meta: dict[str, Any] = {
            "run_id": run_id,
            "experiment": _to_dict(experiment_result.experiment),
            "started_at": experiment_result.started_at,
            "finished_at": experiment_result.finished_at,
            "num_tasks": len(experiment_result.experiment.tasks),
            "trials_a_count": len(experiment_result.trials_a),
            "trials_b_count": len(experiment_result.trials_b),
        }
        meta_path.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return jsonl_path

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def load_results(self, experiment_name: str) -> list[ExperimentResult]:
        """Load all runs for *experiment_name* from disk.

        Returns a list of ExperimentResult objects sorted oldest-first.
        """
        exp_dir = self.results_root / experiment_name
        if not exp_dir.exists():
            return []

        import warnings

        results: list[ExperimentResult] = []
        for meta_path in exp_dir.glob("*_meta.json"):
            run_id = meta_path.stem.replace("_meta", "")
            jsonl_path = exp_dir / f"{run_id}.jsonl"
            if not jsonl_path.exists():
                continue
            try:
                result = self._load_one(meta_path, jsonl_path)
                results.append(result)
            except Exception as exc:  # noqa: BLE001
                # Skip corrupted files but don't crash the whole load
                warnings.warn(
                    f"Could not load result from {meta_path}: {exc}",
                    stacklevel=2,
                )
        results.sort(key=lambda r: r.started_at)
        return results

    def load_latest(self, experiment_name: str) -> ExperimentResult | None:
        """Return the most recent run for *experiment_name*, or None."""
        results = self.load_results(experiment_name)
        return results[-1] if results else None

    def load_by_run_id(
        self, experiment_name: str, run_id: str
    ) -> ExperimentResult | None:
        """Return a specific run by its run_id, or None if not found."""
        exp_dir = self.results_root / experiment_name
        meta_path = exp_dir / f"{run_id}_meta.json"
        jsonl_path = exp_dir / f"{run_id}.jsonl"
        if not meta_path.exists() or not jsonl_path.exists():
            return None
        return self._load_one(meta_path, jsonl_path)

    def _load_one(self, meta_path: Path, jsonl_path: Path) -> ExperimentResult:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

        trials_a: list[TrialResult] = []
        trials_b: list[TrialResult] = []

        agent_a_name = meta["experiment"]["agent_a"]["name"]
        with jsonl_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                trial = _trial_from_dict(json.loads(line))
                if trial.agent_name == agent_a_name:
                    trials_a.append(trial)
                else:
                    trials_b.append(trial)

        # Sort by task_index to restore original order
        trials_a.sort(key=lambda t: t.task_index)
        trials_b.sort(key=lambda t: t.task_index)

        return ExperimentResult(
            experiment=_experiment_from_dict(meta["experiment"]),
            trials_a=trials_a,
            trials_b=trials_b,
            run_id=meta["run_id"],
            started_at=meta["started_at"],
            finished_at=meta["finished_at"],
        )

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_experiments(self) -> list[str]:
        """Return experiment names that have at least one result on disk."""
        if not self.results_root.exists():
            return []
        return sorted(
            d.name
            for d in self.results_root.iterdir()
            if d.is_dir() and any(d.glob("*_meta.json"))
        )

    def list_runs(self, experiment_name: str) -> list[dict[str, Any]]:
        """Return summary dicts for all runs of *experiment_name*."""
        exp_dir = self.results_root / experiment_name
        if not exp_dir.exists():
            return []
        runs = []
        for meta_path in exp_dir.glob("*_meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                runs.append(
                    {
                        "run_id": meta["run_id"],
                        "started_at": meta["started_at"],
                        "finished_at": meta["finished_at"],
                        "num_tasks": meta.get("num_tasks", "?"),
                    }
                )
            except Exception:  # noqa: BLE001
                pass
        runs.sort(key=lambda r: r["started_at"])
        return runs
