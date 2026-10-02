#!/usr/bin/env python3
"""Build r347: defer live LCD map publication without stalling the engine.

r345 can select a completed peer tilemap during an arbitrary visible scanline,
which produces a mixed rotating-spike frame on Pocket hardware.  The rejected
r346 prototype waited in the main publisher until VBlank; that fixed the
raster but delayed joypad and timer cadence.

This overlay keeps the LCD-off path immediate and unchanged in effect.  With
the LCD enabled, fixed $12E0 only arms a WRAM latch and returns.  The existing
bank-13 VBlank hook enters a small latch service before the established color
wrapper, commits SCX/SCY/LCDC while already in VBlank, then tail-jumps to that
wrapper.  No polling, extra interrupt masking interval, or second emulator
service is introduced.

No emulator is invoked by this builder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-pocket-map-authority-r345/candidate.gb"
BASE_RECEIPT = TMP / "stage1-pocket-map-authority-r345/build-receipt.json"
BASE_SHA256 = "d7d388e354dc3649f81a5a62f61266f67ed454a2b2d8ac10e817102d82745a4a"
BASE_RECEIPT_SHA256 = (
    "b1c74bdef48ca07003ac1867de2cc9314168d5d03a4b14da3c56728c4c161056"
)
BASE_SCHEMA = "penta-stage1-pocket-map-authority-r345-build-v1"
DEFAULT_OUTPUT = TMP / "stage1-deferred-vblank-presentation-r347/candidate.gb"
DEFAULT_RECEIPT = (
    TMP / "stage1-deferred-vblank-presentation-r347/build-receipt.json"
)
EXPECTED_CANDIDATE_SHA256 = (
    "de5ec561ae0f4e0858e3010ffc31394106147f7c4246e52b7abebdef0b981e74"
)

ROM_SIZE = 32 * 0x4000
PRIMARY_ADDR = 0x12E0
PRIMARY_END = 0x1303
VBLANK_HOOK_CALL_ADDR = 0x082E
WRAPPER_ADDR = 0x6F1D
COMMIT_ADDR = 0x73FC
COMMIT_FILE_OFFSET = 13 * 0x4000 + COMMIT_ADDR - 0x4000
PENDING_ADDR = 0xDF5C
OLD_PRIMARY = bytes.fromhex(
    "F3 F0 97 FE 02 28 07 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 FA 0B DC B7 3E 83 28 02 "
    "CB DF E0 40 FB C9"
)
NEW_PRIMARY = bytes.fromhex(
    "F3 F0 40 07 38 16 "                  # DI; LCD enabled -> deferred
    "FA 00 DC E6 0F E0 43 "              # LCD off: immediate SCX
    "FA 02 DC E6 0F E0 42 "              # LCD off: immediate SCY
    "F0 40 EE 08 E0 40 18 05 "           # LCD off: peer map; skip latch
    "3E 01 EA 5C DF "                    # LCD on: arm latch last
    "FB C9"                               # restore IME; return
)
OLD_HOOK_CALL = bytes([0xCD, WRAPPER_ADDR & 0xFF, WRAPPER_ADDR >> 8])
NEW_HOOK_CALL = bytes([0xCD, COMMIT_ADDR & 0xFF, COMMIT_ADDR >> 8])
COMMIT_HELPER = bytes.fromhex(
    "FA 5C DF B7 CA 1D 6F "               # no latch -> wrapper
    "AF EA 5C DF "                        # consume latch before commit
    "F0 97 FE 02 28 07 "                  # preserve stock SCX-skip policy
    "FA 00 DC E6 0F E0 43 "              # SCX
    "FA 02 DC E6 0F E0 42 "              # SCY
    "F0 40 EE 08 E0 40 "                 # select completed peer map
    "C3 1D 6F"                            # established wrapper
)
CHECKSUM_OFFSETS = frozenset({0x014D, 0x014E, 0x014F})


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def checked_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved != scratch and scratch in resolved.parents,
            f"{label} must be below repository tmp/")
    return resolved


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == ROM_SIZE, "r345 base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256,
            f"wrong exact r345 base: {digest(source)}")
    require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
            "r345 base receipt identity drifted")
    base_receipt = json.loads(base_receipt_bytes)
    require(base_receipt.get("schema") == BASE_SCHEMA,
            "r345 base receipt schema drifted")
    require(base_receipt.get("candidate_sha256") == BASE_SHA256,
            "r345 base receipt names another candidate")
    require(source[PRIMARY_ADDR:PRIMARY_END] == OLD_PRIMARY,
            "r345 primary publisher preimage drifted")
    require(len(OLD_PRIMARY) == len(NEW_PRIMARY) == 35,
            "primary publisher width changed")
    require(source[VBLANK_HOOK_CALL_ADDR:VBLANK_HOOK_CALL_ADDR + 3]
            == OLD_HOOK_CALL, "VBlank wrapper call preimage drifted")
    require(source[COMMIT_FILE_OFFSET:COMMIT_FILE_OFFSET + len(COMMIT_HELPER)]
            == bytes(len(COMMIT_HELPER)), "bank-13 commit cave is not zero")
    require(source.count(bytes([0xCD, COMMIT_ADDR & 0xFF, COMMIT_ADDR >> 8])) == 0,
            "commit cave already has a direct CALL owner")
    require(source.count(bytes([0xC3, COMMIT_ADDR & 0xFF, COMMIT_ADDR >> 8])) == 0,
            "commit cave already has a direct JP owner")
    for opcode in (bytes.fromhex("FA 5C DF"), bytes.fromhex("EA 5C DF")):
        require(source.count(opcode) == 0,
                "DF5C latch already has a direct absolute owner")

    # Exact branch and ownership contract for the fixed-width main publisher.
    require(PRIMARY_ADDR + 6 + NEW_PRIMARY[5] == PRIMARY_ADDR + 28,
            "LCD-enabled branch does not target the latch arm")
    require(PRIMARY_ADDR + 28 + NEW_PRIMARY[27] == PRIMARY_ADDR + 33,
            "LCD-off branch does not skip the latch arm")
    require(NEW_PRIMARY.count(bytes.fromhex("E0 40")) == 1,
            "main publisher LCD-off map write count changed")
    require(NEW_PRIMARY.count(bytes.fromhex("EA 5C DF")) == 1,
            "main publisher latch arm count changed")
    require(COMMIT_HELPER.count(bytes.fromhex("E0 40")) == 1,
            "VBlank helper map write count changed")
    require(COMMIT_HELPER[-3:] == bytes.fromhex("C3 1D 6F"),
            "VBlank helper does not tail-jump to the established wrapper")

    rom = bytearray(source)
    rom[PRIMARY_ADDR:PRIMARY_END] = NEW_PRIMARY
    rom[VBLANK_HOOK_CALL_ADDR:VBLANK_HOOK_CALL_ADDR + 3] = NEW_HOOK_CALL
    rom[COMMIT_FILE_OFFSET:COMMIT_FILE_OFFSET + len(COMMIT_HELPER)] = COMMIT_HELPER
    update_checksums(rom)
    candidate = bytes(rom)

    owned = set(range(PRIMARY_ADDR, PRIMARY_END))
    owned.update(range(VBLANK_HOOK_CALL_ADDR, VBLANK_HOOK_CALL_ADDR + 3))
    owned.update(range(COMMIT_FILE_OFFSET, COMMIT_FILE_OFFSET + len(COMMIT_HELPER)))
    changed = {
        index for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    require(changed <= owned | CHECKSUM_OFFSETS,
            f"r347 escaped owned bytes: {sorted(changed - owned - CHECKSUM_OFFSETS)}")

    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {candidate_sha}")
    receipt: dict[str, object] = {
        "schema": "penta-stage1-deferred-vblank-presentation-r347-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r345_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": candidate_sha,
        "incident": {
            "hardware_menu_exit_screenshot_sha256": (
                "41e2016a630d9c02a11b56b140111527c01f2b0f9724cacd53aab7dd14e112cc"
            ),
            "phase_gate_first_mismatch_frame": 490,
            "cause": "visible-scanline peer-map publication",
            "rejected_r346": "busy VBlank polling disturbed input/timer cadence",
        },
        "publisher": {
            "main_range": "$12E0-$1302",
            "vblank_hook_call": "$082E",
            "commit_entry": "bank13:$73FC",
            "pending_latch": "$DF5C",
            "lcd_enabled": "arm latch and return without polling",
            "lcd_disabled": "commit SCX/SCY/peer map immediately",
            "vblank_write_order": ["FF43", "FF42", "FF40"],
            "wrapper_tail": "bank13:$6F1D",
        },
        "required_live_gates": [
            "phase-aligned rotating-spike rendered raster",
            "natural Stage1 menu open/close and joypad acceptance",
            "Timer ISR cadence inside stock envelope",
            "all-stage peer-page publication and DF5C collision census",
            "all-stage speed and determinism",
            "Pocket hardware confirmation before promotion",
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
    output = checked_output(args.output, "candidate")
    receipt_path = checked_output(args.receipt, "receipt")
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
