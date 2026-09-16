#!/usr/bin/env python3
"""Rearm natural Stage-1 hazard art and restore the reviewed gold teeth.

Exact r287 enters normal GAME START with DF5B=$FF.  The immutable bank-1 art
loader interprets its low bits as an already-complete count, so a verifier that
does not inject VRAM sees blank hazard patterns.  Rearm DF5B in the existing
one-shot Stage-1 scene-entry timing pad, before the first loader service.

r281 also deliberately changed tooth color 2 from gold to gray.  Hardware
review rejected that choice, so restore the former $03FF word in both exact
Stage-1 palette mirrors.  No steady gameplay instruction changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage4-menu-exit-invalidation-r287/candidate.gb"
DEFAULT_OUTPUT = TMP / "stage1-cold-art-gold-r288/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-cold-art-gold-r288/build-receipt.json"
BASE_SHA256 = "a9bc2d2d5d7112584797229d03bfb2fe55a9bcb5fa3c1a33d30cddc3a8364898"
EXPECTED_SHA256 = "a18660d3ed0f883810d0ed542e63598f0a48a09280eb5f91e48aa621d70eb331"

BANK_SIZE = 0x4000
ENTRY_BANK = 13
ENTRY_ADDR = 0x6A33
ENTRY_OLD = bytes.fromhex("FA FD DC E0 91 3E 11 18 00 00 C3 E5 55")
ENTRY_NEW = bytes.fromhex("FA FD DC E0 91 AF EA 5B DF 00 C3 E5 55")
PALETTE_BANKS = (13, 16)
PALETTE_ADDR = 0x68C8
GRAY_ROW = bytes.fromhex("FF 7F 94 7E 4A 29 00 00")
GOLD_ROW = bytes.fromhex("FF 7F 94 7E FF 03 00 00")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address < 0x8000, "bad banked address")
    return bank * BANK_SIZE + address - 0x4000


def checked_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved != scratch and scratch in resolved.parents,
            f"{label} must be inside repository tmp/")
    return resolved


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == 32 * BANK_SIZE, "base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256, "wrong exact r287 base")

    entry_off = bank_offset(ENTRY_BANK, ENTRY_ADDR)
    require(source[entry_off:entry_off + len(ENTRY_OLD)] == ENTRY_OLD,
            "Stage-1 one-shot entry gate preimage changed")
    require(len(ENTRY_OLD) == len(ENTRY_NEW), "entry patch changed width")
    # Old: LD A,$11 (8T); JR +0 (12T); NOP (4T).
    # New: XOR A (4T); LD [$DF5B],A (16T); NOP (4T).
    require(8 + 12 + 4 == 4 + 16 + 4, "entry timing is not cycle exact")

    rom = bytearray(source)
    rom[entry_off:entry_off + len(ENTRY_NEW)] = ENTRY_NEW
    palette_receipts = []
    for bank in PALETTE_BANKS:
        offset = bank_offset(bank, PALETTE_ADDR)
        require(source[offset:offset + len(GRAY_ROW)] == GRAY_ROW,
                f"bank{bank} gray tooth row preimage changed")
        rom[offset:offset + len(GOLD_ROW)] = GOLD_ROW
        palette_receipts.append({
            "bank": bank,
            "address": f"${PALETTE_ADDR:04X}-${PALETTE_ADDR + 7:04X}",
            "old": GRAY_ROW.hex(" ").upper(),
            "new": GOLD_ROW.hex(" ").upper(),
        })

    update_checksums(rom)
    candidate = bytes(rom)
    require(digest(candidate) == EXPECTED_SHA256,
            f"candidate identity drift: {digest(candidate)}")
    require(candidate[0x014D] == 0xF9, "header checksum changed")
    require(candidate[0x014E:0x0150] == bytes.fromhex("40 DE"),
            "global checksum changed")

    changed = [
        index for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    ]
    allowed = {0x014D, 0x014E, 0x014F}
    allowed.update(range(entry_off, entry_off + len(ENTRY_NEW)))
    for bank in PALETTE_BANKS:
        offset = bank_offset(bank, PALETTE_ADDR)
        allowed.update(range(offset, offset + len(GOLD_ROW)))
    require(set(changed) <= allowed, "r288 escaped its owned byte ranges")
    functional = [offset for offset in changed if offset >= 0x0150]
    require(functional == sorted([
        entry_off + 5, entry_off + 6, entry_off + 7, entry_off + 8,
        bank_offset(13, 0x68CC), bank_offset(13, 0x68CD),
        bank_offset(16, 0x68CC), bank_offset(16, 0x68CD),
    ]), f"functional delta changed: {[hex(value) for value in functional]}")

    receipt: dict[str, object] = {
        "schema": "penta-stage1-cold-art-gold-r288-build-v1",
        "status": "STATIC_PASS_NATURAL_ROUTE_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": EXPECTED_SHA256,
        "checksums": {"header": "F9", "global": "40DE"},
        "entry_rearm": {
            "bank": ENTRY_BANK,
            "address": f"${ENTRY_ADDR:04X}-${ENTRY_ADDR + len(ENTRY_NEW) - 1:04X}",
            "old": ENTRY_OLD.hex(" ").upper(),
            "new": ENTRY_NEW.hex(" ").upper(),
            "operation": "DF5B=0 at exact Stage-1 scene entry",
            "subblock_t_cycles_before": 24,
            "subblock_t_cycles_after": 24,
            "steady_gameplay_path_changed": False,
        },
        "tooth_palette_reversion": palette_receipts,
        "changed_offsets": [f"0x{value:06X}" for value in changed],
        "functional_changed_bytes": len(functional),
        "contracts": {
            "exact_r287_base": True,
            "one_shot_scene_entry_width_and_cycles_exact": True,
            "DF5B_rearmed_before_first_live_loader_service": True,
            "loader_hot_path_byte_exact": True,
            "gray_294A_restored_to_gold_03FF_in_both_mirrors": True,
            "all_other_code_art_attributes_and_palettes_byte_exact": True,
        },
        "required_gates": [
            "untouched blank-SRAM GAME START proves natural bank-1 art load",
            "same-process room05 menu roundtrip and room01 hazard phases",
            "no clear cells, yellow trails, red/green wall bleed, or gray teeth",
            "strict all-stage speed qualification",
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
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
