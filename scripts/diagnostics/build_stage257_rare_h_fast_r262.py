#!/usr/bin/env python3
"""Pass the Stage-2/5/7 rare-LUT selector through H for a faster detour."""

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
    build_special_runtime,
    build_wrapper,
    checksum,
    copy_loop,
    map_jump,
)
from build_stage257_rare_fast_r261 import build_rare_entry_fast


BASE_SHA256 = "f69296c597d8fa8a8bab605d6b4221588716ced1bbaa832ea6b9cb1ee8444a31"


def build_wrapper_h() -> bytes:
    a = Asm(0x5422)
    # Entry A is 0/1/4 for Stage 2/5/7. The original LUT clobbers HL and
    # returns with H=$C6, so carrying the selector in H preserves its ABI.
    a.db(0x67)  # LD H,A
    map_jump(a, BANK, RARE_ENTRY)
    code = a.finish()
    if len(code) > 20:
        raise AssertionError("H-selector wrapper exceeds original helper")
    return code + bytes(20 - len(code))


def build_rare_entry_h(special_length: int) -> bytes:
    a = Asm(RARE_ENTRY)
    a.db(0x7C, 0xB7)                       # LD A,H; OR A
    a.jr(0x28, "stage2")

    a.label("lut")
    # Exact rare-pickup assignments; tail-map bank 13 so the mapper consumes
    # the original helper call return in the correct ROM bank.
    a.db(
        0x21, 0xAE, 0xC6, 0x3E, 0x02, 0x22, 0x77,
        0x2E, 0xBE, 0x22, 0x77,
        0x2E, 0xC6, 0x22, 0x77,
        0x2E, 0xD6, 0x22, 0x77,
        0x3E, 0x0D, 0xC3, MAPPER & 0xFF, MAPPER >> 8,
    )

    a.label("stage2")
    a.db(0x3E, 0x03, 0xE0, 0x70)
    copy_loop(a, SPECIAL_BLOB, ROW_RUNTIME, special_length, "copy_special")
    a.db(
        0xAF,
        0xEA, ROW_TEMP & 0xFF, ROW_TEMP >> 8,
        0xEA, ROW_READY & 0xFF, ROW_READY >> 8,
        0x3E, 0x01, 0xE0, 0x70,
    )
    a.jr(0x18, "lut")
    return a.finish()


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    digest = hashlib.sha256(base).hexdigest()
    if digest != BASE_SHA256:
        raise AssertionError(f"wrong r261 base: {digest}")
    rom = bytearray(base)
    special_length = len(build_special_runtime())

    old_wrapper = build_wrapper()
    new_wrapper = build_wrapper_h()
    wrapper_off = bank_offset(13, 0x5422)
    if rom[wrapper_off:wrapper_off + len(old_wrapper)] != old_wrapper:
        raise AssertionError("r261 bank13 wrapper preimage changed")
    rom[wrapper_off:wrapper_off + len(new_wrapper)] = new_wrapper

    old_rare_active = build_rare_entry_fast(special_length)
    # r261 padded its shorter active body to r255's original 79-byte length.
    from build_stage2_runtime_sparse_r255 import build_rare_entry
    copy_length = len(build_rare_entry(special_length))
    old_rare = old_rare_active + bytes(copy_length - len(old_rare_active))
    new_rare_active = build_rare_entry_h(special_length)
    if len(new_rare_active) > copy_length:
        raise AssertionError("H-selector rare entry exceeds cave ownership")
    rare_off = bank_offset(BANK, RARE_ENTRY)
    if rom[rare_off:rare_off + copy_length] != old_rare:
        raise AssertionError("r261 rare-entry preimage changed")
    new_rare = new_rare_active + bytes(copy_length - len(new_rare_active))
    rom[rare_off:rare_off + copy_length] = new_rare
    checksum(rom)

    candidate = bytes(rom)
    report = {
        "schema": "penta-stage257-rare-h-fast-r262-build-v1",
        "status": "static-pass-emulator-required",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "selector_contract": "entry A=0/1/4 carried in H; original LUT owns HL",
        "bank13_wrapper_active_size": len(new_wrapper.rstrip(b"\x00")),
        "bank21_rare_active_size": len(new_rare_active),
        "stage5_stage7_fast_path": "LD A,H; OR A; fall through exact LUT",
        "stage2_installer_path": "H=0 branch; install special runtime; exact LUT",
        "removed_fast_path_work": [
            "DF56 scene-flag store/load",
            "redundant SVBK1 write",
            "121-byte original-runtime copy",
        ],
        "required_first_gate": "Stage5 2800-frame exact-scroll speed",
    }
    return candidate, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=Path("tmp/stage257-rare-fast-r261/candidate.gb"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("tmp/stage257-rare-h-fast-r262/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage257-rare-h-fast-r262/build-receipt.json"),
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
