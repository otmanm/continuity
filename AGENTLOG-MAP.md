# Input classes mapped to AgentLog 0.2.0 event types

**Mapping only. Nothing here adopts AgentLog.** The plugin keeps its own nine classes (`schemas/inputs.schema.json`) because AgentLog cannot express them (see "What AgentLog cannot say").

Source: AgentLog spec version 0.2.0, status Draft, `spec/agentlog-spec.md` in github.com/braintied/agentlog, read in full from the repository on 2026-10-06 (sections 3.1 to 3.13 and 6.1 to 6.3). Label: FACT for what the spec says, INFERENCE for every "fit" judgement below. A research note written the same day found 0 stars on that repository, so no tool reads this format yet.

## The table

| Plugin class | Nearest AgentLog event | How the fields would be filled | Fit | What the mapping loses or invents |
|---|---|---|---|---|
| `human_typed` | `message` | `role: user`, `content` = the text | Exact | Nothing in the text. "A human wrote this" is only implied by `role: user`, which AgentLog also uses for every other class below. |
| `human_typed_mid_turn` | `message` | `role: user`, `content` = the text, flag in `properties` | Exact for the text | The "typed while a turn was running" fact has no field; it would live in `properties["continuity:mid_turn"]`. |
| `human_card_answer` | `message` | `role: user`, `content` = the chosen answer | Partial | `approval` (section 3.10) is a permission decision with `approver` and `decision` (approved, denied, modified). A card answer is a choice among options, not a permission, so `approval` would invent a decision type the data does not contain. The question text has no field. |
| `human_card_dismissed` | `message` | `role: user`, `content` = the dismissal marker | Partial | `approval` with `decision: denied` was rejected on purpose: it would state a refusal. The one real dismissal seen while building this was a mistranscription, not a refusal. The mistranscription note has no field. |
| `slash_command` | `message` | `role: user`, `content` = the command text | Partial | `terminalCommand` (section 3.5) is a shell command; a harness command is not one. |
| `interrupt_marker` | none; closest `message` | `role: system`, `content` = the marker | None | `error` (section 3.8) is for failures. An interrupt is a deliberate human act that the harness records. AgentLog has no event for it. |
| `harness_injected` | `contextLoad` for instruction files, attachments and app context; `message` with `role: system` for hook text | `source: file` (or `custom`), `reason` = the rule name | Likely | `contextLoad` (section 3.13) carries `source`, `query`, `itemCount`, `tokenCount` and `reason`, not the text. Codex stores these lines as role user; mapping them to `message` with `role: user` would make a harness line look human, which is the exact fault this plugin exists to prevent. |
| `ai_compact_summary` | `checkpoint` | `checkpointType: custom`, `restorable: false`, `label` = "compaction summary" | Partial | `checkpoint` (section 3.12) has no field for text, only `label` and `reference`, so the summary text would sit in `properties`. `restorable` is required and a summary cannot restore anything. |
| `ai_meta` | `message` with `role: system` for hook feedback and skill text; `handoff` for a subagent report | for `handoff`: `status: completed`, `result` = the report | Partial | A `handoff` (section 3.9) needs `fromAgent` and `toAgent`, which the raw line gives only as an agent id. |

## What AgentLog cannot say

1. **Who wrote a `user` message.** The only authorship field is `role`, and `role: user` is where Claude Code and Codex both store injected, compacted and meta text. Section 3.2 gives three roles, so the fault this plugin fixes cannot be expressed in the base format.
2. **A dismissal that is not a refusal, and an interrupt.** No event type fits either.
3. **Quote versus derived versus inference.** Not in the spec (also found in the research note, section 3).

## How it would be carried if it were ever used

Section 6.2 lets a producer put vendor keys in `properties`. The plugin class would travel as `properties["continuity:class"]` on every event, with `properties["continuity:raw_line"]` pointing at the raw file line. That keeps the AgentLog document valid while the plugin's classes stay readable. Not built, not tested.
