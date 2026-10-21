#!/usr/bin/env python3
"""
locate_quote.py v1.0.0 (deterministic, standard library only)

Purpose: an AI must never type a line number by hand (finding T5b: 18 percent wrong).
Given a record file and a quote, print every line number where the quote appears.

Usage:
  python3 locate_quote.py <record.md> "<quote>"
  python3 locate_quote.py <record.md> --quote-file <file with the quote>

Matching: exact substring on each line first. If the quote spans lines, or has
collapsed whitespace, a second pass matches on whitespace normalized text and
reports the first and last line of each match.
Output: one line per match, "L<first>" or "L<first>-L<last>", then exit 0.
Exit 1 when not found, exit 2 on usage error. No writes, no network.
"""
import re, sys

VERSION = "1.0.0"


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def locate(lines, quote):
    q = quote.rstrip("\n")
    hits = [f"L{i}" for i, ln in enumerate(lines, 1) if q and q in ln]
    if hits:
        return hits
    nq = norm(q)
    if not nq:
        return []
    # whitespace normalized pass over the whole file, mapping char offsets to lines
    buf, owner = [], []
    for i, ln in enumerate(lines, 1):
        for ch in ln + " ":
            buf.append(ch)
            owner.append(i)
    text = "".join(buf)
    # collapse whitespace while keeping the owner map
    ctext, cown, prev_space = [], [], False
    for ch, o in zip(text, owner):
        if ch.isspace():
            if prev_space:
                continue
            ctext.append(" "); cown.append(o); prev_space = True
        else:
            ctext.append(ch); cown.append(o); prev_space = False
    ctext = "".join(ctext)
    out, start = [], 0
    while True:
        k = ctext.find(nq, start)
        if k < 0:
            break
        a, b = cown[k], cown[k + len(nq) - 1]
        out.append(f"L{a}" if a == b else f"L{a}-L{b}")
        start = k + 1
    return out


def main(argv):
    if len(argv) == 3:
        path, quote = argv[1], argv[2]
    elif len(argv) == 4 and argv[2] == "--quote-file":
        path = argv[1]
        with open(argv[3], encoding="utf-8") as f:
            quote = f.read()
    else:
        sys.stderr.write(__doc__)
        return 2
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().split("\n")
    hits = locate(lines, quote)
    if not hits:
        sys.stderr.write("NOT_FOUND\n")
        return 1
    print("\n".join(hits))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
