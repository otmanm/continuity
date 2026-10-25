#!/usr/bin/env python3
"""
session_metrics.py  (Layer 0 counters: deterministic, no AI)

Reads Layer 0 session files (Claude Code JSONL, Codex rollout JSONL) and writes one CSV row
per session file. Same input bytes + same script version + same --run-at = same output bytes.

Rules (v1.1.0):
  1. Standard library only. No network. No randomness. The clock is an input (--run-at).
  2. Never writes to an input file; open(..., "rb") only. Run it on copies.
  3. Tokens are counted ONCE PER API RESPONSE: Claude by message.id (the same usage is repeated
     on every line of one message; the per field maximum is kept), Codex by response_id of
     token_usage_record (fallback: token_count events, repeated totals skipped).
  4. Files that share message uuids (Claude) or a thread id (Codex) form one conversation_group.
     Inside a group, files are processed oldest first and each later file counts only the lines,
     messages and responses the earlier files did not already contain. Summing a group's rows
     gives the conversation total with nothing counted twice.
  5. Any value the file cannot support is the literal UNKNOWN, never a guess.
  6. Every string cell passes through the same fixed secret regexes as make_record.py v1.0.0.
  7. (1.1.0) A user line or queued command that starts with <command-name> or <command-message>
     (a slash command such as /model) is counted in slash_commands, never in user_messages.

Usage: python3 session_metrics.py --run-at <ISO time> --out metrics.csv <file.jsonl> [...]
Method per column: the comments beside each count in this script.
"""
import argparse, collections, csv, datetime, hashlib, io, json, os, re, sys

VERSION = "1.1.0"  # 1.1.0 (2026-10-06): D2 slash command lines leave user_messages, new column slash_commands
# 1.0.1: queued commands from subagents (origin.kind "peer") no longer count as the human's
U = "UNKNOWN"
SECRETS = [  # identical to make_record.py v1.0.0
    ("anthropic_or_openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}")),
    ("aws_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}")),
]
COLUMNS = ["harness", "session_id", "conversation_group", "source_path", "source_sha256",
           "first_timestamp", "last_timestamp", "wall_clock_seconds", "user_messages",
           "user_messages_mid_turn", "slash_commands", "assistant_messages", "tool_calls_total", "tool_calls_top5",
           "mcp_tool_calls", "input_tokens", "output_tokens", "cache_read_tokens",
           "cache_write_tokens", "raw_tokens_total", "max_context_per_turn", "hook_blocks",
           "resends_after_block", "approval_words_typed", "questions_to_human",
           "loaded_skills_count", "mcp_tools_count", "script_version", "run_at"]
APPROVAL_EXACT = {"go", "apply", "approve", "approved", "go ahead"}
CLAUDE_NOT_HUMAN = ("<local-command-stdout>", "<local-command-caveat>", "<local-command-stderr>",
                    "[Request interrupted by user", "<system-reminder>", "<task-notification>",
                    "<agent-message")
SLASH_COMMAND = ("<command-name>", "<command-message>")  # 1.1.0: settings commands, not messages


def sha(b):
    return hashlib.sha256(b).hexdigest()


def redact(s):
    s = str(s)
    for kind, rx in SECRETS:
        s = rx.sub(lambda m, kind=kind: "[REDACTED:%s:%s]" % (kind, sha(m.group(0).encode())[:8]), s)
    return s


def load(path):
    raw = open(path, "rb").read()
    recs = []
    for ln in raw.split(b"\n"):
        if not ln.strip():
            continue
        try:
            o = json.loads(ln.decode("utf-8"))
        except Exception:
            continue
        if isinstance(o, dict):
            recs.append(o)
    return raw, recs


def harness_of(path, recs):
    if os.path.basename(path).startswith("rollout-") or any(r.get("type") == "session_meta" for r in recs[:5]):
        return "codex"
    return "claude"


def text_blocks(content):
    if isinstance(content, str):
        return [content]
    out = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") in ("text", "input_text", "output_text") and isinstance(b.get("text"), str):
            out.append(b["text"])
    return out


def is_approval(text):
    t = text.strip()
    return t.lower() in APPROVAL_EXACT or t.startswith("APPROVE-")


def parse_ts(s):
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def top5(counter):
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return ";".join("%s:%d" % kv for kv in items)


# ---------- Claude Code ----------

def claude_ids(recs):
    return {r["uuid"] for r in recs if isinstance(r.get("uuid"), str)}


def claude_row(recs, seen):
    """seen: dict of sets shared across the files of one group (uuids, message ids, tool ids)."""
    new = [r for r in recs if not (isinstance(r.get("uuid"), str) and r["uuid"] in seen["uuid"])]
    has_attachments = any(r.get("type") == "attachment" for r in recs)
    usage = {}          # message id -> per field max
    msg_order = []      # message ids in file order
    asked = set()       # message ids that call AskUserQuestion
    last_text = {}      # message id -> last text block
    tools = collections.Counter()
    mcp = 0
    users = mid = approvals = blocks = resends = slash = 0
    pending_stop_block = False
    skills = mcp_tools = None
    mcp_live = set()
    for r in new:
        t = r.get("type")
        if t == "attachment":
            a = r.get("attachment") or {}
            at = a.get("type")
            if at == "queued_command" and isinstance(a.get("prompt"), str) and a["prompt"].strip():
                kind = (a.get("origin") or {}).get("kind") if isinstance(a.get("origin"), dict) else None
                if kind is not None and kind != "human":
                    continue  # v1.0.1: subagent reports ("peer") also arrive as queued commands
                if kind is None and a["prompt"].lstrip().startswith(CLAUDE_NOT_HUMAN):
                    continue
                if a["prompt"].lstrip().startswith(SLASH_COMMAND):
                    slash += 1
                    continue
                users += 1
                mid += 1
                approvals += is_approval(a["prompt"])
                pending_stop_block = False
            elif at == "hook_blocking_error":
                blocks += 1
                if a.get("hookEvent") == "Stop":
                    pending_stop_block = True
            elif at == "skill_listing" and skills is None and a.get("isInitial") and isinstance(a.get("skillCount"), int):
                skills = a["skillCount"]
            elif at == "deferred_tools_delta":
                for n in (a.get("addedNames") or []) + (a.get("readdedNames") or []):
                    if str(n).startswith("mcp__"):
                        mcp_live.add(n)
                for n in a.get("removedNames") or []:
                    mcp_live.discard(n)
                mcp_tools = max(mcp_tools or 0, len(mcp_live))
            continue
        if r.get("isSidechain"):
            continue
        msg = r.get("message")
        if not isinstance(msg, dict):
            continue
        if t == "user":
            if r.get("isMeta") or r.get("isCompactSummary") or "toolUseResult" in r:
                continue
            texts = [x for x in text_blocks(msg.get("content")) if x.strip()]
            if not texts or texts[0].lstrip().startswith(CLAUDE_NOT_HUMAN):
                continue
            if texts[0].lstrip().startswith(SLASH_COMMAND):
                slash += 1
                continue
            users += 1
            approvals += is_approval("\n".join(texts))
            pending_stop_block = False
        elif t == "assistant":
            mid_ = msg.get("id")
            if not isinstance(mid_, str) or msg.get("model") == "<synthetic>":
                continue
            if mid_ in seen["msg"]:
                continue
            if mid_ not in usage:
                usage[mid_] = {}
                msg_order.append(mid_)
            u = msg.get("usage") or {}
            for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                v = u.get(k)
                if isinstance(v, int):
                    usage[mid_][k] = max(usage[mid_].get(k, 0), v)
            for b in msg.get("content") or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use":
                    tid = b.get("id")
                    if isinstance(tid, str):
                        if tid in seen["tool"]:
                            continue
                        seen["tool"].add(tid)
                    name = str(b.get("name"))
                    tools[name] += 1
                    mcp += name.startswith("mcp__")
                    if name == "AskUserQuestion":
                        asked.add(mid_)
                elif b.get("type") == "text" and isinstance(b.get("text"), str) and b["text"].strip():
                    last_text[mid_] = b["text"]
                    if pending_stop_block:
                        resends += 1
                        pending_stop_block = False
    for m in msg_order:
        seen["msg"].add(m)
    for r in new:
        if isinstance(r.get("uuid"), str):
            seen["uuid"].add(r["uuid"])
    questions = sum(1 for m in msg_order if m in asked or last_text.get(m, "").rstrip().endswith("?"))
    tok = {k: sum(usage[m].get(k, 0) for m in msg_order) for k in
           ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
    has_usage = any(usage[m] for m in msg_order)
    ctx = [usage[m].get("input_tokens", 0) + usage[m].get("cache_read_input_tokens", 0) +
           usage[m].get("cache_creation_input_tokens", 0) for m in msg_order if usage[m]]
    row = {
        "user_messages": users,
        "user_messages_mid_turn": mid if has_attachments else U,
        "slash_commands": slash,
        "assistant_messages": len(msg_order),
        "tool_calls_total": sum(tools.values()),
        "tool_calls_top5": top5(tools),
        "mcp_tool_calls": mcp,
        "input_tokens": tok["input_tokens"] if has_usage else U,
        "output_tokens": tok["output_tokens"] if has_usage else U,
        "cache_read_tokens": tok["cache_read_input_tokens"] if has_usage else U,
        "cache_write_tokens": tok["cache_creation_input_tokens"] if has_usage else U,
        "raw_tokens_total": sum(tok.values()) if has_usage else U,
        "max_context_per_turn": max(ctx) if ctx else U,
        "hook_blocks": blocks if has_attachments else U,
        "resends_after_block": resends if has_attachments else U,
        "approval_words_typed": approvals,
        "questions_to_human": questions,
        "loaded_skills_count": skills if skills is not None else U,
        "mcp_tools_count": mcp_tools if mcp_tools is not None else U,
    }
    session_id = next((r["sessionId"] for r in recs if isinstance(r.get("sessionId"), str)), U)
    return new, session_id, row


# ---------- Codex ----------

def codex_thread(recs):
    for r in recs:
        if r.get("type") == "session_meta":
            p = r.get("payload") or {}
            return p.get("id") or p.get("session_id")
    return None


def codex_row(recs, seen):
    tools = collections.Counter()
    mcp = users = approvals = questions = assistants = 0
    resp = {}
    order = []
    for r in recs:
        p = r.get("payload") or {}
        t, pt = r.get("type"), p.get("type")
        if t == "token_usage_record":
            rid = p.get("response_id")
            u = p.get("usage") or {}
            if isinstance(rid, str) and rid not in seen["msg"] and rid not in resp:
                resp[rid] = u
                order.append(rid)
        elif t == "response_item" and pt in ("function_call", "custom_tool_call"):
            cid = p.get("call_id") or p.get("id")
            if isinstance(cid, str):
                if cid in seen["tool"]:
                    continue
                seen["tool"].add(cid)
            name = (p.get("namespace") + "." if p.get("namespace") else "") + str(p.get("name"))
            tools[name] += 1
            if p.get("name") in ("request_user_input", "request_user_input_async"):
                questions += 1
        elif t == "event_msg" and pt == "item_completed":
            it = p.get("item") or {}
            iid = it.get("id")
            if isinstance(iid, str):
                if iid in seen["item"]:
                    continue
                seen["item"].add(iid)
            if it.get("type") == "UserMessage":
                users += 1
                approvals += is_approval("\n".join(text_blocks(it.get("content"))))
            elif it.get("type") == "AgentMessage":
                assistants += 1
                txt = "\n".join(text_blocks(it.get("content"))) or str(it.get("text", ""))
                questions += txt.rstrip().endswith("?")
            elif it.get("type") == "McpToolCall":
                mcp += 1
                tools["mcp:%s/%s" % (it.get("server"), it.get("tool"))] += 1
    if not order:  # fallback: token_count events, repeated cumulative totals skipped
        prev = None
        for i, r in enumerate(recs):
            p = r.get("payload") or {}
            if r.get("type") == "event_msg" and p.get("type") == "token_count" and isinstance(p.get("info"), dict):
                tot = json.dumps(p["info"].get("total_token_usage"), sort_keys=True)
                if tot == prev or not isinstance(p["info"].get("last_token_usage"), dict):
                    continue
                prev = tot
                key = "token_count:%d" % i
                resp[key] = p["info"]["last_token_usage"]
                order.append(key)
    for k in order:
        seen["msg"].add(k)

    def g(u, k):
        v = u.get(k)
        return v if isinstance(v, int) else 0
    inp = sum(g(resp[k], "input_tokens") - g(resp[k], "cached_input_tokens") for k in order)
    out = sum(g(resp[k], "output_tokens") for k in order)
    cr = sum(g(resp[k], "cached_input_tokens") for k in order)
    cw = sum(g(resp[k], "cache_write_input_tokens") for k in order)
    has = bool(order)
    row = {
        "user_messages": users,
        "user_messages_mid_turn": U,
        "slash_commands": U,  # 1.1.0: Codex rollouts carry no slash command marker
        "assistant_messages": assistants,
        "tool_calls_total": sum(tools.values()),
        "tool_calls_top5": top5(tools),
        "mcp_tool_calls": mcp,
        "input_tokens": inp if has else U,
        "output_tokens": out if has else U,
        "cache_read_tokens": cr if has else U,
        "cache_write_tokens": cw if has else U,
        "raw_tokens_total": inp + out + cr + cw if has else U,
        "max_context_per_turn": max(g(resp[k], "input_tokens") for k in order) if has else U,
        "hook_blocks": U,
        "resends_after_block": U,
        "approval_words_typed": approvals,
        "questions_to_human": questions,
        "loaded_skills_count": U,
        "mcp_tools_count": U,
    }
    return recs, codex_thread(recs) or U, row


# ---------- grouping and main ----------

def groups(files):
    """Union files that share a Claude message uuid or a Codex thread id. Returns path -> group key."""
    parent = {f["path"]: f["path"] for f in files}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    owner = {}
    for f in files:
        keys = f["ids"] if f["harness"] == "claude" else ({"thread:" + f["thread"]} if f["thread"] else set())
        for k in sorted(keys):
            if k in owner:
                a, b = find(owner[k]), find(f["path"])
                if a != b:
                    parent[max(a, b)] = min(a, b)
            else:
                owner[k] = f["path"]
    return {f["path"]: find(f["path"]) for f in files}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-at", required=True, help="ISO time written in run_at; an input so output stays deterministic")
    ap.add_argument("--out", required=True)
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    files = []
    for path in a.files:
        raw, recs = load(path)
        h = harness_of(path, recs)
        stamps = sorted(r["timestamp"] for r in recs if isinstance(r.get("timestamp"), str))
        files.append({"path": path, "raw": raw, "recs": recs, "harness": h,
                      "ids": claude_ids(recs) if h == "claude" else set(),
                      "thread": codex_thread(recs) if h == "codex" else None,
                      "first": stamps[0] if stamps else ""})
    gmap = groups(files)
    by_group = collections.defaultdict(list)
    for f in files:
        by_group[gmap[f["path"]]].append(f)
    rows = []
    for gkey in sorted(by_group):
        members = sorted(by_group[gkey], key=lambda f: (f["first"], f["path"]))
        seen = {"uuid": set(), "msg": set(), "tool": set(), "item": set()}
        group_id = None
        for f in members:
            fn = claude_row if f["harness"] == "claude" else codex_row
            counted, sid, row = fn(f["recs"], seen)
            if group_id is None:
                group_id = sid
            if f["harness"] == "claude" and not f["ids"]:
                group_id_cell = U
            else:
                group_id_cell = group_id
            stamps = sorted(r["timestamp"] for r in counted if isinstance(r.get("timestamp"), str))
            t0, t1 = (stamps[0], stamps[-1]) if stamps else (U, U)
            d0, d1 = parse_ts(t0) if stamps else None, parse_ts(t1) if stamps else None
            row.update({
                "harness": f["harness"], "session_id": sid, "conversation_group": group_id_cell,
                "source_path": f["path"], "source_sha256": sha(f["raw"]),
                "first_timestamp": t0, "last_timestamp": t1,
                "wall_clock_seconds": int((d1 - d0).total_seconds()) if d0 and d1 else U,
                "script_version": VERSION, "run_at": a.run_at,
            })
            rows.append(row)
    rows.sort(key=lambda r: (r["harness"], str(r["first_timestamp"]), r["source_path"]))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNS)
    for r in rows:
        w.writerow([redact(r[c]) for c in COLUMNS])
    with open(a.out, "w", encoding="utf-8", newline="") as fh:
        fh.write(buf.getvalue())
    print(json.dumps({"rows": len(rows), "groups": len(by_group), "script_version": VERSION}, sort_keys=True))


if __name__ == "__main__":
    main()
