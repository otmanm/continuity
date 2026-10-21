---
name: context-closeout
description: Close a Claude Code or Codex task (Hermes through the Codex copies) without using the session as memory. Reviews the human's own decision files and says, per file, what must change before the session ends. Use when the human asks to close, compact, clear, archive, or hand off work, or asks what survives, what is complete, or what must change in their files.
---

# Context Closeout

Close work against the human's own files. Never turn an inference into human intent, and never archive a task on your own.

## Activation boundary

Maintenance is not invocation. A request to inspect, audit, debug, test, or edit this skill keeps the current task active and does not run the closeout workflow, produce a closeout verdict, or invoke `handoff`. Run the workflow only when the human asks to close, compact, clear, archive, or hand off work, or asks what must survive that transition.

## Where the human's files live

The human keeps their intent and decisions in plain Markdown files in one folder (the "intent folder"). Find it in this order:

1. the environment variable `CONTINUITY_INTENT_DIR`;
2. a folder named `intent/` at the project root;
3. otherwise ask the human once for the path, and say that no intent folder was found. Never invent one.

If the folder has an `INDEX.md`, read it first and follow its order of precedence. Read only the files named below and the exact sources already in scope. Do not search unrelated folders.

## Workflow

1. Identify the project and its state and decision files.
2. Review every category below, even when the answer is `NO_CHANGE`. A file the human does not keep is reported `NOT_PRESENT`, never created without approval.

| Category | Review target (inside the intent folder) |
| --- | --- |
| Mission | `MISSION.md` |
| Goals | `GOALS.md` |
| Human intent | `INTENT.md` |
| Overall state | `STATE.md` |
| Project registry | `PROJECTS.md` |
| Cross project decisions | `DECISIONS.md` |
| Project state | the project's own `STATE.md` |
| Project decisions | the project's own `DECISIONS.md` |
| Continuity | existing files versus a short handoff |

3. Classify surviving work:
   - one concrete next physical action owned by the human;
   - `WAITING_EXTERNAL` with a named trigger and no invented obligation;
   - complete, with evidence and no surviving action;
   - genuinely unclear and requiring the human's decision.
4. Label each category `PATCH`, `NO_CHANGE` or `NOT_PRESENT`.
5. Show every `PATCH` as an exact diff. Apply it only if the human approved this closeout's scope at the start of the session (destination files and what may change), or approves the shown diff now. A new human decision written into `INTENT.md`, `GOALS.md`, `MISSION.md` or a `DECISIONS.md` always needs the human's explicit approval of that exact text.
6. Validate the applied patches and report each one as a diff plus a link to the file.
7. Produce the verdict and stop. The human performs any archive action.

## Writeback rules

- `STATE.md` holds current state only; remove completed work from the overall view.
- `PROJECTS.md` keeps a compact row after a project completes.
- A project's `STATE.md` carries dated transitions and completion evidence.
- `DECISIONS.md` is append only; a cross project decision must truly affect more than one project.
- Do not create a conversation record by default.
- Use the existing files when they can restore the work.
- Invoke `handoff` only when concrete unfinished work survives and the files alone cannot restore it.
- Session record step (v0.1.5): at the end of every long session, write the record as a new Markdown file beside the task's work, `SESSION-INTENT-DECISIONS-<YYYY-MM-DD-HHMM>.md`. It holds the `checkpoint` sections 1 to 4b: intent evolution from `list_inputs.py`, decisions, pending decisions as A/B/C cards, probable future decisions, meta decisions and the branch map. Have an independent model or a fresh session check it against the conversation record before delivery and apply its corrections. Show the same content in the chat, in full. If the human mirrors records into a notes tool or an issue tracker, write there only after showing the exact destination and text and getting a yes; nothing else from the closeout goes to an external tool.
- Never install software, authenticate, upload, change permissions, send messages, or archive tasks through implied approval.

## Versioning and traceability

- Before patching any file in the intent folder, save a dated copy in a `_versions/` folder beside it, named `<name>.<YYYY-MM-DD-HHMM>.<ext>`. Take the time from `date +%Y-%m-%d-%H%M`; never type a guessed time.
- When the session changed instruction files (`CLAUDE.md`, `AGENTS.md`), settings, skills or hooks, or deleted anything, write a traceability report: one row per changed file (before path, after path, lines added and removed, SHA-256 before and after, who applied it and when) plus the full unified diff computed from the dated copy, never from memory. Link it in the closeout output.
- Commit changes with explicit paths only, never `git add -A`, and only after a secret scan.

## Required output

```text
VERDICT: ARCHIVE_NOW | ARCHIVE_AFTER_APPROVED_WRITE | KEEP_ACTIVE | NEEDS_HUMAN_DECISION

INTENT FOLDER: <path> (found by CONTINUITY_INTENT_DIR | intent/ | asked)

REVIEW MATRIX:
- MISSION: PATCH | NO_CHANGE | NOT_PRESENT
- GOALS: PATCH | NO_CHANGE | NOT_PRESENT
- INTENT: PATCH | NO_CHANGE | NOT_PRESENT
- STATE: PATCH | NO_CHANGE | NOT_PRESENT
- PROJECTS: PATCH | NO_CHANGE | NOT_PRESENT
- DECISIONS: PATCH | NO_CHANGE | NOT_PRESENT
- PROJECT_STATE: PATCH | NO_CHANGE | NOT_PRESENT
- PROJECT_DECISIONS: PATCH | NO_CHANGE | NOT_PRESENT
- CONTINUITY: EXISTING_FILES_ARE_ENOUGH | SHORT_HANDOFF_REQUIRED | NO_CONTEXT_WORTH_PRESERVING

EXACT PATCHES:
- <file and diff, applied or awaiting approval, or NONE>

TRACEABILITY:
- <report link, or NOT_APPLICABLE>

LOCAL / COMMIT:
- <saved paths; committed or uncommitted>

SURVIVING ACTION:
- <one action, WAITING_EXTERNAL with trigger, or NONE>

MANUAL ACTION: ARCHIVE | KEEP_OPEN | DECIDE
```

Do not claim a closeout is complete until every applied patch is validated. Do not claim a task is archived unless its state is visibly verified.

## Plugin additions

- Step 0: if the human attached a file, write `YOUR INPUT IN THIS FILE` with their quoted input before the review matrix.
- Step 0b: run the `checkpoint` skill first when its decision tables (1 to 4b) do not yet exist for this task; decision tables come before any handover or closeout.
- Every quote cited in a patch or verdict carries a line reference produced by `scripts/locate_quote.py`.

## Shared plugin rules

- YOUR INPUT IN THIS FILE: when the human attaches a file, first extract and quote their own input from it (their words, decisions and corrections) under the heading `YOUR INPUT IN THIS FILE`, before any analysis.
- Line references: every line number cited for a quote comes from `python3 <PLUGIN_ROOT>/scripts/locate_quote.py <record> "<quote>"`. Never type a line number by hand (in testing, 8 of 44 hand typed line numbers were wrong). If the script exits non zero, the quote is not in the record: fix the quote or drop it.
- Never overwrite: write a new versioned file `<name>.<YYYY-MM-DD-HHMM>.<ext>` (time from `date +%Y-%m-%d-%H%M`). Never delete, move or rename an existing file.
- Every assumption names its source: `ASSUMPTION, derived from <file, sentence, search result, or "nothing, I filled a hole">`.
