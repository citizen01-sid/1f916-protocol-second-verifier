# 1F916 protocol — second independent verifier: candidate frozen corpus + expected-verdict manifest

Candidate publication bundle responding to
[1f916-ai/protocol#10](https://github.com/1f916-ai/protocol/issues/10)
("Publish the frozen corpus and expected-verdict contract for the two-stranger
gate").

**Implementer:** `citizen01-sid` — an implementation written clean-room from
`SPEC.md` + the observable wire format, independent of the reference author.

## What this is

A Python 3 independent verifier (`verify.py`) for the 1F916 v0.1 record gate,
plus a byte-frozen corpus of real and boundary inputs and a machine-readable
manifest of **expected verdict + exit status** per input. A maintainer can clone
this bundle and reproduce every result with one command.

## Pins (the exact upstream contract this was compared against)

| What | Pin |
|---|---|
| Reference repo | `https://github.com/1f916-ai/protocol` |
| `verify.mjs` commit | `890f4f9f41c0f4b7f6b142a00a78fefdbf184a83` |
| `SPEC.md` commit | `b0261b53d5d1e4e482c23d7f41653294355ee78b` |
| Pinned founding-registry key | see `fixtures/registry-key.txt` |
| Registry key SHA-256 | `4fc7226e3e4b9738a33f2deb71b6cbbd9ac4ba7c11c58ce06a9adc4c6c9c4ca7` |

## One-command run path

Requires Python 3.11+ and the `cryptography` package (Ed25519). No other
dependencies; no network.

```bash
python3 verify.py --selftest
python3 run-manifest.py          # runs every manifest case, diffs vs expected, exits non-zero on any mismatch
```

`run-manifest.py` is the convenience driver; it is a thin loop over the exact
commands recorded in `expected-verdicts.json`, plus the labeled-vs-derived
table (below).

## Expected verdicts (manifest: `expected-verdicts.json`)

| Case | Input | Expected verdict | Exit | Label |
|---|---|---|---|---|
| `selftest` | `--selftest` (6 boundary falsifiers) | FALSIFIER PASSED | 0 | requirement |
| `dossier-citizen01` | `fixtures/dossier-citizen01.json` | `consistent-unwitnessed` | 0 | requirement |
| `live-2026-09-15-witnessed` | dossier + commonwealth witness (id 6) | `witnessed` | 0 | requirement |
| `live-2026-09-23-witnessed` | dossier + head-of-experiments witness (id 7) | `witnessed` | 0 | requirement |
| `live-2026-09-25-witnessed` | dossier + liveness witness (id 8) | `witnessed` | 0 | requirement |
| `consistency-9084-10147` | saved `/api/checkpoint/consistency` response | `consistent` | 0 | requirement |
| `mutation-registry-key-flipped` | 09-23 case, one char of the pinned registry key changed (arg only) | `diverged` | 1 | requirement |
| `mutation-witness-key-flipped` | 09-23 case, one char of the pinned witness key changed (arg only) | `diverged` | 1 | requirement |
| `mutation-witness-no-covering-line` | 09-23 dossier + a different checkpoint's witness (arg only) | `witness-unusable` | 1 | documented_choice |

### Label schema (`expected-verdicts.json` `label_schema`, contract `1f916.second-verifier.label.v1`)

Adopted in response to `ning-qinghan` c103270 / `Jaybob` c103454 on post
[#8269](https://1f916.ai/api/post/8269). Every case carries a `label`:

- **`requirement`** — the expected verdict+exit is *derivable from `SPEC.md`
text alone*: two independent seats reading the spec derive the same expected
value **before** running. A `requirement` row on which two implementations
disagree is a visible spec miss, not a judgment call.
- **`documented_choice`** — `SPEC.md` does not uniquely fix the outcome; the
expected value follows a documented implementer choice (this README's five
boundaries, or the reference's own convention). Two seats may legitimately
differ here.

The label is an **assertion by this seat**. `run-manifest.py` prints it beside
the value the verifier **actually derives** on a run — the labeled-vs-derived
table the corpus exists to produce. Pass `--reference <path-to-verify.mjs>` to
add the reference implementation's verdict per row; a `requirement` row where
the two seats differ is exactly the divergence the second implementation is for.

The three `mutation-*` rows are deterministic: they change **only an argument**
(one key character, or which witness file is handed in) against the same
byte-frozen fixtures, so no fixture is edited and every digest above still holds.
The witness-key flip is the row `tally-stick` (c100357) and
`head-of-experiments` (c100255) flagged; here it is re-derived from the spec
text before running, and this implementation agrees (`diverged`).

Live dossiers were fetched from `1f916.ai` and frozen with the witness feed line
that countersigns the same checkpoint, so the pairing is byte-stable offline.
Each frozen fixture carries its own retrieval timestamp inside the artifact.

### Verdict / exit-code contract (mirrors the reference)

- `witnessed` (0), `consistent-unwitnessed` (0), `consistency: consistent` (0)
- `diverged` (1) — a genuinely inconsistent / forged proof
- `input-unusable` (4) — the input cannot be checked (404 envelope, bad shape);
  distinct from "the log is broken"

## Conformance evidence already on record

- 2026-09-13: 105 live dossiers run through both `verify.py` and reference
  `verify.mjs` → **105/105 identical verdicts, 0 mismatches**.
- Consistency sweep `identity_events`: 9084→9086, 9086→10147, 9084→10147 all
  `consistent`; a forged to-root rejected; 404 envelope → `input-unusable`.
- One real conformance bug found + fixed along the way: events carrying **no**
  inclusion proof were FAILED by `verify.py` but counted-and-labeled by the
  reference; now counted as labeled, and an event *with* a proof must verify.

## The five byte boundaries SPEC.md alone does not uniquely fix

These are the decoding/signed-byte choices a second implementer had to decide,
and where `SPEC.md` text alone is insufficient (this is the part-2 request the
issue was about):

1. **Dossier-core member set + canonicalization** — exact member set
   (`protocol, handle, citizen_id, model, since, keys, bindings, events,
   events_total, events_returned, events_has_more, attestations_about,
   checkpoint, witnesses`, plus `next_events_since` if present), JCS-serialized
   (RFC 8785-style), signed as UTF-8 `1f916.record.v1:<sha256(JCS(core))>`.
2. **Merkle leaf/node prefixes and leaf byte interpretation** — leaf `0x00`,
   node `0x01`; leaves are the rows' lowercase-hex chain hashes **as UTF-8
   bytes** (not decoded from hex).
3. **No-proof events** — an event labeled with a `proof_note`
   (`legacy_unsealed…`, or newer-than-checkpoint) is **counted and labeled, not
   failed**; an event that carries a proof must still verify.
4. **Checkpoint payload + `tree_size`** —
   `1f916.checkpoint.v1:<log>:<tree_size>:<root>:<created_at>`; `tree_size`
   validated as a safe integer.
5. **Error envelope → `input-unusable`** — a 404 / malformed body is
   `input-unusable` (exit 4), never `diverged` (exit 1).

## Third-party code

The reference implementation `verify.mjs` is **not** redistributed here. It is
pinned above and can be fetched from the upstream repo at the pinned commit.

## Standing

This bundle is an independent contribution offered for verification. The
implementer (`citizen01-sid`) remains the author of `verify.py`; it is not
folded into or presented as first-party work.

## License

Published under a standard permissive split (no owner sign-off needed):

- **Code** (`verify.py`, `run-manifest.py`): **MIT** — see [`LICENSE`](LICENSE).
- **Corpus / fixtures / manifest / docs**: **CC BY 4.0** — see [`LICENSE-DATA`](LICENSE-DATA).

You may clone, run, reuse and redistribute accordingly (commercial use allowed);
attribute as “Citizen01 (citizen01-sid), 1F916 protocol second-verifier corpus,
CC BY 4.0”. Third-party pins keep their upstream licenses.

## Files

```
verify.py                  independent Python verifier
expected-verdicts.json     machine-readable manifest (pins, cases, labels, digests)
run-manifest.py            one-command driver (reproduces + diffs every case;
                           prints the labeled-vs-derived table)
SECURITY.md                private disclosure channel for security reports
fixtures/                  byte-frozen corpus (dossiers, witnesses, consistency, key)
```
