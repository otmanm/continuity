# Explainer: continuity v0.2.0, the first public version

This page is for someone with no context. If you have never used an AI coding tool, start at the top and read in order.

## What it is

When you work with an AI coding tool such as Claude Code or Codex, every conversation is saved on your computer as a raw file. Each line of that file says who wrote it: you, the AI, or the tool itself. The trouble is that the tool sometimes stores its own text, or the AI's text, under your name. A later session can then read that text and believe you said it.

continuity is a plugin that fixes this. It has two halves:

1. **Seven small Python scripts.** They read the raw file and sort every line into a fixed list of classes: typed by you, a card you answered, a slash command, text the tool injected, a summary the AI wrote, and so on. They do this the same way every time.
2. **Four skills.** A skill is a page of instructions the AI reads before a task. The four skills tell the AI how to write a checkpoint, a conversation record, a closeout review of your decision files, and a handoff for the next session.

**Analogy.** Think of a court reporter and a lawyer. The court reporter types exactly who said what, word for word, and never interprets. The lawyer reads that transcript and argues about what it means. In continuity, the scripts are the court reporter and the AI is the lawyer. The judge, who decides, is you.

## Why this path

### Why scripts for the exact part and the AI for the judgement part

Deciding who wrote a line is a question with one right answer. A script gives the same answer every time. An AI can give a slightly different answer each time, and it can mistake its own summary for your words. Deciding what matters in a long session, or what to do next, has no single right answer. That is where the AI is useful.

| Option | Good at | Weak at |
|---|---|---|
| Scripts do everything | Same output every time, cheap, checkable | Cannot judge what matters or propose next steps |
| AI does everything | Reads meaning, writes summaries | Can misquote, can mix up who said what, output changes between runs |
| Scripts for facts, AI for judgement (chosen) | Facts are fixed; judgement is still available | Two parts to maintain; the AI can still ignore the skill text |

**Decision rule:** if a question has one right answer that can be read from the file, a script answers it; if it needs judgement, the AI answers it and the human decides.

### Why a public version now, while it is early

The author said, on 21 October 2026: "we can make a public version and then we can update it later." He also said: "it's not ready yet. There are, like, some things I like to add, and the telemetry is not yet really clear for me." So this version is marked pre release, and the README says plainly what is not done.

| Option | Benefit | Cost |
|---|---|---|
| Publish now as a pre release (chosen) | Others can try it and report problems; the work is visible | Some parts are unfinished and the metrics are not validated |
| Wait until everything is finished | Fewer rough edges on first contact | Nobody else tests it; feedback comes later |

**Decision rule:** publish when the core works and every known gap is written down; keep the pre release label until the gaps are closed.

### Why Apache 2.0

The files read for this explainer do not record the author's reason for the licence. The table shows what each common choice gives, so a reader can see what Apache 2.0 means for them.

| Licence | What it allows | What it asks |
|---|---|---|
| Apache 2.0 (chosen) | Use, change and share, including in paid products | Keep the licence and notices, mark files you changed; includes an explicit patent grant from contributors |
| MIT | Use, change and share, including in paid products | Keep the licence text; shorter, no explicit patent grant |
| No licence | Nothing by default; others cannot legally reuse the code | Nothing, because nobody may use it |

**Decision rule:** if you reuse this code, keep the `LICENSE` file and say what you changed.

### Why one repository with a Codex mirror folder instead of two repositories

The scripts are the same for Claude Code and for Codex. Only the skill texts differ, because each tool finds the plugin folder in a different way. Claude Code fills in `${CLAUDE_PLUGIN_ROOT}`; the Codex copies in `codex/skills/` use `<PLUGIN_ROOT>`, which you replace by hand.

| Option | Benefit | Cost |
|---|---|---|
| One repository, `codex/skills/` mirror folder (chosen) | One copy of the scripts; one place to fix a bug; one changelog | The two skill copies can drift apart if one is edited and the other is not |
| Two repositories, one per tool | Each tool gets a clean, separate install | Scripts copied twice; a fix in one can be forgotten in the other |

**Decision rule:** keep one repository while the scripts are shared; after any skill edit, apply the same edit to its mirror copy in the same change.

## Limits

- **File formats change.** The scripts read the fields the tools leave in their files. When a tool changes its format, a line can be put in the wrong class.
- **The record header lags the list.** Some tool text is still headed `USER` in the conversation record. The input list from `list_inputs.py` is correct; cite the list.
- **No automatic saving.** Nothing copies session files when a session ends.
- **One person's sessions.** The rules were checked on one person's history of sessions. Other setups may have lines the rules have not seen.
- **Voice dictation.** Only one misheard word is flagged (`clothes` for Claude).
- **Instruction only parts.** The decision tables, the meta decisions table, the branch map, the closeout review and the handoff are text the AI is asked to follow. A script checks the quotes in the checkpoint, but nothing forces the AI to follow every other instruction.
- **Telemetry.** The session metrics are counts from the raw file and have not been compared with the tool's own numbers.

## How to extend

**A new harness prefix.** When you meet a line that the tool wrote but the scripts class as yours, find a fixed start of that text. For Codex, add it to `CODEX_INJECTED` in `scripts/make_record.py`. For Claude Code, add it to the Claude prefix list in `scripts/list_inputs.py`. Then add a line like it to `examples/demo-session.jsonl`, add the expected class in `examples/check_example.py`, and run `python3 examples/check_example.py` until it prints `ALL ... CHECKS PASS`.

**A new misheard word.** If voice dictation turns a word into another one, add the pair to `VOICE_MISHEARD` in `scripts/list_inputs.py`, for example `"clothes": "Claude"`. Write down where you saw it, so the next person knows it is real.

**A fifth skill.** Create `skills/<name>/SKILL.md` with a short front matter block (`name` and `description`) and the workflow. If it needs facts from the session file, call an existing script instead of asking the AI to count or quote by hand. Then write the Codex copy in `codex/skills/<name>/SKILL.md`, with `<PLUGIN_ROOT>` in place of `${CLAUDE_PLUGIN_ROOT}`, add a row to the README skills table, and add a line to `CHANGELOG.md`.

**A new harness mirror.** For a third tool, add a folder such as `<tool>/skills/` holding copies of the four skills, with the plugin path written the way that tool expects. Check whether the scripts can read that tool's session files. If they cannot, the script that reads raw files needs a new reader and rules, and the example needs a session from that tool.

## GAPS

What is not done in v0.2.0:

1. **Telemetry not validated.** The counts in `session_metrics.py` have not been compared with the harness's own numbers.
2. **No automated tests beyond the example.** `examples/check_example.py` runs 12 checks on one invented session. There is no wider test suite.
3. **Linux and Windows untested.** All runs so far were on macOS with Python 3.14.
4. **Three `conversation-record` sentences from an older version not re added.** They were dropped in an earlier rewrite and have not been put back.
5. **No SessionStart or PreCompact hook.** Nothing runs the scripts on its own at the start of a session or before a compaction. The human or the AI has to call the skills.
6. **The 0.1.6 compaction proof evidence proposal is not included.** It stays a proposal and is not part of this release.
