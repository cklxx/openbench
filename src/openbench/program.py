"""ResearchProgram — the natural language objective driving auto-research."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ResearchProgram:
    """User's natural language research objective (the 'program.md' equivalent)."""

    objective: str
    """What to optimize: e.g. 'Find best system prompt for a coding assistant that maximizes correctness while minimizing verbosity'"""

    domain: str
    """Agent domain: e.g. 'coding assistant', 'customer service', 'data analysis'"""

    optimization_targets: list[str]
    """Ordered priorities: e.g. ['quality', 'cost', 'latency']. First = most important."""

    constraints: dict[str, Any] = field(default_factory=dict)
    """E.g. {'model': 'claude-haiku-4-5', 'max_turns': 3, 'allowed_tools': [], 'max_iterations': 5, 'max_cost_usd': 2.0}"""

    eval_rubric: str | None = None
    """Custom evaluation criteria. If None, auto-generated from objective."""

    context: str = ""
    """Additional domain knowledge or constraints for the planner."""

    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        import dataclasses
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ResearchProgram":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_natural_language(cls, text: str, **overrides) -> "ResearchProgram":
        """Create a basic ResearchProgram from a natural language string.
        The planner will further refine this during planning.
        """
        return cls(
            objective=text,
            domain=overrides.get("domain", "general"),
            optimization_targets=overrides.get("optimization_targets", ["quality"]),
            constraints=overrides.get("constraints", {}),
            eval_rubric=overrides.get("eval_rubric", None),
            context=overrides.get("context", ""),
        )
