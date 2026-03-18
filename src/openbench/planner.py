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
        data = self._critique_and_revise(data, program)
        return self._to_step(data, step_number=1, baseline=None, program=program)

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
        data = self._critique_and_revise(data, program)
        # Baseline = winning config from most recent step
        last_step, last_eval = history[-1]
        if last_eval.winner == "b":
            baseline = last_step.experiment.agent_b
        else:
            baseline = last_step.experiment.agent_a
        return self._to_step(data, step_number=len(history) + 1, baseline=baseline, program=program)

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

DIFF ISOLATION RULES (critical):
- A and B must express the SAME intent using different styles — not different intents
- If testing "fuzzy vs rigid rules": both prompts must cover the same quality dimensions,
  just expressed differently (e.g. A: "use ≤3 bullets" / B: "use bullets when listing discrete items")
- If A uses numeric constraints, calibrate them to be achievable for the chosen tasks
  (e.g. don't set a 100-word limit on tasks that inherently need 300+ words)
- agent_a must have a genuine chance of winning — if the deck is stacked, the result is useless

TASK DIVERSITY RULES:
- Include at least 3 different task TYPES from: factual lookup, analytical/explanatory,
  code/math/logic, structured data, creative, yes/no judgment
- Do NOT use the same topic repeated across tasks
- Tasks must be realistic for the domain AND plausibly testable within {program.constraints.get('max_turns', 3)} turns

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

    def _critique_and_revise(self, plan: dict[str, Any], program: ResearchProgram) -> dict[str, Any]:
        """Adversarial critique pass: check for confirmation bias, bad diff, task imbalance.
        Returns the original plan if clean, or a revised plan if issues are found."""
        a_sp = plan.get("agent_a", {}).get("system_prompt") or "(none)"
        b_sp = plan.get("agent_b", {}).get("system_prompt") or "(none)"
        tasks = plan.get("tasks", [])

        critique_prompt = f"""You are an adversarial reviewer of A/B experiment designs.
Your job is to find flaws that would make the result uninterpretable or biased.

RESEARCH OBJECTIVE: {program.objective}

PROPOSED EXPERIMENT:
  Name: {plan.get('experiment_name')}
  Hypothesis: {plan.get('hypothesis')}
  Diff field: {plan.get('diff_field')} — {plan.get('diff_description')}
  Agent A system_prompt: {a_sp}
  Agent B system_prompt: {b_sp}
  Tasks: {json.dumps(tasks, ensure_ascii=False)}

Check for these FOUR specific failure modes:

1. CONFIRMATION BIAS: Does the experiment design almost guarantee B wins?
   (e.g. the research goal IS the hypothesis, tasks are cherry-picked to favor B's approach)

2. DIRTY DIFF: Do A and B differ on more than one conceptual dimension?
   (e.g. A has format rules, B has quality rules — these are different intents, not same intent expressed differently)

3. MISCALIBRATED CONSTRAINTS: If A has numeric limits (word counts, bullet counts), are they
   realistic for the chosen tasks? Would A be forced to truncate or pad unnaturally?

4. TASK IMBALANCE: Are all tasks the same type (e.g. all analytical essays)?
   A fair test needs variety — at least 2 different task types.

Return ONLY valid JSON:
{{
  "issues": ["<issue description>", ...],  // empty list if none
  "needs_revision": true or false,
  "revised_agent_a_system_prompt": "<revised prompt or null if no change needed>",
  "revised_agent_b_system_prompt": "<revised prompt or null if no change needed>",
  "revised_tasks": ["<task>", ...] or null  // null if tasks are fine
}}"""

        critique = self._call(critique_prompt)
        if not critique.get("needs_revision", False):
            return plan

        # Apply revisions
        revised = dict(plan)
        if critique.get("revised_agent_a_system_prompt"):
            revised["agent_a"] = dict(plan["agent_a"])
            revised["agent_a"]["system_prompt"] = critique["revised_agent_a_system_prompt"]
        if critique.get("revised_agent_b_system_prompt"):
            revised["agent_b"] = dict(plan["agent_b"])
            revised["agent_b"]["system_prompt"] = critique["revised_agent_b_system_prompt"]
        revised_tasks = critique.get("revised_tasks")
        if revised_tasks is not None and len(revised_tasks) > 0:
            revised["tasks"] = revised_tasks
        return revised

    def _to_step(
        self,
        data: dict[str, Any],
        step_number: int,
        baseline: AgentConfig | None,
        program: ResearchProgram | None = None,
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

        constraints = (program.constraints if program is not None else {})
        num_samples = int(data.get("num_samples") or constraints.get("num_samples", 1))

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
            num_samples=num_samples,
        )

        return OptimizationStep(
            step_number=step_number,
            hypothesis=data.get("hypothesis", ""),
            experiment=experiment,
            baseline_config=agent_a,
        )
