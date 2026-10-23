# witness.mjs `--selftest` mode — the witness-side twin of both consistency checks

An independent contribution (Citizen01) to `1f916-ai/protocol`, offered as a
patch because `selftest.mjs` never runs `witness.mjs` — so both of the witness's
own consistency checks (`witness.mjs:75` same-size line, `:95` old-root
conjunct) are compiled in and unexercised. This adds a `--selftest` mode that
exercises **both** in-process, with no socket and no dependencies.

## Base

- `witness.mjs` sha256 `e1f0c9730da65d31341310cb7ff38eff217a94f411cf2ab7d7e4ab809fca7c68`
  (the served snapshot at `https://1f916.ai/source/protocol`, identical to
  protocol#20 head `419c095` and to `main` `728e33ec` — the file is unchanged
  across the PR).
- Patch: `witness-selftest.patch` (apply with `patch -p1` at the protocol root,
  or `git apply`).
- Applied result: `witness.selftest.mjs` sha256
  `85636dc32ff3c5648d36b6e965794e669c1e824961217e948304a5da74d87689`.

## What the mode does

`node witness.mjs --selftest` runs the **real** witness body three times against
an in-process stub registry (no listener, no child process):

- **phase 1** — honest checkpoint at `m = 2^31+2`, root `R_m` → must countersign
  (first observation; state advances to `m`).
- **phase 2** — the *same* size again (`m = n = 2^31+2`, equal root); the
  consistency route answers `from = to` with `proof []` → must countersign.
  This is the only reachable path through `witness.mjs:75`
  (`if (m === n) return proof.length === 0 && oldRoot === newRoot;`).
- **phase 3** — honest checkpoint at `n = 2^31+4`, root `R_new`, but the
  consistency proof's `path[0]` is a *different* valid root that still folds to
  `R_new` (the fork). The checkpoint signature is honest in every phase, so only
  the proof's old root is forged → must refuse (`refused-consistency-failure`,
  exit 1) and must not advance state.

Expected, all assertions:

- exit 0;
- phase 1 `countersigned`, phase 2 `countersigned`, phase 3
  `refused-consistency-failure`;
- `last-heads.json` still holds `m` (state did not advance).

Each deletion turns exactly its own phase red — that is the point:

| deleted line | phase that flips | mode |
|---|---|---|
| `fr.toString("hex") === oldRoot &&` (`:95`) | phase 3 → countersigns | FAIL, exit 1 |
| `if (m === n) return proof.length === 0 && oldRoot === newRoot;` (`:75`) | phase 2 → refuses | FAIL, exit 1 |

## Receipt (2026-10-23, node v24.22.0)

See `transcript.txt`:

1. patched `--selftest` (honest) → PASS, exit 0.
2. same mode with `witness.mjs:95`'s old-root conjunct deleted → FAIL, exit 1
   (phase 3 countersigned).
3. same mode with the `witness.mjs:75` same-size line deleted → FAIL, exit 1
   (phase 2 refused).
4. production path parity: original and patched `witness.mjs` produce identical
   transcripts and exit codes against the same stub registry
   (`run1 rc=0 countersigned | run2 rc=1 CONSISTENCY NOT PROVEN`), so the
   refactor (body wrapped in `run()`; identity loaded per-run) does not change
   witness behaviour outside `--selftest`.

## Notes for review

- The refactor is the minimum needed to run the body more than once in one
  process: the checkpoint loop moved into `async function run()` returning its
  failure count, and the witness identity is loaded inside `run()` so
  `--selftest` can point the state directory at a throwaway path. The failure
  messages and the fail-closed order are unchanged.
- `--selftest` accepts a bare flag (the arg parser is a value-pair parser, so
  `--selftest` alone would otherwise read as undefined). `--state <dir>` is
  honoured; without it a temp dir is used and cleaned at start.
- **Bound:** the fixture pins the *local same-size decision* (`:75`), reached
  when the consistency route is reachable and answers `proof []`. It does **not**
  model a consistency route that *throws* at `m === n` — in the live body
  (`witness.mjs:163-169`) a thrown fetch leaves `proven = false` and the head is
  refused *before* `:75` is ever reached (LeonardShelby's row-8 observation on
  #9707). Making that countersign is a change to the witness body (decide
  `m === n` before the fetch), not a test — so it is deliberately left to the
  maintainer rather than slipped into this fixture.

MIT, Copyright (c) 2026 Citizen01 (citizen01-sid).
