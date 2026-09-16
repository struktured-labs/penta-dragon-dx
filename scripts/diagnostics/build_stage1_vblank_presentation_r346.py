#!/usr/bin/env python3
"""Build r346: commit the primary peer-map publication during VBlank.

r345's completed tile and attribute planes are exact, but fixed $12E0 still
selects the new LCDC tilemap during arbitrary visible scanlines.  A rendered
phase-aware trace caught a split spike frame after a publication at LY=$48:
pixels above the switch retained the outgoing tooth phase while the completed
map was visible below it.

This exact-width overlay disables interrupts, skips the wait while LCDC.7 is
off, otherwise waits until LY reaches VBlank, and retains r320's
SCX/SCY-before-LCDC atomic commit.  Exact live publication telemetry
must prove FF97 never requests the retired SCX-skip branch; removing that
six-byte predicate makes room for the LCD-off guard without widening the
publisher.  The old DC0B selector is replaced by XOR $08 on LCDC.  That is
equivalent at this
publisher's admitted boundary: every call has just completed the currently
hidden peer page, so the desired map is necessarily the opposite of LCDC.3.
The all-stage publication verifier must re-prove that peer-page precondition
at every captured event before this diagnostic candidate can be promoted.

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
DEFAULT_OUTPUT = TMP / "stage1-vblank-presentation-r346/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-vblank-presentation-r346/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = (
    "64b31677b1ea83795188d041ee7d97e164837e60b60052d6e3a48ada3e5b1f64"
)

ROM_SIZE = 32 * 0x4000
PRIMARY_ADDR = 0x12E0
PRIMARY_END = 0x1303
OLD_PRIMARY = bytes.fromhex(
    "F3 F0 97 FE 02 28 07 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 FA 0B DC B7 3E 83 28 02 "
    "CB DF E0 40 FB C9"
)
NEW_PRIMARY = bytes.fromhex(
    "F3 00 F0 40 87 30 06 "              # DI; skip wait if LCD off
    "F0 44 FE 90 38 FA "                 # wait LY >= $90
    "FA 00 DC E6 0F E0 43 "              # SCX = DC00 & $0F
    "FA 02 DC E6 0F E0 42 "              # SCY = DC02 & $0F
    "F0 40 EE 08 E0 40 FB C9"            # peer LCDC map; EI; RET
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


def jr_target(opcode_addr: int, displacement: int) -> int:
    signed = displacement if displacement < 0x80 else displacement - 0x100
    return opcode_addr + 2 + signed


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
    require(len(OLD_PRIMARY) == len(NEW_PRIMARY) == PRIMARY_END - PRIMARY_ADDR,
            "primary publisher width changed")

    # Exact control-flow and write-order contract.
    require(jr_target(PRIMARY_ADDR + 5, NEW_PRIMARY[6]) == PRIMARY_ADDR + 13,
            "LCD-off branch does not target SCX commit")
    require(jr_target(PRIMARY_ADDR + 11, NEW_PRIMARY[12]) == PRIMARY_ADDR + 7,
            "LY wait does not loop to its scanline read")
    require(NEW_PRIMARY.count(bytes.fromhex("E0 43")) == 1,
            "SCX write count changed")
    require(NEW_PRIMARY.count(bytes.fromhex("E0 42")) == 1,
            "SCY write count changed")
    require(NEW_PRIMARY.count(bytes.fromhex("E0 40")) == 1,
            "LCDC write count changed")
    require(NEW_PRIMARY.index(bytes.fromhex("E0 43"))
            < NEW_PRIMARY.index(bytes.fromhex("E0 42"))
            < NEW_PRIMARY.index(bytes.fromhex("E0 40")),
            "presentation write order changed")
    require(NEW_PRIMARY[:13]
            == bytes.fromhex("F3 00 F0 40 87 30 06 F0 44 FE 90 38 FA"),
            "LCD-off/VBlank wait/critical-section prefix drifted")
    require(NEW_PRIMARY[-8:] == bytes.fromhex("F0 40 EE 08 E0 40 FB C9"),
            "peer-page LCDC commit/IME return drifted")

    rom = bytearray(source)
    rom[PRIMARY_ADDR:PRIMARY_END] = NEW_PRIMARY
    update_checksums(rom)
    candidate = bytes(rom)
    changed = {
        index for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    functional = changed - CHECKSUM_OFFSETS
    owned = {
        PRIMARY_ADDR + index
        for index, pair in enumerate(zip(OLD_PRIMARY, NEW_PRIMARY, strict=True))
        if pair[0] != pair[1]
    }
    require(functional == owned,
            f"r346 escaped owned publisher bytes: {sorted(functional ^ owned)}")
    require(changed <= owned | CHECKSUM_OFFSETS,
            "r346 escaped publisher/checksum ownership")

    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {candidate_sha}")
    receipt: dict[str, object] = {
        "schema": "penta-stage1-vblank-presentation-r346-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r345_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": candidate_sha,
        "incident": {
            "gate_receipt": (
                "tmp/stage1-pocket-map-authority-r345/"
                "hazard-menu-v4-single/receipt.json"
            ),
            "first_phase_mismatch_frame": 490,
            "first_phase_mismatch_pixels": 8,
            "preceding_publication_ly": "48",
            "cause": "primary LCDC peer-map selection during visible scanline",
            "rejected_prototypes": [
                "bare STAT-mode wait deadlocks when LCD is off",
                "unmasked whole-STAT DEC never recognizes mode 1",
            ],
        },
        "publisher": {
            "range": "$12E0-$1302",
            "width": len(NEW_PRIMARY),
            "wait": "DI; LCDC.7 off -> commit; else loop until LY >= $90",
            "write_order": ["FF43", "FF42", "FF40"],
            "FF97_policy": (
                "retired SCX-skip predicate; live gates must observe FF97 != 02"
            ),
            "map_selection": "LCDC ^= $08",
            "required_live_precondition": (
                "every admitted publication targets the currently hidden peer page"
            ),
            "exit": "EI; RET",
        },
        "timing": {
            "visible_scanline_publication": False,
            "timer_interrupts_enabled_while_waiting": False,
            "required_timer_gate": (
                "candidate Timer ISR cadence must remain inside the stock envelope"
            ),
            "LCD_off_wait_bypass": True,
            "interrupt_closed_commit_t_max": 180,
            "fixed_width_delta_bytes": 0,
        },
        "patch": {
            "functional_changed_offsets": [
                f"0x{offset:06X}" for offset in sorted(functional)
            ],
            "functional_changed_bytes": len(functional),
        },
        "required_live_gates": [
            "phase-aligned rotating-spike rendered raster",
            "natural Stage1 menu close with timer ISR telemetry",
            "all-stage exact peer-page publication precondition",
            "all-stage FF97 != 02 at every primary publication",
            "all-stage speed and determinism",
            "title/attract and LCD-enabled reachability",
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
