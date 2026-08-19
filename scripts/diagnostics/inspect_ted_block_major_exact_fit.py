#!/usr/bin/env python3
"""Emit deterministic hashes and protected-range checks for Ted block-major."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_v302_title_fix as build  # noqa: E402

REFERENCE_ROMS = (
    ROOT / "rom/working/penta_dragon_dx_v301.gb",
    ROOT / "rom/working/penta_dragon_dx_FIXED.gb",
)
PRIVATE_CAVES = (
    (0x50E8, 7), (0x6100, 7), (0x6140, 9), (0x61C0, 7), (0x6500, 13),
)
ABSOLUTE_OPERAND_OPCODES = {
    0x01, 0x08, 0x11, 0x21, 0x31,
    0xC2, 0xC3, 0xCA, 0xCD, 0xD2, 0xDA, 0xEA, 0xFA,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate-rom", type=Path)
    args = parser.parse_args()

    fragments = build.build_ted_block_major_exact_fit_draft()
    rows = []
    protected_overlaps = []
    for address, payload in sorted(fragments.items()):
        end = address + len(payload)
        rows.append({
            "start": f"{address:04X}",
            "end": f"{end - 1:04X}",
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
        if address < 0x8000:
            for protected_start, protected_end, owner in (
                build.TED_INCREMENTAL_CELL_PROTECTED_ROM_RANGES
            ):
                # Ted owns $7600-$76FF; every other arena page remains
                # protected.  Record that explicit exception rather than
                # weakening the global protected range.
                allowed_ted_page = (
                    protected_start == 0x7200
                    and protected_end == 0x7B00
                    and 0x7600 <= address and end <= 0x7700
                )
                if (
                    not allowed_ted_page
                    and address < protected_end and end > protected_start
                ):
                    protected_overlaps.append({
                        "start": f"{address:04X}",
                        "end": f"{end - 1:04X}",
                        "owner": owner,
                    })

    runtime = fragments[build.TED_INCREMENTAL_TRACKER_ADDR]
    live_runtime = runtime.rstrip(b"\x00")
    writer = runtime[:build.TED_INCREMENTAL_TRACKER_EXIT_ADDR
                     - build.TED_INCREMENTAL_TRACKER_ADDR]
    raw_test = writer.find(bytes.fromhex("1A 13 FE 06"))
    first_classifier = writer.find(bytes.fromhex("CD 03 D5"))
    crown_record = writer.find(bytes.fromhex("E5 21 41 D8 73 23 72 E1"))
    writer_controls = {
        "raw_tile_06_test_offset": raw_test,
        "crown_record_offset": crown_record,
        "first_classifier_call_offset": first_classifier,
        "raw_test_precedes_record_and_classifier": (
            0 <= raw_test < crown_record < first_classifier
        ),
    }
    private_source = fragments[build.TED_TABLE_ADDR + 68]
    page_tail = fragments[build.TED_TABLE_ADDR + 68 + len(private_source)]
    repair_entry = fragments[build.TED_ENVELOPE_COMPARE_ROM_ADDR]
    renderer_controls = {
        "clear_draw_mode_sequence_present": bytes.fromhex(
            "7D C6 10 3F 9F CD 00 65"
        ) in page_tail,
        "repair_masks_desired_to_nibble": repair_entry.startswith(
            bytes.fromhex("E6 0F")
        ),
    }
    old_block_major = os.environ.get(build.TED_BLOCK_MAJOR_ENV)
    os.environ[build.TED_BLOCK_MAJOR_ENV] = "1"
    try:
        single_writer = build.build_ted_direct_single_writer_helpers()
    finally:
        if old_block_major is None:
            os.environ.pop(build.TED_BLOCK_MAJOR_ENV, None)
        else:
            os.environ[build.TED_BLOCK_MAJOR_ENV] = old_block_major
    single_writer_controls = {
        "bytes": len(single_writer),
        "available_before_installer_5e48": 64,
        "ends_with_balanced_pop_af_ret": single_writer.endswith(
            bytes.fromhex("E1 D1 C1 F1 C9")
        ),
        "uses_private_reverse_lut": bytes.fromhex(
            "7A 2F 6F 26 D5 7E 02"
        ) in single_writer,
        "fits_before_installer_5e48": len(single_writer) <= 64,
    }
    publisher_controls = {
        "required_fixed_caller": "CD80DB",
        "gate_entry": "DB80",
        "invalid_mid_instruction_entry": "DB87",
    }
    whole = b"".join(
        address.to_bytes(2, "little") + len(payload).to_bytes(2, "little")
        + payload
        for address, payload in sorted(fragments.items())
    )
    provenance = []
    for rom_path in REFERENCE_ROMS:
        rom = rom_path.read_bytes()
        bank13 = 13 * 0x4000
        for address, capacity in PRIVATE_CAVES:
            start = bank13 + address - 0x4000
            native = rom[start:start + capacity]
            references = []
            # Only fixed bank 0 and bank 13 can address these bank-13 caves.
            for target in range(address, address + capacity):
                needle = target.to_bytes(2, "little")
                for region_start, region_end in ((0, 0x4000), (bank13, bank13 + 0x4000)):
                    cursor = region_start
                    while True:
                        operand = rom.find(needle, cursor, region_end)
                        if operand < 0:
                            break
                        opcode = rom[operand - 1] if operand > region_start else -1
                        if opcode in ABSOLUTE_OPERAND_OPCODES:
                            references.append({
                                "rom_offset": f"{operand - 1:05X}",
                                "target": f"{target:04X}",
                                "opcode": f"{opcode:02X}",
                            })
                        cursor = operand + 1
            provenance.append({
                "rom": str(rom_path.relative_to(ROOT)),
                "start": f"{address:04X}",
                "end": f"{address + capacity - 1:04X}",
                "capacity": capacity,
                "native_hex": native.hex(),
                "native_all_zero": native == bytes(capacity),
                "fixed_or_bank13_absolute_references": references,
                "retired_block_major_owner": (
                    address == build.TED_ENVELOPE_COMPARE_ROM_ADDR
                    and rom_path.name == "penta_dragon_dx_FIXED.gb"
                    and native == build.build_ted_inside_envelope_rom()[0]
                ),
            })
    candidate = None
    candidate_mismatches = []
    if args.candidate_rom:
        candidate_bytes = args.candidate_rom.read_bytes()
        bank13 = 13 * 0x4000
        for address, payload in sorted(fragments.items()):
            if address >= 0x8000:
                continue
            offset = bank13 + address - 0x4000
            actual = candidate_bytes[offset:offset + len(payload)]
            if actual != payload:
                candidate_mismatches.append({
                    "start": f"{address:04X}",
                    "expected_sha256": hashlib.sha256(payload).hexdigest(),
                    "actual_sha256": hashlib.sha256(actual).hexdigest(),
                })
        helper_cursor = 0
        for address, capacity in build.TED_DIRECT_FIXED_HELPER_SOURCE_CHUNKS:
            payload = single_writer[helper_cursor:helper_cursor + capacity]
            helper_cursor += len(payload)
            if not payload:
                continue
            offset = bank13 + address - 0x4000
            actual = candidate_bytes[offset:offset + len(payload)]
            if actual != payload:
                candidate_mismatches.append({
                    "start": f"{address:04X}",
                    "owner": "block-major single-writer helper",
                    "expected_sha256": hashlib.sha256(payload).hexdigest(),
                    "actual_sha256": hashlib.sha256(actual).hexdigest(),
                })
        assert helper_cursor == len(single_writer)
        publisher_controls["candidate_fixed_caller"] = candidate_bytes[
            0x028A:0x028D
        ].hex().upper()
        publisher_controls["candidate_enters_gate"] = (
            candidate_bytes[0x028A:0x028D] == bytes.fromhex("CD 80 DB")
        )
        if not publisher_controls["candidate_enters_gate"]:
            candidate_mismatches.append({
                "start": "028A",
                "owner": "block-major DB80 publisher caller",
                "expected_hex": "CD80DB",
                "actual_hex": candidate_bytes[0x028A:0x028D].hex().upper(),
            })
        candidate = {
            "path": str(args.candidate_rom),
            "bytes": len(candidate_bytes),
            "sha256": hashlib.sha256(candidate_bytes).hexdigest(),
            "fragment_mismatches": candidate_mismatches,
        }
    passed = (
        not protected_overlaps
        and len(runtime) == 155
        and len(live_runtime) == 155
        and len(private_source) == 121
        and len(page_tail) == 67
        and build.TED_TABLE_ADDR + 68 + len(private_source) == 0x76BD
        and writer_controls["raw_test_precedes_record_and_classifier"]
        and all(renderer_controls.values())
        and all(
            value
            for key, value in single_writer_controls.items()
            if key not in {"bytes", "available_before_installer_5e48"}
        )
        and all(
            (
                row["native_all_zero"]
                and not row["fixed_or_bank13_absolute_references"]
            ) or row["retired_block_major_owner"]
            for row in provenance
        )
        and not candidate_mismatches
    )
    report = {
        "schema": "penta-ted-block-major-exact-fit-v1",
        "status": "pass" if passed else "fail",
        "runtime_candidate": True,
        "environment": build.TED_BLOCK_MAJOR_ENV,
        "whole_fragment_sha256": hashlib.sha256(whole).hexdigest(),
        "runtime": {
            "allocated_bytes": len(runtime),
            "live_bytes": len(live_runtime),
            "capacity_bytes": 155,
        },
        "private_source_bytes": len(private_source),
        "page_tail_bytes": len(page_tail),
        "writer_controls": writer_controls,
        "renderer_controls": renderer_controls,
        "single_writer_controls": single_writer_controls,
        "publisher_controls": publisher_controls,
        "protected_range_overlaps": protected_overlaps,
        "private_cave_provenance": provenance,
        "candidate": candidate,
        "fragments": rows,
        "remaining_runtime_gate": "emulator semantic/cadence receipts",
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
