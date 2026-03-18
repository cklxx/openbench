# openbench — Claude Code Config

You are assisting **ckl** with OpenBench, an A/B testing platform for Claude agents.

---

## Project Overview

OpenBench automates the "plan → run → evaluate → repeat" research loop for optimizing agent configurations. Key concepts:

- **Experiment**: One A/B test with two agent configs (agent_a vs agent_b), differing in exactly ONE variable
- **ResearchProgram**: Natural language objective driving the auto-research loop
- **AutoResearchLoop**: Orchestrates ExperimentPlanner → ExperimentRunner → AutoEvaluator → ResultStore

Entry point: `openbench` CLI (`cli.py`). Run `openbench --help` for commands.

---

## Key Files

| File | Purpose |
|------|---------|
| `src/openbench/types.py` | Core dataclasses (AgentConfig, Experiment, TrialResult, etc.) |
| `src/openbench/runner.py` | Executes A/B agent trials via claude-agent-sdk |
| `src/openbench/evaluator.py` | LLM-as-judge scoring |
| `src/openbench/planner.py` | NL → experiment design (LLM-powered) |
| `src/openbench/autoloop.py` | Orchestration loop |
| `src/openbench/storage.py` | JSONL result persistence under `results/` |
| `src/openbench/_utils.py` | Shared helpers (`_parse_json`) |

---

## Behavior Rules

- **Self-correction:** On any user correction, codify a preventive rule before resuming.
- **Auto-continue:** If next step is obvious, proceed with an inline note. Ask when ambiguous, irreversible, or high-blast-radius.
- **One diff at a time:** When designing experiments, always change exactly ONE variable between agent_a and agent_b.
- **SDK first:** Prefer SDK-reported metrics (tokens, cost, duration) over estimates; fall back only when SDK returns zero.
- **Isolation:** Each agent trial runs in its own `tempfile.TemporaryDirectory` — never share state between trials.

---

## Development

```bash
pip install -e ".[dev]"     # editable install
openbench run experiments/quicktest_model.py   # quick smoke test
openbench research "your goal"                 # full auto-research loop
```

Results are written to `results/<experiment_name>/`.
