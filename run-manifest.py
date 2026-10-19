#!/usr/bin/env python3
"""One-command driver: reproduce every case in expected-verdicts.json and diff.

Exit 0 iff every case matches the recorded expected verdict + exit status.
No network, no state. Requires python3 + `cryptography`.

It also prints the labeled-vs-derived table the corpus is for: each row's
`label` (this seat's assertion that the expected value follows from SPEC.md
text alone, or is a documented implementer choice) beside the value the
verifier actually derives when run. The label is an assertion; the derived
column is the measurement. Pass `--reference <verify.mjs>` to add the
reference implementation's verdict per row, which is what turns a
`requirement` row whose two seats disagree into a visible spec miss.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "expected-verdicts.json")


def run_case(c, driver=None):
    cmd = ["python3", "verify.py"] + c["cmd"] if driver is None else driver + c["cmd"]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
    v = None
    for line in r.stdout.splitlines():
        if line.startswith("verdict:"):
            v = line.split(":", 1)[1].strip()
        if "UNUSABLE" in line:
            v = "input-unusable"
    if c["name"] == "selftest":
        v = "FALSIFIER PASSED" if "FALSIFIER PASSED" in r.stdout else v
    return v, r.returncode


def main() -> int:
    args = sys.argv[1:]
    reference = None
    if "--reference" in args:
        i = args.index("--reference")
        reference = args[i + 1] if len(args) > i + 1 else None
        if reference and not os.path.exists(reference):
            print(f"[warn] --reference {reference!r} not found; deriving locally only")
            reference = None
    node = None
    if reference:
        node = shutil.which("node")

    m = json.load(open(MANIFEST, encoding="utf-8"))
    bad = 0
    rows = []
    for c in m["cases"]:
        v, rc = run_case(c)
        ok = (v == c["expected_verdict"] and rc == c["expected_exit"])
        bad += 0 if ok else 1
        ref = ""
        if reference and node:
            rv, rrc = run_case(c, driver=[node, reference])
            ref = f"  reference={rv!r}/{rrc}" + ("" if (rv == v and rrc == rc) else "  <-- DIVERGES FROM THIS SEAT")
        lab = c.get("label", "?")
        print(f"[{'ok' if ok else 'MISMATCH'}] {c['name']}  label={lab}: "
              f"derived={v!r} exit={rc} (expected {c['expected_verdict']!r}/{c['expected_exit']}){ref}")
        rows.append({"name": c["name"], "label": lab, "derived_verdict": v,
                     "derived_exit": rc, "expected_verdict": c["expected_verdict"],
                     "expected_exit": c["expected_exit"], "match": ok})
    print(f"\n{len(m['cases']) - bad}/{len(m['cases'])} cases reproduced.")
    print("labeled-vs-derived table (label asserted by this seat; derived = value when run):")
    for r in rows:
        print(f"  {r['label']:17s} {r['name']:36s} derived={r['derived_verdict']}")
    print(json.dumps({"contract": m.get("label_schema", {}).get("contract"),
                      "rows": rows}, indent=2))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
