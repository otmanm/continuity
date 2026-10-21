---
name: conversation-record
description: Save the current chat as one faithful Markdown conversation record built by a deterministic script from the raw session file. Use only when the user explicitly invokes `$conversation-record` or says "record this conversation", or when the checkpoint skill needs a record for line references.
---

# Conversation Record

Create one faithful historical record of the current chat. It is evidence of what was said, not approved intent, current state, or a decision log.

## Workflow

1. Confirm the request: the human explicitly asked for a record, or the `checkpoint` skill needs one. Never infer it from closeout, handoff or context pressure.
2. Find the raw session file or files: Claude `~/.claude/projects/<project slug>/<session id>.jsonl`, Codex `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` or, for older and archived threads, `rollout-*.jsonl.zst` and `~/.codex/archived_sessions/` (v0.1.4: Codex compresses older rollouts in place; in one real installation most of them were compressed). One conversation can span several files (resume or continue): group the files that share message `uuid` values, the same rule `scripts/session_metrics.py` uses for conversation groups, and record each file of the group in order.
3. Make the scratch copies. Codex (v0.1.4): run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/zst_to_scratch.py --out <scratch>/raw --thread <thread id>` (or pass the rollout files instead of `--thread`); it decompresses `.jsonl.zst`, copies plain `.jsonl`, writes `manifest.json` with SHA-256 values, never touches the source, and prints a final `ARGS:` line: use those paths, in that order, for every script below. Claude: copy each raw file to scratch. Then run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/make_record.py <scratch copy> [<scratch copy 2> ...] <record.md>`. Pass every file of one resumed conversation in the same call (v0.1.2): the script orders them, tags them F1, F2, and turns lines already present in an earlier file into DUPLICATE pointers. Compaction summaries and meta lines are headed `COMPACT_SUMMARY (AI)` and `META (AI)`, never USER. The script is the record: verbatim, one block per raw line headed `## L<n>` (`## F<k> L<n>` for several files), blobs and secrets replaced by labelled placeholders, same input gives same bytes.
4. Human messages: the counts come from `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/session_metrics.py --run-at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --out <scratch>/metrics.csv <scratch copy>`, columns `user_messages` (typed by the human), `user_messages_mid_turn` (queued while a turn ran) and `assistant_messages`. Never count by hand: the marker `[Request interrupted by user]` is written by the harness and is not their message, and the script already excludes it, as it excludes subagent reports (`origin.kind` `peer`). State the counts in the reply and cite the CSV path.
5. Destination: use the path the human gave. If none, write beside the task's work as `YYYY-MM-DD_<short-topic>_conversation-record.<YYYY-MM-DD-HHMM>.md`. Never overwrite an existing record.
6. Any summary written on top of the record quotes text and gets its line numbers only from `scripts/locate_quote.py`.
7. Return the exact file path, the script version, the metrics CSV path and the SHA-256 of the record, and state that the record has no canonical authority.

## Prohibited behavior

Do not create a handover, generate a prompt for another AI, promote any statement into canonical intent, state, goals, mission, project registry or decisions, update memory or global instructions, perform work discussed in the conversation, or hand edit the script output.

## Shared plugin rules (continuity v0.1.0)

- YOUR INPUT IN THIS FILE: when the human attaches a file, first extract and quote their own input from it (their words, decisions and corrections) under the heading `YOUR INPUT IN THIS FILE`, before any analysis.
- Line references: every line number cited for a quote comes from `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/locate_quote.py <record> "<quote>"`. Never type a line number by hand (in testing, 8 of 44 hand typed line numbers were wrong). If the script exits non zero, the quote is not in the record: fix the quote or drop it.
- Never overwrite: write a new versioned file `<name>.<YYYY-MM-DD-HHMM>.<ext>` (time from `date +%Y-%m-%d-%H%M`). Never delete, move or rename an existing file.
- Every assumption names its source: `ASSUMPTION, derived from <file, sentence, search result, or "nothing, I filled a hole">`.
