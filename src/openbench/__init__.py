"""OpenBench - A/B testing platform for Claude agents."""

__version__ = "0.2.0"

from .types import (
    AgentConfig,
    DiffSpec,
    Experiment,
    ExperimentResult,
    TaskItem,
    TrialMetrics,
    TrialResult,
)

__all__ = [
    "AgentConfig",
    "DiffSpec",
    "Experiment",
    "ExperimentResult",
    "TaskItem",
    "TrialMetrics",
    "TrialResult",
]
