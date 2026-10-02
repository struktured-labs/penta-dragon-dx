#!/usr/bin/env python3
"""Build safe r277 Stage-7 helper timing variants for diagnostic sweeps.

Every selectable patch is width exact and independently proved by
``build_stage7_pointer_advance_r278.py``.  Outputs are diagnostic artifacts;
the chosen combination must be hard-bound in its release builder and pass the
full verifier from a fresh stock baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage7_pointer_advance_r278 as r278


ROOT = Path(__file__).resolve().parents[2]

# Ordered from smaller to larger theoretical saving.  Keeping the phase of
# each saving explicit lets the live route gate select the deterministic point
# instead of assuming equal cycle totals are behaviorally interchangeable.
VARIANTS: dict[str, tuple[bool, bool, int, bool]] = {
    # name: (pointer, attribute marker, odd-row INC-E count, tile marker)
    "p": (True, False, 0, False),
    "a": (False, True, 0, False),
    "t": (False, False, 0, True),
    "pa": (True, True, 0, False),
    "pt": (True, False, 0, True),
    "at": (False, True, 0, True),
    "pat": (True, True, 0, True),
    "ato5": (False, True, 5, True),
    "pato5": (True, True, 5, True),
    "ato10": (False, True, 10, True),
    "pato10": (True, True, 10, True),
    "ato15": (False, True, 15, True),
    "pato15": (True, True, 15, True),
    "pao23": (True, True, 23, False),
    "pto23": (True, False, 23, True),
    "pato20": (True, True, 20, True),
    "pato23": (True, True, 23, True),
}


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def patch_exact(rom: bytearray, base: bytes, address: int,
                old: bytes, new: bytes) -> list[int]:
    if len(old) != len(new):
        raise AssertionError("diagnostic patch changed width")
    offset = r278.bank_offset(r278.HELPER_BANK, address)
    if base[offset:offset + len(old)] != old:
        raise AssertionError(f"preimage moved at bank22:${address:04X}")
    rom[offset:offset + len(new)] = new
    return list(range(offset, offset + len(new)))


def build_variant(base: bytes, name: str) -> tuple[bytes, dict[str, object]]:
    if sha256(base) != r278.BASE_SHA256:
        raise AssertionError(f"wrong exact r277 base: {sha256(base)}")
    pointer, attr_marker, odd_count, tile_marker = VARIANTS[name]
    if not 0 <= odd_count <= r278.PATCHED_ADVANCES_PER_RECORD:
        raise AssertionError(odd_count)
    # Run the release builder's exhaustive proofs even when a particular
    # diagnostic variant does not select every patch.
    all_source_offsets, record_proof = r278.odd_record_proof(base)
    r278.pointer_rows()
    marker_proof = r278.marker_counter_proof()

    rom = bytearray(base)
    allowed: set[int] = {0x014D, 0x014E, 0x014F}
    if pointer:
        allowed.update(patch_exact(
            rom, base, r278.POINTER_ADVANCE_ADDR,
            r278.OLD_POINTER_ADVANCE, r278.NEW_POINTER_ADVANCE,
        ))
    if attr_marker:
        allowed.update(patch_exact(
            rom, base, r278.ATTR_COUNTER_ADDR,
            r278.OLD_ATTR_COUNTER, r278.NEW_ATTR_COUNTER,
        ))
    if odd_count:
        chosen: list[int] = []
        for record in range(r278.ODD_RECORD_COUNT):
            record_start = record * r278.PATCHED_ADVANCES_PER_RECORD
            chosen.extend(all_source_offsets[
                record_start:record_start + odd_count
            ])
        if len(chosen) != r278.ODD_RECORD_COUNT * odd_count:
            raise AssertionError("odd-row sweep site count changed")
        for offset in chosen:
            if base[offset] != r278.OLD_SOURCE_ADVANCE:
                raise AssertionError(f"source advance moved at 0x{offset:X}")
            rom[offset] = r278.NEW_SOURCE_ADVANCE
        allowed.update(chosen)
    if tile_marker:
        allowed.update(patch_exact(
            rom, base, r278.TILE_COUNTER_ADDR,
            r278.OLD_TILE_COUNTER, r278.NEW_TILE_COUNTER,
        ))

    r278.update_checksums(rom)
    candidate = bytes(rom)
    changed = [index for index, pair in enumerate(zip(base, candidate))
               if pair[0] != pair[1]]
    if set(changed) - allowed:
        raise AssertionError("diagnostic change escaped selected patches")
    saved = (
        (136 if pointer else 0)
        + (308 if attr_marker else 0)
        + odd_count * r278.ODD_RECORD_COUNT * 4
        + (308 if tile_marker else 0)
    )
    return candidate, {
        "schema": "penta-stage7-helper-timing-variant-v1",
        "status": "DIAGNOSTIC_ONLY_FULL_GATE_REQUIRED",
        "name": name,
        "base_sha256": sha256(base),
        "candidate_sha256": sha256(candidate),
        "changed_bytes_including_checksums": len(changed),
        "selection": {
            "pointer": pointer,
            "attribute_marker": attr_marker,
            "odd_inc_e_per_record": odd_count,
            "tile_marker": tile_marker,
        },
        "saved_t_per_admitted_publication": saved,
        "proofs_reused": {
            "pointer_rows": 20,
            "odd_records": record_proof,
            "marker_truth_table": marker_proof,
        },
        "promotable": False,
    }


def names(raw: str) -> list[str]:
    result = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [name for name in result if name not in VARIANTS]
    if not result or unknown:
        raise argparse.ArgumentTypeError(
            "unknown or empty variant list: " + ",".join(unknown)
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", type=Path,
        default=ROOT / "tmp/stage7-isolated-router-r277/candidate.gb",
    )
    parser.add_argument(
        "--variants", type=names,
        default=list(VARIANTS),
        help="comma-separated names; default builds the ordered full sweep",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage7-helper-timing-sweep",
    )
    args = parser.parse_args()
    base = args.base.read_bytes()
    summary: list[dict[str, object]] = []
    for name in args.variants:
        candidate, receipt = build_variant(base, name)
        directory = args.output / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "candidate.gb").write_bytes(candidate)
        (directory / "build-receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n"
        )
        summary.append({
            "name": name,
            "candidate_sha256": receipt["candidate_sha256"],
            "saved_t_per_admitted_publication": (
                receipt["saved_t_per_admitted_publication"]
            ),
        })
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
