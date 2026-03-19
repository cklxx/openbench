# OpenBench TODOS

## P2 — Skill Synthesis (Phase 2, after tool/skill A/B ships)

**What:** Teach the planner to autonomously generate new SkillConfig variants based on lineage winners.
**Why:** Closes the loop from experiment results back into skill design — the planner reads lineage, identifies what worked (e.g., "v2 won because it added step-by-step reasoning"), and proposes v3 with targeted modifications (e.g., add conciseness constraints to the winning pattern).
**Pros:** Fully autonomous skill improvement without human hypothesis injection.
**Cons:** Planner needs access to lineage data — adds a new input to `plan_next()`.
**Context:** Depends on SkillConfig type and lineage.jsonl both being shipped. Planner's `_next_prompt` would gain a `SKILL_LINEAGE` section summarizing prior skill versions and their scores. `_to_step` would emit a `SkillConfig` (not just a system_prompt string) when operating in skill-synthesis mode.
**Effort:** M (human: ~2d / CC: ~25min) | **Priority:** P2
**Depends on:** SkillConfig (#4), skill lineage tracking (#6) from tool/skill A/B plan
