#!/usr/bin/env python3
"""
validate_inputs.py  (stdlib only; no jsonschema package needed)

Checks every line of a list_inputs.py JSONL file against ../schemas/inputs.schema.json.
Supported schema keywords: type, enum, required, additionalProperties false, pattern, minimum, items.
That is every keyword the schema uses. Exit 0 and "VALID <n> rows" when all rows pass, else exit 1
and one line per problem.

Usage: python3 validate_inputs.py <rows.jsonl> [<schema.json>]
"""
import json, os, re, sys

TYPES = {"string": str, "integer": int, "boolean": bool, "array": list, "object": dict}


def check(v, sch, path, errs):
    t = sch.get("type")
    if t:
        ok = isinstance(v, TYPES[t]) and not (t == "integer" and isinstance(v, bool))
        if not ok:
            errs.append("%s: expected %s, got %s" % (path, t, type(v).__name__)); return
    if "enum" in sch and v not in sch["enum"]:
        errs.append("%s: %r not in enum" % (path, v))
    if "pattern" in sch and isinstance(v, str) and not re.search(sch["pattern"], v):
        errs.append("%s: does not match %s" % (path, sch["pattern"]))
    if "minimum" in sch and isinstance(v, int) and v < sch["minimum"]:
        errs.append("%s: below minimum %s" % (path, sch["minimum"]))
    if isinstance(v, dict):
        for k in sch.get("required", []):
            if k not in v:
                errs.append("%s: missing required %s" % (path, k))
        props = sch.get("properties", {})
        for k, x in v.items():
            if k in props:
                check(x, props[k], "%s.%s" % (path, k), errs)
            elif sch.get("additionalProperties") is False:
                errs.append("%s: unexpected field %s" % (path, k))
    if isinstance(v, list) and "items" in sch:
        for i, x in enumerate(v):
            check(x, sch["items"], "%s[%d]" % (path, i), errs)


def main(argv):
    if not argv:
        sys.stderr.write(__doc__); return 2
    schema_path = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "schemas", "inputs.schema.json")
    sch = json.load(open(schema_path, encoding="utf-8"))
    errs, n = [], 0
    for i, ln in enumerate(open(argv[0], encoding="utf-8"), 1):
        if not ln.strip():
            continue
        n += 1
        try:
            o = json.loads(ln)
        except Exception as e:
            errs.append("line %d: not JSON (%s)" % (i, e)); continue
        check(o, sch, "line %d" % i, errs)
    for e in errs:
        print(e)
    print(("VALID %d rows" % n) if not errs else ("INVALID: %d problem(s) in %d rows" % (len(errs), n)))
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
