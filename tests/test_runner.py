"""Tests for ExperimentRunner.on_trial_done callback."""
from __future__ import annotations

import sys
from typing import Any
from unittest.mock import patch

import pytest

from openbench.runner import ExperimentRunner
from openbench.types import (
    AgentConfig,
    DiffSpec,
    Experiment,
    TrialMetrics,
    TrialResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_experiment(num_tasks: int = 2, num_samples: int = 1) -> Experiment:
    return Experiment(
        name="test_exp",
        description="test",
        diff=DiffSpec(field="system_prompt", description="test"),
        agent_a=AgentConfig(
            name="A",
            model="claude-haiku-4-5",
            system_prompt=None,
            allowed_tools=[],
            max_turns=1,
            extra_options={},
        ),
        agent_b=AgentConfig(
            name="B",
            model="claude-haiku-4-5",
            system_prompt="test",
            allowed_tools=[],
            max_turns=1,
            extra_options={},
        ),
        tasks=[f"task {i}" for i in range(num_tasks)],
        tags=[],
        num_samples=num_samples,
    )


def _make_trial(
    agent_name: str,
    task_index: int,
    cost: float = 0.001,
    error: str | None = None,
) -> TrialResult:
    return TrialResult(
        trial_id="test",
        experiment_name="test_exp",
        agent_name=agent_name,
        task=f"task {task_index}",
        task_index=task_index,
        output="ok",
        metrics=TrialMetrics(
            latency_ms=100.0,
            total_tokens=10,
            input_tokens=8,
            output_tokens=2,
            estimated_cost_usd=cost,
            num_tool_calls=0,
            tool_call_names=[],
            num_turns=1,
            stop_reason="error" if error else "end_turn",
            error=error,
        ),
        timestamp="2026-01-01T00:00:00+00:00",
        workdir="/tmp",
    )


def _run_with_fake_trials(
    experiment: Experiment,
    callback: Any = None,
    error: str | None = None,
) -> Any:
    """Run an experiment with _run_trial patched to return fake data."""
    runner = ExperimentRunner()

    async def fake_trial(exp: Any, config: Any, task: Any, task_index: int, on_turn: Any = None) -> TrialResult:
        return _make_trial(config.name, task_index, error=error)

    with patch("openbench.runner._require_sdk"):
        with patch.object(runner, "_run_trial", new=fake_trial):
            return runner.run(experiment, on_trial_done=callback)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOnTrialDoneCallback:
    def test_called_correct_number_of_times(self) -> None:
        calls: list[tuple] = []
        exp = _make_experiment(num_tasks=3, num_samples=1)
        _run_with_fake_trials(exp, callback=lambda *a: calls.append(a))
        # 3 tasks × 1 sample × 2 agents = 6 calls
        assert len(calls) == 6

    def test_called_with_both_agent_names(self) -> None:
        calls: list[tuple] = []
        exp = _make_experiment(num_tasks=1, num_samples=1)
        _run_with_fake_trials(exp, callback=lambda *a: calls.append(a))
        agent_names = {c[0] for c in calls}
        assert agent_names == {"A", "B"}

    def test_ok_true_on_success(self) -> None:
        calls: list[tuple] = []
        exp = _make_experiment(num_tasks=1, num_samples=1)
        _run_with_fake_trials(exp, callback=lambda *a: calls.append(a))
        assert all(c[2] is True for c in calls)

    def test_ok_false_on_error(self) -> None:
        calls: list[tuple] = []
        exp = _make_experiment(num_tasks=1, num_samples=1)
        _run_with_fake_trials(exp, callback=lambda *a: calls.append(a), error="boom")
        assert all(c[2] is False for c in calls)

    def test_none_callback_no_crash(self) -> None:
        exp = _make_experiment(num_tasks=1, num_samples=1)
        result = _run_with_fake_trials(exp, callback=None)
        assert len(result.trials_a) == 1
        assert len(result.trials_b) == 1

    def test_callback_exception_does_not_cancel_trials(self) -> None:
        def bad_callback(*args: Any) -> None:
            raise RuntimeError("progress broke")

        exp = _make_experiment(num_tasks=2, num_samples=1)
        # Must not raise; both tasks must complete despite the callback error.
        result = _run_with_fake_trials(exp, callback=bad_callback)
        assert len(result.trials_a) == 2
        assert len(result.trials_b) == 2

    def test_cost_usd_passed_as_float(self) -> None:
        calls: list[tuple] = []
        exp = _make_experiment(num_tasks=1, num_samples=1)
        _run_with_fake_trials(exp, callback=lambda *a: calls.append(a))
        # 4th argument is cost_usd
        assert all(isinstance(c[3], float) for c in calls)
        assert all(c[3] >= 0.0 for c in calls)

    def test_num_samples_multiplies_calls(self) -> None:
        calls: list[tuple] = []
        exp = _make_experiment(num_tasks=2, num_samples=3)
        _run_with_fake_trials(exp, callback=lambda *a: calls.append(a))
        # 2 tasks × 3 samples × 2 agents = 12 calls
        assert len(calls) == 12
