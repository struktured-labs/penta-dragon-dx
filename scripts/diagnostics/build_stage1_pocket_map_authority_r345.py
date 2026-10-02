#!/usr/bin/env python3
"""Build r345: keep Stage-1 map authority out of serial SB.

r344 keeps an odd/even publication tag in FF01 (SB): bit 0 is the dirty
decision and bits 2+ encode the exact $9800/$9C00 destination.  A corrected
read-boundary mutation of those map bits recreates the Pocket menu-exit
palette residue.

At map completion H already identifies the completed physical page.  Replace
four of the five pure-path padding NOPs with a width-contained raw-H save to
HDMA3, then continue using only FF01 bit 0 for the dirty branch.  Dirty DMA
setup normalizes HDMA3 with ``AND $FC``; the Stage-1 semantic row owner does
the same after transfer.  The remaining paid NOP preserves the pure-path
cadence, while a spare byte sits after RET and is unreachable on both arms.
The dirty branch pays the new raw-H save once, adding 16 T-cycles before the
existing compiler; that branch-specific cost is explicit in the receipt and
covered by the live all-stage speed gate.

This is a diagnostic candidate until exact Stage-1, later-stage, speed, and
Pocket gates pass.  No emulator is invoked by this builder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage4-delay-trim-r344/candidate.gb"
BASE_SHA256 = "3b35f1c938b4fefc1c6f6c02408494f4a6663be50f564b4476b502399c1f714e"
DEFAULT_OUTPUT = TMP / "stage1-pocket-map-authority-r345/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-pocket-map-authority-r345/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = "TO_BE_BOUND"

BANK_SIZE = 0x4000
ROM_SIZE = 32 * BANK_SIZE
CHECKSUM_OFFSETS = frozenset({0x014D, 0x014E, 0x014F})

MAP_DONE_BANK = 1
MAP_DONE_ADDR = 0x42ED
MAP_DONE_OLD = bytes.fromhex(
    "F0 01 1F 38 0A CD F1 DB 00 00 00 00 00 FB C9"
)
MAP_DONE_NEW = bytes.fromhex(
    "7C E0 53 F0 01 1F 38 07 CD F1 DB 00 FB C9 00"
)

DMA_DEST_BANK = 1
DMA_DEST_ADDR = 0x4328
DMA_DEST_OLD = bytes.fromhex("F0 01 3D 67 E0 53")
DMA_DEST_NEW = bytes.fromhex("F0 53 E6 FC E0 53")

ROW_BANK = 19
ROW_CLEAR_ADDR = 0x6C51
ROW_CLEAR_OLD = bytes.fromhex("E0 01")
ROW_CLEAR_NEW = bytes.fromhex("E0 53")
ROW_DEST_ADDR = 0x6CCE
ROW_DEST_OLD = bytes.fromhex("F0 01 E6 FE 67")
ROW_DEST_NEW = bytes.fromhex("F0 53 E6 FC 67")


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address < 0x8000,
            f"invalid banked address bank{bank}:${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


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


def patch_range(
    rom: bytearray, source: bytes, bank: int, address: int,
    old: bytes, new: bytes, label: str,
) -> set[int]:
    require(len(old) == len(new), f"{label} width changed")
    offset = bank_offset(bank, address)
    require(source[offset:offset + len(old)] == old,
            f"{label} preimage changed")
    rom[offset:offset + len(new)] = new
    return {
        offset + index
        for index, pair in enumerate(zip(old, new, strict=True))
        if pair[0] != pair[1]
    }


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == ROM_SIZE, "r344 base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256,
            f"wrong exact r344 base: {digest(source)}")
    rom = bytearray(source)
    owned: set[int] = set()
    owned |= patch_range(
        rom, source, MAP_DONE_BANK, MAP_DONE_ADDR,
        MAP_DONE_OLD, MAP_DONE_NEW, "map-done authority save",
    )
    owned |= patch_range(
        rom, source, DMA_DEST_BANK, DMA_DEST_ADDR,
        DMA_DEST_OLD, DMA_DEST_NEW, "dirty DMA destination restore",
    )
    owned |= patch_range(
        rom, source, ROW_BANK, ROW_CLEAR_ADDR,
        ROW_CLEAR_OLD, ROW_CLEAR_NEW, "Stage-1 row-owner clear",
    )
    owned |= patch_range(
        rom, source, ROW_BANK, ROW_DEST_ADDR,
        ROW_DEST_OLD, ROW_DEST_NEW, "Stage-1 row-owner destination",
    )
    update_checksums(rom)
    candidate = bytes(rom)

    changed = {
        index for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    functional = changed - CHECKSUM_OFFSETS
    require(functional == owned,
            f"r345 escaped owned machine-code bytes: {sorted(functional ^ owned)}")
    require(changed <= owned | CHECKSUM_OFFSETS,
            "r345 escaped code/checksum ownership")

    # Branch at $42F3 must still enter the existing compiler at $42FC.
    displacement = MAP_DONE_NEW[7]
    require(MAP_DONE_ADDR + 8 + displacement == 0x42FC,
            "new dirty branch does not target the compiler")
    require(MAP_DONE_NEW[11:15] == bytes.fromhex("00 FB C9 00"),
            "pure path lost exact paid NOP/EI/RET/unreachable-pad layout")
    require(DMA_DEST_NEW[:2] == bytes.fromhex("F0 53")
            and DMA_DEST_NEW[2:4] == bytes.fromhex("E6 FC")
            and DMA_DEST_NEW[-2:] == bytes.fromhex("E0 53"),
            "dirty path does not normalize and round-trip HDMA3 authority")
    require(ROW_DEST_NEW == bytes.fromhex("F0 53 E6 FC 67"),
            "row owner does not normalize post-transfer HDMA3")

    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {candidate_sha}")
    receipt: dict[str, object] = {
        "schema": "penta-stage1-pocket-map-authority-r345-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r344_sha256": BASE_SHA256,
        "candidate_sha256": candidate_sha,
        "root_control": {
            "candidate": BASE_SHA256,
            "fault": "FF01 map bit 2 flipped 99->9D at bank1:$4328 read",
            "result": "57 post-close bad frames; 27 mismatched cells on first failure",
            "receipt": (
                "tmp/hardware-incidents/r344-menu-exit-red-green/"
                "ff01-read-negative-control/report.txt"
            ),
        },
        "authority_contract": {
            "map_done": "raw completed H stored in HDMA3 before dirty decision",
            "FF01": "bit 0 dirty decision only; map bits are ignored",
            "dirty_DMA": "HDMA3 & FC -> HDMA3, width/cycle exact",
            "Stage1_post_DMA": "HDMA3 & FC -> H; FF01 not read",
            "pure_semantic": "pre-DMA HDMA3 & FC -> H; FF01 not read",
        },
        "timing": {
            "map_done_pure_delta_t": 0,
            "map_done_dirty_delta_t": 16,
            "dirty_DMA_boundary_delta_t": 0,
            "Stage1_row_destination_delta_t": 0,
            "instruction_width_delta_bytes": 0,
        },
        "patch": {
            "functional_changed_offsets": [
                f"0x{offset:06X}" for offset in sorted(functional)
            ],
            "functional_changed_bytes": len(functional),
        },
        "required_live_gates": [
            "natural Stage1 menu-close visible-page oracle",
            "FF01 map-bit mutation no longer affects displayed page",
            "FF01 dirty-bit mutation remains an effective negative control",
            "rotating-spike semantic and rendered continuity",
            "Stage1 wall-edge/north/room-transition oracles",
            "later-stage dual-plane ABI, visuals, and containment",
            "all-stage speed and audio cadence telemetry",
            "Analogue Pocket hardware confirmation before promotion",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = checked_output(args.output, "candidate")
    receipt_path = checked_output(args.receipt, "receipt")
    candidate, receipt = build(args.base.read_bytes())
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
