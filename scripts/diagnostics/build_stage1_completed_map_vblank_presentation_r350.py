#!/usr/bin/env python3
"""Build r350: VBlank-present the compiler's completed physical map.

The r349 event trace proved that Stage-1 publication is not always a peer-map
operation.  Hazard animation compiles the peer map, while native menu repair
can compile the map that is already displayed.  A relative LCDC toggle exposes
the unfinished peer in the latter case; reading HDMA3 later is also invalid
because hardware transfer state overwrites it.

r350 saves the completed map's raw H at bank1:$42ED directly in DF5C, then
arms a separate DF5D pending flag only at the fixed publication boundary.
The VBlank service consumes that flag and merges the saved map bit into the
current LCDC without changing its window or sprite controls.  No emulator is
invoked by this builder.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import build_stage1_deferred_vblank_presentation_r347 as r347


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
DEFAULT_OUTPUT = TMP / "stage1-completed-map-vblank-presentation-r350/candidate.gb"
DEFAULT_RECEIPT = (
    TMP / "stage1-completed-map-vblank-presentation-r350/build-receipt.json"
)
EXPECTED_CANDIDATE_SHA256 = (
    "a56ab3f2ee6d094088c71f931434a63b3471b2b63b9c018d9d5597300d1a9afe"
)

MAP_DONE_ADDR = 0x42ED
MAP_DONE_OLD = bytes.fromhex(
    "7C E0 53 F0 01 1F 38 07 CD F1 DB 00 FB C9 00"
)
MAP_DONE_NEW = bytes.fromhex(
    "7C EA 5C DF F0 01 1F 38 06 CD F1 DB FB C9 00"
)
TARGET_ADDR = 0xDF5C
PENDING_ADDR = 0xDF5D

NEW_PRIMARY = bytes.fromhex(
    "F3 F0 40 07 38 16 "                  # DI; LCD enabled -> deferred
    "FA 00 DC E6 0F E0 43 "              # LCD off: immediate SCX
    "FA 02 DC E6 0F E0 42 "              # LCD off: immediate SCY
    "F0 40 EE 08 E0 40 18 05 "           # LCD off: peer map; skip arm
    "3E 01 EA 5D DF "                    # LCD on: arm completed-map target
    "FB C9"                               # restore IME; return
)

COMMIT_HELPER = bytes.fromhex(
    "FA 5D DF B7 CA 1D 6F "               # no pending publication -> wrapper
    "AF EA 5D DF "                        # consume pending flag
    "F0 97 FE 02 28 07 "                  # preserve stock SCX-skip policy
    "FA 00 DC E6 0F E0 43 "              # SCX
    "FA 02 DC E6 0F E0 42 "              # SCY
    "FA 5C DF E6 04 07 47 "               # completed H bit 2 -> LCDC bit 3
    "F0 40 E6 F7 B0 E0 40 "              # merge map into current LCDC
    "C3 1D 6F"                            # established wrapper
)


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    r347.require(len(source) == r347.ROM_SIZE,
                 "r345 base is not exactly 512 KiB")
    r347.require(r347.digest(source) == r347.BASE_SHA256,
                 f"wrong exact r345 base: {r347.digest(source)}")
    r347.require(r347.digest(base_receipt_bytes) == r347.BASE_RECEIPT_SHA256,
                 "r345 base receipt identity drifted")
    base_receipt = json.loads(base_receipt_bytes)
    r347.require(base_receipt.get("schema") == r347.BASE_SCHEMA,
                 "r345 base receipt schema drifted")
    r347.require(base_receipt.get("candidate_sha256") == r347.BASE_SHA256,
                 "r345 base receipt names another candidate")
    r347.require(source[MAP_DONE_ADDR:MAP_DONE_ADDR + len(MAP_DONE_OLD)]
                 == MAP_DONE_OLD, "r345 map-done preimage drifted")
    r347.require(source[r347.PRIMARY_ADDR:r347.PRIMARY_END] == r347.OLD_PRIMARY,
                 "r345 primary publisher preimage drifted")
    r347.require(len(MAP_DONE_OLD) == len(MAP_DONE_NEW) == 15,
                 "map-done width changed")
    r347.require(len(r347.OLD_PRIMARY) == len(NEW_PRIMARY) == 35,
                 "primary publisher width changed")
    r347.require(
        source[r347.VBLANK_HOOK_CALL_ADDR:r347.VBLANK_HOOK_CALL_ADDR + 3]
        == r347.OLD_HOOK_CALL,
        "VBlank wrapper call preimage drifted",
    )
    r347.require(
        source[r347.COMMIT_FILE_OFFSET:
               r347.COMMIT_FILE_OFFSET + len(COMMIT_HELPER)]
        == bytes(len(COMMIT_HELPER)),
        "bank-13 commit cave is not zero",
    )
    r347.require(
        source[0x06D1:0x06D5] == bytes.fromhex("F5 C5 D5 E5"),
        "outer VBlank handler no longer preserves AF/BC/DE/HL",
    )
    for opcode in (
        bytes([0xCD, r347.COMMIT_ADDR & 0xFF, r347.COMMIT_ADDR >> 8]),
        bytes([0xC3, r347.COMMIT_ADDR & 0xFF, r347.COMMIT_ADDR >> 8]),
        bytes.fromhex("FA 5C DF"), bytes.fromhex("EA 5C DF"),
        bytes.fromhex("FA 5D DF"), bytes.fromhex("EA 5D DF"),
    ):
        r347.require(source.count(opcode) == 0,
                     "r350-owned hook/latch already has an owner")

    r347.require(MAP_DONE_ADDR + 9 + MAP_DONE_NEW[8] == 0x42FC,
                 "map-done dirty branch no longer targets compiler")
    r347.require(MAP_DONE_NEW[:4] == bytes.fromhex("7C EA 5C DF"),
                 "completed H is not saved directly in DF5C")
    r347.require(MAP_DONE_NEW[12:15] == bytes.fromhex("FB C9 00"),
                 "map-done pure path lost EI/RET/unreachable pad")
    r347.require(r347.PRIMARY_ADDR + 6 + NEW_PRIMARY[5]
                 == r347.PRIMARY_ADDR + 28,
                 "LCD-enabled branch does not target pending arm")
    r347.require(r347.PRIMARY_ADDR + 28 + NEW_PRIMARY[27]
                 == r347.PRIMARY_ADDR + 33,
                 "LCD-off branch does not skip pending arm")
    r347.require(NEW_PRIMARY[28:33] == bytes.fromhex("3E 01 EA 5D DF"),
                 "main publisher does not arm DF5D")
    r347.require(COMMIT_HELPER.count(bytes.fromhex("E0 40")) == 1,
                 "VBlank helper map write count changed")
    r347.require(bytes.fromhex("FA 5C DF E6 04 07 47") in COMMIT_HELPER,
                 "VBlank helper does not decode completed physical map")
    r347.require(bytes.fromhex("F0 40 E6 F7 B0 E0 40") in COMMIT_HELPER,
                 "VBlank helper does not preserve non-map LCDC bits")
    r347.require(COMMIT_HELPER[-3:] == bytes.fromhex("C3 1D 6F"),
                 "VBlank helper does not tail-jump to established wrapper")

    rom = bytearray(source)
    rom[MAP_DONE_ADDR:MAP_DONE_ADDR + len(MAP_DONE_NEW)] = MAP_DONE_NEW
    rom[r347.PRIMARY_ADDR:r347.PRIMARY_END] = NEW_PRIMARY
    rom[
        r347.VBLANK_HOOK_CALL_ADDR:r347.VBLANK_HOOK_CALL_ADDR + 3
    ] = r347.NEW_HOOK_CALL
    rom[
        r347.COMMIT_FILE_OFFSET:r347.COMMIT_FILE_OFFSET + len(COMMIT_HELPER)
    ] = COMMIT_HELPER
    r347.update_checksums(rom)
    candidate = bytes(rom)

    owned = set(range(MAP_DONE_ADDR, MAP_DONE_ADDR + len(MAP_DONE_NEW)))
    owned.update(range(r347.PRIMARY_ADDR, r347.PRIMARY_END))
    owned.update(range(
        r347.VBLANK_HOOK_CALL_ADDR, r347.VBLANK_HOOK_CALL_ADDR + 3,
    ))
    owned.update(range(
        r347.COMMIT_FILE_OFFSET,
        r347.COMMIT_FILE_OFFSET + len(COMMIT_HELPER),
    ))
    changed = {
        index for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    r347.require(changed <= owned | r347.CHECKSUM_OFFSETS,
                 f"r350 escaped owned bytes: "
                 f"{sorted(changed - owned - r347.CHECKSUM_OFFSETS)}")

    candidate_sha = r347.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        r347.require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
                     f"candidate identity drift: {candidate_sha}")
    receipt: dict[str, object] = {
        "schema": "penta-stage1-completed-map-vblank-presentation-r350-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r345_sha256": r347.BASE_SHA256,
        "base_receipt_sha256": r347.BASE_RECEIPT_SHA256,
        "candidate_sha256": candidate_sha,
        "rejected_candidates": {
            "r347": {
                "sha256": r347.EXPECTED_CANDIDATE_SHA256,
                "fault": "relative toggle exposes peer during active-page menu repair",
            },
            "r348": {
                "sha256": "72daa7dc52122134681fd14eeb03dd49709abb3e61ac68e43e221709bb7e7e5c",
                "fault": "post-transfer HDMA3 pins rotating-hazard presentation",
            },
            "r349": {
                "sha256": "b0d880bb3004d0cce06b259c88de6b497afa730dd0663df3e22164af9714a235",
                "fault": "request-time peer is still wrong for active-page menu repair",
            },
        },
        "publisher": {
            "completed_map_owner": "bank1:$42ED raw H -> DF5C",
            "main_range": "$12E0-$1302",
            "vblank_hook_call": "$082E",
            "commit_entry": "bank13:$73FC",
            "target_latch": "$DF5C",
            "pending_latch": "$DF5D",
            "lcd_enabled": "arm completed-map target and return without polling",
            "lcd_disabled": "commit SCX/SCY/peer map immediately",
            "vblank_target": "completed H bit 2",
            "vblank_lcdc_policy": "preserve current LCDC bits 7-4 and 2-0",
            "wrapper_tail": "bank13:$6F1D",
        },
        "timing": {
            "map_done_pure_delta_t_vs_r345": 0,
            "map_done_dirty_delta_t_vs_r345": 4,
            "main_publisher_wait_cycles": 0,
        },
        "required_live_gates": [
            "authenticated operator menu-exit replay",
            "phase-aligned rotating-spike rendered raster",
            "natural Stage1 menu open/close and joypad acceptance",
            "Timer ISR cadence inside stock envelope",
            "all-stage DF5C/DF5D collision and LCD-off lifecycle census",
            "all-stage speed and determinism",
            "Pocket hardware confirmation before promotion",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=r347.BASE)
    parser.add_argument("--base-receipt", type=Path, default=r347.BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r347.checked_output(args.output, "candidate")
    receipt_path = r347.checked_output(args.receipt, "receipt")
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "candidate_sha256": receipt["candidate_sha256"],
        "output": str(output),
        "status": receipt["status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
