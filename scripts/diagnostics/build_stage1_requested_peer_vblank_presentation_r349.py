#!/usr/bin/env python3
"""Build r349: publish the requested peer map during VBlank.

r347 safely delayed each Stage-1 peer-map switch until VBlank, but its Boolean
latch derived the target from LCDC at interrupt time.  Native menu teardown can
change LCDC between the publication request and that interrupt, making the
relative toggle select an unfinished page.  r348 tried to carry an absolute
target through HDMA3; live rotating-hazard evidence proved that hardware HDMA
state overwrites that register and can pin the display to one page.

r349 instead snapshots LCDC at the publication request.  The VBlank service
selects the peer of that saved map bit while preserving every other current
LCDC bit.  Repeated requests before one VBlank coalesce to the same absolute
target, and later menu/window changes cannot redirect the commit.  No emulator
is invoked by this builder.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import build_stage1_deferred_vblank_presentation_r347 as r347


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
DEFAULT_OUTPUT = TMP / "stage1-requested-peer-vblank-presentation-r349/candidate.gb"
DEFAULT_RECEIPT = (
    TMP / "stage1-requested-peer-vblank-presentation-r349/build-receipt.json"
)
EXPECTED_CANDIDATE_SHA256 = (
    "b0d880bb3004d0cce06b259c88de6b497afa730dd0663df3e22164af9714a235"
)

NEW_PRIMARY = bytes.fromhex(
    "F3 F0 40 07 38 16 "                  # DI; LCD enabled -> deferred
    "FA 00 DC E6 0F E0 43 "              # LCD off: immediate SCX
    "FA 02 DC E6 0F E0 42 "              # LCD off: immediate SCY
    "F0 40 EE 08 E0 40 18 05 "           # LCD off: peer map; skip latch
    "F0 40 EA 5C DF "                    # LCD on: snapshot request-time LCDC
    "FB C9"                               # restore IME; return
)

COMMIT_HELPER = bytes.fromhex(
    "FA 5C DF B7 CA 1D 6F "               # no saved request -> wrapper
    "E6 08 EE 08 47 "                    # requested peer bit -> B
    "AF EA 5C DF "                        # consume saved request
    "F0 97 FE 02 28 07 "                  # preserve stock SCX-skip policy
    "FA 00 DC E6 0F E0 43 "              # SCX
    "FA 02 DC E6 0F E0 42 "              # SCY
    "F0 40 E6 F7 B0 E0 40 "              # merge peer bit into current LCDC
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
    r347.require(source[r347.PRIMARY_ADDR:r347.PRIMARY_END] == r347.OLD_PRIMARY,
                 "r345 primary publisher preimage drifted")
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
    ):
        r347.require(source.count(opcode) == 0,
                     "r349-owned hook/latch already has an owner")

    r347.require(r347.PRIMARY_ADDR + 6 + NEW_PRIMARY[5]
                 == r347.PRIMARY_ADDR + 28,
                 "LCD-enabled branch does not target request snapshot")
    r347.require(r347.PRIMARY_ADDR + 28 + NEW_PRIMARY[27]
                 == r347.PRIMARY_ADDR + 33,
                 "LCD-off branch does not skip request snapshot")
    r347.require(NEW_PRIMARY[28:33] == bytes.fromhex("F0 40 EA 5C DF"),
                 "main publisher does not snapshot request-time LCDC")
    r347.require(COMMIT_HELPER.count(bytes.fromhex("E0 40")) == 1,
                 "VBlank helper map write count changed")
    r347.require(bytes.fromhex("F0 40 E6 F7 B0 E0 40") in COMMIT_HELPER,
                 "VBlank helper does not preserve non-map LCDC bits")
    r347.require(COMMIT_HELPER[-3:] == bytes.fromhex("C3 1D 6F"),
                 "VBlank helper does not tail-jump to established wrapper")

    rom = bytearray(source)
    rom[r347.PRIMARY_ADDR:r347.PRIMARY_END] = NEW_PRIMARY
    rom[
        r347.VBLANK_HOOK_CALL_ADDR:r347.VBLANK_HOOK_CALL_ADDR + 3
    ] = r347.NEW_HOOK_CALL
    rom[
        r347.COMMIT_FILE_OFFSET:r347.COMMIT_FILE_OFFSET + len(COMMIT_HELPER)
    ] = COMMIT_HELPER
    r347.update_checksums(rom)
    candidate = bytes(rom)

    owned = set(range(r347.PRIMARY_ADDR, r347.PRIMARY_END))
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
                 f"r349 escaped owned bytes: "
                 f"{sorted(changed - owned - r347.CHECKSUM_OFFSETS)}")

    candidate_sha = r347.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        r347.require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
                     f"candidate identity drift: {candidate_sha}")
    receipt: dict[str, object] = {
        "schema": "penta-stage1-requested-peer-vblank-presentation-r349-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r345_sha256": r347.BASE_SHA256,
        "base_receipt_sha256": r347.BASE_RECEIPT_SHA256,
        "candidate_sha256": candidate_sha,
        "rejected_candidates": {
            "r347": {
                "sha256": r347.EXPECTED_CANDIDATE_SHA256,
                "fault": "interrupt-time relative toggle can follow a later menu LCDC change",
            },
            "r348": {
                "sha256": "72daa7dc52122134681fd14eeb03dd49709abb3e61ac68e43e221709bb7e7e5c",
                "fault": "post-transfer HDMA3 is not a durable absolute display target",
            },
        },
        "publisher": {
            "main_range": "$12E0-$1302",
            "vblank_hook_call": "$082E",
            "commit_entry": "bank13:$73FC",
            "pending_latch": "$DF5C",
            "lcd_enabled": "save request-time LCDC and return without polling",
            "lcd_disabled": "commit SCX/SCY/peer map immediately",
            "vblank_target": "peer of request-time LCDC.3",
            "vblank_lcdc_policy": "preserve current LCDC bits 7-4 and 2-0",
            "outer_register_contract": "ROM0:$06D1 saves AF/BC/DE/HL",
            "wrapper_tail": "bank13:$6F1D",
        },
        "required_live_gates": [
            "authenticated operator menu-exit replay",
            "phase-aligned rotating-spike rendered raster",
            "natural Stage1 menu open/close and joypad acceptance",
            "Timer ISR cadence inside stock envelope",
            "all-stage DF5C collision and LCD-off lifecycle census",
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
