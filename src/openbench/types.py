"""Core types for OpenBench A/B testing platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentConfig:
    """Configuration for one agent in an A/B test."""

    name: str
    """Human-readable name, e.g. 'agent_a' or 'verbose_prompt'."""

    model: str
    """Claude model identifier, e.g. 'claude-opus-4-6'."""

    system_prompt: str | None = None
    """Optional system prompt override."""

    allowed_tools: list[str] = field(default_factory=list)
    """Tool names the agent may use, e.g. ['Read', 'Bash', 'Glob']."""

    max_turns: int = 10
    """Maximum number of agentic turns."""

    extra_options: dict[str, Any] = field(default_factory=dict)
    """Additional ClaudeAgentOptions fields passed as kwargs."""


@dataclass
class DiffSpec:
    """Describes the single variable being tested between agent_a and agent_b."""

    field: str
    """The field name that differs: 'system_prompt', 'model', 'tools', etc."""

    description: str
    """Human-readable description of the difference."""


@dataclass
class Experiment:
    """Defines a complete A/B experiment."""

    name: str
    """Unique experiment name (used as directory name for results)."""

    description: str
    """What this experiment is measuring."""

    diff: DiffSpec
    """The ONE thing that differs between agent_a and agent_b."""

    agent_a: AgentConfig
    """Control agent."""

    agent_b: AgentConfig
    """Variant agent."""

    tasks: list[str]
    """List of prompts / tasks to run through both agents."""

    tags: list[str] = field(default_factory=list)
    """Arbitrary tags for filtering/searching experiments."""

    num_samples: int = 1
    """Number of independent trials per (agent, task) pair.
    Use ≥3 to compute pass@k metrics. Higher = more reliable estimates, higher cost."""

    setup_files: dict[str, str] = field(default_factory=dict)
    """Files to write into each trial's isolated working directory before the agent starts.
    Keys are relative paths (e.g. 'problem.py'), values are file contents.
    Paths must be relative and must not contain '..' (directory traversal is rejected)."""

    setup_script: str | None = None
    """Optional shell command run in the workdir after setup_files are written
    but before the agent starts. Use for environment setup, e.g. 'pip install -q pytest'.
    A non-zero exit code causes the trial to be recorded as an error."""


@dataclass
class TrialMetrics:
    """Performance metrics for a single agent run on a single task."""

    latency_ms: float
    """Wall-clock time from first token request to final result, in milliseconds."""

    total_tokens: int
    """Total tokens used (input + output). May be estimated if SDK doesn't expose exact counts."""

    input_tokens: int
    """Input / prompt tokens. May be estimated."""

    output_tokens: int
    """Output / completion tokens. May be estimated."""

    estimated_cost_usd: float
    """Estimated cost in USD based on model pricing."""

    num_tool_calls: int
    """Total number of tool-use invocations."""

    tool_call_names: list[str]
    """Ordered list of tool names that were called."""

    num_turns: int
    """Number of assistant turns (AssistantMessage objects received)."""

    stop_reason: str
    """How the run ended: 'end_turn', 'max_turns', 'error', etc."""

    error: str | None
    """Error message if the run failed, otherwise None."""


@dataclass
class TrialResult:
    """Full result for one agent on one task."""

    trial_id: str
    """UUID identifying this specific trial."""

    experiment_name: str
    """Name of the parent experiment."""

    agent_name: str
    """Name of the agent config that ran (e.g. 'agent_a')."""

    task: str
    """The input prompt / task text."""

    task_index: int
    """Zero-based index of this task in the experiment's task list.
    Multiple trials with the same task_index are different samples for pass@k."""

    output: str
    """Final text result produced by the agent."""

    metrics: TrialMetrics
    """Collected performance metrics."""

    timestamp: str
    """ISO-8601 timestamp of when this trial started."""

    workdir: str
    """Temporary working directory that was used for isolation (already deleted)."""


@dataclass
class ExperimentResult:
    """Complete results for an entire experiment run."""

    experiment: Experiment
    """The experiment definition (snapshot at run time)."""

    trials_a: list[TrialResult]
    """All trial results for agent_a. With num_samples>1, contains num_samples entries per task."""

    trials_b: list[TrialResult]
    """All trial results for agent_b. With num_samples>1, contains num_samples entries per task."""

    run_id: str
    """UUID for this specific experiment run."""

    started_at: str
    """ISO-8601 timestamp when the run started."""

    finished_at: str
    """ISO-8601 timestamp when the run finished."""
