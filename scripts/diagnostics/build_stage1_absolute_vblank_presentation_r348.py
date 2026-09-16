#!/usr/bin/env python3
"""Build r348: defer one absolute Stage-1 map target to VBlank.

r347 used a Boolean pending latch and toggled LCDC.3 when VBlank arrived.
That is safe for one request, but the native menu-close path can issue more
than one completed-page publication before the next VBlank.  Coalescing those
requests as one toggle loses parity and briefly exposes incomplete tile and
attribute planes.

r345 already preserves the completed physical page in HDMA3 (FF53) at the
publisher boundary.  r348 snapshots that absolute $98/$9C page byte into the
pending latch.  The VBlank service selects $83/$8B from the saved page, so
multiple requests coalesce to the final target instead of to one toggle.

No emulator is invoked by this builder.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import build_stage1_deferred_vblank_presentation_r347 as r347


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
DEFAULT_OUTPUT = TMP / "stage1-absolute-vblank-presentation-r348/candidate.gb"
DEFAULT_RECEIPT = (
    TMP / "stage1-absolute-vblank-presentation-r348/build-receipt.json"
)
EXPECTED_CANDIDATE_SHA256 = (
    "72daa7dc52122134681fd14eeb03dd49709abb3e61ac68e43e221709bb7e7e5c"
)

NEW_PRIMARY = bytes.fromhex(
    "F3 F0 40 07 38 16 "                  # DI; LCD enabled -> deferred
    "FA 00 DC E6 0F E0 43 "              # LCD off: immediate SCX
    "FA 02 DC E6 0F E0 42 "              # LCD off: immediate SCY
    "F0 40 EE 08 E0 40 18 05 "           # LCD off: peer map; skip latch
    "F0 53 EA 5C DF "                    # LCD on: snapshot completed H
    "FB C9"                               # restore IME; return
)

COMMIT_HELPER = bytes.fromhex(
    "FA 5C DF B7 CA 1D 6F "               # no absolute target -> wrapper
    "F0 97 FE 02 28 07 "                  # preserve stock SCX-skip policy
    "FA 00 DC E6 0F E0 43 "              # SCX
    "FA 02 DC E6 0F E0 42 "              # SCY
    "FA 5C DF E6 04 07 F6 83 E0 40 "      # $98/$9C -> LCDC $83/$8B
    "AF EA 5C DF "                        # consume committed target
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
        source.count(bytes([
            0xCD, r347.COMMIT_ADDR & 0xFF, r347.COMMIT_ADDR >> 8,
        ])) == 0,
        "commit cave already has a direct CALL owner",
    )
    r347.require(
        source.count(bytes([
            0xC3, r347.COMMIT_ADDR & 0xFF, r347.COMMIT_ADDR >> 8,
        ])) == 0,
        "commit cave already has a direct JP owner",
    )
    for opcode in (bytes.fromhex("FA 5C DF"), bytes.fromhex("EA 5C DF")):
        r347.require(source.count(opcode) == 0,
                     "DF5C target latch already has a direct absolute owner")

    r347.require(r347.PRIMARY_ADDR + 6 + NEW_PRIMARY[5]
                 == r347.PRIMARY_ADDR + 28,
                 "LCD-enabled branch does not target the absolute latch")
    r347.require(r347.PRIMARY_ADDR + 28 + NEW_PRIMARY[27]
                 == r347.PRIMARY_ADDR + 33,
                 "LCD-off branch does not skip the absolute latch")
    r347.require(NEW_PRIMARY[28:33] == bytes.fromhex("F0 53 EA 5C DF"),
                 "main publisher does not snapshot completed HDMA3 page")
    r347.require(COMMIT_HELPER.count(bytes.fromhex("E0 40")) == 1,
                 "VBlank helper map write count changed")
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
                 "r348 escaped its owned code/checksum bytes")

    candidate_sha = r347.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        r347.require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
                     f"candidate identity drift: {candidate_sha}")
    receipt: dict[str, object] = {
        "schema": "penta-stage1-absolute-vblank-presentation-r348-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r345_sha256": r347.BASE_SHA256,
        "base_receipt_sha256": r347.BASE_RECEIPT_SHA256,
        "candidate_sha256": candidate_sha,
        "replaces_r347_sha256": r347.EXPECTED_CANDIDATE_SHA256,
        "r347_failure": {
            "operator_capture": "operator-corrupted-walls",
            "post_close_wrong_immutable_tile_frames": 2,
            "post_close_wrong_semantic_attr_frames": 1,
            "cause": "Boolean toggle latch coalesced an absolute page handoff",
        },
        "publisher": {
            "main_range": "$12E0-$1302",
            "vblank_hook_call": "$082E",
            "commit_entry": "bank13:$73FC",
            "pending_absolute_page": "$DF5C receives HDMA3 $98/$9C",
            "lcd_enabled": "snapshot final completed page and return",
            "lcd_disabled": "commit the immediate peer-map path",
            "vblank_write_order": ["FF43", "FF42", "FF40", "DF5C=0"],
            "coalescing": "last absolute target wins; toggle parity is irrelevant",
        },
        "required_live_gates": [
            "authenticated scene-$0B operator menu roundtrips",
            "natural Stage1 menu temporal raster",
            "all rotating-spike phase rasters",
            "all-stage speed, timer, and audio cadence",
            "all-stage DF5C collision and LCD-off lifecycle census",
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
