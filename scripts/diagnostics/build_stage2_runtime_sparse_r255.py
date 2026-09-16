#!/usr/bin/env python3
"""Install a Stage-2-only sparse publisher through the existing WRAM row slot.

r254 proved that a 56-cell Stage-2 pickup window is both semantically complete
and fast, but its bank-1 compiler detour changed Stage-1 timing.  This isolated
experiment leaves bank 1 byte-for-byte identical to qualified r231.  Stage-2
scene entry replaces only SVBK3:$D400 with a compact dispatcher/row compiler:

* the first full publication to each physical map remains full;
* later rendered publications rewrite rows 0..3, columns 8..21;
* an unexpected non-Stage-2 call restores the original row helper and then
  executes it with the original bank-1 continuation;
* Stage 5/7 rare-LUT entry proactively restores the original helper.

This is diagnostic-only until every visual, semantic, and speed gate passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_stage2_sparse_pickup_r113 import Asm, bank_offset, checksum


BASE_SHA256 = "1e51c4801bfbc8ff961b81e09958e7ce4ba55de0ec4f8644e36f897d6aebc09c"
BANK = 21
RARE_ENTRY = 0x4200
SPARSE_ENTRY = 0x4300
RESTORE_ENTRY = 0x4900
ORIGINAL_BLOB = 0x4A00
SPECIAL_BLOB = 0x4B00
MAPPER = 0x0061

ROW_RUNTIME = 0xD400
ROW_TEMP = 0xD47E
ROW_READY = 0xD47F
SCENE_FLAG = 0xDF56

ATOMIC_DEST = 0xA5
STAGE = 0xBA
ROW_COUNT = 0xE0


def original_row_helper() -> bytes:
    code = bytes(
        opcode
        for _ in range(24)
        for opcode in (0x1A, 0x13, 0x4F, 0x0A, 0x22)
    ) + bytes((0xC9,))
    assert len(code) == 121
    return code


def copy_loop(a: Asm, source: int, destination: int, length: int, label: str) -> None:
    assert 0 < length <= 0xFF
    a.db(
        0x21, source & 0xFF, source >> 8,
        0x11, destination & 0xFF, destination >> 8,
        0x06, length,
    )
    a.label(label)
    a.db(0x2A, 0x12, 0x13, 0x05)
    a.jr(0x20, label)


def map_jump(a: Asm, bank: int, destination: int) -> None:
    a.db(
        0x01, destination & 0xFF, destination >> 8,
        0xC5,
        0x3E, bank,
        0xC3, MAPPER & 0xFF, MAPPER >> 8,
    )


def build_special_runtime() -> bytes:
    a = Asm(ROW_RUNTIME)
    # Any stale/non-Stage-2 use restores the byte-exact stock-width compiler.
    a.db(0xF0, STAGE, 0xFE, 0x01)
    a.jr(0x20, "restore")

    # C = ready bits. FFA5 is the tagged exact destination ($99/$9D).
    a.db(
        0xFA, ROW_READY & 0xFF, ROW_READY >> 8,
        0x4F,
        0xF0, ATOMIC_DEST,
        0xCB, 0x57,                       # BIT 2,A: $9D selects $9C00
    )
    a.jr(0x20, "map_9c")
    a.db(0x79, 0xCB, 0x41)                # BIT 0,C
    a.jr(0x20, "sparse")
    a.db(0xF0, ROW_COUNT, 0xFE, 0x01)
    a.jr(0x20, "full_row")
    a.db(0xCB, 0xC1, 0x79, 0xEA, ROW_READY & 0xFF, ROW_READY >> 8)
    a.jr(0x18, "full_row")

    a.label("map_9c")
    a.db(0x79, 0xCB, 0x49)                # BIT 1,C
    a.jr(0x20, "sparse")
    a.db(0xF0, ROW_COUNT, 0xFE, 0x01)
    a.jr(0x20, "full_row")
    a.db(0xCB, 0xC9, 0x79, 0xEA, ROW_READY & 0xFF, ROW_READY >> 8)
    a.jr(0x18, "full_row")

    a.label("sparse")
    # Sparse is legal only on the first row call and with a running LCD.
    a.db(0xF0, ROW_COUNT, 0xFE, 0x18)
    a.jr(0x20, "full_row")
    a.db(0xF0, 0x40, 0xCB, 0x7F)
    a.jr(0x28, "full_row")
    a.db(0xC1)                             # discard CALL $D400 return
    map_jump(a, BANK, SPARSE_ENTRY)

    a.label("restore")
    # Retain the CALL $D400 return beneath the mapper's synthetic frame.
    map_jump(a, BANK, RESTORE_ENTRY)

    a.label("full_row")
    # Compact semantic equivalent of the generated 24-cell unrolled helper.
    # D47E is outside the production helper's exact D400-D478 ownership.
    a.db(0x3E, 0x18, 0xEA, ROW_TEMP & 0xFF, ROW_TEMP >> 8)
    a.label("cell")
    a.db(
        0x1A, 0x13,                       # A=[DE], DE++
        0x4F, 0x0A, 0x22,                 # C=A; A=[BC]; [HL+]=A
        0xFA, ROW_TEMP & 0xFF, ROW_TEMP >> 8,
        0x3D,
        0xEA, ROW_TEMP & 0xFF, ROW_TEMP >> 8,
    )
    a.jr(0x20, "cell")
    a.db(0xC9)
    code = a.finish()
    assert len(code) <= ROW_TEMP - ROW_RUNTIME, len(code)
    return code


def build_sparse_helper() -> bytes:
    a = Asm(SPARSE_ENTRY)
    a.db(
        0x11, 0xA8, 0xC1,                 # DE = packed row0,col8
        0xF0, ATOMIC_DEST, 0xE6, 0xFE,
        0x67, 0x2E, 0x08,                 # HL = exact map row0,col8
        0x06, 0xC6,                       # BC = C600 + tile ID
        0x3E, 0x01, 0xE0, 0x4F,           # VBK1
    )
    for row in range(4):
        for column in range(14):
            wait3 = f"r{row}_c{column}_wait3"
            wait0 = f"r{row}_c{column}_wait0"
            # Preserve the compiled attribute in C while polling STAT in A;
            # no stack access is permitted before SVBK1 is restored.
            a.db(0x1A, 0x13, 0x4F, 0x0A, 0x4F)
            a.label(wait3)
            a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
            a.jr(0x20, wait3)
            a.label(wait0)
            a.db(0xF0, 0x41, 0xE6, 0x03)
            a.jr(0x20, wait0)
            a.db(0x79, 0x22)
        if row != 3:
            a.db(0x7B, 0xC6, 0x0A, 0x5F)
            a.jr(0x30, f"src_ok_{row}")
            a.db(0x14)
            a.label(f"src_ok_{row}")
            a.db(0x7D, 0xC6, 0x12, 0x6F)
            a.jr(0x30, f"dst_ok_{row}")
            a.db(0x24)
            a.label(f"dst_ok_{row}")
    a.db(
        0xAF, 0xE0, 0x4F,                 # VBK0
        0x3E, 0x01, 0xE0, 0x70,           # restore stack's SVBK1
    )
    map_jump(a, 1, 0x4353)                # exact dirty completion
    return a.finish()


def build_restore_helper() -> bytes:
    a = Asm(RESTORE_ENTRY)
    a.db(0x3E, 0x03, 0xE0, 0x70)
    copy_loop(a, ORIGINAL_BLOB, ROW_RUNTIME, len(original_row_helper()), "copy")
    # Recreate the exact registers at the first CALL $D400, then restore ROM
    # bank 1 and land on the newly restored row helper. Its RET consumes the
    # original compiler call frame still resident in SVBK3.
    a.db(
        0x11, 0xA0, 0xC1,
        0x21, 0x00, 0xD0,
        0x06, 0xC6,
    )
    map_jump(a, 1, ROW_RUNTIME)
    return a.finish()


def build_rare_entry(special_length: int) -> bytes:
    a = Asm(RARE_ENTRY)
    a.db(0xFA, SCENE_FLAG & 0xFF, SCENE_FLAG >> 8, 0xB7)
    a.jr(0x20, "restore_original")
    a.db(0x3E, 0x03, 0xE0, 0x70)
    copy_loop(a, SPECIAL_BLOB, ROW_RUNTIME, special_length, "copy_special")
    a.db(
        0xAF,
        0xEA, ROW_TEMP & 0xFF, ROW_TEMP >> 8,
        0xEA, ROW_READY & 0xFF, ROW_READY >> 8,
    )
    a.jr(0x18, "runtime_ready")

    a.label("restore_original")
    a.db(0x3E, 0x03, 0xE0, 0x70)
    copy_loop(a, ORIGINAL_BLOB, ROW_RUNTIME, len(original_row_helper()), "copy_original")

    a.label("runtime_ready")
    a.db(
        0x3E, 0x01, 0xE0, 0x70,
        # Byte-exact Stage-2/5/7 rare-pickup LUT.
        0x21, 0xAE, 0xC6, 0x3E, 0x02, 0x22, 0x77,
        0x2E, 0xBE, 0x22, 0x77,
        0x2E, 0xC6, 0x22, 0x77,
        0x2E, 0xD6, 0x22, 0x77,
        0x3E, 0x0D, 0xC3, MAPPER & 0xFF, MAPPER >> 8,
    )
    return a.finish()


def build_wrapper() -> bytes:
    a = Asm(0x5422)
    a.db(0xB7)
    a.jr(0x20, "not_stage2")
    a.db(0xAF)
    a.jr(0x18, "store")
    a.label("not_stage2")
    a.db(0x3E, 0x01)
    a.label("store")
    a.db(0xEA, SCENE_FLAG & 0xFF, SCENE_FLAG >> 8)
    map_jump(a, BANK, RARE_ENTRY)
    code = a.finish()
    assert len(code) == 20
    return code


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    digest = hashlib.sha256(base).hexdigest()
    if digest != BASE_SHA256:
        raise AssertionError(f"wrong qualified r231 base: {digest}")
    rom = bytearray(base)
    rare_preimage = bytes.fromhex(
        "21 AE C6 3E 02 22 77 2E BE 22 77 2E C6 22 77 2E D6 22 77 C9"
    )
    rare_off = bank_offset(13, 0x5422)
    if rom[rare_off:rare_off + len(rare_preimage)] != rare_preimage:
        raise AssertionError("rare-LUT preimage changed")

    original = original_row_helper()
    special = build_special_runtime()
    sparse = build_sparse_helper()
    restore = build_restore_helper()
    rare = build_rare_entry(len(special))
    wrapper = build_wrapper()
    regions = (
        (RARE_ENTRY, rare, "rare entry"),
        (SPARSE_ENTRY, sparse, "sparse helper"),
        (RESTORE_ENTRY, restore, "restore helper"),
        (ORIGINAL_BLOB, original, "original row blob"),
        (SPECIAL_BLOB, special, "special row blob"),
    )
    ordered = sorted((address, address + len(payload), label)
                     for address, payload, label in regions)
    for (_, end, left), (start, _, right) in zip(ordered, ordered[1:]):
        if end > start:
            raise AssertionError(f"{left} overlaps {right}")
    for address, payload, label in regions:
        off = bank_offset(BANK, address)
        if rom[off:off + len(payload)] != bytes([0xFF]) * len(payload):
            raise AssertionError(f"{label} cave is not erased")
        rom[off:off + len(payload)] = payload
    rom[rare_off:rare_off + len(wrapper)] = wrapper

    # The central safety invariant: the compiler and all Stage-1 postcopy
    # bytes remain exactly qualified-r231. No global detour is installed.
    compiler_slice = slice(0x42EC, 0x435B)
    if rom[compiler_slice] != base[compiler_slice]:
        raise AssertionError("bank-1 compiler/postcopy path changed")

    checksum(rom)
    changed = [i for i, (old, new) in enumerate(zip(base, rom)) if old != new]
    receipt = {
        "schema": "penta-stage2-runtime-sparse-r255-build-v1",
        "status": "static-pass-emulator-required",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(rom).hexdigest(),
        "changed_byte_count_including_checksums": len(changed),
        "bank1_compiler_sha256": hashlib.sha256(base[compiler_slice]).hexdigest(),
        "bank1_compiler_byte_exact": True,
        "special_runtime_size": len(special),
        "production_runtime_range": "$D400-$D478",
        "private_runtime_state": ["$D47E", "$D47F"],
        "sparse_window": "packed/VRAM rows 0..3, columns 8..21",
        "regions": {
            label: f"bank{BANK}:${address:04X}-${address + len(payload) - 1:04X}"
            for address, payload, label in regions
        },
        "required_gates": [
            "Stage1 menu/item/low-health visual contract before speed",
            "Stage1 atomic tilemap-copy contract",
            "Stage2 strict exact-scroll speed >= .99",
            "Stage2 8000-frame dual-map semantic equality and zero trails",
            "Stages3-7 8000-frame semantic containment",
            "full r231 visual incident matrix",
        ],
    }
    return bytes(rom), receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
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
