#!/usr/bin/env python3
"""Run this verifier against the UPSTREAM frozen corpus (two-stranger gate).

    python3 run_corpus.py /path/to/1f916-ai/protocol

The upstream repo carries `testvectors/expected-verdicts.json` and
`testvectors/corpus/<name>/`. For each vector we run this implementation with
the vector's own `args`, then compare BOTH the verdict string and the exit
status. Exit 0 iff every vector matches.

Why both: the verdict string and the exit status are the two things callers
quote and branch on (`CONTRACT.md`). Matching one and not the other is the
defect this driver exists to catch — `unanchored` is a conformant verdict with
exit 0, and "did it pass" is the wrong test for it.

No network. Requires the upstream checkout plus python3 + `cryptography`.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VERIFIER = os.path.join(HERE, "verify.py")


def parse_verdict(stdout: str):
    for line in stdout.splitlines():
        low = line.strip().lower()
        if low.startswith("verdict:"):
            return line.split(":", 1)[1].strip()
        if low.startswith("verdict "):
            return line.split(None, 1)[1].strip()
    return None


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    repo = os.path.abspath(sys.argv[1])
    tv = os.path.join(repo, "testvectors")
    manifest_path = os.path.join(tv, "expected-verdicts.json")
    if not os.path.isfile(manifest_path):
        print(f"error: {manifest_path} not found", file=sys.stderr)
        return 2
    manifest = json.load(open(manifest_path, encoding="utf-8"))

    bad = 0
    total = 0
    for v in manifest["vectors"]:
        base = os.path.join(tv, "corpus", v["name"])
        if v["kind"] == "dossier":
            argv = ["--dossier", os.path.join(base, v["files"]["dossier"])]
        elif v["kind"] == "witness":
            argv = ["--checkpoint", os.path.join(base, v["files"]["checkpoint"]),
                    "--witness", os.path.join(base, v["files"]["witness"])]
        else:
            print(f"SKIP  {v['name']}: unknown kind {v['kind']!r}")
            continue
        argv += list(v.get("args") or [])
        proc = subprocess.run([sys.executable, VERIFIER] + argv,
                              capture_output=True, text=True)
        got = parse_verdict((proc.stdout or "") + (proc.stderr or ""))
        total += 1
        ok = got == v["expected_verdict"] and proc.returncode == v["expected_exit"]
        if ok:
            print(f"PASS  {v['name']}: {got} / exit {proc.returncode}")
        else:
            bad += 1
            print(f"FAIL  {v['name']}: manifest says "
                  f"{v['expected_verdict']} / exit {v['expected_exit']}, "
                  f"got {got} / exit {proc.returncode}")
            for line in ((proc.stdout or "") + (proc.stderr or "")).splitlines():
                if line.strip():
                    print("        " + line[:160])

    print(f"\n{total} vectors, {bad} disagreed. "
          f"spec {manifest.get('spec_version')}, "
          f"pinned {str(manifest.get('pinned_commit'))[:12]}.")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
