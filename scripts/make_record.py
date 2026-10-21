#!/usr/bin/env python3
"""
make_record.py  (Layer 1: deterministic transform, no AI)

Turns one raw session file (Layer 0: Claude Code or Codex JSONL) into one readable
Markdown record. Same input bytes + same script version = same output bytes, always.

Rules (v1.0.0):
  1. One block per raw line, headed "## L<n>" with the raw line number, in order. No line is skipped.
  2. Dialogue is rendered verbatim: user text, assistant text, thinking text, tool calls
     (name + full JSON input), tool results (full text). Metadata fields of these lines
     (uuid, parentUuid, cwd...) are not repeated; they stay in Layer 0 at the same line.
  3. Every other record type is dumped as its full raw JSON (sorted keys), so nothing is dropped.
  4. Opaque blobs are replaced by a labelled placeholder with length and sha256:
     keys "data" (base64 images), "encrypted_content", "signature".
  5. Secrets are replaced by "[REDACTED:<kind>:<sha256 first 8>]" using fixed regexes.
  6. No timestamps, no randomness, no network. Python standard library only.
  7. (1.1.0) A Claude "user" line that Claude Code wrote itself is never headed USER:
     isCompactSummary -> "COMPACT_SUMMARY (AI)", isMeta -> "META (AI)". Text is kept verbatim.
  8. (1.1.0) Several raw files of one resumed conversation give one record. Files are ordered by
     (first timestamp, last timestamp, file name) and tagged F1, F2... Headings become "## F<k> L<n>".
     A line whose uuid, or whose exact bytes, already appeared in an EARLIER FILE is kept as a
     one line DUPLICATE pointer to that block, so every raw line of every file still has a block.
     With one file the output format is unchanged ("## L<n>").
  9. (1.2.0, Codex only) Codex stores harness text under role "user". A Codex user role message that
     matches CODEX_INJECTED, or CODEX_ATTACHMENT with an empty request, is headed "INJECTED (HARNESS)"
     (never "USER message"); its text is kept verbatim. The rule table below is shared with
     list_inputs.py, so the record and the human input list can never disagree. Claude records are
     unchanged: same bytes as 1.1.0 except the two header rows `script` and `script_sha256`.

Usage: python3 make_record.py <raw.jsonl> [<raw2.jsonl> ...] <out.md>
Prints one JSON line of counts to stdout (for the tests).
"""
import hashlib, json, re, sys, os

VERSION = "1.2.0"  # 1.2.0 (2026-10-06): G9b Codex injected user role messages headed INJECTED (HARNESS)
# 1.1.0 (2026-10-06): D1 AI authored user lines labelled, G5 multi file record
# 1.0.1 (2026-10-06): signed URL signatures redacted
BLOB_KEYS = {"data", "encrypted_content", "signature"}
SECRETS = [
    ("anthropic_or_openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("aws_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}")),
    ("signed_url", re.compile(r"\bsig=[0-9a-f]{20,}")),  # 1.0.1: signed link signatures seen in a real session file
]
COUNT = {"lines": 0, "user_text": 0, "assistant_text": 0, "thinking": 0,
         "tool_use": 0, "tool_result": 0, "raw_dump": 0, "blobs": 0, "redactions": 0,
         "compact_summary_ai": 0, "meta_ai": 0, "duplicates": 0}


# Codex user role rules (shared with list_inputs.py). The text is tested after lstrip(); first match wins.
# Source of every prefix: survey of 1,120 Codex rollouts (versions 0.87.0 to 0.160.0) on 2026-10-06,
# plus six prefixes found in real Codex rollouts. Codex PR 14609 (merged 2026-03-14) moved the
# skills LIST to the developer role; "<skill" (a skill the human invoked) still arrives as role user.
CODEX_INJECTED = [
    ("agents_md", "# AGENTS.md instructions"),
    ("skill", "<skill"),
    ("hook_prompt", "<hook_prompt"),
    ("external_codex_apps", "<external_codex_apps"),
    ("environment_context", "<environment_context"),
    ("recommended_plugins", "<recommended_plugins"),
    ("previous_cards", "<previous_cards"),
    ("in_app_browser", "# In app browser:"),
    ("in_app_browser_context", "<in-app-browser-context"),
    ("chrome_tabs", "# Chrome tabs:"),
    ("codex_internal_context", "<codex_internal_context"),
    ("codex_delegation", "<codex_delegation"),
    ("user_action", "<user_action"),
    ("heartbeat", "<heartbeat"),
    ("subagent_notification", "<subagent_notification"),
    ("user_instructions", "<user_instructions"),
    ("automation_system_line", "System: ["),
]
# Wrappers that carry the human's attachments or selections; the request, if any, follows "## My request:".
CODEX_ATTACHMENT = [
    ("files_mentioned", "# Files mentioned by the user"),
    ("applications_mentioned", "# Applications mentioned by the user"),
    ("selected_text", "# Selected text:"),
    ("response_annotations", "# Response annotations:"),
]
CODEX_INTERRUPT = ("turn_aborted", "<turn_aborted")
CODEX_CARD = ("question_reply", "<send_user_message_question_reply")
REQUEST_MARK = "## My request:"
IMAGE_TOKENS = re.compile(r"<image[^>]*>|</image>|\[Image #\d+\]")


def codex_user_kind(text):
    """Classify the text of one Codex user role message.
    Returns (kind, rule, request): kind is injected, attachment, interrupt, card or typed.
    `request` is the human's own text with image wrapper tokens removed (may be empty)."""
    t = text.lstrip()
    for rule, pre in CODEX_INJECTED:
        if t.startswith(pre):
            return "injected", rule, ""
    for rule, pre in CODEX_ATTACHMENT:
        if t.startswith(pre):
            i = t.find(REQUEST_MARK)
            req = IMAGE_TOKENS.sub("", t[i + len(REQUEST_MARK):]).strip() if i >= 0 else ""
            return "attachment", rule, req
    if t.startswith(CODEX_INTERRUPT[1]):
        return "interrupt", CODEX_INTERRUPT[0], ""
    if t.startswith(CODEX_CARD[1]):
        return "card", CODEX_CARD[0], ""
    req = IMAGE_TOKENS.sub("", t).strip()
    return ("typed" if req else "attachment"), ("typed" if req else "image_only"), req


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()


def redact(s):
    for kind, rx in SECRETS:
        def rep(m, kind=kind):
            COUNT["redactions"] += 1
            return "[REDACTED:%s:%s]" % (kind, sha(m.group(0))[:8])
        s = rx.sub(rep, s)
    return s


def deblob(o):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if k in BLOB_KEYS and isinstance(v, str) and len(v) > 64:
                COUNT["blobs"] += 1
                out[k] = "[BLOB:%s:%d chars:sha256 %s]" % (k, len(v), sha(v))
            else:
                out[k] = deblob(v)
        return out
    if isinstance(o, list):
        return [deblob(x) for x in o]
    return o


def fence(text, lang=""):
    runs = [len(r) for r in re.findall(r"`+", text)]
    f = "`" * max(3, (max(runs) + 1) if runs else 3)
    return "%s%s\n%s\n%s" % (f, lang, text, f)


def dump(o):
    COUNT["raw_dump"] += 1
    return fence(redact(json.dumps(deblob(o), ensure_ascii=False, sort_keys=True, indent=1)), "json")


def text_of(content):
    if isinstance(content, str):
        return content
    parts = []
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict):
                if "text" in b:
                    parts.append(str(b.get("text") or ""))
                else:
                    parts.append(json.dumps(deblob(b), ensure_ascii=False, sort_keys=True))
            else:
                parts.append(str(b))
    return "\n".join(parts)


def claude_block(o):
    t = o.get("type")
    msg = o.get("message")
    if t not in ("user", "assistant") or not isinstance(msg, dict):
        return t or "unknown", [dump(o)]
    content = msg.get("content")
    who = "USER" if t == "user" else "ASSISTANT"
    text_key = "user_text" if t == "user" else "assistant_text"
    if t == "user" and o.get("isCompactSummary"):  # rule 7: only the heading changes
        who, text_key = "COMPACT_SUMMARY (AI)", None
        COUNT["compact_summary_ai"] += 1
    elif t == "user" and o.get("isMeta"):
        who, text_key = "META (AI)", None
        COUNT["meta_ai"] += 1
    if isinstance(content, str):
        if text_key:
            COUNT[text_key] += 1
        return who, [fence(redact(content))]
    out = []
    for b in content or []:
        if not isinstance(b, dict):
            out.append(fence(redact(str(b))))
            continue
        bt = b.get("type")
        if bt == "text":
            if text_key:
                COUNT[text_key] += 1
            out.append("**text**\n" + fence(redact(b.get("text", ""))))
        elif bt == "thinking":
            COUNT["thinking"] += 1
            out.append("**thinking**\n" + fence(redact(b.get("thinking", ""))))
        elif bt == "tool_use":
            COUNT["tool_use"] += 1
            out.append("**tool_use** `%s` id `%s`\n%s" % (b.get("name"), b.get("id"),
                       fence(redact(json.dumps(deblob(b.get("input")), ensure_ascii=False, sort_keys=True, indent=1)), "json")))
        elif bt == "tool_result":
            COUNT["tool_result"] += 1
            err = " (error)" if b.get("is_error") else ""
            out.append("**tool_result**%s for `%s`\n%s" % (err, b.get("tool_use_id"), fence(redact(text_of(b.get("content"))))))
        else:
            out.append("**%s**\n%s" % (bt, dump(b)))
    return who, out


def codex_block(o):
    t = o.get("type")
    p = o.get("payload")
    if t != "response_item" or not isinstance(p, dict):
        return t or "unknown", [dump(o)]
    pt = p.get("type")
    if pt == "message":
        role = p.get("role")
        if role == "user":  # rule 9: harness text stored as role user is never headed USER
            joined = "".join(b.get("text", "") for b in (p.get("content") or []) if isinstance(b, dict) and b.get("type") == "input_text") \
                if isinstance(p.get("content"), list) else str(p.get("content") or "")
            kind, rule, req = codex_user_kind(joined)
            if kind == "injected" or (kind == "attachment" and not req):
                COUNT["injected_harness"] = COUNT.get("injected_harness", 0) + 1
                return "INJECTED (HARNESS)", [fence(redact(text_of(p.get("content"))))]
        COUNT["user_text" if role == "user" else "assistant_text"] += 1
        return "%s message" % str(role).upper(), [fence(redact(text_of(p.get("content"))))]
    if pt in ("function_call", "custom_tool_call"):
        COUNT["tool_use"] += 1
        args = p.get("arguments", p.get("input", ""))
        return "TOOL CALL", ["**tool_use** `%s` id `%s`\n%s" % (p.get("name"), p.get("call_id"), fence(redact(str(args))))]
    if pt in ("function_call_output", "custom_tool_call_output"):
        COUNT["tool_result"] += 1
        out = p.get("output")
        return "TOOL RESULT", ["**tool_result** for `%s`\n%s" % (p.get("call_id"), fence(redact(out if isinstance(out, str) else json.dumps(deblob(out), ensure_ascii=False, sort_keys=True, indent=1))))]
    if pt == "reasoning":
        COUNT["thinking"] += 1
        summ = text_of(p.get("summary"))
        return "REASONING", ["**reasoning summary**\n" + fence(redact(summ)), "**raw**\n" + dump(p)]
    return "response_item/%s" % pt, [dump(o)]


def read_lines(src):
    raw = open(src, "rb").read()
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines = lines[:-1]
    stamps = []
    for ln in lines:
        try:
            o = json.loads(ln.decode("utf-8"))
        except Exception:
            continue
        if isinstance(o, dict) and isinstance(o.get("timestamp"), str):
            stamps.append(o["timestamp"])
    stamps.sort()
    return {"path": src, "raw": raw, "lines": lines,
            "first": stamps[0] if stamps else "", "last": stamps[-1] if stamps else ""}


def main(srcs, dst):
    files = [read_lines(s) for s in srcs]
    multi = len(files) > 1
    if multi:  # rule 8: oldest conversation first
        files.sort(key=lambda f: (f["first"], f["last"], os.path.basename(f["path"])))
    harness = "codex" if os.path.basename(files[0]["path"]).startswith("rollout-") else "claude"
    script_sha = sha(open(os.path.abspath(__file__), "rb").read())
    body = []
    seen_uuid, seen_bytes = {}, {}  # uuid or sha256 of raw bytes -> label of the first block
    for k, f in enumerate(files, 1):
        new_uuid, new_bytes = {}, {}  # merged after the file: pointers only go to EARLIER files
        for n, ln in enumerate(f["lines"], 1):
            COUNT["lines"] += 1
            label = "F%d L%d" % (k, n) if multi else "L%d" % n
            try:
                o = json.loads(ln.decode("utf-8"))
            except Exception:
                body.append("## %s · UNPARSEABLE\n%s\n" % (label, fence(redact(ln.decode("utf-8", "replace")))))
                continue
            ts = o.get("timestamp", "") if isinstance(o, dict) else ""
            if multi:
                u = o.get("uuid") if isinstance(o, dict) and isinstance(o.get("uuid"), str) else None
                first = seen_uuid.get(u) if u else None
                why = "same uuid"
                if first is None:
                    first, why = seen_bytes.get(sha(ln)), "same bytes"
                if first is not None:
                    COUNT["duplicates"] += 1
                    body.append("## %s · DUPLICATE · %s\n\n%s as %s; content not repeated.\n" % (label, ts, why.capitalize(), first))
                    continue
                if u:
                    new_uuid.setdefault(u, label)
                new_bytes.setdefault(sha(ln), label)
            kind, parts = (codex_block if harness == "codex" else claude_block)(o) if isinstance(o, dict) else ("value", [dump(o)])
            body.append("## %s · %s · %s\n\n%s\n" % (label, kind, ts, "\n\n".join(parts)))
        for d, nd in ((seen_uuid, new_uuid), (seen_bytes, new_bytes)):
            for key, val in nd.items():
                d.setdefault(key, val)
    if multi:
        src_rows = ["| source_files | %d, ordered by first then last timestamp |" % len(files)]
        for k, f in enumerate(files, 1):
            src_rows.append("| F%d | %s · sha256 %s · %d lines · %s to %s |" % (
                k, os.path.basename(f["path"]), sha(f["raw"]), len(f["lines"]), f["first"], f["last"]))
        src_rows.append("| duplicate_pointers | %d |" % COUNT["duplicates"])
    else:
        f = files[0]
        src_rows = ["| source_file | %s |" % os.path.basename(f["path"]),
                    "| source_sha256 | %s |" % sha(f["raw"]),
                    "| source_lines | %d |" % len(f["lines"])]
    head = [
        "# Layer 1 record: %s session" % harness,
        "",
        "| field | value |", "|---|---|",
    ] + src_rows + [
        "| script | make_record.py v%s |" % VERSION,
        "| script_sha256 | %s |" % script_sha,
        "| method | deterministic script, no AI; rules in the script header |",
        "| blobs_replaced | %d |" % COUNT["blobs"],
        "| redactions | %d |" % COUNT["redactions"],
        "| ai_labelled_user_lines | %d compaction summaries, %d meta |" % (COUNT["compact_summary_ai"], COUNT["meta_ai"]),
    ] + (["| injected_harness_user_role | %d |" % COUNT.get("injected_harness", 0)] if harness == "codex" else []) + [
        "",
        "Layer 0 (the raw file%s above) is the evidence. If this record and Layer 0 disagree, Layer 0 wins." % ("s" if multi else ""),
        "",
    ]
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(head) + "\n" + "\n".join(body))
    print(json.dumps(COUNT, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.stderr.write(__doc__)
        sys.exit(2)
    main(sys.argv[1:-1], sys.argv[-1])
