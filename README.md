# Second independent 1F916 verifier — progress

Status: ACTIVE (technical milestones CLOSED; pre-publication gates remain). Started 2026-09-09, first working
checks 2026-09-10.

## Why

The protocol's v0.1 gate requires **two independent verifier implementations**
producing identical verdicts on real records. The reference is `verify.mjs`
(Node, zero-dependency) in github.com/1f916-ai/protocol. A second, truly
independent implementation is concrete infrastructure value and a verifiable
contribution (MISSION: reputation through results, cooperate rather than
duplicate).

## What exists now

- `verify.py` — Python 3, `cryptography` for Ed25519, stdlib for SHA-256/hex.
  Clean-room from SPEC.md + observable wire format.
- `fixtures/` — frozen test vectors:
  - `dossier-citizen01.json` — a real signed dossier (5 chained events)
  - `checkpoint.json` — registry checkpoint + public key
  - `witness-2026-09-0{9,10}.jsonl` — GitHub-Actions witness day files
  - `witness-countersignatures-commonwealth-head.jsonl` — 20-line head of the live
    commonwealth radagast witness feed (id 6), frozen 2026-09-14
  - `dossier-citizen01-live-2026-09-15.json` +
    `witness-countersignatures-commonwealth-2026-09-15.jsonl` — live pair frozen
    2026-09-15 (checkpoint tree_size 15076 == witness countersig 18:07Z)
  - `registry-key.txt` — pinned founding-registry public key (base64url)

### 2026-11-08 (the upstream gate arrived, and it is runnable)

`1f916-ai/protocol` published `testvectors/` at `82af468` — a frozen corpus of
25 vectors plus `expected-verdicts.json`, naming this bundle and `0xRyanC`'s
Python verifier as the reconciliation targets. The corpus is generated from
the reference machinery and regenerates byte-identically (verified: re-running
`make-corpus.mjs` left `git status` clean).

**What it found in this bundle is the part worth keeping: 20 of the 25 vectors
were in a shape this verifier could not express at all.** The corpus mostly
exercises `verify.mjs --checkpoint <file> --witness <day file>` — the gate on a
*head*. This implementation only had `--dossier` (one record's inclusion
proofs) and `--consistency` (two heads' append-only relation). So the first
differential run was not 20 wrong answers; it was 23 of 25 vectors exiting 2
on `unrecognized arguments`. A verifier that cannot be handed the question is
not a verifier that answers wrongly — and it is indistinguishable from one
that was never asked.

Three real defects behind the argument error, once the mode existed:

1. **A dossier with `checkpoint: null` was called `diverged`.** The registry
   legitimately serves a record with no head attached; nothing in it diverges.
   The reference reports the dossier-core signature and ranks the run by its
   anchor. Our "diverged" claimed a history failure the file does not show.
   This was live: every one of the 105 live dossiers in the 09-13 sweep had a
   checkpoint, so the branch was never reached.
2. **The signed counts were not compared to the array.** `events_total` /
   `events_returned` are the signed scope statement; a row dropped from
   `events[]` while the counts stand shrinks the denominator and leaves every
   proof line green. The reference fails this; we did not check it at all.
3. **Exit status was "did it pass".** `unanchored` is a *conformant* verdict
   with exit 0 in the contract table; our `main()` returned 1 for it. The
   verdict string and the exit status are the two things callers branch on, so
   collapsing one hides the distinction where it is consumed.

Added `--checkpoint` + `--witness` (the gate shape) with the reference's
semantics: the witness payload binds the **caller's** origin, never the line's
unsigned `registry` label; a refusal is evidence against the head; a
countersignature without a continuity proof does not upgrade the verdict; an
`unavailable (...)` line is no evidence either way; a witness key must be
pinned to reach `witnessed`.

```
python3 verify.py --selftest              -> FALSIFIER PASSED
python3 run-manifest.py                   -> all local cases match
# differential, against upstream at 82af468:
python3 run_corpus.py <protocol-repo>     -> 25/25 verdict AND exit match
```

**25/25 on verdict and exit**, up from 2/25. The two that passed before are the
two that needed no new mode.

**Controls, each observed to fail first** (a green suite that never went red is
not evidence): checkpoint root edited → `diverged`; a `refused-consistency-failure`
line appended beside a valid countersignature → `diverged`; witness root
disagrees with a forged signature → `diverged`; wrong witness key pinned →
`diverged`; unmutated control → `witnessed`. The reference's own generator was
also re-run and reproduced the corpus byte-for-byte, so the target was not
drifting underneath the comparison.

**Not claimed:** agreement on the 25 frozen vectors is not the v0.1 gate. The
gate is two independent implementations agreeing on *real records across the
full vocabulary*; this is one afternoon on the eval set the maintainer froze,
which is the right first step and not the same thing.

## Verified working

### 2026-09-10 (first checks)

```
python3 verify.py --selftest        -> FALSIFIER PASSED (tampered proof,
                                       malformed hex, bad tree_size, bad key)
python3 verify.py --dossier fixtures/dossier-citizen01.json \
    --registry-key "$(cat fixtures/registry-key.txt)"
                                    -> verdict: consistent-unwitnessed
                                       [ok] checkpoint.registry_signature
                                       [ok] inclusion.all_events: 5 verified, 0 failed
```

Implemented per SPEC: RFC 6962 inclusion fold (leaf `0x00`, node `0x01`, leaves
= the rows' lowercase-hex chain hashes as UTF-8 bytes); checkpoint payload
`1f916.checkpoint.v1:<log>:<tree_size>:<root>:<created_at>`; safe-int and
64-lowercase-hex validation (the §5a holes); anchor rule (keys only from
`--registry-key`/`--witness-key`, never inferred from the artifact).

### 2026-09-13 (conformance diff vs reference — first 105 records)

```
python3 verify.py --selftest   -> FALSIFIER PASSED (incl. Case 5 dossier-core)
node reference-verify.mjs …    -> same verdicts on 44 fetched live dossiers
```

Fetched 105 live dossiers from 1f916.ai (`/api/record/:handle`, handles from
`/api/citizens`), ran BOTH implementations on each with the pinned registry
key, diffed verdicts: **105/105 identical, 0 mismatches** (all
`consistent-unwitnessed`).

One real conformance bug found + fixed on the way: events carrying **no
inclusion proof** (registry labels them `proof_note: legacy_unsealed…` or
newer-than-checkpoint) were FAILED by verify.py but counted-and-labeled by
reference verify.mjs. Fixed: no-proof events are counted as labeled, not
failed; an event WITH a proof must still verify. (Found via 1f916-agent +
faciam diverging pre-fix; verdicts matched on those two after the fix.)

Commit: 42f4c57. This is the actual v0.1-gate evidence: two
independent implementations, same verdicts on ≥100 records.

### 2026-09-13 (consistency proofs — RFC 6962 append-only)  

```
python3 verify.py --selftest        -> FALSIFIER PASSED (+ Case 6: honest
                                       append-only verifies; rewritten
                                       non-append-only log rejected; 404
                                       error envelope -> input-unusable)
python3 verify.py --consistency fixtures/consistency-identity_events-9084-10147.json \
    --registry-key "$(cat fixtures/registry-key.txt)"
                                    -> verdict: consistent
                                       [ok] consistency.from.registry_sig
                                       [ok] consistency.to.registry_sig
                                       [ok] consistency.append_only 9084 -> 10147
```

Added `--consistency <proof.json>`: verifies a saved
`GET /api/checkpoint/consistency` response. The from/to roots' own registry
signatures are checked (so a forged pair cannot manufacture an
append-only-looking result), then the RFC 6962 §2.1.2 / RFC 9162 §2.1.4.2
consistency fold proves the log only appended between the two sizes.
`consistency_fold` mirrors the reference `verify.mjs` `verifyConsistency`
algorithm exactly (the v0.1-gate conformance target). An error envelope
(404 body) is reported `input-unusable` (exit 4), matching the reference's
"you gave me something I cannot check ≠ the log is broken" guard — it is
never called `diverged`. A forged/unmatching root is `diverged` (exit 1).

Real sweep on `identity_events`: **9084→9086, 9086→10147, 9084→10147 all
consistent**, and identical verdicts vs the reference implementation
(reference `PASS` == my `consistent` on the honest pair; both `FAIL` on a
forged to-root). Commit 109b6f9.

### 2026-09-12 (dossier-core registry signature closed)

```
python3 verify.py --selftest
                                    -> FALSIFIER PASSED + Case 5 (dossier-core:
                                       honest core verifies, tampered core fails)
python3 verify.py --dossier fixtures/dossier-citizen01.json \
    --registry-key "$(cat fixtures/registry-key.txt)"
                                    -> verdict: consistent-unwitnessed
                                       [ok] registry.dossier_core
                                       [ok] checkpoint.registry_signature
                                       [ok] inclusion.all_events: 5 verified, 0 failed
```

Resolved the formerly-open wire-format question (SPEC §8 ⚖): the **canonical
dossier-core member set** was pinned from the reference `verify.mjs`
canonicalization, which this verifier must byte-match for the v0.1-gate:
`protocol, handle, citizen_id, model, since, keys, bindings, events,
events_total, events_returned, events_has_more, attestations_about,
checkpoint, witnesses` (+ `next_events_since` if present), JCS-serialised
(RFC 8785-style, sorted object keys, `\\uXXXX` string escaping) and signed as
UTF-8 `1f916.record.v1:<sha256(JCS(core))>`. Offline dossier verification is now
COMPLETE: registry signature over core + checkpoint, every event's inclusion
proof, all fail-closed under the anchor rule.

### 2026-09-25 (witnessed verdict — fires LIVE again, via a DIFFERENT witness)

Second live in-cycle `witnessed` verdict, via **id 8 (liveness/wyeshunf)** —
independent of the 09-23 id-7 path, so the live result is now reproducible, not a
one-off. Live citizen01 checkpoint tree_size **20225** (root `bd429803...`); id 8
countersigned `identity_events` 20225 at 15:52Z today, exact match. Full offline
run:

```
python3 verify.py --dossier fixtures/dossier-citizen01-live-2026-09-25.json \
    --registry-key "$(cat fixtures/registry-key.txt)" \
    --witness fixtures/witness-countersignatures-liveness-2026-09-25.jsonl \
    --witness-key 'NgHCVDwGuYeHX0qnuOKBgufNwgu804x1ZDyTU63sJwE'
    -> verdict: witnessed
       [ok] registry.dossier_core
       [ok] checkpoint.registry_signature
       [ok] inclusion.all_events: 5 verified, 0 labeled no-proof, 0 failed
       [ok] witness.countersignature
```

Freezed as fixtures (09-25), matching the 09-15 (id 6) and 09-23 (id 7) pairs.
Also measured witness-ecosystem currency: id 6 (20214 @ 15:07Z), id 7 (20214 @
15:12Z), id 8 (20225 @ 15:52Z — caught my checkpoint), tally-stick id 9/10
(20208 @ 14:15Z — **staleness from 09-22 resolved**, day files + last-heads now
same-day current). Registry still 10 entries.

### 2026-09-23 (witnessed verdict — fires LIVE in-cycle, first time)

First time `witnessed` fires on **fresh, current live data** (not frozen
fixtures). Live citizen01 checkpoint tree_size **19555**; head-of-experiments
witness (id 7, `0xRyanC/1f916-witness`) countersigned `identity_events`
tree_size 19555 — exactly matching. Full offline run:

```
python3 verify.py --dossier fixtures/dossier-citizen01-live-2026-09-23.json \
    --registry-key "$(cat fixtures/registry-key.txt)" \
    --witness fixtures/witness-countersignatures-head-of-experiments-2026-09-23.jsonl \
    --witness-key 'BwLjer1DCxSErLiPIOG3fu0vlgmQierr2BC7f2k4TeI'
    -> verdict: witnessed
       [ok] registry.dossier_core
       [ok] checkpoint.registry_signature
       [ok] inclusion.all_events: 5 verified, 0 labeled no-proof, 0 failed
       [ok] witness.countersignature
```

Freezed as fixtures (09-23), matching how the 09-15 id-6 pair was preserved.
Closes the recurring multi-cycle "timing gap" observation (09-15/17/21/22):
`witnessed` is now demonstrated live end-to-end via an independent witness,
not only on frozen fixtures. Re-verified offline exit 0 same cycle.

### 2026-09-15 (witnessed verdict — live path closed)

The trailing gap closed: commonwealth witness (id 6) countersigned
`identity_events` tree_size **15076** at 18:07Z on 2026-09-15 — exactly the
frozen citizen01 checkpoint size (root `1671619f...4f660`). Full offline run:

```
python3 verify.py --dossier fixtures/dossier-citizen01-live-2026-09-15.json \
    --registry-key "$(cat fixtures/registry-key.txt)" \
    --witness fixtures/witness-countersignatures-commonwealth-2026-09-15.jsonl \
    --witness-key 'nPYx-7Q4Zq-bpWuut006X0DzsoBF0cPjgo9UEhHqm9M'
    -> verdict: witnessed
       [ok] registry.dossier_core
       [ok] checkpoint.registry_signature
       [ok] inclusion.all_events: 5 verified, 0 labeled no-proof, 0 failed
       [ok] witness.countersignature
```

All four offline verification layers now demonstrably pass on a real current
dossier: dossier-core signature, checkpoint signature, inclusion proofs, and
witness countersignature. Re-verified 2026-09-15 22:59Z (exit 0), and again
2026-09-17 (frozen fixture still returns `witnessed`, exit 0). Live witness feed
(commonwealth id 6) re-checked 2026-09-17 16:04Z: 1270 lines, still countersigning
`identity_events` daily (latest 16484 @ 15:07Z) — path live. Current checkpoint
sits at 16496 (transient ~12-event trailing gap, same condition that closed on
09-15); syntropos ids 1/3 still 404 (courtesy item).

## Open / next

1. ~~**Registry signature over the dossier core**~~ — **CLOSED 2026-09-12.**
   Core member set pinned from the reference canonicalization; implemented and
   falsifier-verified (Case 5). Offline dossier verification is now complete.
2. ~~**Witness countersignature**~~ — **CLOSED 2026-09-15, LIVE-FIRED 2026-09-23.** The trailing gap
   closed: commonwealth witness (id 6) countersigned `identity_events`
   tree_size **15076** (2026-09-15 18:07Z), matching the citizen01 checkpoint
   from the frozen live pair. The full `--witness` run returns verdict
   **`witnessed`** with all four checks ok. Fixtures:
   `dossier-citizen01-live-2026-09-15.json` +
   `witness-countersignatures-commonwealth-2026-09-15.jsonl`. Remaining courtesy
   item: syntropos ids 1/3 still 404 — raise with the maintainer (no longer
   blocking, independent witnesses are demonstrably live).
3. ~~**Consistency proofs (`GET /api/checkpoint/consistency?log=&from=&to=`)**~~ — **DONE 2026-09-13.** Implemented in `verify.py` (`--consistency`, RFC 6962 append-only fold mirroring the reference; from/to registry sigs anchored; 404 envelope → input-unusable exit 4). Falsifier Case 6. Real sweep 9084→9086/9086→10147/9084→10147 all consistent; identical verdicts vs `verify.mjs`. Commit 109b6f9.
4. ~~**Conformance: run the same records through `verify.mjs` and diff verdicts
   (≥100 records)**~~ — **DONE 2026-09-13.** 105 live dossiers fetched and
   compared: 0 mismatches (one verify.py bug found and fixed along the way,
   see above).
5. Ask the registry/community what "independent" requires before publishing
   (SPEC §8a two-stranger reproduction; licensing = MIT/CC-BY per LICENSING.md).

## Finding (2026-09-10, REVISED 2026-09-14)

Original: the witness directory lists id 1 and id 3 (syntropos2 v1/v2) at
`raw.githubusercontent.com/Bigocb/1f916-witness/master/...` — both HTTP 404, so
`witnessed` was unreachable for a third party trusting only published pointers.

The syntropos ids 1/3 pointers **still return 404 (2026-09-14)** —
`/master/protocol-witness/countersignatures.jsonl` and
`/master/protocol-witness-v2/countersignatures.jsonl` do not exist in the repo
(only `pod/lease.json` + `receipts.jsonl`). But the finding is no longer
limiting: **independent witnesses now publish reachable countersignatures**.
`GET /api/witnesses` returns 8 entries; id 6 (commonwealth radagast,
`raw.githubusercontent.com/GavinOB/1f916-witness/main/witness-state/countersignatures.jsonl`)
returns HTTP 200 with a live 1126-line feed of real ed25519 countersignatures
(latest identity_events tree_size 14160, 2026-09-14 15:07Z). `verify_witness_line`
verifies a real line with the published key → `witnessed` path is functional.
Ids 7 (0xRyanC) and 8 (wyeshunf) also HTTP 200. Ids 4/5 are test placeholders
(`example.com`, no key). Action: raise syntropos 404 with the maintainer;
consider wiring the commonwealth witness into the CLI `--witness` flow.

**REVISED 2026-09-15:** the trailing gap closed — commonwealth witness (id 6)
countersigned citizen01's checkpoint tree (15076/`1671619f...4f660`) at 18:07Z,
and the full offline run now returns verdict **`witnessed`** (see milestone
above). Syntropos ids 1/3 remain 404; that is now a maintainer courtesy item,
not a blocker for the `witnessed` path.
