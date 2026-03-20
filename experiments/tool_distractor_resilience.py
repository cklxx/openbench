"""
Experiment 3: Tool Distractor Resilience — Accuracy vs Tool Count

OPEN QUESTION: Models have a "Chekhov's gun" effect — they tend to use ALL
provided tools even when unnecessary. How does accuracy degrade as we add
irrelevant distractor tools?

Published: "Tool preferences in agentic LLMs are unreliable" (2025).
NOT published: degradation CURVE for haiku vs sonnet, or which model
is more robust to distractor tools.

Design: Same simple task, vary allowed_tools from [Bash] to [Bash + 19 distractors].
The task only needs Bash. Extra tools are distractors.

4 conditions: 1 tool, 5 tools, 10 tools, 20 tools.
"""
from openbench.types import AgentConfig, TaskItem, TournamentConfig

# The task only needs Bash to run Python one-liners
TASK = TaskItem(
    prompt=(
        "Calculate the sum of all prime numbers below 100. "
        "Use a Python one-liner via Bash. Give the final number."
    ),
    expected="1060",
    check_fn='"1060" in output',
    difficulty="easy",
    tags=["primes", "simple-calculation"],
)

# Distractor tool sets (tools that exist in the SDK but are irrelevant)
TOOLS_1 = ["Bash"]
TOOLS_5 = ["Bash", "Read", "Write", "Glob", "Edit"]
TOOLS_10 = ["Bash", "Read", "Write", "Glob", "Edit",
            "Grep", "WebSearch", "WebFetch", "NotebookEdit", "Agent"]
TOOLS_20 = ["Bash", "Read", "Write", "Glob", "Edit",
            "Grep", "WebSearch", "WebFetch", "NotebookEdit", "Agent",
            "TodoRead", "TodoWrite", "MultiEdit", "Lint",
            "SearchReplace", "FileManager", "Terminal", "Browser",
            "ImageGen", "Summarize"]

def make_config(name, model, tools):
    return AgentConfig(
        name=name,
        model=model,
        system_prompt=None,  # No hint about which tool to use
        allowed_tools=tools,
        max_turns=6,
    )

tournament = TournamentConfig(
    name="tool_distractor_resilience",
    description=(
        "Same task, varying tool count (1/5/10/20). "
        "Measures distractor tool impact on haiku vs sonnet."
    ),
    configs=[
        # Haiku with varying tools
        make_config("haiku_1tool", "claude-haiku-4-5", TOOLS_1),
        make_config("haiku_5tools", "claude-haiku-4-5", TOOLS_5),
        make_config("haiku_10tools", "claude-haiku-4-5", TOOLS_10),
        make_config("haiku_20tools", "claude-haiku-4-5", TOOLS_20),
        # Sonnet with varying tools
        make_config("sonnet_1tool", "claude-sonnet-4-6", TOOLS_1),
        make_config("sonnet_5tools", "claude-sonnet-4-6", TOOLS_5),
        make_config("sonnet_10tools", "claude-sonnet-4-6", TOOLS_10),
        make_config("sonnet_20tools", "claude-sonnet-4-6", TOOLS_20),
    ],
    tasks=[
        TASK,
        # Second task: slightly more complex, still only needs Bash
        TaskItem(
            prompt=(
                "Write a Python script that computes the first 20 Fibonacci numbers "
                "and prints them as a comma-separated list. Run it via Bash."
            ),
            expected="6765",
            check_fn='"6765" in output',  # F(20)=6765
            difficulty="easy",
            tags=["fibonacci", "simple"],
        ),
        # Third task: needs Read + Bash (2 tools useful out of N)
        TaskItem(
            prompt=(
                "Read the file data.csv in the current directory. "
                "Count the number of lines (excluding the header). "
                "Print just the count."
            ),
            expected="10",
            check_fn='"10" in output',
            difficulty="easy",
            tags=["file-read", "counting"],
        ),
    ],
    setup_files={
        "data.csv": "name,age,salary,department\nAlice,30,75000,Engineering\nBob,25,55000,Marketing\nCarol,35,92000,Engineering\nDave,28,61000,Marketing\nEve,32,88000,Engineering\nFrank,45,105000,Management\nGrace,29,58000,Marketing\nHank,38,95000,Engineering\nIvy,33,72000,Sales\nJack,41,99000,Management\n",
    },
    num_samples=3,
    tags=["distractor-tools", "resilience", "chekhov-gun"],
)
