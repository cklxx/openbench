# Design: Tool & Skill A/B Testing

**Status:** ACTIVE
**Date:** 2026-03-19
**Review:** /plan-ceo-review (SELECTIVE EXPANSION)

## Problem

OpenBench can optimize agent prompts but cannot autonomously discover optimal tool configurations. The planner passes `allowed_tools` identically to both agents, so the research loop is blind to tool improvements. There is also no concept of a named, versioned skill — prompts are anonymous strings.

## Goal

Make OpenBench a **capability optimizer**, not just a prompt optimizer. The research loop should be able to ask and answer:
- "What is the optimal tool set for a coding assistant?"
- "Does adding Glob improve file-search tasks?"
- "Which version of the chain-of-thought skill performs best?"

## Accepted Scope

### Baseline (Approach B)
- **Planner tool-varying:** `_initial_prompt` and `_next_prompt` emit different `allowed_tools` per agent when `diff_field == "allowed_tools"`
- **Tool-aware task design:** Planner generates tasks that exercise the tool difference (file-search tasks for Glob experiments, etc.)
- **Tool-quality evaluation:** `AutoEvaluator` gains a `tool_efficiency` dimension; judge prompt includes `tool_call_names` sequence
- **`agent_input` fix:** `runner.py` includes `allowed_tools` in the `agent_input` snapshot on every trial
- **Per-agent tool constraints:** `program.constraints` supports `tool_set_a` / `tool_set_b` for pre-configured tool experiments

### Expansions

**SkillConfig type** (`types.py`)
```python
@dataclass
class SkillConfig:
    name: str
    version: str
    description: str
    system_prompt: str
    required_tools: list[str] = field(default_factory=list)
```
`AgentConfig.system_prompt` becomes `str | SkillConfig | None`. A `_resolve_system_prompt()` helper in `_utils.py` resolves to `str | None` before the SDK call.

**MCP server A/B** (pending SDK verification)
`AgentConfig` gains an optional `mcp_servers: list[dict] | None` field, passed through `extra_options` to `ClaudeAgentOptions`. Planner gains MCP-aware experiment generation.
**Gate:** Verify `mcp_servers` is accepted by `ClaudeAgentOptions` before implementing.

**Tool portfolio tournament**
`TournamentRunner` runs N*(N-1)/2 A/B pairs for N tool configs and produces a `TournamentResult` with a ranked leaderboard and Pareto frontier (quality vs cost). Cost preview confirmation required before execution.

**Skill lineage**
When a trial uses a `SkillConfig`, `storage.py` appends to `results/_lineage/<skill_name>.jsonl`. A new `openbench lineage <skill>` CLI command renders the evolution tree.

## Critical Implementation Notes

1. **SkillConfig resolution** — `_run_agent_async` must call `_resolve_system_prompt()` before building `options_kwargs`. Missing this causes `AttributeError` deep in the SDK.
2. **Lineage concurrent writes** — Use `anyio.Lock()` or post-run write to prevent corruption during tournament runs.
3. **Tournament N guard** — Raise `ValueError` if fewer than 2 configs provided.
4. **Tool sequence truncation** — Truncate `tool_call_names` to last 50 before injecting into judge prompt to avoid token limit issues.
5. **Lineage path sanitization** — Sanitize `skill_name` before using as a filesystem path: `re.sub(r'[^a-zA-Z0-9_-]', '_', skill_name)`.

## Architecture

```
ResearchProgram / TournamentConfig
        │
        ▼
ExperimentPlanner (tool-aware)
        │  generates Experiment with per-agent allowed_tools
        │  generates tasks that exercise the tool diff
        ▼
ExperimentRunner / TournamentRunner
        │  runs trials in isolated workdirs
        │  collects tool_call_names, full_trace
        ▼
AutoEvaluator (tool-aware)
        │  judge sees output + tool_call_names sequence
        │  scores: task_completion, accuracy, conciseness, tool_efficiency
        ▼
ResultStore
        │  writes JSONL trials
        │  writes lineage.jsonl if SkillConfig used
        ▼
ExperimentEvaluation / TournamentResult
```

## Files Changed

| File | Change |
|------|--------|
| `src/openbench/types.py` | Add `SkillConfig`; update `AgentConfig.system_prompt` union type; add `TournamentConfig`, `TournamentResult` |
| `src/openbench/_utils.py` | Add `_resolve_system_prompt()` helper |
| `src/openbench/runner.py` | Add `allowed_tools` to `agent_input` snapshot; call `_resolve_system_prompt()` |
| `src/openbench/planner.py` | Add `_tool_diff_hint()` helper; update both prompt methods; passthrough `mcp_servers` |
| `src/openbench/evaluator.py` | Add `tool_efficiency` dimension; inject tool sequence into judge prompt |
| `src/openbench/storage.py` | Add lineage.jsonl write with lock |
| `src/openbench/cli.py` | Add `openbench lineage <skill>` subcommand |
| `src/openbench/tournament.py` (NEW) | `TournamentRunner` |

## NOT In Scope

- External skill marketplace / sharing
- Abstract base class for Runner (not yet justified — only 2 concrete runners)
- Skill synthesis (planner generates SkillConfig variants from lineage) — see TODOS.md P2
- Cross-program lineage aggregation

## Phase 2 (see TODOS.md)

- **Skill synthesis:** Planner reads lineage and proposes new SkillConfig variants autonomously
