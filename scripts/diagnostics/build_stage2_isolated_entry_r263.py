#!/usr/bin/env python3
"""Route only Stage 2 through the qualified six-row HDMA colorizer.

r260 installed its transition wrapper over the rare-pickup helper shared by
Stages 2, 5, and 7.  Although the wrapper preserved pixels, that bank-switch
detour shifted Stage 5 below its otherwise-qualified timing.  This diagnostic
restores the original bank-13 rare helper byte-for-byte and retargets only the
Stage-2 branch in the existing later-stage dispatcher to a nine-byte mapper
trampoline.  Stage 5 and Stage 7 therefore retain their original instruction
stream, while Stage 2 still installs r260's exact D400 runtime.

The trampoline occupies the trailing zero bytes of the existing generated
36-byte OAM-copy continuation record at bank13:$5546-$5569.  Its live prefix
ends in RET at $555C; the next resource record begins at $556A.  The installer
asserts that entire record, the dispatcher branch, and every replaced helper
byte before making any change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_stage2_runtime_sparse_r255 import (
    Asm,
    BANK,
    MAPPER,
    RARE_ENTRY,
    ROW_READY,
    ROW_RUNTIME,
    ROW_TEMP,
    SPECIAL_BLOB,
    bank_offset,
    build_rare_entry,
    build_special_runtime as build_r255_special_runtime,
    checksum,
    copy_loop,
    map_jump,
)


BASE_SHA256 = "799b288c6adf2939672685121127c7f60fc0ff2eb00e3f1eb27f8b7d12d7bff7"
STAGE2_BRANCH = 0x53F5
TRAMPOLINE = 0x555D
CONTINUATION_RECORD = 0x5546
CONTINUATION_RECORD_SIZE = 36

ORIGINAL_RARE = bytes.fromhex(
    "21 AE C6 3E 02 22 77 2E BE 22 77 2E C6 22 77 2E D6 22 77 C9"
)
CONTINUATION_PREFIX = bytes.fromhex(
    "11 F1 DB 21 30 58 0E 0C CD B3 09 CD 16 55 "
    "3E A8 EA 51 DF E1 D1 C1 C9"
)


def build_stage2_entry(runtime_length: int) -> bytes:
    """Install r260's runtime, reset its state, publish the rare LUT, return."""
    a = Asm(RARE_ENTRY)
    a.db(0x3E, 0x03, 0xE0, 0x70)  # SVBK3
    copy_loop(a, SPECIAL_BLOB, ROW_RUNTIME, runtime_length, "copy_special")
    a.db(
        0xAF,
        0xEA, ROW_TEMP & 0xFF, ROW_TEMP >> 8,
        0xEA, ROW_READY & 0xFF, ROW_READY >> 8,
        0x3E, 0x01, 0xE0, 0x70,  # restore stack's SVBK1
    )
    a.db(*ORIGINAL_RARE[:-1])      # omit RET; bank 13 mapper returns instead
    a.db(0x3E, 0x0D, 0xC3, MAPPER & 0xFF, MAPPER >> 8)
    return a.finish()


def raw_absolute_references(bank: bytes, address: int) -> list[int]:
    """Conservative census of literal little-endian target bytes in bank 13."""
    needle = bytes((address & 0xFF, address >> 8))
    return [
        0x4000 + offset
        for offset in range(len(bank) - 1)
        if bank[offset:offset + 2] == needle
    ]


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    digest = hashlib.sha256(base).hexdigest()
    if digest != BASE_SHA256:
        raise AssertionError(f"wrong qualified r260 base: {digest}")
    rom = bytearray(base)

    runtime_length = len(build_r255_special_runtime())
    old_entry = build_rare_entry(runtime_length)
    entry_off = bank_offset(BANK, RARE_ENTRY)
    if rom[entry_off:entry_off + len(old_entry)] != old_entry:
        raise AssertionError("r260 shared rare-entry preimage changed")

    rare_off = bank_offset(13, 0x5422)
    old_wrapper = bytes.fromhex(
        "B7 20 03 AF 18 02 3E 01 EA 56 DF 01 00 42 C5 3E 15 C3 61 00"
    )
    if rom[rare_off:rare_off + len(old_wrapper)] != old_wrapper:
        raise AssertionError("r260 bank13 rare wrapper preimage changed")

    branch_off = bank_offset(13, STAGE2_BRANCH)
    if rom[branch_off:branch_off + 3] != bytes.fromhex("CA 22 54"):
        raise AssertionError("Stage2 dispatcher branch preimage changed")

    record_off = bank_offset(13, CONTINUATION_RECORD)
    expected_record = CONTINUATION_PREFIX + bytes(
        CONTINUATION_RECORD_SIZE - len(CONTINUATION_PREFIX)
    )
    if rom[record_off:record_off + CONTINUATION_RECORD_SIZE] != expected_record:
        raise AssertionError("generated OAM continuation record changed")

    bank13 = base[13 * 0x4000:14 * 0x4000]
    preexisting_refs = raw_absolute_references(bank13, TRAMPOLINE)
    if preexisting_refs:
        raise AssertionError(
            f"trampoline address already appears in bank13: {preexisting_refs}"
        )

    trampoline = Asm(TRAMPOLINE)
    map_jump(trampoline, BANK, RARE_ENTRY)
    trampoline_code = trampoline.finish()
    if len(trampoline_code) != 9:
        raise AssertionError("mapper trampoline must remain exactly nine bytes")

    new_entry_active = build_stage2_entry(runtime_length)
    if len(new_entry_active) > len(old_entry):
        raise AssertionError("Stage2-only entry unexpectedly grew")
    new_entry = new_entry_active + bytes(len(old_entry) - len(new_entry_active))

    rom[entry_off:entry_off + len(old_entry)] = new_entry
    rom[rare_off:rare_off + len(ORIGINAL_RARE)] = ORIGINAL_RARE
    rom[branch_off:branch_off + 3] = bytes(
        (0xCA, TRAMPOLINE & 0xFF, TRAMPOLINE >> 8)
    )
    tramp_off = bank_offset(13, TRAMPOLINE)
    rom[tramp_off:tramp_off + len(trampoline_code)] = trampoline_code

    checksum(rom)
    candidate = bytes(rom)

    # Fail closed on the core containment claim after checksum mutation.
    if candidate[rare_off:rare_off + len(ORIGINAL_RARE)] != ORIGINAL_RARE:
        raise AssertionError("Stage5/7 rare helper was not restored exactly")
    if candidate[branch_off:branch_off + 3] != bytes.fromhex("CA 5D 55"):
        raise AssertionError("Stage2 dispatcher did not target the trampoline")
    if candidate[tramp_off:tramp_off + 9] != trampoline_code:
        raise AssertionError("Stage2 trampoline installation changed")

    changed = [index for index, pair in enumerate(zip(base, candidate))
               if pair[0] != pair[1]]
    report = {
        "schema": "penta-stage2-isolated-entry-r263-build-v1",
        "status": "static-pass-emulator-required",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "changed_byte_count_including_checksums": len(changed),
        "stage2_dispatch": "bank13:$53F5 JP Z,$555D",
        "trampoline": "bank13:$555D-$5565 -> bank21:$4200",
        "trampoline_record": "generated OAM continuation $5546-$5569",
        "trampoline_preexisting_absolute_refs": preexisting_refs,
        "stage5_stage7_rare_helper_byte_exact": True,
        "stage2_runtime_copy_length": runtime_length,
        "old_shared_entry_size": len(old_entry),
        "new_stage2_entry_size": len(new_entry_active),
        "non_stage2_restore_fallback_preserved": True,
        "required_first_gates": [
            "Stage5 strict speed >= .99 with exact scroll",
            "Stage2 strict speed >= .99 with exact scroll",
            "Stage2 8000-frame semantic equality and zero trails",
            "Stages5/7 transition and semantic containment",
        ],
    }
    return candidate, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=Path("tmp/stage2-runtime-hdma6-r260/candidate.gb"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("tmp/stage2-isolated-entry-r263/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage2-isolated-entry-r263/build-receipt.json"),
    )
    args = parser.parse_args()
    candidate, receipt = install(args.base.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
