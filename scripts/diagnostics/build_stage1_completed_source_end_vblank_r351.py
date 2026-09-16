#!/usr/bin/env python3
"""Build r351: carry the completed map through the packed-source end byte.

At bank1:$42ED the copier has consumed exactly C1A0-C3DF, so DE is C3E0 and
H identifies the completed $9800/$9C00 page.  Preserve r345's required HDMA3
write and use the otherwise out-of-range C3E0 byte as a short-lived target
mailbox.  The fixed publisher arms DF5C; VBlank consumes it and selects the
completed map while preserving all other LCDC controls.  No emulator is run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import build_stage1_deferred_vblank_presentation_r347 as r347


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
DEFAULT_OUTPUT = TMP / "stage1-completed-source-end-vblank-r351/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-completed-source-end-vblank-r351/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = (
    "7bd53a4b19899f83a7a5429a17a40527d2901b70c746f50459d29ce1ec8d58a1"
)

MAP_DONE_ADDR = 0x42ED
MAP_DONE_OLD = bytes.fromhex(
    "7C E0 53 F0 01 1F 38 07 CD F1 DB 00 FB C9 00"
)
MAP_DONE_NEW = bytes.fromhex(
    "7C E0 53 12 F0 01 1F 38 06 CD F1 DB FB C9 00"
)
TARGET_ADDR = 0xC3E0
PENDING_ADDR = 0xDF5C

NEW_PRIMARY = bytes.fromhex(
    "F3 F0 40 07 38 16 "
    "FA 00 DC E6 0F E0 43 FA 02 DC E6 0F E0 42 "
    "F0 40 EE 08 E0 40 18 05 3E 01 EA 5C DF FB C9"
)
COMMIT_HELPER = bytes.fromhex(
    "FA 5C DF B7 CA 1D 6F "               # no pending publication
    "AF EA 5C DF "                        # consume pending flag
    "F0 97 FE 02 28 07 "                  # stock SCX-skip policy
    "FA 00 DC E6 0F E0 43 FA 02 DC E6 0F E0 42 "
    "FA E0 C3 E6 04 07 47 "               # completed H bit 2 -> B bit 3
    "F0 40 E6 F7 B0 E0 40 "              # merge map, preserve LCDC controls
    "C3 1D 6F"
)


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    r347.require(len(source) == r347.ROM_SIZE, "r345 base size changed")
    r347.require(r347.digest(source) == r347.BASE_SHA256,
                 f"wrong exact r345 base: {r347.digest(source)}")
    r347.require(r347.digest(base_receipt_bytes) == r347.BASE_RECEIPT_SHA256,
                 "r345 base receipt identity drifted")
    base_receipt = json.loads(base_receipt_bytes)
    r347.require(base_receipt.get("schema") == r347.BASE_SCHEMA,
                 "r345 base receipt schema drifted")
    r347.require(base_receipt.get("candidate_sha256") == r347.BASE_SHA256,
                 "r345 receipt names another candidate")
    r347.require(source[MAP_DONE_ADDR:MAP_DONE_ADDR + 15] == MAP_DONE_OLD,
                 "r345 map-done preimage drifted")
    r347.require(source[r347.PRIMARY_ADDR:r347.PRIMARY_END] == r347.OLD_PRIMARY,
                 "r345 primary publisher preimage drifted")
    r347.require(source[r347.VBLANK_HOOK_CALL_ADDR:
                        r347.VBLANK_HOOK_CALL_ADDR + 3] == r347.OLD_HOOK_CALL,
                 "VBlank hook preimage drifted")
    r347.require(source[r347.COMMIT_FILE_OFFSET:
                        r347.COMMIT_FILE_OFFSET + len(COMMIT_HELPER)]
                 == bytes(len(COMMIT_HELPER)), "commit cave is not zero")
    r347.require(source[0x06D1:0x06D5] == bytes.fromhex("F5 C5 D5 E5"),
                 "outer VBlank register-save contract changed")
    for opcode in (
        bytes([0xCD, r347.COMMIT_ADDR & 0xFF, r347.COMMIT_ADDR >> 8]),
        bytes([0xC3, r347.COMMIT_ADDR & 0xFF, r347.COMMIT_ADDR >> 8]),
        bytes.fromhex("FA 5C DF"), bytes.fromhex("EA 5C DF"),
    ):
        r347.require(source.count(opcode) == 0,
                     "r351 hook/pending latch already has an owner")

    r347.require(len(MAP_DONE_NEW) == 15 and len(NEW_PRIMARY) == 35,
                 "fixed-width patch changed size")
    r347.require(MAP_DONE_NEW[:4] == bytes.fromhex("7C E0 53 12"),
                 "map-done does not preserve HDMA3 then write (DE)")
    r347.require(MAP_DONE_ADDR + 9 + MAP_DONE_NEW[8] == 0x42FC,
                 "dirty branch no longer targets compiler")
    r347.require(MAP_DONE_NEW[12:] == bytes.fromhex("FB C9 00"),
                 "pure return contract changed")
    r347.require(r347.PRIMARY_ADDR + 6 + NEW_PRIMARY[5]
                 == r347.PRIMARY_ADDR + 28,
                 "LCD-enabled branch misses pending arm")
    r347.require(r347.PRIMARY_ADDR + 28 + NEW_PRIMARY[27]
                 == r347.PRIMARY_ADDR + 33,
                 "LCD-off branch does not skip pending arm")
    r347.require(NEW_PRIMARY[28:33] == bytes.fromhex("3E 01 EA 5C DF"),
                 "main publisher does not arm DF5C")
    r347.require(bytes.fromhex("FA E0 C3 E6 04 07 47") in COMMIT_HELPER,
                 "helper does not decode C3E0 completed target")
    r347.require(bytes.fromhex("F0 40 E6 F7 B0 E0 40") in COMMIT_HELPER,
                 "helper does not preserve non-map LCDC bits")
    r347.require(COMMIT_HELPER[-3:] == bytes.fromhex("C3 1D 6F"),
                 "helper does not tail-jump to established wrapper")

    rom = bytearray(source)
    rom[MAP_DONE_ADDR:MAP_DONE_ADDR + 15] = MAP_DONE_NEW
    rom[r347.PRIMARY_ADDR:r347.PRIMARY_END] = NEW_PRIMARY
    rom[r347.VBLANK_HOOK_CALL_ADDR:
        r347.VBLANK_HOOK_CALL_ADDR + 3] = r347.NEW_HOOK_CALL
    rom[r347.COMMIT_FILE_OFFSET:
        r347.COMMIT_FILE_OFFSET + len(COMMIT_HELPER)] = COMMIT_HELPER
    r347.update_checksums(rom)
    candidate = bytes(rom)

    owned = set(range(MAP_DONE_ADDR, MAP_DONE_ADDR + 15))
    owned.update(range(r347.PRIMARY_ADDR, r347.PRIMARY_END))
    owned.update(range(r347.VBLANK_HOOK_CALL_ADDR,
                       r347.VBLANK_HOOK_CALL_ADDR + 3))
    owned.update(range(r347.COMMIT_FILE_OFFSET,
                       r347.COMMIT_FILE_OFFSET + len(COMMIT_HELPER)))
    changed = {i for i, pair in enumerate(zip(source, candidate, strict=True))
               if pair[0] != pair[1]}
    r347.require(changed <= owned | r347.CHECKSUM_OFFSETS,
                 f"r351 escaped owned bytes: "
                 f"{sorted(changed - owned - r347.CHECKSUM_OFFSETS)}")

    sha = r347.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        r347.require(sha == EXPECTED_CANDIDATE_SHA256,
                     f"candidate identity drift: {sha}")
    receipt: dict[str, object] = {
        "schema": "penta-stage1-completed-source-end-vblank-r351-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r345_sha256": r347.BASE_SHA256,
        "base_receipt_sha256": r347.BASE_RECEIPT_SHA256,
        "candidate_sha256": sha,
        "replaces": {
            "r347": r347.EXPECTED_CANDIDATE_SHA256,
            "r348": "72daa7dc52122134681fd14eeb03dd49709abb3e61ac68e43e221709bb7e7e5c",
            "r349": "b0d880bb3004d0cce06b259c88de6b497afa730dd0663df3e22164af9714a235",
            "r350": "a56ab3f2ee6d094088c71f931434a63b3471b2b63b9c018d9d5597300d1a9afe",
        },
        "publisher": {
            "completed_target": "bank1:$42F0 LD (DE),A with DE=$C3E0",
            "target_mailbox": "$C3E0 (one byte beyond exact C1A0-C3DF source)",
            "pending_latch": "$DF5C",
            "commit_entry": "bank13:$73FC",
            "commit_pc": "bank13:$7427",
            "lcdc_policy": "completed map in VBlank; preserve all other bits",
        },
        "timing": {
            "map_done_pure_delta_t_vs_r345": 4,
            "map_done_dirty_delta_t_vs_r345": 8,
            "publisher_wait_cycles": 0,
        },
        "required_live_gates": [
            "authenticated operator menu-exit replay",
            "phase-aligned rotating-spike rendered raster",
            "natural Stage1 menu and Timer ISR cadence",
            "all-stage C3E0/DF5C ownership and LCD-off lifecycle census",
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
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"],
                      "output": str(output), "status": receipt["status"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
