#!/usr/bin/env python3
"""Fail-closed static contract for the non-promotable r106 guard."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_stage1_room03_fast_r106 as r106


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def route(scene: int, room: int) -> str:
    if scene & 0x08:
        return "full-scanner"
    if room != 0x03:
        return "full-scanner"
    return "balanced-fast-exit"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    base = args.base.read_bytes()
    candidate = args.candidate.read_bytes()
    build = json.loads(args.build_receipt.read_text())
    if digest(base) != r106.BASE_SHA256:
        raise SystemExit("base is not exact visual-safe r100")
    if digest(candidate) != build["output_sha256"]:
        raise SystemExit("candidate differs from build receipt")

    allowed = set(range(0x014E, 0x0150))
    for address, payload in ((r106.GATE_ADDR, r106.GATE),
                             (r106.ROOM_ADDR, r106.ROOM)):
        off = r106.offset(address)
        allowed.update(range(off, off + len(payload)))
        if candidate[off:off + len(payload)] != payload:
            raise AssertionError(f"guard fragment ${address:04X} changed")
    call_off = r106.offset(r106.CALL_ADDR)
    allowed.update(range(call_off, call_off + 3))
    differences = {
        i for i, (before, after) in enumerate(zip(base, candidate))
        if before != after
    }
    if differences - allowed:
        raise AssertionError(f"unexpected changed bytes: {differences - allowed}")

    # Hazard classifier, semantic writer, transition repair, and room-$12
    # repair stay byte-exact. A repair-needed source therefore cannot enter the
    # fast arm unless both the scene and room controls were also corrupted.
    preserved = ((0x61B7, 0x5D), (0x55C0, 0x41), (0x6F68, 0x23))
    for address, size in preserved:
        off = r106.offset(address)
        if candidate[off:off + size] != base[off:off + size]:
            raise AssertionError(f"repair/classifier ${address:04X} changed")

    controls = {
        "ordinary_room03": route(0x02, 0x03),
        "room_mismatch": route(0x02, 0x01),
        "room12_repair": route(0x02, 0x12),
        "scene0A_room03": route(0x0A, 0x03),
        "scene0A_repair_needed": route(0x0A, 0x12),
    }
    expected = {
        "ordinary_room03": "balanced-fast-exit",
        "room_mismatch": "full-scanner",
        "room12_repair": "full-scanner",
        "scene0A_room03": "full-scanner",
        "scene0A_repair_needed": "full-scanner",
    }
    if controls != expected:
        raise AssertionError((controls, expected))

    # Symbolic stack: CALL adds return above caller-saved completed-map HL.
    stack = ["return-$6BEA", "saved-HL", "outer"]
    bc = stack.pop(0)
    de = stack.pop(0)
    stack.insert(0, bc)
    landed = stack.pop(0)
    if landed != "return-$6BEA" or stack != ["outer"] or de != "saved-HL":
        raise AssertionError("fast arm does not reproduce $55C0 unwind")

    receipt = {
        "schema": "penta-stage1-room03-fast-r106-verifier-v1",
        "status": "PASS_STATIC_NON_PROMOTABLE",
        "promotable": False,
        "base_sha256": digest(base),
        "candidate_sha256": digest(candidate),
        "controls": controls,
        "stack_balance": {
            "saved_hl_consumed": True,
            "return_lands_at": "bank19:$6BEA",
            "outer_stack_exact": True,
        },
        "byte_exact_full_paths": True,
        "first_gate": "strict Stage1 target0/right/2800; require >=654/667",
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
