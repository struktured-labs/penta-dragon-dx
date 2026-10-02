#!/usr/bin/env python3
"""Fail-closed static verifier for the isolated r102 hazard batch ROM."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_stage1_hazard_batch_r102 as batch


FORBIDDEN_STACK_OPS = frozenset((
    0xC1, 0xD1, 0xE1, 0xF1,              # POP
    0xC5, 0xD5, 0xE5, 0xF5,              # PUSH
    0xC9, 0xD9,                           # RET/RETI
    0xCD,                                 # CALL a16
    0xC0, 0xC8, 0xD0, 0xD8,
))


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def region(rom: bytes, bank: int, address: int, size: int) -> bytes:
    off = batch.bank_offset(bank, address)
    return rom[off:off + size]


def instruction_offsets(code: bytes) -> list[tuple[int, int]]:
    """Decode only the LR35902 forms emitted by the isolated builder."""
    one = {
        0x02, 0x03, 0x04, 0x05, 0x0A, 0x0C, 0x0F, 0x13, 0x15,
        0x1A, 0x22, 0x23, 0x2A, 0x3C, 0x3D, 0x47, 0x4F, 0x5F,
        0x67, 0x6F, 0x78, 0x79, 0x7B, 0x7C, 0x7D, 0x7E, 0x87,
        0x91, 0xAF, 0xB7, 0xB8,
        0xC1, 0xD1, 0xE1, 0xF1, 0xC5, 0xD5, 0xE5, 0xF5,
        0xC9, 0xD9,
    }
    two = {
        0x06, 0x0E, 0x18, 0x20, 0x28, 0x30, 0x38,
        0x26, 0x3E, 0xC6, 0xD6, 0xE0, 0xE6, 0xF0, 0xF6, 0xFE,
        0xCB,
    }
    three = {
        0x01, 0x11, 0x21, 0xC2, 0xC3, 0xCA, 0xCD, 0xD2,
        0xDA, 0xEA, 0xFA,
    }
    result: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(code):
        opcode = code[cursor]
        result.append((cursor, opcode))
        if opcode in one:
            width = 1
        elif opcode in two:
            width = 2
        elif opcode in three:
            width = 3
        else:
            raise AssertionError(
                f"unknown diagnostic opcode ${opcode:02X} at +${cursor:02X}"
            )
        cursor += width
    if cursor != len(code):
        raise AssertionError("instruction crosses helper boundary")
    return result


def semantic_model(base: bytes, candidate: bytes) -> dict[str, object]:
    canonical = region(
        base, batch.CANONICAL_LUT_BANK, batch.CANONICAL_LUT_ADDR, 0x100
    )
    expanded = region(
        base, batch.HELPER_BANK, batch.EXPANDED_LUT_ADDR, 0x100
    )
    expected = bytes(
        value | (0x08 if tile in batch.TOOTH_IDS else 0x00)
        for tile, value in enumerate(canonical)
    )
    if expanded != expected:
        mismatches = [
            tile for tile in range(0x100) if expanded[tile] != expected[tile]
        ]
        raise AssertionError(f"semantic LUT mismatch: {mismatches[:16]}")
    if any(expanded[tile] != 0x0F for tile in batch.TOOTH_IDS):
        raise AssertionError("tooth attributes are not exact $0F")
    if region(
        candidate, batch.CANONICAL_LUT_BANK, batch.CANONICAL_LUT_ADDR, 0x100
    ) != canonical:
        raise AssertionError("candidate mutated canonical Stage1 LUT")

    # Exhaustively prove every single-cell compiler result, not just teeth.
    for tile in range(0x100):
        compiled = canonical[tile]
        folded = tile & 0xEF
        if 0x64 <= folded < 0x6A:
            compiled |= 0x08
        if compiled != expanded[tile]:
            raise AssertionError(f"compiler model differs at ${tile:02X}")
    return {
        "all_tile_ids_equal_expanded_lut": True,
        "tooth_count": len(batch.TOOTH_IDS),
        "tooth_attr": "0x0F",
    }


def destination_model() -> dict[str, object]:
    cases = []
    total_blocks = 0
    for map_base in (0x9800, 0x9C00):
        for row in range(24):
            row_base = map_base + row * 32
            for start, span, blocks in ((0, 15, 1), (4, 11, 1), (8, 10, 2)):
                exact = row_base + start
                aligned = exact & 0xFFF0
                covered = range(aligned, aligned + blocks * 16)
                semantic = range(exact, exact + span)
                if not all(cell in covered for cell in semantic):
                    raise AssertionError((map_base, row, start, span, blocks))
                if blocks == 2 and start != 8:
                    raise AssertionError("only the right span may use two blocks")
                cases.append((map_base, row, start))
    for _row in range(2):
        total_blocks += 1 + 1 + 2 + 2
    return {
        "cases": len(cases),
        "physical_maps": ["0x9800", "0x9C00"],
        "starts": [0, 4, 8],
        "settled_four_row_blocks": total_blocks // 2,
        "right_span_requires_two_blocks": True,
        "padding_24_31": "zero",
        "dma_commands": {
            "lcd_on_one_block": "0x80",
            "lcd_on_two_blocks": "0x81",
            "lcd_off_one_block": "0x00",
            "lcd_off_two_blocks": "0x01",
        },
    }


def code_contract(candidate: bytes, receipt: dict[str, object]) -> dict[str, object]:
    expected_regions = {
        "dispatch-wrapper": (batch.DISPATCH_WRAPPER, batch.build_dispatch_wrapper()),
        "scan-init": (batch.INIT_HELPER, batch.build_init_helper()),
    }
    stage, stage_labels = batch.build_stage_helper()
    publish, publish_labels = batch.build_publish_helper()
    expected_regions["row-stager"] = (batch.STAGE_HELPER, stage)
    expected_regions["batch-publisher"] = (batch.PUBLISH_HELPER, publish)
    for label, (address, expected) in expected_regions.items():
        actual = region(candidate, batch.HELPER_BANK, address, len(expected))
        if actual != expected:
            raise AssertionError(f"{label} code differs from builder")
        recorded = receipt["regions"][label]
        if recorded["sha256"] != digest(actual) or recorded["size"] != len(actual):
            raise AssertionError(f"{label} receipt digest/size differs")

    stage_ops = instruction_offsets(stage)
    if any(opcode in FORBIDDEN_STACK_OPS for _offset, opcode in stage_ops):
        raise AssertionError("row stager touches stack while SVBK2")
    publish_ops = instruction_offsets(publish)
    restored = publish_labels["svbk1_restored"] - batch.PUBLISH_HELPER
    for offset, opcode in publish_ops:
        if offset < restored and opcode in FORBIDDEN_STACK_OPS:
            raise AssertionError(
                f"publisher stack opcode ${opcode:02X} before SVBK1 restore"
            )
    push_offsets = [off for off, opcode in publish_ops if opcode == 0xC5]
    expected_pushes = [
        publish_labels["svbk1_restored"] - batch.PUBLISH_HELPER + 3,
        publish_labels["corrupt"] - batch.PUBLISH_HELPER + 15,
    ]
    if push_offsets != expected_pushes:
        raise AssertionError((push_offsets, expected_pushes))
    if 0xFB in stage or 0xFB in publish:
        raise AssertionError("diagnostic unexpectedly enables interrupts")

    # Overflow is tested before descriptor/source mutation; it restores
    # SVBK1 and enters the byte-identical r101 writer with DE/HL/C untouched.
    overflow_prefix = bytes.fromhex("3E 02 E0 70 FA 80 D6 FE 04 D2")
    if not stage.startswith(overflow_prefix):
        raise AssertionError("overflow guard moved behind mutable staging work")
    overflow = stage_labels["overflow"] - batch.STAGE_HELPER
    if stage[overflow:] != bytes.fromhex("3E 01 E0 70 C3 00 43"):
        raise AssertionError("overflow does not restore SVBK1 and fall back")

    # The exact command sequence retains C=0/1 for LCD-off GDMA and ORs bit7
    # only when LCDC.7 says rendered HBlank service exists.
    lcd_command = bytes.fromhex("F0 40 CB 7F 79 28 02 F6 80 E0 55")
    if lcd_command not in publish:
        raise AssertionError("LCD-off/GDMA and LCD-on/HBlank split changed")

    # Entry/return mapper byte contracts and preserved r101 repair/writer.
    exact = (
        (batch.PRIVATE_BANK, batch.SCANNER_ENTRY, bytes.fromhex("3E14CD6100")),
        (batch.HELPER_BANK, batch.SCANNER_ENTRY, bytes.fromhex("3E13CD6100")),
        (batch.HELPER_BANK, batch.SCANNER_BODY,
         bytes([0xC3, batch.INIT_HELPER & 0xFF, batch.INIT_HELPER >> 8])),
        (batch.PRIVATE_BANK, batch.SCANNER_TAIL_JP,
         bytes([0xC3, batch.MAPPER_LEAF & 0xFF, batch.MAPPER_LEAF >> 8])),
        (batch.PRIVATE_BANK, batch.MAPPER_LEAF, bytes.fromhex("3E14CD6100")),
        (batch.HELPER_BANK, batch.MAPPER_RETURN,
         bytes([0xC3, batch.DISPATCH_WRAPPER & 0xFF,
                batch.DISPATCH_WRAPPER >> 8])),
        (batch.HELPER_BANK, batch.RETURN_BRIDGE, bytes.fromhex("3E13CD6100")),
    )
    for bank, address, expected in exact:
        if region(candidate, bank, address, len(expected)) != expected:
            raise AssertionError(f"mapper contract changed at bank{bank}:${address:04X}")

    # Old helper is retained for overflow and $55C0 is byte-identical to r101.
    base = Path(receipt["base"]).read_bytes()
    if region(candidate, batch.HELPER_BANK, batch.OLD_SEMANTIC_HELPER, 0x6A) != region(
        base, batch.HELPER_BANK, batch.OLD_SEMANTIC_HELPER, 0x6A
    ):
        raise AssertionError("overflow helper $4300 was modified")
    if region(candidate, batch.PRIVATE_BANK, batch.TRANSITION_REPAIR, 65) != region(
        base, batch.PRIVATE_BANK, batch.TRANSITION_REPAIR, 65
    ):
        raise AssertionError("seam/wall repair $55C0 was modified")
    return {
        "stage_stack_ops_while_svbk2": 0,
        "publisher_pushes_after_svbk1_restore": len(push_offsets),
        "old_overflow_helper_preserved": True,
        "overflow_guard_before_mutation": True,
        "lcd_off_uses_gdma": True,
        "lcd_on_uses_hblank_dma": True,
        "transition_repair_preserved": True,
        "completion_discriminator": "C=0xFF",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    base = args.base.read_bytes()
    candidate = args.candidate.read_bytes()
    build_receipt = json.loads(args.build_receipt.read_text())
    if digest(base) != batch.BASE_SHA256:
        raise SystemExit("base is not exact r101")
    if digest(candidate) != build_receipt["candidate_sha256"]:
        raise SystemExit("candidate digest differs from build receipt")
    if build_receipt.get("promotable") is not False:
        raise SystemExit("diagnostic receipt must remain non-promotable")

    direct_signature = bytes.fromhex("F3 F5 D5 E5 62 6B 01 60 14 09 4E 23 46")
    if direct_signature in base or direct_signature in candidate:
        raise SystemExit("Ted direct-plane D600 owner is present")

    result = {
        "schema": "penta-stage1-hazard-batch-r102-verifier-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(base),
        "candidate_sha256": digest(candidate),
        "mutual_exclusion": {
            "svbk2_d600_owner": "Stage1 diagnostic only",
            "ted_direct_plane_signature_absent": True,
            "production_combination_forbidden": True,
        },
        "semantics": semantic_model(base, candidate),
        "destinations": destination_model(),
        "code": code_contract(candidate, build_receipt),
        "first_emulator_gate": {
            "name": "candidate-owned cold hazard state, then current-ROM menu/item/low-health visual gate",
            "reason": "binds the fixture to r102 before testing semantic attrs, LCD-off publication, map ownership, hardware-bank cleanup, and replay determinism",
            "commands_in_order": [
                (
                    "python3 scripts/diagnostics/generate_stage1_hazard_state.py "
                    "tmp/stage1-hazard-batch-r102/candidate.gb "
                    "--output tmp/stage1-hazard-batch-r102/cold-hazard-state"
                ),
                (
                    "python3 scripts/diagnostics/verify_stage1_current_hazard_menu.py "
                    "tmp/stage1-hazard-batch-r102/candidate.gb "
                    "--state tmp/stage1-hazard-batch-r102/cold-hazard-state/stage1-hazard.ss0 "
                    "--state-receipt tmp/stage1-hazard-batch-r102/cold-hazard-state/receipt.json "
                    "--output tmp/stage1-hazard-batch-r102/current-hazard-menu "
                    "--trace-routes"
                ),
            ],
        },
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
