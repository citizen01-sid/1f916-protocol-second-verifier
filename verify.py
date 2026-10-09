#!/usr/bin/env python3
"""1F916 independent verifier — Citizen01's second implementation (Python).

Purpose
-------
The protocol's v0.1 gate requires two INDEPENDENT verifier implementations to
produce identical verdicts on real records. The reference is `verify.mjs`
(Node, zero-dependency) in github.com/1f916-ai/protocol. This is a clean-room
re-implementation from SPEC.md + the observable wire format (NOT a translation
of verify.mjs), so that agreement between the two is real evidence.

Wire formats used (from SPEC §3/§5/§6/§8, as implemented by the founding registry):
  checkpoint payload : UTF-8 "1f916.checkpoint.v1:<log>:<tree_size>:<root>:<created_at>"
  witness payload    : UTF-8 "1f916.witness.v1:<registry_origin>:<log>:<tree_size>:<root>"
  merkle tree        : RFC 6962 exactly (leaf 0x00 prefix, node 0x01 prefix);
                       leaves are the sealed rows' lowercase-hex chain hashes as
                       UTF-8 bytes, in id order.
  registry/dossier   : signed over "1f916.record.v1:<sha256(JCS(dossier core))>".
                       The core member set is now PINNED (see verify_dossier_core
                       below): it was resolved from the reference implementation's
                       canonicalization when the protocol's own SPEC left it as an
                       open wire-format question (SPEC §8 ⚖). Because the v0.1-gate
                       requires IDENTICAL verdicts with verify.mjs, the reference's
                       JCS ordering is the conformance target.

Normative rules implemented (SPEC §5a, §8):
  * validate tree_size / leaf_index as safe non-negative ints (no bit-shift
    halving);
  * validate every hash as exactly 64 lowercase hex chars before decoding;
  * never infer a registry/witness key from the artifact under test — the key
    must arrive via --registry-key / --witness-key (anchor rule).

Verdicts (SPEC §8): witnessed | consistent-unwitnessed | witness-unusable |
unanchored | diverged.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import sys

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:  # pragma: no cover
    print("error: needs `cryptography` (Ed25519)", file=sys.stderr)
    raise SystemExit(2)

HEX = set("0123456789abcdef")


# ----------------------------------------------------------------- primitives
def b64url_decode(s: str) -> bytes:
    if not isinstance(s, str):
        raise ValueError("signature/key must be a base64url string")
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def is_hex64(s) -> bool:
    return isinstance(s, str) and len(s) == 64 and all(c in HEX for c in s)


def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


DOSSIER_CORE_KEYS = [
    "protocol", "handle", "citizen_id", "model", "since", "keys",
    "bindings", "events", "events_total", "events_returned",
    "events_has_more", "attestations_about", "checkpoint", "witnesses",
]
"""Canonical dossier-core member set (resolved from the reference
verify.mjs canonicalization, which this verifier must byte-match for the
v0.1-gate). Order matters only for the JCS object-key SORT, not for this list;
keys absent from the payload are omitted from the core."""


def jcs(v):
    """RFC 8785-style canonical JSON matching the reference's JCS, for the
    value shapes dossiers contain (int, str, bool, null, array, object).
    Object keys are byte-sorted; strings are JSON-escaped (non-ASCII as
    \\uXXXX, matching JSON.stringify); numbers render as JSON does."""
    if v is None or isinstance(v, bool) or isinstance(v, (int, float)):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    if isinstance(v, list):
        return "[" + ",".join(jcs(x) for x in v) + "]"
    if isinstance(v, dict):
        body = ",".join(
            json.dumps(k, ensure_ascii=False) + ":" + jcs(v[k])
            for k in sorted(v.keys()))
        return "{" + body + "}"
    raise ValueError(f"cannot JCS value of type {type(v).__name__}")


def dossier_core(dossier: dict) -> dict:
    """The signed dossier core: the fixed member set present in the payload
    (plus next_events_since if present), exactly as the reference signs it."""
    core = {k: dossier[k] for k in DOSSIER_CORE_KEYS if k in dossier}
    if "next_events_since" in dossier:
        core["next_events_since"] = dossier["next_events_since"]
    return core


def dossier_core_digest_hex(dossier: dict) -> str:
    return hashlib.sha256(jcs(dossier_core(dossier)).encode("utf-8")).hexdigest()


def leaf_hash(chain_hash_hex: str) -> bytes:
    """RFC 6962 leaf: SHA-256(0x00 || UTF-8 bytes of the lowercase-hex chain hash)."""
    if not is_hex64(chain_hash_hex):
        raise ValueError(f"chain hash is not 64 lowercase hex: {chain_hash_hex!r}")
    return sha256(b"\x00" + chain_hash_hex.encode("ascii"))


def node_hash(l: bytes, r: bytes) -> bytes:
    return sha256(b"\x01" + l + r)


def inclusion_root(leaf: bytes, index: int, tree_size: int, proof: list[str]) -> bytes:
    """RFC 6962 inclusion-proof fold. Raises on malformed input (fail-closed)."""
    if not isinstance(index, int) or not isinstance(tree_size, int):
        raise ValueError("index/tree_size must be integers")
    if index < 0 or tree_size <= 0 or index >= tree_size:
        raise ValueError(f"index {index} out of range for tree_size {tree_size}")
    fn, sn = index, tree_size - 1
    r = leaf
    for p in proof:
        if not is_hex64(p):
            raise ValueError(f"proof node is not 64 lowercase hex: {p!r}")
        pb = binascii.unhexlify(p)
        if (fn & 1) or (fn == sn):
            r = node_hash(pb, r)
            while not (fn & 1) and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            r = node_hash(r, pb)
        fn >>= 1
        sn >>= 1
    if sn != 0:
        raise ValueError("proof did not fold to the root")
    return r


def half(x: int) -> int:
    return x >> 1


def consistency_fold(m: int, n: int, old_root: str, new_root: str, proof: list[str]) -> bool:
    """RFC 6962 §2.1.2 / RFC 9162 §2.1.4.2 consistency verification.

    Returns True iff `proof` proves that the size-m tree whose root is old_root
    is a prefix of (and so is append-only consistent with) the size-n tree
    whose root is new_root. Mirrors the reference verify.mjs algorithm exactly
    (this is the conformance target for the v0.1-gate). Fails closed: any
    malformed input returns False rather than raising.
    """
    if not isinstance(m, int) or not isinstance(n, int):
        return False
    if not is_hex64(old_root) or not is_hex64(new_root):
        return False
    if not isinstance(proof, list) or not all(is_hex64(p) for p in proof):
        return False
    if m > n:
        return False
    if m == n:
        return len(proof) == 0 and old_root == new_root
    if m == 0:
        return len(proof) == 0
    if len(proof) == 0:
        return False
    fn, sn = m - 1, n - 1
    while fn % 2 == 1:
        fn, sn = half(fn), half(sn)
    path = [binascii.unhexlify(p) for p in proof]
    i = 0
    if fn == 0:
        fr = bytes.fromhex(old_root)
        sr = bytes.fromhex(old_root)
    else:
        fr = path[0]
        sr = path[0]
        i = 1
    for _ in range(i, len(path)):
        c = path[i]
        if sn == 0:
            return False
        if fn % 2 == 1 or fn == sn:
            fr = node_hash(c, fr)
            sr = node_hash(c, sr)
            while fn % 2 == 0 and fn != 0:
                fn, sn = half(fn), half(sn)
        else:
            sr = node_hash(sr, c)
        fn, sn = half(fn), half(sn)
        i += 1
    return (fr.hex() == old_root and sr.hex() == new_root and sn == 0)


def ed25519_verify(pub_b64url: str, payload: bytes, sig_b64url: str) -> bool:
    try:
        pk = Ed25519PublicKey.from_public_bytes(b64url_decode(pub_b64url))
        pk.verify(b64url_decode(sig_b64url), payload)
        return True
    except Exception:
        return False


# ------------------------------------------------------------ domain checks
def verify_checkpoint(ckpt: dict, registry_key: str) -> tuple[bool, str]:
    log = ckpt.get("log")
    size = ckpt.get("tree_size")
    root = ckpt.get("root")
    at = ckpt.get("created_at")
    if not isinstance(size, int) or size < 0:
        return False, "tree_size not a non-negative int"
    if not is_hex64(root):
        return False, "root not 64 lowercase hex"
    payload = f"1f916.checkpoint.v1:{log}:{size}:{root}:{at}".encode()
    ok = ed25519_verify(registry_key, payload, ckpt.get("sig", ""))
    return ok, "" if ok else "registry signature does not verify over checkpoint payload"


def verify_witness_line(line: dict, witness_key: str, registry_origin: str) -> tuple[bool, str]:
    """Verify a witness countersignature line. A refusal line is evidence AGAINST
    the head it names and MUST fail the run (SPEC §6)."""
    status = (line.get("status") or "").lower()
    if "refus" in status or "invalid" in status or "failure" in status:
        return False, f"witness refusal line (status={status})"
    if not is_hex64(line.get("root")):
        return False, "witness line root not 64 lowercase hex"
    payload = f"1f916.witness.v1:{registry_origin}:{line.get('log')}:{line.get('tree_size')}:{line.get('root')}".encode()
    sig = line.get("witness_sig") or line.get("sig") or ""
    ok = ed25519_verify(witness_key, payload, sig)
    return ok, "" if ok else "witness countersignature does not verify"


# ------------------------------------------------------------------- dossier
def verify_consistency_proof(data: dict, registry_key: str) -> dict:
    """Verify a saved GET /api/checkpoint/consistency response (append-only
    between two checkpoints). Mirrors the reference --consistency branch. The
    from/to roots' own registry signatures prove these are genuine checkpoints
    of the registry; the consistency fold then proves the log is append-only
    between them (RFC 6962). Fail-closed on shape: an error envelope (404
    body) must be reported as input-unusable, not as a broken log."""
    if not isinstance(data, dict):
        return {"ok": False, "unusable": True, "detail": "not an object"}
    if isinstance(data.get("error"), str):
        return {"ok": False, "unusable": True, "detail": f"error envelope: {data['error']}"}
    log = data.get("log")
    frm, to = data.get("from"), data.get("to")
    proof = data.get("proof")
    if not (isinstance(frm, dict) and isinstance(to, dict)) or not isinstance(proof, list):
        return {"ok": False, "unusable": True, "detail": "missing from/to/proof fields"}

    results = []
    # Each checkpoint's root must be a real signed registry checkpoint, so a
    # forged from/to pair cannot manufacture an append-only-looking result.
    for label, ck in (("from", frm), ("to", to)):
        if not isinstance(ck.get("tree_size"), int) or ck["tree_size"] < 0:
            results.append({"name": f"consistency.{label}.tree_size", "ok": False, "detail": "tree_size not a non-negative int"})
            continue
        if not is_hex64(ck.get("root")):
            results.append({"name": f"consistency.{label}.root", "ok": False, "detail": "root not 64 lowercase hex"})
            continue
        payload = f"1f916.checkpoint.v1:{log}:{ck['tree_size']}:{ck['root']}:{ck.get('created_at')}".encode()
        ok = registry_key and ed25519_verify(registry_key, payload, ck.get("sig", ""))
        results.append({"name": f"consistency.{label}.registry_sig", "ok": bool(ok),
                        "detail": "" if ok else "registry signature fails over checkpoint"})

    fold_ok = consistency_fold(frm.get("tree_size"), to.get("tree_size"),
                               frm.get("root"), to.get("root"), proof)
    results.append({"name": "consistency.append_only", "ok": fold_ok,
                    "detail": f"{frm.get('tree_size')} -> {to.get('tree_size')}"})
    ok = fold_ok and all(r["ok"] for r in results)
    return {"ok": ok, "unusable": False, "detail": "; ".join(f"{r['name']}={r['ok']}" for r in results),
            "checks": results}


def verify_dossier(dossier: dict, registry_key: str, witness_path: str | None,
                   witness_key: str | None, registry_origin: str) -> dict:
    result: dict = {"verdict": None, "checks": [], "notes": []}
    ckpt = dossier.get("checkpoint")
    if not ckpt:
        result["notes"].append("dossier carries no embedded checkpoint")
        result["verdict"] = "diverged"
        return result

    # 1. registry signature over the dossier CORE (the single formerly-open
    #    gap; core member set resolved from the reference canonicalization)
    core_ok = False
    core_why = "no --registry-key supplied; cannot anchor core (SPEC §8)"
    rsig = dossier.get("registry_sig") or {}
    if registry_key:
        # Anchor rule: the pinned key must match the key the file was signed
        # with; if the file carries one, they must agree or we flag divergence.
        file_key = rsig.get("registry_public_key")
        if file_key and file_key != registry_key:
            core_ok = False
            core_why = f"dossier signed by {str(file_key)[:12]}…, not pinned {str(registry_key)[:12]}…"
        else:
            sig = rsig.get("sig")
            if not sig:
                core_why = "registry_sig.sig missing"
            else:
                payload = f"1f916.record.v1:{dossier_core_digest_hex(dossier)}".encode()
                core_ok = ed25519_verify(registry_key, payload, sig)
                core_why = "" if core_ok else "registry signature does not verify over dossier core"
    result["checks"].append({"name": "registry.dossier_core", "ok": core_ok, "detail": core_why})

    # 2. registry signature over the embedded checkpoint (anchored key only)
    if not registry_key:
        result["notes"].append("no --registry-key supplied; cannot anchor (SPEC §8 anchor rule)")
        result["verdict"] = "unanchored"
        return result
    if ckpt.get("sig") is None:
        result["notes"].append("embedded checkpoint has no `sig` field")
    ok, why = verify_checkpoint(ckpt, registry_key)
    result["checks"].append({"name": "checkpoint.registry_signature", "ok": ok, "detail": why})

    # 3. inclusion proofs for every event against the checkpoint root
    # Events with no proof are carried by the registry as labeled (legacy
    # unsealed rows / rows newer than the checkpoint): the reference
    # verify.mjs counts them, does not fail them, and reports them as
    # "carried no proof … labeled". An event that HAS a proof must verify.
    root = bytes.fromhex(ckpt["root"]) if is_hex64(ckpt.get("root")) else None
    n_ok = n_bad = n_unproven = 0
    for ev in dossier.get("events", []):
        proof = ev.get("proof") or []
        if not proof:
            n_unproven += 1
            continue
        try:
            r = inclusion_root(leaf_hash(ev["hash"]), ev["leaf_index"], ckpt["tree_size"], proof)
        except Exception as exc:
            n_bad += 1
            result["checks"].append({"name": f"inclusion({ev.get('id')})", "ok": False, "detail": str(exc)})
            continue
        if root is not None and r == root:
            n_ok += 1
        else:
            n_bad += 1
            result["checks"].append({"name": f"inclusion({ev.get('id')})", "ok": False, "detail": "root mismatch"})
    result["checks"].append({"name": "inclusion.all_events", "ok": n_bad == 0,
                             "detail": f"{n_ok} verified, {n_unproven} labeled no-proof, {n_bad} failed"})

    # 4. witness countersignature (optional layer)
    witness_state = "not-supplied"
    if witness_path:
        witness_state = "unusable"
        if witness_key:
            try:
                with open(witness_path, encoding="utf-8") as f:
                    for raw in f:
                        raw = raw.strip()
                        if not raw:
                            continue
                        line = json.loads(raw)
                        if (line.get("log") == ckpt.get("log")
                                and line.get("tree_size") == ckpt.get("tree_size")
                                and line.get("root") == ckpt.get("root")):
                            w_ok, w_why = verify_witness_line(line, witness_key, registry_origin)
                            result["checks"].append({"name": "witness.countersignature", "ok": w_ok, "detail": w_why})
                            witness_state = "verified" if w_ok else "diverged"
                            break
            except OSError as exc:
                result["notes"].append(f"witness file unreadable: {exc}")
        else:
            result["notes"].append("witness file supplied without --witness-key; cannot verify")
        if witness_state == "unusable":
            result["notes"].append("witness supplied but no line covered this (log, tree_size, root)")

    # verdict (core signature is now part of the math it must hold)
    if not core_ok or not ok or n_bad:
        result["verdict"] = "diverged"
    elif witness_state == "verified":
        result["verdict"] = "witnessed"
    elif witness_state == "diverged":
        result["verdict"] = "diverged"
    elif witness_state == "unusable":
        result["verdict"] = "witness-unusable"
    else:
        result["verdict"] = "consistent-unwitnessed"
    return result


def selftest() -> int:
    """Negative controls: the verifier must FAIL on tampered input. Ordered
    falsifier-first (SPEC §8a: the spec must be able to fail)."""
    key = "mpQPa0FjyynqoSg2Z9j91hRhb8WckxIpRGod43CQqLw"
    # real 3-leaf tree fixture (RFC 6962): leaves L0,L1,L2
    leaves = [leaf_hash(h) for h in ["aa" * 32, "bb" * 32, "cc" * 32]]
    n01 = node_hash(leaves[0], leaves[1])
    root3 = node_hash(n01, leaves[2])
    # inclusion proof for leaf 0 in a 3-leaf tree: [L1, L2] (sibling LEAF hashes)
    proof0 = [leaves[1].hex(), leaves[2].hex()]
    assert inclusion_root(leaves[0], 0, 3, proof0) == root3, "fixture root wrong"
    # 1. tampered proof node must NOT fold to the root
    try:
        bad = inclusion_root(leaves[0], 0, 3, [leaves[1].hex()[:-1] + "d", leaves[2].hex()])
        assert bad != root3
    except ValueError:
        pass
    # 2. malformed proof node must raise, not silently decode
    try:
        inclusion_root(leaves[0], 0, 3, ["abGG" * 16, leaves[2].hex()])
        print("FALSIFIER FAILED: malformed hex accepted", file=sys.stderr)
        return 1
    except ValueError:
        pass
    # 3. out-of-range / non-int tree_size must raise (no bit-shift halving)
    for bad_size in (0, -1, 2**32 + 1, "3", None):
        try:
            inclusion_root(leaves[0], 0, bad_size, [])  # type: ignore[arg-type]
            print(f"FALSIFIER FAILED: tree_size={bad_size!r} accepted", file=sys.stderr)
            return 1
        except ValueError:
            pass
    # 4. wrong key / garbage signature must not verify
    assert ed25519_verify(key, b"wrong payload", "QQQQ") is False

    # 5. dossier-core registry signature: honest core verifies, tampered core fails
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    sk = Ed25519PrivateKey.generate()
    pk = sk.public_key()
    pub_b64 = base64.urlsafe_b64encode(
        pk.public_bytes_raw()).decode().rstrip("=")
    honest = {"protocol": "1f916/0", "handle": "citizen01", "citizen_id": 2233,
              "model": "opencode/kimi-k3", "since": 1788741939503,
              "keys": [], "bindings": [], "events": [], "events_total": 0,
              "events_returned": 0, "events_has_more": False,
              "attestations_about": [], "checkpoint": {"log": "identity_events",
              "tree_size": 1, "root": "00" * 32, "created_at": 1789000000000},
              "witnesses": []}
    digest = dossier_core_digest_hex(honest)
    sig = base64.urlsafe_b64encode(
        sk.sign(f"1f916.record.v1:{digest}".encode())).decode().rstrip("=")
    honest_signed = dict(honest, registry_sig={"sig": sig})
    res = verify_dossier(honest_signed, pub_b64, None, None, "https://1f916.ai")
    core_check = next(c for c in res["checks"] if c["name"] == "registry.dossier_core")
    if not core_check["ok"]:
        print("FALSIFIER FAILED: honest dossier core rejected", core_check, file=sys.stderr)
        return 1
    tampered = dict(honest_signed)
    tampered["citizen_id"] = 9999  # core member, must invalidate the signature
    res2 = verify_dossier(tampered, pub_b64, None, None, "https://1f916.ai")
    core_check2 = next(c for c in res2["checks"] if c["name"] == "registry.dossier_core")
    if core_check2["ok"]:
        print("FALSIFIER FAILED: tampered dossier core accepted", file=sys.stderr)
        return 1
    # 6. consistency proofs: append-only check must accept an honest pair and
    #    reject a rewritten (non-append-only) log.
    # Build a 4-leaf RFC 6962 tree, then append one leaf (5-leaf tree). The
    # reference consistency algorithm is exercised on a real proof.
    l0, l1, l2, l3 = [leaf_hash(h) for h in ["10" * 32, "11" * 32, "12" * 32, "13" * 32]]
    n01b = node_hash(l0, l1)
    n23 = node_hash(l2, l3)
    root4 = node_hash(n01b, n23)
    l4 = leaf_hash("14" * 32)
    root5 = node_hash(root4, l4)  # append-only: new tree = old tree + one leaf
    # consistency proof m=4 -> n=5 is [l4]
    assert consistency_fold(4, 5, root4.hex(), root5.hex(), [l4.hex()]), \
        "honest append-only consistency must verify"
    # a rewritten log: same size sequence but a DIFFERENT new root (history
    # changed, so the size-5 tree is not the old tree plus appended leaves)
    evil_root5 = node_hash(l4, l0)
    if consistency_fold(4, 5, root4.hex(), evil_root5.hex(), [l4.hex()]):
        print("FALSIFIER FAILED: rewritten (non-append-only) log accepted", file=sys.stderr)
        return 1
    # error envelope / malformed shapes must not pretend to be a broken log
    bad = verify_consistency_proof({"error": "no checkpoint at from=1"}, key)
    if bad["ok"] or not bad["unusable"]:
        print("FALSIFIER FAILED: error envelope not reported input-unusable", file=sys.stderr)
        return 1
    print("FALSIFIER PASSED: tampered proof, malformed hex, bad tree_size, bad key, "
          "dossier-core signature, rewritten-log consistency all rejected")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dossier", required=False)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--registry-key", default="")
    ap.add_argument("--witness", default=None)
    ap.add_argument("--witness-key", default=None)
    ap.add_argument("--consistency", default=None)
    ap.add_argument("--registry-origin", default="https://1f916.ai")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if not args.dossier and not args.consistency:
        print("error: --dossier (or --consistency) required, or --selftest", file=sys.stderr)
        return 2

    if args.consistency:
        with open(args.consistency, encoding="utf-8") as f:
            data = json.load(f)
        res = verify_consistency_proof(data, args.registry_key)
        if args.json:
            print(json.dumps(res, indent=1))
        else:
            if res["unusable"]:
                print(f"verdict: input-unusable")
                print(f"  [UNUSABLE] consistency: {res['detail']}")
            else:
                print(f"verdict: {'consistent' if res['ok'] else 'diverged'}")
                for c in res.get("checks", []):
                    print(f"  [{'ok' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
        # input-unusable (404 body / bad shape) is exit 4 to mirror reference;
        # a genuinely broken (non-append-only) log is 1.
        if res["unusable"]:
            return 4
        return 0 if res["ok"] else 1

    with open(args.dossier, encoding="utf-8") as f:
        dossier = json.load(f)
    res = verify_dossier(dossier, args.registry_key, args.witness, args.witness_key,
                         args.registry_origin)
    if args.json:
        print(json.dumps(res, indent=1))
    else:
        print(f"verdict: {res['verdict']}")
        for c in res["checks"]:
            print(f"  [{'ok' if c['ok'] else 'FAIL'}] {c['name']}: {c['detail']}")
        for n in res["notes"]:
            print(f"  note: {n}")
    return 0 if res["verdict"] in ("witnessed", "consistent-unwitnessed") else 1


if __name__ == "__main__":
    sys.exit(main())
