#!/usr/bin/env python3
"""
check_quotes.py v1.1.0 (deterministic, standard library only)

Purpose: a quote typed by a model can be a paraphrase. Before a checkpoint is final,
drop every table row whose double quoted text is not in the conversation record.

Usage:
  python3 check_quotes.py <draft.md> <record.md>

For every Markdown table row that contains a double quoted string AND a line reference
(L<n>, L<a>-L<b>, or "record L<n>"), each quote is matched with the same function as
locate_quote.py (imported from this folder). The row is kept only if every quote is
found at one of the cited lines. A row with a quote and no line reference is kept
only if the quote is found anywhere in the record. A quote shorter than 4 characters
is kept only if found at a cited line (no citation means removed).
Rows without a quoted string, and all non table text, are copied unchanged.
Writes <draft name>.checked.md beside the draft. Prints counts and each removed quote.
A long quote may be cited in the shortened form  "first 8 words [...] last 8 words"  (v1.1.0,
G9c): the text is split at each "[...]" and every part must be found by the same rule, so a
shortened quote is checked and never deleted just for being shortened. A part shorter than
4 characters is treated like any short quote.
Exit 0 always when it ran; exit 2 on usage error. No network.
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from locate_quote import locate  # same matching as locate_quote.py

VERSION = "1.1.0"  # 1.1.0 (2026-10-06): shortened quotes with [...] are checked part by part
QUOTE = re.compile(r'"([^"\n]+)"')
LINEREF = re.compile(r'\bL(\d+)(?:\s*-\s*L?(\d+))?')


def cited_lines(row):
    out = set()
    for m in LINEREF.finditer(row):
        a = int(m.group(1)); b = int(m.group(2)) if m.group(2) else a
        if b < a:
            a, b = b, a
        out.update(range(a, min(b, a + 200) + 1))
    return out


def hit_ranges(hits):
    for h in hits:
        nums = [int(x) for x in re.findall(r"\d+", h)]
        yield nums[0], nums[-1]


def quote_ok(lines, quote, cited):
    q = quote.replace("\\|", "|")
    if "[...]" in q:
        parts = [x.strip() for x in q.split("[...]") if x.strip()]
        return bool(parts) and all(quote_ok(lines, x, cited) for x in parts)
    hits = locate(lines, q)
    if not hits:
        return False
    if cited:
        return any(any(a <= c <= b for c in cited) for a, b in hit_ranges(hits))
    return len(q) >= 4


def main(argv):
    if len(argv) != 3:
        sys.stderr.write(__doc__)
        return 2
    draft, record = argv[1], argv[2]
    with open(record, encoding="utf-8", errors="replace") as f:
        rlines = f.read().split("\n")
    with open(draft, encoding="utf-8") as f:
        dlines = f.read().split("\n")
    kept_rows, removed = 0, []
    out = []
    for ln in dlines:
        if ln.lstrip().startswith("|"):
            quotes = QUOTE.findall(ln)
            if quotes:
                cited = cited_lines(ln)
                bad = [q for q in quotes if not quote_ok(rlines, q, cited)]
                if bad:
                    removed.append(bad)
                    continue
                kept_rows += 1
        out.append(ln)
    base, ext = os.path.splitext(draft)
    outpath = base + ".checked" + ext
    with open(outpath, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"check_quotes.py v{VERSION}")
    print(f"checked file: {outpath}")
    print(f"kept: {kept_rows} rows with quotes")
    print(f"removed: {len(removed)} rows")
    for bad in removed:
        for q in bad:
            print(f"REMOVED QUOTE: {q}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
