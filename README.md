# continuity

**Keep the human's own words and decisions intact across AI coding sessions, compactions and tools.**

A plugin for Claude Code, with a mirror folder for OpenAI Codex, made of four skills and seven plain Python scripts. The scripts read the raw session files the tools already write, and separate what **you typed** from what **the AI or the tool wrote in your name**: compaction summaries, injected instruction files, hook messages, notifications.

## Why I built this (the author's words)

The author described the need in his own words on 21 October 2026, in a dictated note:

> "one of the strong, like, why is that I'm using multiple harnesses to have a second opinion, to not stay, to reduce the AI sycophancy of one, just for bias of one single model."

> "sometimes I stay in that session a long time. And the context has to go from one side to another side. So sometimes I'm limited in the tokens"

> "this limitation actually makes me that I have a need absolutely to create some checkpoints, or to create some things, like, so actually when I'm running out of tokens, I can still resume the work"

> "if I change the computer, or if I want to use, because I have at least three computers: I have one on Linux, I have one on Windows, which is a Lenovo computer that is portable, and I have my Mac Mini, which is here. So actually the context has to keep going"

> "it's linked with Linear, you have to mention Linear, and linked with Notion, so I can resume now with a prompt with the right path of the files that are in my Knowledge Vaulting locally, or with a backup in the cloud."

> "you have to mention the 3-2-1 backup, especially with what happens when AI drifts or delete files, or when we have contaminated files, or we have actually also IT security breaches or risks."

This plugin covers one part of that list: the record and the checkpoint. It keeps who said what, which decisions were taken, and what the AI may do next. The issue tracker (Linear), the notes tool (Notion), the sync across computers and the backup routine named in the last quote are the author's own setup around the plugin. They are not part of the plugin.

## State of this release

This is an early public version: v0.2.1, a pre release. On 21 October 2026 the author said:

> "it's not ready yet. There are, like, some things I like to add, and the telemetry is not yet really clear for me."

> "we can make a public version and then we can update it later."

A fifth skill for verification, drift detection and replay is planned. It is not built yet: this release contains only the four skills listed below.

Some parts of the plugin are exact code. Other parts are instructions that the AI has to follow. The table shows which is which.

| Deterministic (scripts) | Instruction only (the AI must follow the skill text) |
|---|---|
| `list_inputs.py`: lists every human input and gives each row one class from the label list | The decision tables of `checkpoint` (intent evolution, decisions, pending decisions, probable future decisions) |
| `make_record.py`: turns raw session files into one Markdown record, one block per raw line | The meta decisions table |
| `session_metrics.py`: counts messages, turns, tool calls and tokens into a CSV | The branch map (mermaid flowchart plus table) |
| `locate_quote.py`: prints the record line numbers where a quote appears | The closeout review of your decision files |
| `check_quotes.py`: removes checkpoint rows whose quotes are not in the record | The handoff |
| `validate_inputs.py`: checks the input list against its JSON schema | |
| `zst_to_scratch.py`: makes plain copies of compressed Codex session files | |

The session metrics (what the author calls telemetry) are counts taken from the raw session file. They have not been validated against the harness's own numbers. Treat them as indicative.

Testing so far: the author ran the plugin on his own Claude Code and Codex sessions, on macOS, with Python 3.14. The Codex skill copies were loaded in Codex and in Hermes, and the scripts were run from them. Nothing has been tested on Linux or Windows. There is no automated test suite beyond `examples/check_example.py`.

## Why

If you work with AI coding agents every day, you have probably seen at least one of these:

| Problem | What happens |
|---|---|
| Sessions disappear | Session files are deleted after a retention period, or vanish, and nothing saved a copy. |
| The AI's words are stored as yours | A long session gets compacted, and the AI's own summary is stored as a "user" message. Codex stores its injected instruction files and skill texts as "user" messages too. A later session can then quote AI text as your decision. |
| Prohibitions get lost | After compaction or a resume, the agent forgets what you forbade, or which approval was already used, and acts on it. |
| Handoffs paraphrase you | The note for the next session is written by the AI, so it drops items or invents decisions. |

Saving files does not fix this. What has to survive is **who said what**. That job is exact, so it is done by scripts, not by the model: same input, same output, every time. Judgement (what matters, what to do next) stays with the AI, and decisions stay with you.

## The four skills

| Skill | What it does |
|---|---|
| `checkpoint` | At a task boundary, lists every human input with a script, measures the session with a script, then writes four tables: how your intent evolved, decisions taken, pending decisions (each one an A/B/C card with a draft answer), probable future decisions. Adds a meta decisions table (how you chose to decide, for example "read only first") and the next decisions as branches: a mermaid flowchart plus a table, each branch with its source and a confidence level. Every quote is checked against the record by a script; a quote that cannot be found is removed, never retyped. Ends with a "do not" list and the one action the AI may take next (or `WAIT`). |
| `conversation-record` | Turns the raw session file into a readable Markdown record, one block per line, labelled `USER`, `ASSISTANT`, `COMPACT_SUMMARY (AI)`, `META (AI)` or, for Codex, `INJECTED (HARNESS)`. Same input gives the same bytes. |
| `context-closeout` | Before a session ends, reviews your own decision files (mission, goals, intent, state, decisions) and says, per file, whether it needs a change. Shows exact diffs; never writes a new decision of yours without your approval of the exact text. A long session ends with a session record file, `SESSION-INTENT-DECISIONS-<timestamp>.md`, holding the checkpoint tables, and the same content is shown in full in the chat. |
| `handoff` | Only when your files cannot restore unfinished work: one short map and a ready prompt for the next AI. |

## The scripts

All seven live in `scripts/`. They use the Python standard library only.

| Script | Version | Job |
|---|---|---|
| `list_inputs.py` | 1.0.0 | Lists every human input in order, one class per row from the label list below, as Markdown and JSONL. |
| `make_record.py` | 1.2.0 | Turns one or several raw session files into one Markdown record, one block per raw line. |
| `session_metrics.py` | 1.1.0 | Writes one CSV row per session file: messages, slash commands, turns, tool calls, tokens. |
| `locate_quote.py` | 1.0.0 | Prints every record line where a quote appears, so no line number is typed by hand. |
| `check_quotes.py` | 1.1.0 | Removes every checkpoint table row whose quote is not found in the record at the cited line. |
| `validate_inputs.py` | no `VERSION` constant | Checks each row of the `list_inputs.py` JSONL against `schemas/inputs.schema.json`. |
| `zst_to_scratch.py` | 1.0.0 | Makes plain copies of Codex session files compressed as `.jsonl.zst` in a scratch folder, never touching the sources. |

## The label list

Every human input row gets one class from a fixed list:

| Class | Meaning | Counts as the human? |
|---|---|---|
| `human_typed` | You typed it | yes |
| `human_typed_mid_turn` | You typed it while the AI was working | yes |
| `human_card_answer` | You answered a decision card | yes |
| `human_card_dismissed` | You dismissed a card (never read as a refusal) | yes, as a dismissal |
| `slash_command` | A command such as `/model` | listed, not a message |
| `interrupt_marker` | The harness marker for an interrupt | listed, not a sentence |
| `harness_injected` | Text the tool wrote: notifications, instruction files, skills, hooks | **no** |
| `ai_compact_summary` | The AI's compaction summary | **no** |
| `ai_meta` | Hook feedback, subagent reports, meta lines | **no** |

## Try it in one minute (no AI needed)

`examples/demo-session.jsonl` is an invented Claude Code session in which every line is a known trap. Its worst trap is an AI compaction summary that says the user "approved pushing the fix to main", while the user actually wrote "Do not push to main."

```bash
python3 examples/check_example.py
```

Expected output: `ALL 12 CHECKS PASS`. The check confirms that the summary is classed as AI text, that both prohibitions of the opening message are found, and that exactly 5 human inputs are counted. Use the same file to test any other tool: does it tell your words apart from the AI's?

To see the full list for any of your own sessions:

```bash
python3 scripts/list_inputs.py ~/.claude/projects/<project>/<session>.jsonl --md inputs.md --jsonl inputs.jsonl --prohibitions
```

## Install

### Claude Code

```bash
claude plugin marketplace add otmanm/continuity
```

```bash
claude plugin install continuity@agent-continuity
```

Then type `/continuity:` in a session to see the four skills.

For `context-closeout`, keep your decision files (`MISSION.md`, `GOALS.md`, `INTENT.md`, `STATE.md`, `DECISIONS.md`, any you use) in one folder, and point to it with the environment variable `CONTINUITY_INTENT_DIR`, or name the folder `intent/` at your project root. Files you do not keep are reported `NOT_PRESENT`.

### Codex (experimental)

`codex/skills/` holds the same four skills with the plugin path written as `<PLUGIN_ROOT>`. Copy them into your Codex skills folder and replace `<PLUGIN_ROOT>` with the path of this repository. The author loaded these copies in Codex and in Hermes, and ran the scripts from them. The scripts read Codex rollout files and label Codex's injected text as `harness_injected`. Codex compresses older session files as `.jsonl.zst`; to read those, `zst_to_scratch.py` needs the `zstd` command installed.

## Requirements

Python 3, standard library only (tested on Python 3.14). No network, no model calls, no extra packages. The `zstd` command is needed only for compressed Codex session files.

## Known limits

- **Format dependence.** The scripts decide who wrote a line from the fields the tools leave in their files. When a tool changes its file format, a line can be misclassified. Safety counters (events without a matching line, queued text without a row, unknown tags) exist to make that visible, not to prevent it.
- **The record header lags the list.** In `conversation-record`, some harness text (tool results, slash command lines, notifications) is still headed `USER`; the input list (`list_inputs.py`) classifies those lines correctly. Cite the list, not the header.
- **No automatic saving yet.** Nothing in this plugin copies session files when a session ends. Raise your retention setting and keep your own copy outside the tool's folder.
- **Tested on one person's sessions.** The rules were checked against one person's history of about 1,100 Codex rollouts and 4,300 Claude files. Other setups may meet lines the rules have not seen.
- **Voice dictation.** One known mistranscription (`clothes` for Claude) is flagged; others are not.
- **Telemetry not validated.** The session metrics are counts from the raw file. They have not been checked against the harness's own numbers. Treat them as indicative.
- **Linux and Windows untested.** All testing so far ran on macOS.

## How to extend

- A new harness line you meet: add its prefix to `CODEX_INJECTED` in `scripts/make_record.py` (Codex) or to the Claude prefix list in `scripts/list_inputs.py`, then add a line for it to the example and rerun `examples/check_example.py`.
- A new mistranscribed word: add it to `VOICE_MISHEARD` in `scripts/list_inputs.py`, with the evidence.
- `AGENTLOG-MAP.md` maps each class to the nearest event of the AgentLog 0.2.0 draft, for reading only.

## Changelog

Every version is listed in [CHANGELOG.md](CHANGELOG.md).

## Licence

Apache 2.0. See [LICENSE](LICENSE).
