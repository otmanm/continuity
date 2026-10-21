---
name: handoff
description: Create one short continuation map beside the project only when the human's own state and decision files cannot restore concrete unfinished work. Use when the human explicitly requests a handoff, or a context closeout concludes that a handoff is genuinely required.
---

# Handoff

A handoff is a continuity map, never the source of project state, decisions, human intent, or task memory.

## Activation boundary

Maintenance is not invocation. A request to inspect, audit, debug, test, or edit this skill keeps the current task active and does not run `context-closeout` or create a handoff. Invoke this workflow only when the human explicitly requests a handoff, or an actual context closeout concludes that a short handoff is required.

## Mandatory sequence

1. Run `context-closeout` first.
2. Complete its review of the human's files (mission, goals, intent, state, decisions, project registry).
3. Show the exact proposed patches to those files and obtain the human's exact approval.
4. Apply and validate only approved patches.
5. Test whether those files can restore the unfinished work.
6. Create a handoff only if all three conditions hold:
   - concrete unfinished work survives;
   - the existing files are insufficient;
   - one short map would let a fresh AI continue correctly.

If any condition fails, report `EXISTING_FILES_ARE_ENOUGH` and create no handoff.

## Destination

Propose exactly one Markdown file beside the project's files. Show the exact path and wait for approval before writing.

Do not create automatic copies anywhere else (downloads folder, note apps, a global handoff archive, memory, another harness). Do not create a conversation record unless the human separately invokes `conversation-record`.

## Required handoff contents

```md
# Handoff: <title>

Created: <ISO timestamp with timezone>
Decision owner: <the human's name>

## READ FIRST, IN ORDER

1. `<absolute path>`: <why>

## Resume goal

<one bounded outcome>

## Current state

<verified state; point to the human's files rather than duplicating them>

## Unresolved decisions

<human decisions still required, or NONE>

## One next action

<one physical action, owner, and stop condition>

## Prompt for the next AI

<full copy and paste prompt containing scope, files in order, decision boundary, next action, and acceptance condition>
```

Keep the file short. Do not paste conversation histories or duplicate the bodies of state and decision files.

## Chat delivery contract

The final response must include:

1. `Prompt for the next AI` with the full copy and paste prompt.
2. `Files to read in order` with absolute paths and one reason per path.
3. The exact handoff path and every other file updated for continuity.
4. The closeout verdict and the one surviving next action.

When the next AI is a different tool or an outside party, list only the project's own files and extract the minimum rule it needs, instead of exposing private notes or memory indexes.

## Guardrails

- The human approves the handoff path and content before it is written.
- The human remains the decision owner; unresolved judgements stay unresolved.
- Never archive a task, upload a handoff, authenticate, or change permissions.
- If the files later become sufficient, retire the need for the handoff; do not keep a session open as memory.

## Plugin additions

- The handoff links the latest `CHECKPOINT.<YYYY-MM-DD-HHMM>.checked.md` and does not restate its tables.
- When a session record exists (`SESSION-INTENT-DECISIONS-<YYYY-MM-DD-HHMM>.md`, written by `context-closeout`, v0.1.5), the handoff links it and does not restate intent, decisions, meta decisions or branches.
- The handoff is written as a new versioned file; an earlier handoff is never overwritten.

## Shared plugin rules

- YOUR INPUT IN THIS FILE: when the human attaches a file, first extract and quote their own input from it (their words, decisions and corrections) under the heading `YOUR INPUT IN THIS FILE`, before any analysis.
- Line references: every line number cited for a quote comes from `python3 <PLUGIN_ROOT>/scripts/locate_quote.py <record> "<quote>"`. Never type a line number by hand (in testing, 8 of 44 hand typed line numbers were wrong). If the script exits non zero, the quote is not in the record: fix the quote or drop it.
- Never overwrite: write a new versioned file `<name>.<YYYY-MM-DD-HHMM>.<ext>` (time from `date +%Y-%m-%d-%H%M`). Never delete, move or rename an existing file.
- Every assumption names its source: `ASSUMPTION, derived from <file, sentence, search result, or "nothing, I filled a hole">`.
