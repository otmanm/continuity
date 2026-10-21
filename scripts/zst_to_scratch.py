#!/usr/bin/env python3
"""zst_to_scratch.py v1.0.0 (continuity v0.1.4 zst source, 2026-10-19)

Make compressed Codex rollouts readable by the other continuity scripts
(make_record.py, list_inputs.py, session_metrics.py), which read plain JSONL only.

Why: Codex compresses older rollouts in place as rollout-*.jsonl.zst. In one real
installation checked on 2026-10-19, about nine rollouts in ten were compressed, and every
indexed thread still had a rollout file on disk.

What it does, read only on the sources:
  1. collects the given files, or every rollout of a thread id (--thread), including
     fork files whose name carries that id, from ~/.codex/sessions and ~/.codex/archived_sessions;
  2. writes a plain copy of each into --out (zstd -d for .zst, byte copy for .jsonl);
  3. records source and output SHA-256, bytes and line count in <out>/manifest.json;
  4. prints the output paths in chronological order (rollout file names start with the
     timestamp), then one line `ARGS: ...` ready to paste after another script name.

It refuses an --out folder inside ~/.codex or ~/.claude/projects, never writes beside a
source, and never overwrites an existing output file.

Usage:
  python3 zst_to_scratch.py --out <scratch dir> --thread <thread id or prefix>
  python3 zst_to_scratch.py --out <scratch dir> <file.jsonl.zst> [<file.jsonl> ...]
Requires: the zstd command (Homebrew zstd); no Python packages.
"""
import argparse
import glob
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys

VERSION = "1.0.0"
HOME = os.path.expanduser("~")
CODEX_ROOTS = [os.path.join(HOME, ".codex", "sessions"), os.path.join(HOME, ".codex", "archived_sessions")]
FORBIDDEN_OUT = [os.path.join(HOME, ".codex"), os.path.join(HOME, ".claude", "projects")]


def forbidden_root(path):
    """Return the protected root that contains path, or None. Pure check, no I/O beyond realpath."""
    p = os.path.realpath(os.path.expanduser(path))
    for bad in FORBIDDEN_OUT:
        bad = os.path.realpath(bad)
        if p == bad or p.startswith(bad + os.sep):
            return bad
    return None


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def count_lines(path):
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def find_thread(prefix):
    hits = []
    for root in CODEX_ROOTS:
        for p in glob.glob(os.path.join(root, "**", "rollout-*.jsonl*"), recursive=True):
            name = os.path.basename(p)
            if name.startswith("._"):
                continue
            if prefix in name:
                hits.append(p)
    return hits


def plain_name(src):
    name = os.path.basename(src)
    return name[:-4] if name.endswith(".zst") else name


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="scratch folder for the plain copies")
    ap.add_argument("--thread", help="thread id or prefix; collects every rollout whose file name carries it")
    ap.add_argument("files", nargs="*", help="rollout files (.jsonl or .jsonl.zst)")
    a = ap.parse_args()

    out = os.path.realpath(a.out)
    bad = forbidden_root(out)
    if bad:
        sys.exit("REFUSED: --out is inside %s; use a scratch folder" % bad)

    srcs = list(a.files)
    if a.thread:
        srcs += find_thread(a.thread)
    srcs = sorted(set(os.path.realpath(s) for s in srcs), key=lambda p: os.path.basename(p))
    if not srcs:
        sys.exit("NO SOURCES: no file given and no rollout matches --thread")
    for s in srcs:
        if not os.path.isfile(s):
            sys.exit("MISSING: %s" % s)
        if not (s.endswith(".jsonl") or s.endswith(".jsonl.zst")):
            sys.exit("NOT A ROLLOUT: %s" % s)
    if any(s.endswith(".zst") for s in srcs) and not shutil.which("zstd"):
        sys.exit("zstd command not found; install it or pass plain .jsonl files")

    os.makedirs(out, exist_ok=True)
    rows, outs = [], []
    for s in srcs:
        dst = os.path.join(out, plain_name(s))
        if os.path.exists(dst):
            sys.exit("EXISTS, not overwritten: %s" % dst)
        if s.endswith(".zst"):
            with open(dst, "wb") as f:
                r = subprocess.run(["zstd", "-q", "-d", "-c", s], stdout=f)
            if r.returncode != 0:
                os.remove(dst)
                sys.exit("zstd failed (%d) on %s" % (r.returncode, s))
        else:
            shutil.copyfile(s, dst)
        rows.append({
            "source": s,
            "source_sha256": sha256(s),
            "compressed": s.endswith(".zst"),
            "output": dst,
            "output_sha256": sha256(dst),
            "output_bytes": os.path.getsize(dst),
            "output_lines": count_lines(dst),
        })
        outs.append(dst)

    manifest = os.path.join(out, "manifest.json")
    if os.path.exists(manifest):
        manifest = os.path.join(out, "manifest.%d.json" % len(glob.glob(os.path.join(out, "manifest*.json"))))
    with open(manifest, "w") as f:
        json.dump({"script": "zst_to_scratch.py", "version": VERSION, "thread": a.thread, "files": rows}, f, indent=2)

    for p in outs:
        print(p)
    print("MANIFEST: %s" % manifest)
    print("ARGS: %s" % " ".join(shlex.quote(p) for p in outs))


if __name__ == "__main__":
    main()
