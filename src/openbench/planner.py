"""ExperimentPlanner — translate natural language goals into concrete A/B experiments."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .program import ResearchProgram
from ._sdk_call import sdk_call
from ._utils import _parse_json
from .types import AgentConfig, DiffSpec, Experiment


@dataclass
class OptimizationStep:
    step_number: int
    hypothesis: str
    experiment: Experiment
    baseline_config: AgentConfig


class ExperimentPlanner:
    """Generates A/B experiment plans from natural language objectives."""

    def __init__(self, model: str = "claude-opus-4-6") -> None:
        self.model = model

    def plan_initial(self, program: ResearchProgram) -> OptimizationStep:
        """Generate the first experiment from a ResearchProgram."""
        prompt = self._initial_prompt(program)
        data = self._call(prompt)
        return self._to_step(data, step_number=1, baseline=None)

    def plan_next(
        self,
        program: ResearchProgram,
        history: list[tuple[OptimizationStep, Any]],  # Any = ExperimentEvaluation
    ) -> OptimizationStep | None:
        """Propose next experiment given history. Returns None if converged."""
        prompt = self._next_prompt(program, history)
        data = self._call(prompt)
        if data.get("converged", False):
            return None
        # Baseline = winning config from most recent step
        last_step, last_eval = history[-1]
        if last_eval.winner == "b":
            baseline = last_step.experiment.agent_b
        else:
            baseline = last_step.experiment.agent_a
        return self._to_step(data, step_number=len(history) + 1, baseline=baseline)

    # ── private ──────────────────────────────────────────────────────────────

    def _call(self, prompt: str) -> dict[str, Any]:
        text = sdk_call(prompt, model=self.model)
        return _parse_json(text)

    def _initial_prompt(self, program: ResearchProgram) -> str:
        model = program.constraints.get("model", "claude-haiku-4-5")
        max_turns = program.constraints.get("max_turns", 3)
        allowed_tools = program.constraints.get("allowed_tools", [])
        tools_str = json.dumps(allowed_tools)

        return f"""You are designing the FIRST A/B experiment in an automated research loop.

RESEARCH OBJECTIVE: {program.objective}
DOMAIN: {program.domain}
OPTIMIZATION TARGETS (priority order): {', '.join(program.optimization_targets)}
MODEL TO USE FOR AGENTS: {model}
MAX TURNS: {max_turns}
ALLOWED TOOLS: {tools_str}
CONTEXT: {program.context or 'None'}

Design ONE A/B experiment where:
- agent_a = conservative baseline (default/simple configuration)
- agent_b = variant testing ONE specific hypothesis
- EXACTLY ONE thing differs between A and B (the diff field)
- Start with system_prompt as the diff — it's highest impact and cheapest to test
- Choose the highest-impact first experiment for the objective

Generate 3-5 representative test tasks for this domain. Tasks should be:
- Realistic for the domain
- Short enough to complete in 2-3 turns
- Diverse (test different aspects of the objective)

Return ONLY valid JSON (no markdown wrapper):
{{
  "experiment_name": "<snake_case_name_under_40_chars>",
  "description": "<1 sentence what we're testing>",
  "hypothesis": "<why agent_b should perform better>",
  "diff_field": "system_prompt",
  "diff_description": "<e.g. 'no system prompt vs chain-of-thought prompt'>",
  "agent_a": {{
    "name": "baseline",
    "system_prompt": null,
    "allowed_tools": {tools_str},
    "max_turns": {max_turns}
  }},
  "agent_b": {{
    "name": "variant_v1",
    "system_prompt": "<the specific system prompt to test>",
    "allowed_tools": {tools_str},
    "max_turns": {max_turns}
  }},
  "tasks": ["<task1>", "<task2>", "<task3>"]
}}"""

    def _next_prompt(
        self,
        program: ResearchProgram,
        history: list[tuple[OptimizationStep, Any]],
    ) -> str:
        model = program.constraints.get("model", "claude-haiku-4-5")
        max_turns = program.constraints.get("max_turns", 3)
        allowed_tools = program.constraints.get("allowed_tools", [])
        tools_str = json.dumps(allowed_tools)

        history_text = []
        for i, (step, eval_result) in enumerate(history):
            exp = step.experiment
            history_text.append(
                f"Step {i+1}: {exp.name}\n"
                f"  Hypothesis: {step.hypothesis}\n"
                f"  Diff ({exp.diff.field}): {exp.diff.description}\n"
                f"  Agent A ({exp.agent_a.name}) score: {eval_result.avg_score_a:.1f}/100\n"
                f"  Agent B ({exp.agent_b.name}) score: {eval_result.avg_score_b:.1f}/100\n"
                f"  Winner: {eval_result.winner} (confidence: {eval_result.confidence:.2f})\n"
                f"  Analysis: {eval_result.analysis}\n"
                f"  Recommendation: {eval_result.recommendation}"
            )

        # Current best config
        last_step, last_eval = history[-1]
        if last_eval.winner == "b":
            best = last_step.experiment.agent_b
        else:
            best = last_step.experiment.agent_a
        best_sp = repr(best.system_prompt) if best.system_prompt else "null"

        return f"""You are proposing the NEXT experiment in an automated research loop.

RESEARCH OBJECTIVE: {program.objective}
OPTIMIZATION TARGETS (priority order): {', '.join(program.optimization_targets)}
MODEL: {model}
MAX TURNS: {max_turns}
ALLOWED TOOLS: {tools_str}

EXPERIMENT HISTORY:
{chr(10).join(history_text)}

CURRENT BEST CONFIG:
  name: {best.name}
  system_prompt: {best_sp}

Based on what we've learned, propose the next experiment.
The current best config becomes agent_a (baseline).
agent_b tests a NEW hypothesis we haven't tried yet.

Rules:
- ONE diff between A and B
- Don't repeat a hypothesis already tested
- Build on what worked (keep winning elements, try something new)
- If scores are converging (both above 85 and delta < 3pts for 2 steps), set converged=true

Return ONLY valid JSON:
{{
  "converged": false,
  "experiment_name": "<snake_case_name>",
  "description": "<what we're testing>",
  "hypothesis": "<why this will improve on current best>",
  "diff_field": "<system_prompt|max_turns|allowed_tools>",
  "diff_description": "<human readable change description>",
  "agent_a": {{
    "name": "{best.name}_baseline",
    "system_prompt": {best_sp},
    "allowed_tools": {tools_str},
    "max_turns": {max_turns}
  }},
  "agent_b": {{
    "name": "variant_v{len(history)+1}",
    "system_prompt": "<new system prompt or same as A if diff_field != system_prompt>",
    "allowed_tools": {tools_str},
    "max_turns": {max_turns}
  }},
  "tasks": {json.dumps([s.experiment.tasks[0] for s in [step for step, _ in history[:1]]] + ["<task2>", "<task3>"])}
}}"""

    def _to_step(
        self,
        data: dict[str, Any],
        step_number: int,
        baseline: AgentConfig | None,
    ) -> OptimizationStep:
        model = data.get("model", "claude-haiku-4-5")

        def make_config(d: dict, default_model: str) -> AgentConfig:
            return AgentConfig(
                name=d["name"],
                model=default_model,
                system_prompt=d.get("system_prompt"),
                allowed_tools=d.get("allowed_tools", []),
                max_turns=int(d.get("max_turns", 3)),
                extra_options={},
            )

        # Use model from constraints if not in data
        agent_a_data = data["agent_a"]
        agent_b_data = data["agent_b"]
        # If a baseline was provided, carry it forward but allow planner to rename it
        if baseline is not None:
            agent_a = AgentConfig(
                name=agent_a_data.get("name", baseline.name),
                model=baseline.model,
                system_prompt=baseline.system_prompt,
                allowed_tools=baseline.allowed_tools,
                max_turns=baseline.max_turns,
                extra_options=baseline.extra_options,
            )
        else:
            agent_a = make_config(agent_a_data, model)
        agent_b = make_config(agent_b_data, model)

        experiment = Experiment(
            name=data["experiment_name"],
            description=data["description"],
            diff=DiffSpec(
                field=data["diff_field"],
                description=data["diff_description"],
            ),
            agent_a=agent_a,
            agent_b=agent_b,
            tasks=data["tasks"],
            tags=["auto_research"],
        )

        return OptimizationStep(
            step_number=step_number,
            hypothesis=data.get("hypothesis", ""),
            experiment=experiment,
            baseline_config=agent_a,
        )
