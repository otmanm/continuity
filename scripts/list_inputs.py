#!/usr/bin/env python3
"""
list_inputs.py  (G9a: one deterministic list of every human input; no AI, no clock, no network)

Reads one or several raw session files (Claude Code JSONL or Codex rollout JSONL, several files of one
resumed conversation allowed) and writes
  1. one Markdown table of every HUMAN input in order (plus counts, exclusions and the verbatim texts),
  2. one JSONL file, one object per classified input, field "class" from the fixed list below
     (schema: ../schemas/inputs.schema.json).
Same input bytes + same script version = same output bytes. Python standard library only.
Secrets are redacted with make_record.py's own SECRETS, so every text here is findable in the record.

Usage:
  python3 list_inputs.py <raw.jsonl> [<raw2.jsonl> ...] --md <out.md> --jsonl <out.jsonl> [--all] [--prohibitions]
  --all           table also lists the non human rows (injected, compaction summaries, meta lines)
  --prohibitions  adds the sentences of the opening human message that contain a prohibition cue
Stdout: one JSON line of counts, then the line "HUMAN INPUT ROWS: <n>" (the checkpoint pastes it).
Row labels are "F<k> L<n>" for several files and "L<n>" for one, the same labels make_record.py uses.

CLASSES (fixed): human_typed, human_typed_mid_turn, human_card_answer, human_card_dismissed,
  slash_command, interrupt_marker, harness_injected, ai_compact_summary, ai_meta.
The table lists the first six, plus harness_injected rows labelled ATTACHMENT (the human's attachment
names, kept on purpose). Everything else is counted under EXCLUSIONS and written to the JSONL.

EXCLUSION AND CLASSIFICATION RULES (every rule, in the order applied)
Claude Code (a "user" line is one raw line with type "user"; tool results are never inputs):
  C1  isCompactSummary true                      -> ai_compact_summary
  C2  isMeta true, or isSidechain true           -> ai_meta (hook feedback, skill text, subagent prompts)
  C3  content with a tool_result block whose tool_use_id is an AskUserQuestion call:
        toolUseResult.answers present (and none of them is a "[User dismissed" marker; Claude Code
        stores the marker inside answers too), or the text starts "Your questions have been
        answered" or "The user answered"         -> human_card_answer (text = the answers)
        anything else: "[User dismissed ...]", or "The user doesn't want to proceed" (tool use
        rejected)                                -> human_card_dismissed
  C4  any other tool_result block                -> not an input, counted as tool_result_lines
  C5  text starts with "[Request interrupted by user"          -> interrupt_marker
  C6  text starts with "<command-name>" or "<command-message>"   -> slash_command
  C7  origin.kind present (builds 2.1.23 and later):
        "human"                                  -> human_typed
        "peer"                                   -> ai_meta (a subagent report)
        any other kind ("task-notification", "unclassified", unknown) -> harness_injected
  C8  no origin field (older builds): "<local-command-", "<task-notification", "<system-reminder",
        "<agent-message", "<bash-stdout", "<bash-stderr" prefixes -> harness_injected;
        "<bash-input" -> human_typed (bash mode, noted); anything else -> human_typed, noted
        "no origin field, typed by content rule".
  C9  attachment line, attachment.type "queued_command" (a message typed while a turn runs):
        isMeta true                              -> ai_meta
        origin "human"                           -> human_typed_mid_turn
        origin "peer"                            -> ai_meta;  other origin kinds -> harness_injected
        no origin: harness prefix as C8 -> harness_injected, else human_typed_mid_turn (noted inferred)
  C10 queue-operation lines are bookkeeping. EXCEPT: an "enqueue" whose text never became a user line
      or a queued_command (a message a hook blocked, or one that was dropped) is the only trace of a
      human input, so it becomes a human_typed row with delivered false and a note. Machine enqueues
      (QUEUE_MACHINE_PREFIX: claude-mem observer sessions, task notifications, scheduled tasks...) are
      skipped; an enqueue starting with "/" matches a slash_command row of the same name.
  C10b a user line whose text starts "<scheduled-task" is fired by the scheduler -> harness_injected,
      even though the file stamps origin human (the words were written earlier, not in this session).
  C11 a line whose uuid or exact bytes already appeared in an EARLIER file is skipped (counted in
      duplicate_lines, with the class it would have had), the same rule as make_record.py rule 8.
Codex (rollout files; rules shared with make_record.py, tables CODEX_*):
  X1  line type "compacted"                      -> ai_compact_summary (one row; replacement_history is never read)
  X2  response_item message, role developer      -> not an input, counted as developer_role_messages
  X3  role user, text starts with a CODEX_INJECTED prefix ("# AGENTS.md instructions", "<skill",
      "<hook_prompt", "<external_codex_apps", "<environment_context", and the others in the table)
                                                 -> harness_injected, rule name in the note
  X4  role user, text starts with a CODEX_ATTACHMENT header ("# Files mentioned by the user", ...):
        the wrapper -> harness_injected labelled ATTACHMENT (attachment names kept);
        a request after "## My request:" -> its own human_typed row
  X5  role user, "<turn_aborted"                 -> interrupt_marker
  X6  role user, "<send_user_message_question_reply" -> human_card_answer (answers read from its JSON)
  X7  role user, anything else with text left after removing image wrapper tokens -> human_typed
      (noted UNRECOGNISED_TAG when it still starts with a "<tag"; image only -> ATTACHMENT row)
  X8  safety net: event_msg item_completed items of type UserMessage (newer builds) whose text is found in
      no user role line are counted as events_without_user_role_line (expected 0; non zero = a possible
      missed human message). The harness also counts app context blocks, cards and automation lines as
      UserMessage, so the raw count is shown for information only.
Voice notes: a human_card_dismissed row gets the note "possible mistranscription" when the card text, or
the human message just before it, contains a word of VOICE_MISHEARD (the human dictates; "clothes" was
"Claude" in one real session, corrected by the human).
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_record as mr  # shared redaction, hashing, fencing, file reading and the Codex rule tables

VERSION = "1.0.0"
CLASSES = ["human_typed", "human_typed_mid_turn", "human_card_answer", "human_card_dismissed",
           "slash_command", "interrupt_marker", "harness_injected", "ai_compact_summary", "ai_meta"]
TABLE_CLASSES = {"human_typed", "human_typed_mid_turn", "human_card_answer", "human_card_dismissed",
                 "slash_command", "interrupt_marker"}
KIND = {"human_typed": "typed", "human_typed_mid_turn": "typed mid turn", "human_card_answer": "card answer",
        "human_card_dismissed": "card dismissed", "slash_command": "slash command",
        "interrupt_marker": "interrupt marker", "harness_injected": "INJECTED (HARNESS)",
        "ai_compact_summary": "COMPACT_SUMMARY (AI)", "ai_meta": "META (AI)"}
# Words a speech recogniser is known to produce for another word. Source: one real case,
# where "clothes" meant Claude. Extend by evidence only.
VOICE_MISHEARD = {"clothes": "Claude", "clothing": "Claude"}
CLAUDE_HARNESS_PREFIX = ("<local-command-", "<task-notification", "<system-reminder", "<agent-message",
                         "<bash-stdout", "<bash-stderr")
QUEUE_MACHINE_PREFIX = ("<observed_from_primary", "Hello memory agent", "PROGRESS SUMMARY CHECK", "You are a Claude-Mem",
                        "<cross-session-message", "<task-notification", "<agent-message", "<scheduled-task", "<local-command-",
                        "<system-reminder", "<bash-stdout", "<bash-stderr")
PROHIBITION_CUES = [  # (regex, shown as). Cast wide on purpose: a superset is safe, an omission is not.
    (r"\b(?:do not|don't|never|must not|mustn't|not allowed|forbidden|without|does not|doesn't|cannot|can't|won't|no longer)\b", "do not, don't, never, must not, mustn't, not allowed, forbidden, without, does not, doesn't, cannot, can't, won't, no longer"),
    (r"^\s*no\b", "a sentence starting with \"No\""),
    (r"\bonly\b", "only"),
    (r"\bread[- ]only\b", "read only"),
]
TEXT_HEAD = 200


def cut(text, n=TEXT_HEAD):
    return text if len(text) <= n else text[:n]


def abbreviate(text, limit=200):
    """G9c rule: more than 200 characters -> first 8 words, [...], last 8 words."""
    flat = text.strip()
    if len(flat) <= limit:
        return flat
    w = flat.split()
    if len(w) <= 16:
        return flat
    return "%s [...] %s" % (" ".join(w[:8]), " ".join(w[-8:]))


def cell(text):
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", " ⏎ ")


def content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text") or "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def voice_hits(text):
    low = text.lower()
    return sorted(w for w in VOICE_MISHEARD if re.search(r"\b%s\b" % w, low))


class Ctx:
    def __init__(self):
        self.rows = []
        self.counts = {}
        self.auq = {}            # tool_use_id -> {"label","questions","header"}
        self.last_human = ""     # text of the latest human_typed row, for the voice note
        self.enqueued = []       # (label, text) of enqueued human looking queue lines
        self.tool_result_lines = 0
        self.dupes = {}
        self.dev_msgs = 0
        self.user_events = 0
        self.event_texts = []
        self.user_role_texts = []
        self.notes = {}
        self.versions = set()

    def bump(self, key, n=1):
        self.counts[key] = self.counts.get(key, 0) + n


def make_row(cls, harness, tag, n, ts, text, note="", **extra):
    r = {"class": cls, "harness": harness, "file": tag, "line": n, "timestamp": ts or "", "text": text,
         "note": note}
    r.update(extra)
    return r


def claude_line(o, ctx, label, tag, n):
    """Return the list of rows one raw Claude line produces (no state change except AUQ registration)."""
    t = o.get("type")
    ts = o.get("timestamp", "")
    if isinstance(o.get("version"), str):
        ctx.versions.add(o["version"])
    if t == "assistant":
        c = (o.get("message") or {}).get("content")
        for b in c if isinstance(c, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "AskUserQuestion":
                qs = (b.get("input") or {}).get("questions") or []
                ctx.auq[b.get("id")] = {"label": label, "questions": qs}
        return []
    if t == "queue-operation":
        ctx.bump("queue_operation_lines")
        if o.get("operation") == "enqueue" and isinstance(o.get("content"), str) \
                and not o["content"].lstrip().startswith(QUEUE_MACHINE_PREFIX):
            ctx.enqueued.append((label, o["content"], tag, n, ts))
        return []
    if t == "attachment":
        a = o.get("attachment") or {}
        if a.get("type") != "queued_command":
            return []
        prompt = a.get("prompt")
        text = content_text(prompt) if not isinstance(prompt, str) else prompt
        og = a.get("origin") if isinstance(a.get("origin"), dict) else None
        kind = og.get("kind") if og else None
        if a.get("isMeta") is True or kind == "peer":
            return [make_row("ai_meta", "claude", tag, n, ts, text, "queued_command, origin %s" % (kind or "none"))]
        if kind and kind != "human":
            return [make_row("harness_injected", "claude", tag, n, ts, text, "queued_command, origin %s" % kind)]
        if kind is None and text.lstrip().startswith(CLAUDE_HARNESS_PREFIX):
            return [make_row("harness_injected", "claude", tag, n, ts, text, "queued_command, harness prefix")]
        return [make_row("human_typed_mid_turn", "claude", tag, n, ts, text,
                         "queued_command origin human" if kind else "queued_command, no origin field, typed by content rule",
                         origin=kind or "none")]
    if t != "user":
        return []
    msg = o.get("message") or {}
    content = msg.get("content")
    if o.get("isCompactSummary"):
        return [make_row("ai_compact_summary", "claude", tag, n, ts, content_text(content), "isCompactSummary")]
    if o.get("isMeta") or o.get("isSidechain") is True:
        return [make_row("ai_meta", "claude", tag, n, ts, content_text(content),
                         "isMeta" if o.get("isMeta") else "isSidechain")]
    rows = []
    blocks = content if isinstance(content, list) else []
    results = [b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_result"]
    if results:
        ans = (o.get("toolUseResult") or {}).get("answers") if isinstance(o.get("toolUseResult"), dict) else None
        for b in results:
            card = ctx.auq.get(b.get("tool_use_id"))
            if card is None:
                ctx.tool_result_lines += 1
                continue
            raw = b.get("content")
            raw = raw if isinstance(raw, str) else content_text(raw)
            qtext = " | ".join(str(q.get("question", "")) for q in card["questions"] if isinstance(q, dict))
            opts = " ".join("%s %s" % (op.get("label", ""), op.get("description", ""))
                            for q in card["questions"] if isinstance(q, dict) for op in (q.get("options") or []) if isinstance(op, dict))
            vals_all = [str(v) for v in (ans or {}).values()]
            marker = "[User dismissed" in raw or any("[User dismissed" in v for v in vals_all)  # the marker also sits INSIDE answers
            answered = (bool(ans) or raw.startswith(("Your questions have been answered", "The user answered", "User has answered"))) and not marker
            if not answered:
                m = re.search(r"\[User dismissed[^\]]*\]", raw)
                dismissed = vals_all or [m.group(0) if m else raw[:200]]
                hits = voice_hits(qtext + " " + opts) or voice_hits(ctx.last_human)
                where = "card text" if voice_hits(qtext + " " + opts) else "the human message before the card"
                if hits:
                    note = ("possible mistranscription: %s uses %s (the human dictates; %s was heard instead of %s)"
                            % (where, ", ".join("'%s'" % h for h in hits), hits[0], VOICE_MISHEARD[hits[0]]))
                else:
                    note = "dismissed; no known voice word in the card or the message before it, cause unknown"
                rows.append(make_row("human_card_dismissed", "claude", tag, n, ts, " | ".join(dismissed),
                                     note + "; card asked at %s, %d question(s) dismissed" % (card["label"], len(dismissed)), question=qtext))
            else:
                vals = [str(v) for v in (ans or {}).values()]
                if not vals:
                    m = re.findall(r'"=\"(.*?)\"(?:,|\. )', raw)
                    vals = m or [raw]
                rows.append(make_row("human_card_answer", "claude", tag, n, ts, " | ".join(vals),
                                     "card asked at %s" % card["label"], question=qtext))
        if rows or not [b for b in blocks if isinstance(b, dict) and b.get("type") == "text"]:
            return rows
    text = content_text(content)
    s = text.lstrip()
    imgs = len([b for b in blocks if isinstance(b, dict) and b.get("type") == "image"])
    if s.startswith("[Request interrupted by user"):
        return rows + [make_row("interrupt_marker", "claude", tag, n, ts, text, "harness marker, not a human sentence")]
    if s.startswith(("<command-name>", "<command-message>")):
        return rows + [make_row("slash_command", "claude", tag, n, ts, text, "")]
    og = o.get("origin") if isinstance(o.get("origin"), dict) else None
    kind = og.get("kind") if og else None
    if kind == "peer":
        return rows + [make_row("ai_meta", "claude", tag, n, ts, text, "origin peer")]
    if kind and kind != "human":
        return rows + [make_row("harness_injected", "claude", tag, n, ts, text, "origin %s" % kind)]
    if s.startswith("<scheduled-task"):
        return rows + [make_row("harness_injected", "claude", tag, n, ts, text, "scheduler wrapper; origin %s but fired by the scheduler" % (kind or "none"))]
    if kind is None and s.startswith(CLAUDE_HARNESS_PREFIX):
        return rows + [make_row("harness_injected", "claude", tag, n, ts, text, "harness prefix, no origin field")]
    note = ("origin human; promptSource %s" % o.get("promptSource")) if kind else "no origin field, typed by content rule"
    if kind is None and s.startswith("<bash-input"):
        note += "; bash mode"
    if imgs:
        note += "; %d image block(s)" % imgs
    return rows + [make_row("human_typed", "claude", tag, n, ts, text, note, origin=kind or "none")]


def codex_line(o, ctx, label, tag, n):
    t = o.get("type")
    ts = o.get("timestamp", "")
    p = o.get("payload") if isinstance(o.get("payload"), dict) else {}
    if t == "compacted":
        hist = p.get("replacement_history")
        return [make_row("ai_compact_summary", "codex", tag, n, ts,
                         "[compacted record; replacement_history of %d items not read]" % (len(hist) if isinstance(hist, list) else 0),
                         "type compacted")]
    if t == "event_msg":
        if p.get("type") == "item_completed" and isinstance(p.get("item"), dict) and p["item"].get("type") == "UserMessage":
            ctx.user_events += 1
            ic = p["item"].get("content")
            ctx.event_texts.append("".join(b.get("text", "") for b in ic if isinstance(b, dict)) if isinstance(ic, list) else str(ic or ""))
        return []
    if t != "response_item" or p.get("type") != "message":
        return []
    role = p.get("role")
    if role == "developer":
        ctx.dev_msgs += 1
        return []
    if role != "user":
        return []
    c = p.get("content")
    text = "".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "input_text") if isinstance(c, list) else str(c or "")
    ctx.user_role_texts.append(text)
    kind, rule, req = mr.codex_user_kind(text)
    if kind == "injected":
        return [make_row("harness_injected", "codex", tag, n, ts, text, "role user; rule %s" % rule, role="user")]
    if kind == "interrupt":
        return [make_row("interrupt_marker", "codex", tag, n, ts, text, "role user; <turn_aborted>", role="user")]
    if kind == "card":
        m = re.search(r"<send_user_message_question_reply>\s*(.*?)\s*</send_user_message_question_reply>", text, re.S)
        ans, qs = [], []
        try:
            for it in json.loads(m.group(1)):
                ans.append(str(it.get("answer", ""))); qs.append(str(it.get("question", "")))
        except Exception:
            ans, qs = [text], []
        return [make_row("human_card_answer", "codex", tag, n, ts, " | ".join(ans), "role user; question_reply", question=" | ".join(qs), role="user")]
    rows = []
    if kind == "attachment":
        names = re.findall(r"^## (.+?): /", text, re.M) or re.findall(r"<image name=([^ >]+)", text)
        names = names or (["[image]"] if "<image" in text or any(isinstance(b, dict) and b.get("type") == "input_image" for b in (c or [])) else [])
        wrapper = text if not req else text[: text.find(mr.REQUEST_MARK) + len(mr.REQUEST_MARK)]
        rows.append(make_row("harness_injected", "codex", tag, n, ts, wrapper,
                             "ATTACHMENT; role user; rule %s" % rule, role="user", attachments=names, flag="ATTACHMENT"))
        if not req:
            return rows
        text, kind = req, "typed"
    note = "role user"
    if "<image" in text or "[Image #" in text:
        note += "; image attached"
    if re.match(r"\s*<[A-Za-z_]", mr.IMAGE_TOKENS.sub("", text)):
        note += "; UNRECOGNISED_TAG (starts with a tag no rule knows, check by hand)"
        ctx.bump("typed_with_unrecognised_tag")
    rows.append(make_row("human_typed", "codex", tag, n, ts, text, note, role="user"))
    return rows


def load(paths):
    files = [mr.read_lines(p) for p in paths]
    multi = len(files) > 1
    if multi:
        files.sort(key=lambda f: (f["first"], f["last"], os.path.basename(f["path"])))
    for f in files:
        harness = "claude"
        for ln in f["lines"][:5]:
            try:
                o = json.loads(ln.decode("utf-8"))
            except Exception:
                continue
            if isinstance(o, dict) and o.get("type") == "session_meta":
                harness = "codex"
            break
        if harness == "claude" and os.path.basename(f["path"]).startswith("rollout-"):
            harness = "codex"
        f["harness"] = harness
    return files, multi


def build(paths):
    files, multi = load(paths)
    ctx = Ctx()
    per_file = []
    seen_uuid, seen_bytes = {}, {}
    for k, f in enumerate(files, 1):
        tag = "F%d" % k if multi else ""
        new_uuid, new_bytes = {}, {}
        info = {"tag": tag or "F1", "file": os.path.basename(f["path"]), "sha256": mr.sha(f["raw"]),
                "lines": len(f["lines"]), "first": f["first"], "last": f["last"], "harness": f["harness"],
                "version": None}
        ctx.versions, ctx.user_events, ctx.dev_msgs = set(), 0, 0
        ctx.event_texts, ctx.user_role_texts = [], []
        file_rows_before = len(ctx.rows)
        for n, ln in enumerate(f["lines"], 1):
            label = ("F%d L%d" % (k, n)) if multi else ("L%d" % n)
            try:
                o = json.loads(ln.decode("utf-8"))
            except Exception:
                ctx.bump("unparseable_lines")
                continue
            if not isinstance(o, dict):
                continue
            if f["harness"] == "codex" and o.get("type") == "session_meta":
                pl = o.get("payload") or {}
                info["version"] = pl.get("cli_version")
                info["originator"] = pl.get("originator")
                info["source"] = pl.get("source")
            u = o.get("uuid") if isinstance(o.get("uuid"), str) else None
            first = seen_uuid.get(u) if (multi and u) else None
            if multi and first is None:
                first = seen_bytes.get(mr.sha(ln))
            fn = codex_line if f["harness"] == "codex" else claude_line
            if multi and first is not None:  # duplicate of an earlier file: classify on a scratch context
                scratch = Ctx(); scratch.auq = ctx.auq; scratch.last_human = ctx.last_human
                for r in fn(o, scratch, label, tag or "F1", n):
                    ctx.dupes[r["class"]] = ctx.dupes.get(r["class"], 0) + 1
                continue
            rows = fn(o, ctx, label, tag or "F1", n)
            if multi:
                if u:
                    new_uuid.setdefault(u, label)
                new_bytes.setdefault(mr.sha(ln), label)
            for r in rows:
                r["ref"] = label
                if r["class"] == "human_typed":
                    ctx.last_human = r["text"]
                ctx.rows.append(r)
        for d, nd in ((seen_uuid, new_uuid), (seen_bytes, new_bytes)):
            for key, val in nd.items():
                d.setdefault(key, val)
        if f["harness"] == "claude":
            info["version"] = ", ".join(sorted(ctx.versions)) or None
        else:
            typed_like = sum(1 for r in ctx.rows[file_rows_before:] if r["class"] == "human_typed" or r.get("flag") == "ATTACHMENT")
            info["developer_role_messages"] = ctx.dev_msgs
            info["usermessage_events"] = ctx.user_events
            info["typed_plus_attachment_rows"] = typed_like
            big = "\n".join(ctx.user_role_texts)
            lost = [e for e in ctx.event_texts if e.strip() and e.strip()[:60] not in big]
            info["events_without_user_role_line"] = len(lost)
            info["cross_check"] = ("n/a (no UserMessage events in this build)" if not ctx.user_events else
                                   ("0 events without a user role line" if not lost else
                                    "%d event(s) without a user role line, look by hand" % len(lost)))
        per_file.append(info)
    return files, multi, ctx, per_file


def finish_rows(ctx):
    # 1. C10: enqueued human text that never became a user line or queued_command gets its own row
    have = {mr.redact(x["text"]).strip() for x in ctx.rows if x["class"] in ("human_typed", "human_typed_mid_turn")}
    slash = [x["text"] for x in ctx.rows if x["class"] == "slash_command"]
    extra = []
    for label, t, tag, n, ts in ctx.enqueued:
        t2 = mr.redact(t).strip()
        if t2 in have or (t2.startswith("/") and any(t2.split()[0] in x for x in slash)):
            continue
        r = make_row("human_typed", "claude", tag, n, ts, t,
                     "enqueue only: this text never became a user line or queued_command (blocked by a hook or dropped); read the lines after it",
                     origin="none", delivered=False)
        r["ref"] = label
        extra.append(r)
    ctx.notes["queued_text_without_row"] = len(extra)
    ctx.rows = sorted(ctx.rows + extra, key=lambda r: (int(re.sub(r"\D", "", r["file"]) or 1), r["line"]))
    # 2. redact, truncate non human text, number, label
    seq = 0
    for r in ctx.rows:
        seq += 1
        r["seq"] = seq
        full = mr.redact(r["text"])
        r["text_chars"] = len(r["text"])
        r["text_sha256"] = mr.sha(r["text"])
        keep_full = r["class"] in TABLE_CLASSES or r.get("flag") == "ATTACHMENT"
        r["text"] = full if keep_full else cut(full)
        r["text_truncated"] = (not keep_full) and len(full) > TEXT_HEAD
        r["note"] = mr.redact(r["note"])
        if r.get("question"):
            r["question"] = mr.redact(r["question"])
        undelivered = r.get("delivered") is False
        r["kind"] = "ATTACHMENT" if r.get("flag") == "ATTACHMENT" else (KIND[r["class"]] + (" (enqueue only, NOT delivered)" if undelivered else ""))
        r["file_line"] = r.pop("ref")


def counts_by_class(ctx):
    c = {k: 0 for k in CLASSES}
    for r in ctx.rows:
        c[r["class"]] += 1
    c["attachment_rows"] = sum(1 for r in ctx.rows if r["kind"] == "ATTACHMENT")
    return c


def render_md(ctx, files, per_file, multi, show_all, prohibitions):
    cc = counts_by_class(ctx)
    table = [r for r in ctx.rows if show_all or r["class"] in TABLE_CLASSES or r["kind"] == "ATTACHMENT"]
    n_rows = sum(1 for r in ctx.rows if r["class"] in TABLE_CLASSES or r["kind"] == "ATTACHMENT")
    out = ["# Human input list (list_inputs.py v%s)" % VERSION, "",
           "Deterministic, no AI. Layer 0 (the raw files) is the evidence; the line labels below match the labels in the conversation record built by make_record.py.", "",
           "| field | value |", "|---|---|"]
    for p in per_file:
        out.append("| %s | %s · %s · sha256 %s · %d lines · %s to %s · writer version %s |" % (
            p["tag"], p["harness"], p["file"], p["sha256"], p["lines"], p["first"], p["last"], p.get("version") or "unknown"))
    out += ["| script | list_inputs.py v%s |" % VERSION,
            "| script_sha256 | %s |" % mr.sha(open(os.path.abspath(__file__), "rb").read()),
            "| duplicate_lines_skipped | %s |" % (json.dumps(ctx.dupes, sort_keys=True) if ctx.dupes else "0"), "",
            "## Table 1. Every human input, in order", "",
            "| # | timestamp | file and line | kind | text (over 200 characters: first 8 words [...] last 8 words) | note |",
            "|---|---|---|---|---|---|"]
    tnum = {id(r): i for i, r in enumerate(table, 1)}  # table numbers stay out of the rows (and the JSONL)
    for r in table:
        t = abbreviate(r["text"]) if r["class"] in TABLE_CLASSES or r["kind"] == "ATTACHMENT" else cut(r["text"], 80)
        extra = " · %d chars" % r["text_chars"] if r["text_chars"] > 200 else ""
        names = (" · attachments: " + ", ".join(r["attachments"])) if r.get("attachments") else ""
        out.append("| %d | %s | %s | %s | %s | %s |" % (tnum[id(r)], r["timestamp"], r["file_line"], r["kind"], cell(t), cell(r["note"] + extra + names)))
    out += ["", "## Counts", "", "| class | rows |", "|---|---|"]
    out += ["| %s | %d |" % (k, cc[k]) for k in CLASSES]
    out.append("| (ATTACHMENT rows, a subset of harness_injected) | %d |" % cc["attachment_rows"])
    out += ["", "## Exclusions (counted, not listed; every row is in the JSONL)", "", "| item | count |", "|---|---|",
            "| duplicate lines of earlier files, by class | %s |" % (json.dumps(ctx.dupes, sort_keys=True) if ctx.dupes else "0"),
            "| tool_result lines that are not card answers | %d |" % ctx.tool_result_lines,
            "| queue-operation lines (bookkeeping) | %d |" % ctx.counts.get("queue_operation_lines", 0),
            "| human text found only as an enqueue line, row added (expected 0) | %d |" % ctx.notes.get("queued_text_without_row", 0),
            "| typed_with_unrecognised_tag (expected 0) | %d |" % ctx.counts.get("typed_with_unrecognised_tag", 0),
            "| unparseable lines | %d |" % ctx.counts.get("unparseable_lines", 0)]
    for p in per_file:
        if p["harness"] == "codex":
            rules = {}
            for r in ctx.rows:
                if r["file"] == p["tag"] and r["class"] == "harness_injected":
                    m = re.search(r"rule (\w+)", r["note"]); rules[m.group(1) if m else "other"] = rules.get(m.group(1) if m else "other", 0) + 1
            out.append("| %s Codex %s: harness_injected by rule | %s |" % (p["tag"], p.get("version"), json.dumps(rules, sort_keys=True)))
            out.append("| %s Codex developer role messages (never human) | %d |" % (p["tag"], p["developer_role_messages"]))
            out.append("| %s safety net: UserMessage events %d (also count app context, cards, automation) vs typed plus attachment rows %d | %s |" % (
                p["tag"], p["usermessage_events"], p["typed_plus_attachment_rows"], p["cross_check"]))
    breakdown = "typed %d, typed mid turn %d, card answer %d, card dismissed %d, slash command %d, interrupt marker %d, attachment %d" % (
        cc["human_typed"], cc["human_typed_mid_turn"], cc["human_card_answer"], cc["human_card_dismissed"],
        cc["slash_command"], cc["interrupt_marker"], cc["attachment_rows"])
    out += ["", "## Verbatim texts of the table rows", "",
            "Full text of each table row, redacted like the record. Cite from here only with a record line from locate_quote.py.", ""]
    for r in table:
        if r["class"] in TABLE_CLASSES or r["kind"] == "ATTACHMENT":
            out += ["### %d · %s · %s" % (tnum[id(r)], r["file_line"], r["kind"]), "", mr.fence(r["text"]), ""]
    if prohibitions:
        first = next((r for r in ctx.rows if r["class"] == "human_typed"), None)
        out += ["## Prohibition candidates in the opening human message (%s)" % (first["file_line"] if first else "none"), "",
                "Every sentence or line of the opening human message that matches one of these cues: %s." % "; ".join(c for _, c in PROHIBITION_CUES),
                "The do not list of a checkpoint takes ALL of them, verbatim, or names each one it leaves out in GAPS.", ""]
        if first:
            parts = [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", first["text"]) if x.strip()]
            hits = [x for x in parts if any(re.search(rx, x, re.I) for rx, _ in PROHIBITION_CUES)]
            out += ["| # | sentence (verbatim) |", "|---|---|"] + ["| %d | %s |" % (i, cell(x)) for i, x in enumerate(hits, 1)]
            out.append("")
            ctx.notes["prohibition_candidates"] = len(hits)
    out += ["HUMAN INPUT ROWS: %d (%s)" % (n_rows, breakdown), ""]
    return "\n".join(out), n_rows, cc


def main(argv):
    show_all = "--all" in argv
    prohib = "--prohibitions" in argv
    md = jsonl = None
    paths = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--md":
            md = argv[i + 1]; i += 2; continue
        if a == "--jsonl":
            jsonl = argv[i + 1]; i += 2; continue
        if a in ("--all", "--prohibitions"):
            i += 1; continue
        paths.append(a); i += 1
    if not paths:
        sys.stderr.write(__doc__)
        return 2
    files, multi, ctx, per_file = build(paths)
    finish_rows(ctx)
    text, n_rows, cc = render_md(ctx, files, per_file, multi, show_all, prohib)
    if md:
        with open(md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    if jsonl:
        with open(jsonl, "w", encoding="utf-8", newline="\n") as fh:
            for r in ctx.rows:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {"script": "list_inputs.py", "version": VERSION, "rows_in_table": n_rows, "classes": cc,
               "duplicates_by_class": ctx.dupes, "queued_text_without_row": ctx.notes.get("queued_text_without_row", 0),
               "files": [{k: p.get(k) for k in ("tag", "harness", "version", "cross_check", "developer_role_messages", "usermessage_events")} for p in per_file]}
    print(json.dumps(summary, sort_keys=True))
    print("HUMAN INPUT ROWS: %d" % n_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
