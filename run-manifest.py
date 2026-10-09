#!/usr/bin/env python3
"""One-command driver: reproduce every case in expected-verdicts.json and diff.

Exit 0 iff every case matches the recorded expected verdict + exit status.
No network, no state. Requires python3 + `cryptography`.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "expected-verdicts.json")


def main() -> int:
    m = json.load(open(MANIFEST, encoding="utf-8"))
    bad = 0
    for c in m["cases"]:
        r = subprocess.run(["python3", "verify.py"] + c["cmd"],
                           capture_output=True, text=True, cwd=HERE)
        v = None
        for line in r.stdout.splitlines():
            if line.startswith("verdict:"):
                v = line.split(":", 1)[1].strip()
            if "UNUSABLE" in line:
                v = "input-unusable"
        if c["name"] == "selftest":
            v = "FALSIFIER PASSED" if "FALSIFIER PASSED" in r.stdout else v
        ok = (v == c["expected_verdict"] and r.returncode == c["expected_exit"])
        bad += 0 if ok else 1
        print(f"[{'ok' if ok else 'MISMATCH'}] {c['name']}: "
              f"verdict={v!r} exit={r.returncode} (expected {c['expected_verdict']!r}/{c['expected_exit']})")
    print(f"\n{len(m['cases']) - bad}/{len(m['cases'])} cases reproduced.")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
