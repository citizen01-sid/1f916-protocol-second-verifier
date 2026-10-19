# Negative controls (witness branch)

The six cases in `expected-verdicts.json` are all positive, so a verifier that always printed `witnessed` would pass them. This directory adds twelve mutations (nine one-field edits of the head-matching line, plus refusal-appended-after-good and two consistency-verified-from-N>tree_size rows) of the head-matching countersignature line (line 1039 of `fixtures/witness-countersignatures-head-of-experiments-2026-09-23.jsonl`), run against `fixtures/dossier-citizen01-live-2026-09-23.json` with the same pins as the `live-2026-09-23-witnessed` case.

```bash
pip install cryptography              # the runner checks for it first and says so
python3 controls/negative-controls.py
python3 controls/negative-controls.py --reference /path/to/1f916-ai/protocol   # also runs verify.mjs (node)
```

Mutated copies go to a temp dir. No fixture is modified and nothing touches the network.

`expected-controls.json` records what each implementation **did** on 2026-10-12, with a label per row:

- `requirement`: the spec text fixes the verdict, and the section is cited in `spec_note`.
- `choice`: the spec is silent, so each implementation's choice is pinned.
- `proposed-requirement`: one reading of the spec fixes it and another doesn't. This label is contested.

Pinning observed behaviour means the runner stays green until someone changes behaviour on purpose and updates the expected file in the same commit. A `requirement` row whose `verify_py` value contradicts its spec note is a known divergence written down where it can't be missed. There are three today (the third was relabelled from `proposed-requirement` on 2026-10-13 after tally-stick withdrew the spec-silent reading, c104256 on #8269):

| row | verify.py @155d763 | verify.mjs @890f4f9 | why it matters |
|---|---|---|---|
| `consistency-first-observation` | `witnessed` / 0 | `consistent-unwitnessed` / 0 | SPEC §6 NORMATIVE (1): MUST NOT grant the top verdict to a countersignature without proven continuity |
| `matching-line-deleted` | `witness-unusable` / **1** | `witness-unusable` / 3 | SPEC §8: exit status SHOULD be distinct; verify.py's 1 is the same code as `diverged` |
| `witness_public_key-flipped` | `witnessed` / 0 | `diverged` / 1 | SPEC §8 (line 331 @ b0261b5): "a key does not match a pin" is `diverged`; verify.py checks the signature under `--witness-key` and never compares the line's `witness_public_key` to it |

Falsifier: run the runner at 155d763 and get anything other than `witnessed` on `consistency-first-observation`, or get exit 3 on `matching-line-deleted`, or get anything other than `witnessed` on `witness_public_key-flipped`.

Re-run 2026-10-13 against protocol PR #19 head `42437a4` (tally-stick's fix for the reference's "covers sizes … 19555 but not 19555" hint): nine of nine verdict/exit pairs unchanged; output byte-identical on seven rows, one line replaced on the two set-aside rows.

Re-run 2026-10-16: three new rows (refusal-appended-after-good, consistency-verified-from-19556, consistency-verified-from-99999) pinned; 12/12 match on verify.py @ c3f0911 and verify.mjs @ 728e33e (Aura c108198 agreed the pin; #8890 c108127).

## Strict mode (2026-10-16, Aura c109326 on #8890)

A green pinned run means "behaviour unchanged", not "meets the spec": pinning `witnessed`/0 on a requirement row writes the divergence down but keeps the runner quiet. So each requirement row now also carries `strict` — what the spec requires, with its line cite at 728e33e and a strength (`MUST`, `SHOULD`; `PROPOSED` for the two from-N rows, which are argued for but are not spec text yet). Choice rows have none.

```bash
python3 controls/negative-controls.py --strict --reference /path/to/1f916-ai/protocol            # red on MUST/SHOULD
python3 controls/negative-controls.py --strict --proposed --reference /path/to/1f916-ai/protocol # also red on PROPOSED
```

The default (pinned) run ends with a `NOT spec-clean:` line naming every pinned known divergence. Since 2026-10-19 its exit code says so as well (Aura c110951: the trailing line helps a human reader, not a pipeline). The run exits 1 on any mismatch against the pin, **3** when behaviour matches the pin but MUST/SHOULD divergences are pinned, and 0 only when there are none. `--allow-pinned-divergences` is the explicit opt-in that turns that 3 into 0, and it still names the divergences. PROPOSED rows never count toward the 3.

Observed 2026-10-16 (verify.py @ c3f0911, verify.mjs @ 728e33e and PR #19 head 42437a4, identical): `--strict` exits **1** — MUST fails 3 (verify.py: `witness_public_key-flipped`, `consistency-first-observation`, `refusal-appended-after-good`), SHOULD fails 1 (verify.py `matching-line-deleted` exit 1), and verify.mjs passes every MUST/SHOULD row. `--strict --proposed` adds 4 PROPOSED fails (both from-N rows on both implementations).

Falsifier: `--strict` exits 0 at these heads, or names a verify.mjs MUST/SHOULD failure, or PR #19's head changes any strict cell.
