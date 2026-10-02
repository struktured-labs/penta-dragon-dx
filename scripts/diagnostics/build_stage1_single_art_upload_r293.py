#!/usr/bin/env python3
"""Seed r292's complete immutable-art upload at pass 3 of 3.

The Stage-1 bank-1 loader gates on ``DF5B & 3 == 3``.  Every admitted pass
increments DF5B once and then executes the same complete synchronous GDMA
chain: neutral 01-04 (64 bytes), low teeth 64-69 (96 bytes), and high teeth
74-79 (96 bytes).  Starting natural Stage 1 at zero therefore uploads all
256 bytes three times.  Seed DF5B with two instead: the first service still
misses the ready gate, increments to three, uploads the complete 256-byte
image once, and arms the existing cold attribute sweep at the same terminal
value.

This diagnostic changes only the cycle-equal five-byte scene-entry subblock
and checksums.  It does not change any loader, art, palette, attribute, menu,
or gameplay hot-path byte.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-exact-background-r292/candidate.gb"
BASE_RECEIPT = TMP / "stage1-exact-background-r292/build-receipt.json"
DEFAULT_OUTPUT = TMP / "stage1-single-art-upload-r293/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-single-art-upload-r293/build-receipt.json"

BASE_SHA256 = "924173f3cd82ea0ee2aeb9d520746d60d97ae6b224a965e3f15a150d047d1cb1"
BASE_RECEIPT_SHA256 = (
    "fa5f837e0b5809d05dc1acafaa799613ff472720c0e8fda7e5b9406597125bd0"
)
EXPECTED_SHA256 = "b58c5de03c6c560f40e54a8d12b9c0a6c91820292027f1e608f7725f28c94497"

BANK_SIZE = 0x4000
ROM_SIZE = 32 * BANK_SIZE
ENTRY_BANK = 13
ENTRY_ADDR = 0x6A33
ENTRY_OLD = bytes.fromhex("FA FD DC E0 91 AF EA 5B DF 00 C3 E5 55")
ENTRY_NEW = bytes.fromhex("FA FD DC E0 91 3E 02 EA 5B DF C3 E5 55")

# Exact r292 loader chain.  These fixed preimages prove that the counter is a
# pass counter, not a three-way chunk selector, and that one pass owns all
# sixteen 16-byte GDMA blocks before returning to the VBlank wrapper.
LOADER_BLOBS = (
    (13, 0x6A0E, bytes.fromhex(
        "FA 5B DF E6 03 FE 03 C8 FA 80 D8 E6 F7 FE 02 C0 "
        "01 AA 6C C5 3E 13 C3 61 00 C9"
    )),
    (19, 0x6CAA, bytes.fromhex(
        "21 5B DF 34 3E 01 E0 4F 3E 6C E0 51 3E 10 E0 52 "
        "3E 90 E0 53 3E 10 E0 54 C3 EE 6B"
    )),
    (19, 0x6BEE, bytes.fromhex(
        "3E 03 E0 55 3E 56 E0 51 3E 40 E0 52 3E 96 E0 53 "
        "3E 40 E0 54 01 FF 6B C5 3E 07 C3 61 00"
    )),
    (7, 0x6BFF, bytes.fromhex(
        "3E 05 E0 55 3E 57 E0 51 3E 40 E0 52 C3 FF 65"
    )),
    (7, 0x65FF, bytes.fromhex(
        "3E 97 E0 53 3E 40 E0 54 3E 05 E0 55 C3 40 69"
    )),
    (7, 0x6940, bytes.fromhex(
        "01 83 6C C5 AF E0 4F 3E 0D C3 61 00"
    )),
    (13, 0x6C83, bytes.fromhex(
        "FA 5B DF FE 03 C0 21 4E DF C3 65 7D"
    )),
    (13, 0x7D65, bytes.fromhex("7E FE 7F C0 36 92 C9")),
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if bank <= 0 or not 0x4000 <= address < 0x8000:
        raise AssertionError((bank, address))
    return bank * BANK_SIZE + address - 0x4000


def checked_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    if resolved == scratch or scratch not in resolved.parents:
        raise AssertionError(f"{label} must be inside repository tmp/")
    return resolved


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict]:
    if len(source) != ROM_SIZE or digest(source) != BASE_SHA256:
        raise AssertionError("input is not the exact r292 candidate")
    if digest(base_receipt_bytes) != BASE_RECEIPT_SHA256:
        raise AssertionError("r292 receipt identity changed")
    base_receipt = json.loads(base_receipt_bytes)
    if base_receipt.get("candidate_sha256") != BASE_SHA256:
        raise AssertionError("r292 receipt names another candidate")

    for bank, address, payload in LOADER_BLOBS:
        offset = bank_offset(bank, address)
        if source[offset:offset + len(payload)] != payload:
            raise AssertionError(
                f"loader preimage changed at bank{bank}:${address:04X}"
            )

    # Static execution proof for one admitted loader service.
    fixed_loader = LOADER_BLOBS[0][2]
    private_loader = LOADER_BLOBS[1][2]
    if fixed_loader[:8] != bytes.fromhex("FA 5B DF E6 03 FE 03 C8"):
        raise AssertionError("DF5B ready gate is not exact")
    if private_loader[:4] != bytes.fromhex("21 5B DF 34"):
        raise AssertionError("DF5B is not incremented exactly once per pass")
    gdma_lengths = (0x03 + 1, 0x05 + 1, 0x05 + 1)
    gdma_bytes = tuple(blocks * 16 for blocks in gdma_lengths)
    if gdma_bytes != (64, 96, 96) or sum(gdma_bytes) != 256:
        raise AssertionError("loader no longer uploads one complete art image")
    start_index = 2
    if start_index & 3 == 3 or (start_index + 1) & 0xFF != 3:
        raise AssertionError("single-pass counter model changed")

    entry_offset = bank_offset(ENTRY_BANK, ENTRY_ADDR)
    if source[entry_offset:entry_offset + len(ENTRY_OLD)] != ENTRY_OLD:
        raise AssertionError("r292 Stage-1 entry preimage changed")
    rom = bytearray(source)
    rom[entry_offset:entry_offset + len(ENTRY_NEW)] = ENTRY_NEW
    update_checksums(rom)
    candidate = bytes(rom)
    if digest(candidate) != EXPECTED_SHA256:
        raise AssertionError(f"candidate identity drift: {digest(candidate)}")
    if candidate[0x014D] != 0xF9 or candidate[0x014E:0x0150] != bytes.fromhex(
        "56 93"
    ):
        raise AssertionError("candidate checksums changed")

    changed = [
        index
        for index, (old, new) in enumerate(zip(source, candidate, strict=True))
        if old != new
    ]
    functional = [index for index in changed if index >= 0x0150]
    if functional != list(range(entry_offset + 5, entry_offset + 10)):
        raise AssertionError("r293 escaped its five-byte entry subblock")
    if changed != [0x014E, 0x014F, *functional]:
        raise AssertionError("r293 changed bytes outside checksums and entry")

    receipt = {
        "schema": "penta-stage1-single-art-upload-r293-build-v1",
        "status": "STATIC_PASS_EXACT_NATURAL_AND_SPEED_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": EXPECTED_SHA256,
        "patch": {
            "bank": ENTRY_BANK,
            "address": "$6A38-$6A3C",
            "old": ENTRY_OLD[5:10].hex(" ").upper(),
            "new": ENTRY_NEW[5:10].hex(" ").upper(),
            "operation": "seed DF5B=2 at exact natural Stage-1 entry",
            "functional_changed_bytes": len(functional),
            "changed_offsets": [f"0x{index:06X}" for index in changed],
        },
        "static_loader_proof": {
            "ready_test": "DF5B & 3 == 3",
            "entry_index": start_index,
            "increment_before_first_gdma": True,
            "terminal_index": 3,
            "passes_from_r292_zero": 3,
            "passes_from_r293_two": 1,
            "redundant_complete_passes_removed": 2,
            "gdma_bytes_per_pass": list(gdma_bytes),
            "complete_bytes_per_pass": sum(gdma_bytes),
            "cold_sweep_still_arms_only_at_index_3": True,
            "loader_code_changed": False,
        },
        "timing_contract": {
            "old_entry_subblock_t_cycles": 24,
            "new_entry_subblock_t_cycles": 24,
            "entry_t_cycle_delta": 0,
            "steady_gameplay_t_cycle_delta": 0,
            "one_time_complete_uploads_removed": 2,
        },
        "observed_speed_context": {
            "r287_main_loop_hits": 661,
            "r292_main_loop_hits": 650,
            "original_main_loop_hits": 667,
            "r292_ratio": 650 / 667,
            "release_floor": 0.95,
            "r293_projection": "measure; static proof claims no exact hit count",
        },
        "transferred_r292_contracts": {
            "all_art_palette_attribute_and_menu_bytes_exact": True,
            "exact_background_model_unchanged": True,
            "live_LCDC_menu_selector_unchanged": True,
            "loader_and_cold_sweep_code_byte_exact": True,
        },
        "required_gates": [
            "natural blank-SRAM route reaches DF5B=3 after one loader pass",
            "natural bank-1 neutral/tooth art has zero mismatched bytes",
            "Stage-1 strict speed ratio remains at least 0.95",
            "menu entry/exit and low-health hazard receipts remain exact",
            "human review accepts the r292 dark-lavender tooth outline",
        ],
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = checked_output(args.output, "output")
    receipt_path = checked_output(args.receipt, "receipt")
    candidate, receipt = build(
        args.base.resolve().read_bytes(),
        args.base_receipt.resolve().read_bytes(),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
