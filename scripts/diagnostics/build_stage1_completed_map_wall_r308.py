#!/usr/bin/env python3
"""Build r308: repair 35 room-$01 wall attrs on the completed map.

r305 fixes the relocated scene-$0B publisher but still exposes the completed
room-$01 map for six frames before later semantic hazard rows repaint its
dual-use wall IDs.  r306 proved that changing the later bank-20 row dispatch
cannot affect this prepublication window.

Reuse r294's reviewed transition-only algorithm and exact position oracle.
The release restores bank 14 to native layout, so the helper is relocated to
receipt-proven erased space after r305's bank-31 multiplexer.  Native bank 19
$6F68 already receives the exact completed-map high byte in D and gates the
committed room at FFBD.  A bank-14 helper writes the 35 invariant room-$01
companion positions (18 HBlank intervals) on D:000 only, preserves the stock
room-$12 repair, and performs no write for room $05 or any other room.  This
strict causal candidate is based directly on r305; rejected r306 and the
separate bank-16 installer hardening are excluded.  No emulator is invoked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import build_stage1_room01_wall_context_r294 as r294
import build_stage1_unified_scene0b_r305 as r305


ROOT = r305.ROOT
TMP = r305.TMP
BASE = r305.DEFAULT_OUTPUT
BASE_RECEIPT = r305.DEFAULT_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-completed-map-wall-r308/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-completed-map-wall-r308/build-receipt.json"

BASE_SHA256 = r305.EXPECTED_CANDIDATE_SHA256
BASE_RECEIPT_SHA256 = (
    "71a3a477a2be2fad9f0f83e24b9bdf6cacd940c7d772a546658bbaca1166c450"
)
R305_LIVE_REJECTION = BASE.parent / "live-scene0b-dcbb40/receipt.json"
R305_LIVE_REJECTION_SHA256 = (
    "7ceca21f33dabaf91437934549ba1fa1960f42bd4b03b901370b67f445a513b7"
)
R306_LIVE_REJECTION = (
    TMP / "stage1-effective-room-trampolines-r306/"
    "live-scene0b-dcbb40/receipt.json"
)
R306_LIVE_REJECTION_SHA256 = (
    "9e1f6d683202f8fc5847fb851b0cc615a7d7bf1ff1aa2ae7e134232314884452"
)
R308_LIVE_REJECTION = DEFAULT_OUTPUT.parent / "live-scene0b-dcbb40/receipt.json"
R308_LIVE_REJECTION_SHA256 = (
    "2cdd1f522e9f8e3ef871181657ecc765685e097cacd8cd140235f9273b3968c0"
)
EXPECTED_CANDIDATE_SHA256 = (
    "5656241b51558b59c7a708754da32f7f7c9e9601a0719c91268f860f4f13c088"
)

BANK_SIZE = r294.BANK_SIZE
LIVE_BANK = r294.LIVE_BANK
AUX_BANK = 31
DISPATCH_ADDR = r294.DISPATCH_ADDR
LIVE_DISPATCH_SIZE = r294.LIVE_DISPATCH_SIZE
LIVE_RETURN_ADDR = r294.LIVE_RETURN_ADDR
AUX_ENTRY_ADDR = 0x6F6D
AUX_RETURN_ADDR = 0x6F70
REPAIR_ADDR = 0x6D00
ROW_WRITER_ADDR = 0x6D70
PAIR_WRITER_ADDR = 0x6D90
OLD_LIVE_DISPATCH = r294.OLD_LIVE_DISPATCH
ROW_WRITER = r294.ROW_WRITER
PAIR_WRITER = r294.PAIR_WRITER
LIVE_STUB = bytearray(LIVE_DISPATCH_SIZE)
LIVE_STUB[:5] = bytes.fromhex("3E 1F CD 61 00")
LIVE_STUB[LIVE_RETURN_ADDR - DISPATCH_ADDR] = 0xC9
LIVE_STUB = bytes(LIVE_STUB)
AUX_ENTRY = bytes((0xC3, REPAIR_ADDR & 0xFF, REPAIR_ADDR >> 8))
AUX_RETURN = bytes.fromhex("3E 13 CD 61 00")
CHECKSUM_OFFSETS = r305.CHECKSUM_OFFSETS


def relocate_r294_repair() -> bytes:
    """Rebase only r294's absolute helper CALLs and repair/return JPs."""
    result = bytearray(r294.build_repair())
    replacements = (
        (r294.PAIR_WRITER_ADDR, PAIR_WRITER_ADDR, 5),
        (r294.ROW_WRITER_ADDR, ROW_WRITER_ADDR, 4),
        (r294.AUX_RETURN_ADDR, AUX_RETURN_ADDR, 3),
    )
    for old, new, expected_count in replacements:
        count = 0
        for index in range(len(result) - 2):
            if (result[index] in (0xCD, 0xC3)
                    and result[index + 1:index + 3]
                    == old.to_bytes(2, "little")):
                result[index + 1:index + 3] = new.to_bytes(2, "little")
                count += 1
        r305.r304.require(count == expected_count,
                          f"r294 relocation count changed for ${old:04X}")
    return bytes(result)


REPAIR = relocate_r294_repair()

EXPECTED_COMPONENT_SHA256 = {
    "repair": "cc117924abb2f6683e249f2a3b1fa5b81823906a8eab0b079d0d389537a0d84e",
    "row_writer": "876d9a8893cb1832ccc20394dab1675f6d143ea083674410ca9096bd399c9367",
    "pair_writer": "d8249222fba996399e0ed5bbc97db5102b198ca088836b38b3530f84d5692c04",
}


def bank_offset(bank: int, address: int) -> int:
    return r305.r304.bank_offset(bank, address)


def component_contract() -> dict[str, Any]:
    components = {
        "repair": REPAIR,
        "row_writer": ROW_WRITER,
        "pair_writer": PAIR_WRITER,
    }
    for name, payload in components.items():
        r305.r304.require(
            r305.r304.digest(payload) == EXPECTED_COMPONENT_SHA256[name],
            f"audited r294 {name} changed",
        )
    r305.r304.require(len(REPAIR) == 99, "r294 repair width changed")
    r305.r304.require(len(ROW_WRITER) == 27, "r294 row writer width changed")
    r305.r304.require(len(PAIR_WRITER) == 31,
                      "r294 pair writer width changed")
    return {
        name: {
            "bytes": len(payload),
            "sha256": EXPECTED_COMPONENT_SHA256[name],
        }
        for name, payload in components.items()
    }


def room01_offsets() -> tuple[int, ...]:
    return tuple(sorted(row * 32 + column
                        for row, column in r294.ROOM01_TARGET_CELLS))


def writes_for(room: int, destination_h: int) -> tuple[int, ...]:
    r305.r304.require(destination_h in (0x98, 0x9C),
                      "model destination must be a physical BG map")
    if room != 1:
        return ()
    return tuple((destination_h << 8) + offset for offset in room01_offsets())


def semantic_contract(source: bytes) -> dict[str, Any]:
    packed = r294.ROOM01_CAPTURE.read_bytes()
    r305.r304.require(len(packed) == 24 * 24,
                      "room01 packed capture width changed")
    packed_positions = {
        row * 24 + column for row, column in r294.ROOM01_TARGET_CELLS
    }
    physical = set(room01_offsets())
    r305.r304.require(len(packed_positions) == len(physical) == 35,
                      "fixed wall position count changed")
    r305.r304.require(
        {packed[index] for index in packed_positions} == {0x24, 0x27, 0x30, 0x33},
        "fixed positions no longer contain only reviewed dual-use IDs",
    )

    # The immutable compiler LUT remains the room05/default negative control.
    table = bank_offset(13, 0x7000)
    r305.r304.require(
        all((source[table + tile] & 7) == 0
            for tile in (0x24, 0x27, 0x30, 0x33)),
        "default target semantics are no longer BG0",
    )

    maps = []
    for destination_h, other_h in ((0x98, 0x9C), (0x9C, 0x98)):
        writes = set(writes_for(1, destination_h))
        expected = {(destination_h << 8) + offset for offset in physical}
        r305.r304.require(writes == expected and len(writes) == 35,
                          "exact completed-map write set changed")
        r305.r304.require(
            all(not (other_h << 8) <= address < (other_h << 8) + 0x400
                for address in writes),
            "repair touched outgoing/other physical map",
        )
        maps.append({
            "D": f"{destination_h:02X}",
            "unique_cells": len(writes),
            "first": f"${min(writes):04X}",
            "last": f"${max(writes):04X}",
            "other_map_touched": False,
        })
    r305.r304.require(writes_for(5, 0x98) == writes_for(5, 0x9C) == (),
                      "room05 negative control performed a repair write")

    # Model the exact post-repair values without assuming either physical map
    # starts clear.  Only the 35 reviewed cells become BG6 in room01.
    seed = [(index * 29 + 11) & 7 for index in range(0x400)]
    after = list(seed)
    for offset in physical:
        after[offset] = 6
    r305.r304.require(
        all(after[index] == (6 if index in physical else seed[index])
            for index in range(0x400)),
        "room01 physical-map value model escaped target cells",
    )
    return {
        "packed_capture_sha256": r305.r304.digest(packed),
        "packed_stride": 24,
        "physical_stride": 32,
        "reviewed_tile_ids": ["24", "27", "30", "33"],
        "fixed_positions": 35,
        "hblank_intervals": 18,
        "completed_map_models": maps,
        "room01_value": "06",
        "room05_repair_writes": 0,
        "room05_default_LUT_value": "00",
        "non_target_cells_changed": 0,
    }


def owned_ranges() -> set[int]:
    live = bank_offset(LIVE_BANK, DISPATCH_ADDR)
    repair = bank_offset(AUX_BANK, REPAIR_ADDR)
    row = bank_offset(AUX_BANK, ROW_WRITER_ADDR)
    pair = bank_offset(AUX_BANK, PAIR_WRITER_ADDR)
    entry = bank_offset(AUX_BANK, AUX_ENTRY_ADDR)
    return (
        set(range(live, live + len(LIVE_STUB)))
        | set(range(repair, repair + len(REPAIR)))
        | set(range(row, row + len(ROW_WRITER)))
        | set(range(pair, pair + len(PAIR_WRITER)))
        | set(range(entry, entry + 8))
    )


def validate_live_rejections() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for revision, path, expected_sha, expected_rom in (
        ("r305", R305_LIVE_REJECTION, R305_LIVE_REJECTION_SHA256, BASE_SHA256),
        ("r306", R306_LIVE_REJECTION, R306_LIVE_REJECTION_SHA256,
         "8e170f2eaf3f718c924f47ac3be0c7dec1b5433ffd3975a5f5e299a7a60fb06d"),
    ):
        payload = path.read_bytes()
        r305.r304.require(r305.r304.digest(payload) == expected_sha,
                          f"{revision} live receipt identity changed")
        result = json.loads(payload)
        r305.r304.require(result.get("rom_sha256") == expected_rom,
                          f"{revision} live receipt names another ROM")
        r305.r304.require(result.get("passed") is False,
                          f"{revision} receipt is not a rejection")
        mismatch = result.get("hazard_mismatch_frames", {})
        r305.r304.require(mismatch.get("first", {}).get("sample") == 75,
                          f"{revision} transient signature changed")
        results[revision] = {
            "receipt_sha256": expected_sha,
            "rom_sha256": expected_rom,
            "first_mismatch_sample": mismatch["first"]["sample"],
            "mismatch_frames": mismatch["total"],
        }
    r305.r304.require(results["r306"]["mismatch_frames"] == 56,
                      "r306 rejection frame count changed")
    return results


def validate_self_rejection() -> dict[str, Any]:
    payload = R308_LIVE_REJECTION.read_bytes()
    r305.r304.require(r305.r304.digest(payload) == R308_LIVE_REJECTION_SHA256,
                      "r308 live rejection identity changed")
    result = json.loads(payload)
    mismatches = result.get("hazard_mismatch_frames", {})
    counters = result.get("hazard_publication_counters", {})
    r305.r304.require(
        result.get("rom_sha256") == EXPECTED_CANDIDATE_SHA256
        and result.get("passed") is False
        and mismatches.get("total") == 160
        and mismatches.get("first", {}).get("sample") == 73,
        "r308 live rejection signature changed",
    )
    r305.r304.require(
        counters.get("scene0b_decider_dirty") == 14
        and counters.get("scene0b_dirty_copy") == 15
        and counters.get("scene0b_mapdone_odd") == 15,
        "r308 transaction phase-shift signature changed",
    )
    return {
        "receipt_sha256": R308_LIVE_REJECTION_SHA256,
        "rom_sha256": EXPECTED_CANDIDATE_SHA256,
        "passed": False,
        "mismatch_frames": 160,
        "first_mismatch_sample": 73,
        "scene0b_transaction_counts": {
            "decider_dirty": 14,
            "dirty_copy": 15,
            "mapdone_odd": 15,
        },
        "conclusion": (
            "postcompile positions are overwritten by later publications; "
            "transition hook also phase-shifts one transaction"
        ),
    }


def validate_preimages(source: bytes) -> dict[str, Any]:
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "wrong exact r305 base")
    live = bank_offset(LIVE_BANK, DISPATCH_ADDR)
    r305.r304.require(source[live:live + LIVE_DISPATCH_SIZE]
                      == OLD_LIVE_DISPATCH,
                      "native room12 transition helper changed")
    # The native call site enters immediately after the exact Stage-1 guard.
    call_site = bank_offset(LIVE_BANK, 0x55C3)
    call_preimage = bytes.fromhex("F0 B7 FE 02 00 00 00 C0 CD 68 6F")
    r305.r304.require(source[call_site:call_site + len(call_preimage)]
                      == call_preimage,
                      "transition-only call site changed")

    repair = bank_offset(AUX_BANK, REPAIR_ADDR)
    row = bank_offset(AUX_BANK, ROW_WRITER_ADDR)
    pair = bank_offset(AUX_BANK, PAIR_WRITER_ADDR)
    entry = bank_offset(AUX_BANK, AUX_ENTRY_ADDR)
    r305.r304.require(source[repair:repair + len(REPAIR)]
                      == bytes([0xFF]) * len(REPAIR),
                      "bank31 repair cave changed")
    r305.r304.require(source[row:row + len(ROW_WRITER)]
                      == bytes([0xFF]) * len(ROW_WRITER),
                      "bank31 row writer cave changed")
    r305.r304.require(source[pair:pair + len(PAIR_WRITER)]
                      == bytes([0xFF]) * len(PAIR_WRITER),
                      "bank31 pair writer cave changed")
    r305.r304.require(source[entry:entry + 8] == bytes([0xFF]) * 8,
                      "bank31 mapper landing changed")
    mux = bank_offset(r305.BANK31, r305.MUX_ADDR)
    r305.r304.require(source[mux:mux + len(r305.MUX)] == r305.MUX,
                      "r305 bank31 mux changed")
    r305.r304.require(REPAIR_ADDR > r305.MUX_ADDR + len(r305.MUX),
                      "wall repair overlaps r305 bank31 mux")
    return {
        "native_call": "bank19:$55CB CALL $6F68",
        "native_gate": "FFB7=02 transition path",
        "native_dispatch_preimage": "bank19:$6F68 FFBD=$12 gate",
        "destination_abi": "D is exact completed physical map high byte",
        "bank31_private_caves_erased": True,
        "bank14_release_layout_untouched": True,
    }


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    r305.r304.require(len(source) == len(candidate) == r305.r304.ROM_SIZE,
                      "ROM size changed")
    changed = r305.r304.delta(source, candidate)
    functional = r305.r304.delta(source, candidate, functional=True)
    allowed = owned_ranges() | CHECKSUM_OFFSETS
    r305.r304.require(changed <= allowed,
                      f"r308 escaped ownership: {sorted(changed-allowed)[:8]}")
    expected = {offset for offset in owned_ranges()
                if source[offset] != candidate[offset]}
    r305.r304.require(functional == expected,
                      "r308 functional delta differs from reviewed patch")

    live = bank_offset(LIVE_BANK, DISPATCH_ADDR)
    repair = bank_offset(AUX_BANK, REPAIR_ADDR)
    row = bank_offset(AUX_BANK, ROW_WRITER_ADDR)
    pair = bank_offset(AUX_BANK, PAIR_WRITER_ADDR)
    entry = bank_offset(AUX_BANK, AUX_ENTRY_ADDR)
    r305.r304.require(candidate[live:live + len(LIVE_STUB)] == LIVE_STUB,
                      "live bank19 bridge changed")
    r305.r304.require(candidate[repair:repair + len(REPAIR)] == REPAIR,
                      "r294 repair changed")
    r305.r304.require(candidate[row:row + len(ROW_WRITER)] == ROW_WRITER,
                      "r294 row writer changed")
    r305.r304.require(candidate[pair:pair + len(PAIR_WRITER)] == PAIR_WRITER,
                      "r294 pair writer changed")
    r305.r304.require(candidate[entry:entry + 3] == AUX_ENTRY,
                      "bank31 repair entry changed")
    r305.r304.require(candidate[entry + 3:entry + 8] == AUX_RETURN,
                      "bank31 bank19 return changed")

    # The rejected FFE5 diagnostic and modular bank16 hardening are absent.
    for address in r305.r303.r300.TRAMPOLINE_ADDRS:
        offset = bank_offset(r305.r303.r300.SEMANTIC_BANK, address)
        r305.r304.require(candidate[offset:offset + 9]
                          == source[offset:offset + 9]
                          == r305.r303.r300.CONTEXT_TRAMPOLINE,
                          "rejected r306 operand leaked into r308")
    bank16 = slice(16 * BANK_SIZE, 17 * BANK_SIZE)
    r305.r304.require(candidate[bank16] == source[bank16],
                      "modular bank16 hardening leaked into r308")
    bank14 = slice(14 * BANK_SIZE, 15 * BANK_SIZE)
    r305.r304.require(candidate[bank14] == source[bank14],
                      "r308 touched restored native bank14")
    return {
        "functional_changed_bytes": len(functional),
        "changed_offsets": [f"0x{x:06X}" for x in sorted(functional)],
        "escaped_bytes": 0,
        "r305_outside_wall_component_exact": True,
        "rejected_r306_excluded": True,
        "modular_bank16_hardening_excluded": True,
        "native_bank14_byte_exact": True,
    }


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    r305.r304.require(r305.r304.digest(base_receipt_bytes)
                      == BASE_RECEIPT_SHA256,
                      "r305 build receipt identity changed")
    base_receipt = json.loads(base_receipt_bytes)
    r305.r304.require(base_receipt.get("candidate_sha256") == BASE_SHA256,
                      "r305 receipt names another ROM")
    components = component_contract()
    preimages = validate_preimages(source)
    semantic = semantic_contract(source)
    rejections = validate_live_rejections()
    self_rejection = validate_self_rejection()

    rom = bytearray(source)
    allowed: set[int] = set()
    r305.patch_exact(
        rom, source, bank_offset(LIVE_BANK, DISPATCH_ADDR),
        OLD_LIVE_DISPATCH, LIVE_STUB, allowed,
        "transition-only bank31 wall bridge",
    )
    r305.patch_exact(
        rom, source, bank_offset(AUX_BANK, REPAIR_ADDR),
        bytes([0xFF]) * len(REPAIR), REPAIR, allowed,
        "exact r294 contextual wall repair",
    )
    r305.patch_exact(
        rom, source, bank_offset(AUX_BANK, ROW_WRITER_ADDR),
        bytes([0xFF]) * len(ROW_WRITER), ROW_WRITER, allowed,
        "exact r294 room12 row writer",
    )
    r305.patch_exact(
        rom, source, bank_offset(AUX_BANK, PAIR_WRITER_ADDR),
        bytes([0xFF]) * len(PAIR_WRITER), PAIR_WRITER, allowed,
        "exact r294 room01 pair writer",
    )
    entry = bank_offset(AUX_BANK, AUX_ENTRY_ADDR)
    r305.patch_exact(
        rom, source, entry, bytes([0xFF]) * 3, AUX_ENTRY, allowed,
        "bank31 repair landing",
    )
    r305.patch_exact(
        rom, source, entry + 3, bytes([0xFF]) * 5, AUX_RETURN, allowed,
        "bank19 mapper return",
    )
    r305.r304.require(allowed == owned_ranges(),
                      "ownership construction drifted")
    r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    sha = r305.r304.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r305.r304.require(sha == EXPECTED_CANDIDATE_SHA256,
                          f"candidate identity drift: {sha}")

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-completed-map-wall-r308-build-v1",
        "status": "LIVE_REJECTED",
        "promotable": False,
        "emulator_invoked": False,
        "base": {
            "revision": "r305-live-rejected-wall-transient",
            "candidate_sha256": BASE_SHA256,
            "build_receipt_sha256": BASE_RECEIPT_SHA256,
        },
        "candidate_sha256": sha,
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "causal_rejections": rejections,
        "live_rejection": self_rejection,
        "root_cause": (
            "room01 dual-use wall cells are published from the default BG0 "
            "semantic LUT before later hazard rows can select room-local BG6"
        ),
        "patch": {
            "live_bridge": "bank19:$6F68-$6F8A",
            "repair": f"bank31:${REPAIR_ADDR:04X}-${REPAIR_ADDR+len(REPAIR)-1:04X}",
            "row_writer": f"bank31:${ROW_WRITER_ADDR:04X}-${ROW_WRITER_ADDR+len(ROW_WRITER)-1:04X}",
            "pair_writer": f"bank31:${PAIR_WRITER_ADDR:04X}-${PAIR_WRITER_ADDR+len(PAIR_WRITER)-1:04X}",
            "mapper_landing": "bank31:$6F6D-$6F74",
            "audited_r294_components": components,
        },
        "offline_contract": {
            "preimages": preimages,
            "semantic": semantic,
            "abi": {
                "destination": "D:000 exact completed map only",
                "outgoing_map_written": False,
                "room05_writes": 0,
                "room12_native_semantics_preserved": True,
                "VBK_restored": 0,
                "ROM_bank_restored": 19,
                "SVBK_untouched": True,
            },
            "timing": {
                "ordinary_frame_delta_t_cycles": 0,
                "renderer_delta_t_cycles": 0,
                "room01_hblank_intervals": 18,
                "room01_unique_writes": 35,
                "room05_dispatch_overhead_t_cycles": 268,
                "scope": "transition helper only",
            },
        },
        "ownership": ownership,
        "required_live_gates": [
            "REJECTED: room01 entry retained/persisted target attr mismatches",
            "room01 exit/room05 completed map retains BG0 target semantics",
            "only D-selected completed physical map is written",
            "room12 seam repair remains exact",
            "r305 FFA5 remains 99/9D",
            "full reported-regression and speed gates",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r305.r304.checked_output(args.output, "candidate output")
    receipt_path = r305.r304.checked_output(args.receipt, "receipt output")
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_bytes(r305.r304.receipt_bytes(receipt))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
