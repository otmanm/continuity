# Changelog

Newest first. Dates are in the format YYYY-MM-DD.

## 0.2.1 (2026-10-25)

README and TESTED.md only, no change to skills or scripts. Removes the install note from the private phase, and states that the planned fifth skill (verification, drift detection, replay) is not built. Fixes a pointer in `session_metrics.py` to a METHOD.md file that is not in this repository. Adds TESTED.md with the first clean install test.

## 0.2.0 (2026-10-21)

First public version, marked pre release. Skill texts reworded in neutral terms for any user. Includes `zst_to_scratch.py`, the meta decisions table, the branch map, A/B/C cards for pending decisions and the session record step in `context-closeout`. The README gains the sections "Why I built this" and "State of this release".

## 0.1.5 (2026-10-20)

`checkpoint` adds a meta decisions table (how the human chose to decide) and the next decisions as branches (mermaid flowchart plus table). `context-closeout` adds the session record step: a `SESSION-INTENT-DECISIONS-<timestamp>.md` file, shown in full in the chat.

## 0.1.4 (2026-10-19)

New script `zst_to_scratch.py`: makes plain scratch copies of Codex rollouts compressed as `.jsonl.zst`, so the other scripts can read them.

## 0.1.3 (2026-10-06)

New script `list_inputs.py`: one deterministic list of every human input. `checkpoint` now builds its tables from that list, lists the prohibitions of the opening message, and follows a coverage rule: every listed input appears in the intent table or is named in GAPS with a reason.

## 0.1.2 (2026-10-06)

`make_record.py` builds one record from several files of a resumed conversation. User lines written by the AI (compaction summaries, meta lines) are labelled as AI text. Slash commands are counted apart from messages. New citation rule: a quote of the human's words cites a `USER` block only.

## 0.1.0 (2026-10-06)

Four skills in one plugin: `checkpoint`, `conversation-record`, `context-closeout`, `handoff`. First scripts: `make_record.py`, `session_metrics.py`, `locate_quote.py`.
