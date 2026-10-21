#!/usr/bin/env python3
"""
check_example.py: run the scripts on examples/demo-session.jsonl and compare with the known answers.

The demo session is invented. Every line is a known trap:
  L1  the human's opening message, with two prohibitions
  L4  the human picks option A on a decision card
  L5  a background notification (harness text, not the human)
  L6  an interrupt marker (written by the harness)
  L7  an AI compaction summary that falsely says "approved pushing the fix to main"
  L8  hook feedback (meta text, not the human)
  L9  a /model slash command
  L10 the human: "Still no push to main"

A tool that keeps the human's words intact must count 5 human input rows, must NOT count L5, L7 or L8
as the human, and must find both prohibitions of L1. Python standard library only.
Usage: python3 examples/check_example.py     (exit 0 = all checks pass)
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEMO = os.path.join(HERE, "demo-session.jsonl")

EXPECTED_CLASS = {
    1: "human_typed",
    4: "human_card_answer",
    5: "harness_injected",
    6: "interrupt_marker",
    7: "ai_compact_summary",
    8: "ai_meta",
    9: "slash_command",
    10: "human_typed",
}
EXPECTED_ROWS = 5
EXPECTED_PROHIBITIONS = ["Do not push to main.", "Never touch the payments folder."]
HUMAN_CLASSES = {"human_typed", "human_typed_mid_turn", "human_card_answer", "human_card_dismissed"}


def run(args):
    return subprocess.run([sys.executable, "-B"] + args, capture_output=True, text=True, check=True).stdout


def main():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        md, jl = os.path.join(tmp, "inputs.md"), os.path.join(tmp, "inputs.jsonl")
        out = run([os.path.join(ROOT, "scripts", "list_inputs.py"), DEMO, "--md", md, "--jsonl", jl, "--prohibitions"])
        rows = [json.loads(line) for line in open(jl, encoding="utf-8")]
        got = {r["line"]: r["class"] for r in rows}
        for line, cls in EXPECTED_CLASS.items():
            if got.get(line) != cls:
                failures.append("L%d: expected %s, got %s" % (line, cls, got.get(line)))
        if "HUMAN INPUT ROWS: %d" % EXPECTED_ROWS not in out:
            failures.append("expected 'HUMAN INPUT ROWS: %d' in the output" % EXPECTED_ROWS)
        summary = [r for r in rows if r["line"] == 7]
        if summary and summary[0]["class"] in HUMAN_CLASSES:
            failures.append("L7, the AI summary claiming approval, was counted as the human")
        text = open(md, encoding="utf-8").read()
        for p in EXPECTED_PROHIBITIONS:
            if "| %s |" % p not in text:
                failures.append("prohibition not listed: %s" % p)
        out = run([os.path.join(ROOT, "scripts", "validate_inputs.py"), jl])
        if "VALID" not in out:
            failures.append("inputs JSONL failed the schema check")
    for f in failures:
        print("FAIL", f)
    print("ALL %d CHECKS PASS" % (len(EXPECTED_CLASS) + 4) if not failures else "%d FAILED" % len(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
