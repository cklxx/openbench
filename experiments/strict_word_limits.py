"""Experiment 3: format-adaptive rules vs stricter word-budget constraints.

Builds on format_adaptive_conciseness (exp 2 winner).
Hypothesis: explicit word budgets per question type and tighter bullet limits
push average score toward 98+ while further reducing token cost.

Run with:
    openbench run experiments/strict_word_limits.py
"""

from openbench.types import AgentConfig, DiffSpec, Experiment

_PROMPT_A = """\
You are a concise Q&A assistant. No preamble, no filler, no repeating the question.

Format rules:
- Factual questions: answer in one sentence or fewer.
- Comparisons/technical concepts: use ≤5 bullet points, each under 15 words.
- Math/logic problems: show only essential steps and the final answer.
- Yes/no questions: start with Yes or No, then ≤1 sentence of justification if needed.

Always: fewest words possible while staying accurate and complete.\
"""

_PROMPT_B = """\
You are a concise Q&A assistant. No preamble, no filler, no repeating the question.
No parenthetical elaborations (avoid phrases like "(i.e. ...)" or "(e.g. ...)").

Format rules:
- Factual questions: ≤50 words.
- Comparisons/technical concepts: ≤3 bullet points, each under 12 words.
- Math/logic problems: one line of working + the final answer only.
- Yes/no questions: start with Yes or No, then ≤15 words of justification if needed.

Always: fewest words possible while staying accurate and complete.\
"""

experiment = Experiment(
    name="strict_word_limits",
    description=(
        "Test whether stricter word budgets (≤3 bullets, ≤50/100-word caps, "
        "no parentheticals) improve over the format-adaptive baseline (exp 2 winner). "
        "Only the system_prompt differs."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="format-adaptive rules (≤5 bullets) vs strict word-budget rules (≤3 bullets + word caps)",
    ),
    agent_a=AgentConfig(
        name="variant_v2_baseline",
        model="claude-haiku-4-5",
        system_prompt=_PROMPT_A,
        max_turns=2,
    ),
    agent_b=AgentConfig(
        name="variant_v3",
        model="claude-haiku-4-5",
        system_prompt=_PROMPT_B,
        max_turns=2,
    ),
    tasks=[
        "What is the capital of Australia?",
        "What are the key differences between TCP and UDP?",
        "Solve: A train travels 120 km in 1.5 hours. What is its average speed in km/h?",
        "Is Python an interpreted language?",
        "Explain what a DNS server does.",
    ],
    tags=["system_prompt", "brevity", "word_limits"],
)
