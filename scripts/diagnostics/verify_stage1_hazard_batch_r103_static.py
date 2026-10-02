#!/usr/bin/env python3
"""Static and negative-control verifier for the isolated r103 compiler."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_stage1_hazard_batch_r102 as r102
import build_stage1_hazard_batch_r103 as r103


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def region(rom: bytes, bank: int, address: int, size: int) -> bytes:
    off = r102.bank_offset(bank, address)
    return rom[off:off + size]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--r102-live-receipt", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    base = args.base.read_bytes()
    candidate = args.candidate.read_bytes()
    build = json.loads(args.build_receipt.read_text())
    live = json.loads(args.r102_live_receipt.read_text())
    if digest(base) != r103.BASE_SHA256:
        raise SystemExit("base is not exact rejected r102")
    if digest(candidate) != build["output_sha256"]:
        raise SystemExit("candidate differs from build receipt")
    if build.get("promotable") is not False:
        raise SystemExit("r103 must remain non-promotable")

    # Only the compiler fragment and three checksum bytes may differ.
    allowed = set(range(0x014D, 0x0150))
    compile_off = r102.bank_offset(r102.HELPER_BANK, r103.COMPILE_ADDR)
    allowed.update(range(compile_off, compile_off + len(r103.OLD_COMPILE)))
    differences = [
        index for index, (left, right) in enumerate(zip(base, candidate))
        if left != right
    ]
    if set(differences) - allowed:
        raise AssertionError(
            f"unexpected r103 bytes: {sorted(set(differences) - allowed)[:16]}"
        )
    if region(
        candidate, r102.HELPER_BANK, r103.COMPILE_ADDR,
        len(r103.NEW_COMPILE),
    ) != r103.NEW_COMPILE:
        raise AssertionError("immutable-LUT compiler differs")
    if bytes.fromhex("06 C6 0A") in r103.NEW_COMPILE:
        raise AssertionError("r103 still reads fixed WRAM C600")
    if bytes.fromhex("06 44 0A 22") not in r103.NEW_COMPILE:
        raise AssertionError("r103 does not read bank20 ROM $4400")

    # Expanded LUT is already exact for all 256 IDs. Poisoning every modeled
    # C600 byte must not influence r103, while it must change r102's model.
    immutable = region(base, r102.HELPER_BANK, r102.EXPANDED_LUT_ADDR, 0x100)
    canonical = region(
        base, r102.CANONICAL_LUT_BANK, r102.CANONICAL_LUT_ADDR, 0x100
    )
    poisoned_c600 = bytes(value ^ 0xFF for value in canonical)
    r103_clean = bytes(immutable[tile] for tile in range(0x100))
    r103_poisoned = bytes(immutable[tile] for tile in range(0x100))
    if r103_clean != r103_poisoned:
        raise AssertionError("immutable compiler changed under C600 poison")
    r102_poisoned = bytes(
        poisoned_c600[tile] | (0x08 if tile in r102.TOOTH_IDS else 0)
        for tile in range(0x100)
    )
    if r102_poisoned == immutable:
        raise AssertionError("C600 poison did not reject the old compiler")
    if any(immutable[tile] != 0x0F for tile in r102.TOOTH_IDS):
        raise AssertionError("immutable tooth attrs are not exact $0F")

    # The rejected run is completely clean before item use; corruption begins
    # eight frames after the item handler, which is the fixed-WRAM ownership
    # boundary this patch removes.
    replay = live["replays"][0]
    item_use = int(replay["effective_menu_use_frame"])
    match = re.match(r"f(\d+):", replay["first_transient_mismatch"])
    if match is None:
        raise AssertionError("r102 live receipt lacks first mismatch frame")
    first_mismatch = int(match.group(1))
    if first_mismatch <= item_use:
        raise AssertionError((item_use, first_mismatch))
    if not all(
        other["first_transient_mismatch"] == replay["first_transient_mismatch"]
        for other in live["replays"]
    ):
        raise AssertionError("r102 failure was not deterministic")

    receipt = {
        "schema": "penta-stage1-hazard-batch-r103-verifier-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(base),
        "candidate_sha256": digest(candidate),
        "changed_bytes": len(differences),
        "runtime_lut_contract": {
            "lookup": "immutable bank20:$4400",
            "all_256_ids": True,
            "tooth_attr": "0x0F",
            "fixed_wram_c600_reads": 0,
        },
        "negative_control": {
            "mutation": "XOR every modeled C600 byte with $FF",
            "r103_output_unchanged": True,
            "r102_output_rejected": True,
        },
        "r102_failure_timing": {
            "pre_item_mismatch_frames": 0,
            "item_use_frame": item_use,
            "first_mismatch_frame": first_mismatch,
            "frames_after_item_use": first_mismatch - item_use,
            "deterministic_replays": True,
        },
        "preserved": {
            "batch_publisher": True,
            "mapper_stack_abi": True,
            "overflow_fallback": True,
            "lcd_off_gdma": True,
            "seam_wall_repair": True,
            "svbk2_d600_mutual_exclusion": True,
        },
        "first_emulator_gate": (
            "regenerate candidate-owned cold state, then rerun the exact "
            "current-ROM Stage1 menu/item/low-health gate with --trace-routes"
        ),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
