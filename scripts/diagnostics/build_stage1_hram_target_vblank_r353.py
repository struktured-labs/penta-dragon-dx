#!/usr/bin/env python3
"""Build r353: relocate exact-map authority to audited-free HRAM FFC4.

FFC4 is outside the native FFA4-FFAB CHR-selector array and has no executable
reads in the current ROM.  Relocate r345's four map-authority sites from the
hardware-owned HDMA3 register to FFC4 without changing width or cycles.  Dirty
DMA setup still writes the normalized target to HDMA3 immediately before use.

The fixed publisher arms DF5C.  During VBlank, a nonzero FFC4 selects the
completed absolute page; a zero target preserves the legacy relative-toggle
fallback for non-Stage-1 routes that deliberately clear the latch.  No
emulator is invoked by this builder.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import build_stage1_deferred_vblank_presentation_r347 as r347


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
DEFAULT_OUTPUT = TMP / "stage1-hram-target-vblank-r353/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-hram-target-vblank-r353/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = (
    "45502bf1914f9d8b365978296e2186ce122fe513e400ca4996dbaa744e5f0f67"
)

TARGET_OPERAND = 0xC4
PENDING_ADDR = 0xDF5C
TARGET_SITES = (
    (1, 0x42EE, 0xE0, 0x53, "map-done target write"),
    (1, 0x4328, 0xF0, 0x53, "dirty DMA target read"),
    (19, 0x6C51, 0xE0, 0x53, "non-Stage-1 target clear"),
    (19, 0x6CCE, 0xF0, 0x53, "Stage-1 row target read"),
)

NEW_PRIMARY = bytes.fromhex(
    "F3 F0 40 07 38 16 "
    "FA 00 DC E6 0F E0 43 FA 02 DC E6 0F E0 42 "
    "F0 40 EE 08 E0 40 18 05 3E 01 EA 5C DF FB C9"
)

COMMIT_HELPER = bytes.fromhex(
    "FA 5C DF B7 CA 1D 6F AF EA 5C DF "
    "F0 97 FE 02 28 07 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 "
    "F0 C4 B7 28 10 "                       # zero -> legacy relative fallback
    "E6 04 07 47 AF E0 C4 "                # absolute page bit; consume target
    "F0 40 E6 F7 B0 E0 40 18 06 "         # preserve other LCDC controls
    "F0 40 EE 08 E0 40 "                   # zero target: relative toggle
    "C3 1D 6F"
)


def bank_offset(bank: int, address: int) -> int:
    return address if bank == 0 else bank * 0x4000 + address - 0x4000


def executable_hram_sites(source: bytes, operand: int) -> list[tuple[int, int, int]]:
    """Return reviewed direct LDH/absolute references, excluding raw data hits.

    The current production history already enumerates every executable FFC4
    reference as zero.  Keep a conservative raw census in the receipt and
    reject any actual read opcode or absolute access; raw E0 C4 pairs are
    known LD-DE immediate operands and are not executable LDH stores.
    """
    found: list[tuple[int, int, int]] = []
    for opcode in (0xF0, 0xE0):
        start = 0
        needle = bytes((opcode, operand))
        while True:
            offset = source.find(needle, start)
            if offset < 0:
                break
            found.append((offset // 0x4000, offset, opcode))
            start = offset + 1
    return found


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    r347.require(len(source) == r347.ROM_SIZE, "r345 base size changed")
    r347.require(r347.digest(source) == r347.BASE_SHA256,
                 f"wrong exact r345 base: {r347.digest(source)}")
    r347.require(r347.digest(receipt_bytes) == r347.BASE_RECEIPT_SHA256,
                 "r345 base receipt identity drifted")
    base_receipt = json.loads(receipt_bytes)
    r347.require(base_receipt.get("schema") == r347.BASE_SCHEMA,
                 "r345 receipt schema drifted")
    r347.require(base_receipt.get("candidate_sha256") == r347.BASE_SHA256,
                 "r345 receipt names another candidate")
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
    r347.require(source.count(bytes.fromhex("F0 C4")) == 0,
                 "FFC4 acquired a raw direct read")
    r347.require(source.count(bytes.fromhex("FA C4 FF")) == 0
                 and source.count(bytes.fromhex("EA C4 FF")) == 0,
                 "FFC4 acquired an absolute owner")
    for opcode in (
        bytes([0xCD, r347.COMMIT_ADDR & 0xFF, r347.COMMIT_ADDR >> 8]),
        bytes([0xC3, r347.COMMIT_ADDR & 0xFF, r347.COMMIT_ADDR >> 8]),
        bytes.fromhex("FA 5C DF"), bytes.fromhex("EA 5C DF"),
    ):
        r347.require(source.count(opcode) == 0,
                     "r353 hook/pending latch already has an owner")

    rom = bytearray(source)
    owned: set[int] = set()
    for bank, address, opcode, old_operand, label in TARGET_SITES:
        offset = bank_offset(bank, address)
        r347.require(source[offset:offset + 2] == bytes((opcode, old_operand)),
                     f"{label} preimage drifted")
        rom[offset + 1] = TARGET_OPERAND
        owned.add(offset + 1)
    rom[r347.PRIMARY_ADDR:r347.PRIMARY_END] = NEW_PRIMARY
    owned.update(range(r347.PRIMARY_ADDR, r347.PRIMARY_END))
    rom[r347.VBLANK_HOOK_CALL_ADDR:
        r347.VBLANK_HOOK_CALL_ADDR + 3] = r347.NEW_HOOK_CALL
    owned.update(range(r347.VBLANK_HOOK_CALL_ADDR,
                       r347.VBLANK_HOOK_CALL_ADDR + 3))
    rom[r347.COMMIT_FILE_OFFSET:
        r347.COMMIT_FILE_OFFSET + len(COMMIT_HELPER)] = COMMIT_HELPER
    owned.update(range(r347.COMMIT_FILE_OFFSET,
                       r347.COMMIT_FILE_OFFSET + len(COMMIT_HELPER)))
    r347.update_checksums(rom)
    candidate = bytes(rom)

    r347.require(candidate[0x42ED:0x42F2] == bytes.fromhex("7C E0 C4 F0 01"),
                 "map-done does not save H to FFC4 before dirty decision")
    r347.require(candidate[0x4328:0x432E]
                 == bytes.fromhex("F0 C4 E6 FC E0 53"),
                 "dirty DMA does not normalize FFC4 into HDMA3")
    row_clear = bank_offset(19, 0x6C50)
    row_dest = bank_offset(19, 0x6CCE)
    r347.require(candidate[row_clear:row_clear + 3]
                 == bytes.fromhex("AF E0 C4"),
                 "non-Stage-1 route does not clear FFC4")
    r347.require(candidate[row_dest:row_dest + 5]
                 == bytes.fromhex("F0 C4 E6 FC 67"),
                 "Stage-1 row owner does not consume FFC4")
    r347.require(len(NEW_PRIMARY) == 35
                 and NEW_PRIMARY[28:33] == bytes.fromhex("3E 01 EA 5C DF"),
                 "fixed publisher does not arm DF5C")
    r347.require(bytes.fromhex("F0 C4 B7 28 10") in COMMIT_HELPER,
                 "VBlank helper lacks target/fallback branch")
    r347.require(bytes.fromhex("AF E0 C4") in COMMIT_HELPER,
                 "VBlank helper does not consume FFC4")
    r347.require(COMMIT_HELPER[-3:] == bytes.fromhex("C3 1D 6F"),
                 "VBlank helper tail changed")

    changed = {i for i, pair in enumerate(zip(source, candidate, strict=True))
               if pair[0] != pair[1]}
    r347.require(changed <= owned | r347.CHECKSUM_OFFSETS,
                 f"r353 escaped owned bytes: "
                 f"{sorted(changed - owned - r347.CHECKSUM_OFFSETS)}")
    sha = r347.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        r347.require(sha == EXPECTED_CANDIDATE_SHA256,
                     f"candidate identity drift: {sha}")
    raw_ffc4 = executable_hram_sites(source, TARGET_OPERAND)
    receipt: dict[str, object] = {
        "schema": "penta-stage1-hram-target-vblank-r353-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r345_sha256": r347.BASE_SHA256,
        "base_receipt_sha256": r347.BASE_RECEIPT_SHA256,
        "candidate_sha256": sha,
        "authority": {
            "exact_target": "FFC4",
            "pending": "DF5C",
            "relocated_sites": [
                f"bank{bank}:${address:04X}" for bank, address, *_ in TARGET_SITES
            ],
            "source_direct_read_sites": 0,
            "source_absolute_sites": 0,
            "source_raw_e0c4_pairs": sum(1 for _, _, op in raw_ffc4 if op == 0xE0),
            "raw_e0c4_classification": "LD DE,$C4E0 immediate operand pairs",
            "native_selector_array": "FFA4-FFAB untouched",
        },
        "publisher": {
            "absolute_commit_pc": "bank13:$742C",
            "fallback_commit_pc": "bank13:$7434",
            "lcdc_policy": "VBlank only; preserve non-map bits",
            "zero_target_policy": "legacy relative toggle",
        },
        "timing": {
            "map_done_delta_t_vs_r345": 0,
            "DMA_setup_delta_t_vs_r345": 0,
            "Stage1_row_delta_t_vs_r345": 0,
            "publisher_wait_cycles": 0,
        },
        "required_live_gates": [
            "authenticated operator menu-exit replay",
            "phase-aligned rotating-spike rendered raster",
            "natural Stage1 menu and Timer ISR cadence",
            "FFC4 dynamic collision and native death/Continue lifecycle",
            "later-stage relative-fallback publication",
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
