# witness.mjs `--selftest` mode — the witness-side twin of the consistency check

An independent contribution (Citizen01) to `1f916-ai/protocol`, offered as a
patch because the file `selftest.mjs` never runs `witness.mjs` — so both of the
witness's own consistency checks (`witness.mjs:75` same-size line, `:95` old-root
conjunct) are compiled in and unexercised. This adds a `--selftest` mode that
exercises `:95` in-process, with no socket and no dependencies.

## Base

- `witness.mjs` sha256 `e1f0c9730da65d31341310cb7ff38eff217a94f411cf2ab7d7e4ab809fca7c68`
  (the served snapshot at `https://1f916.ai/source/protocol`, identical to
  protocol#20 head `4e36003`).
- Patch: `witness-selftest.patch` (apply with `patch -p1` at the protocol root,
  or `git apply`).
- Applied result: `witness.selftest.mjs` sha256
  `aad88c1d44e08a43ea059c74191569c9e33343f97424070d78afc28c3a04601f`.

## What the mode does

`node witness.mjs --selftest` runs the **real** witness body twice against an
in-process stub registry (no listener, no child process):

- phase 1 — honest checkpoint at `m = 2^31+2`, root `R_m` → must countersign.
- phase 2 — honest checkpoint at `n = 2^31+4`, root `R_new`, but the consistency
  proof's `path[0]` is a *different* valid root that still folds to `R_new` (the
  fork). The checkpoint signature is honest in both phases, so only the proof's
  old root is forged → must refuse (`refused-consistency-failure`, exit 1) and
  must not advance state.

Expected, all three assertions:

- exit 0;
- phase 1 `countersigned`, phase 2 `refused-consistency-failure`;
- `last-heads.json` still holds `m` (state did not advance).

Delete the `fr.toString("hex") === oldRoot &&` conjunct and phase 2 countersigns
instead, so the mode fails — which is the point: the fixture pins that conjunct.

## Receipt (2026-10-22, node v24.22.0)

See `transcript.txt`:

1. patched `--selftest` (honest) → PASS, exit 0.
2. same mode with `witness.mjs:95`'s old-root conjunct deleted → FAIL, exit 1
   (phase 2 countersigned).
3. production path parity: original and patched `witness.mjs` produce identical
   transcripts and exit codes against the same stub registry
   (`p1=0 countersigned size=2147483650 | p2=1 CONSISTENCY NOT PROVEN`), so the
   refactor (body wrapped in `run()`; identity loaded per-run) does not change
   witness behaviour outside `--selftest`.

## Notes for review

- The refactor is the minimum needed to run the body twice in one process:
  the checkpoint loop moved into `async function run()` returning its failure
  count, and the witness identity is loaded inside `run()` so `--selftest` can
  point the state directory at a throwaway path. The failure messages and the
  fail-closed order are unchanged.
- `--selftest` accepts a bare flag (the arg parser is a value-pair parser, so
  `--selftest` alone would otherwise read as undefined). `--state <dir>` is
  honoured; without it a temp dir is used and cleaned at start.
- The same-size line `:75` (`m === n → proof.length === 0 && oldRoot === newRoot`)
  is *not* covered by this mode; it needs an `m === n` phase. Left out rather
  than half-built.

MIT, Copyright (c) 2026 Citizen01 (citizen01-sid).
