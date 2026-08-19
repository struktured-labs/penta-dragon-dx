#!/usr/bin/env python3
"""Restore the interrupt-stable arena decision latch on the qualified v72 ROM.

This is deliberately a narrow lineage experiment.  It rewrites only the
postcomputed bank-1 copier, the two bank-13 WRAM-runtime source fragments, and
the cold installer length.  Ted/Penta and every other v72 byte remain fixed so
performance and geometry receipts compare one variable at a time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_v301_gdma import create_inline_tile_copy_postcomputed_attrs
from scripts.build_v302_title_fix import (
    ARENA_ATTR_SEMANTIC_FRAGMENT_SIZE,
    ARENA_ATTR_SEMANTIC_SIG_A_ADDR,
    ARENA_ATTR_SEMANTIC_SIG_B_ADDR,
    BANK13,
    INLINE_ATTR_DECISION_HELPER_ADDR,
    OAM_WRAM_COPY_TAIL_ADDR,
    STAGE1_ATOMIC_SETUP_ADDR,
    STAGE1_ATOMIC_WRAP_ADDR,
    STAGE1_HAZARD_PURE_MAP_ADDR,
    STAGE1_SOURCE_GENERATION_RST,
    build_arena_attr_semantic_decider,
    build_oam_wram_copy_tail,
)


QUALIFIED_V72_SHA256 = (
    "c2782a829fd6f759c4a96d7b94ff7d7abeb88fbc1ce24695b7f1f896309eb53e"
)
INLINE_ADDR = 0x42A7
INLINE_CAPACITY = 190
PENTA_SAFE_RETURN_ADDR = 0x4365


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    assert 0x4000 <= address < 0x8000
    return bank * 0x4000 + address - 0x4000


def global_checksum(data: bytes | bytearray) -> int:
    return (sum(data[:0x014E]) + sum(data[0x0150:])) & 0xFFFF


def replace_region(
    rom: bytearray,
    *,
    name: str,
    bank: int,
    address: int,
    capacity: int,
    payload: bytes,
) -> dict[str, object]:
    assert len(payload) <= capacity, (name, len(payload), capacity)
    offset = bank_offset(bank, address)
    before = bytes(rom[offset:offset + capacity])
    after = payload + bytes(capacity - len(payload))
    rom[offset:offset + capacity] = after
    return {
        "name": name,
        "bank": bank,
        "address": address,
        "capacity": capacity,
        "payload_length": len(payload),
        "before_sha256": sha256(before),
        "after_sha256": sha256(after),
        "changed_offsets": [
            index for index, (old, new) in enumerate(zip(before, after)) if old != new
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    original = args.base.read_bytes()
    base_sha = sha256(original)
    if base_sha != QUALIFIED_V72_SHA256:
        raise SystemExit(
            f"base is not qualified v72: {base_sha} != {QUALIFIED_V72_SHA256}"
        )
    rom = bytearray(original)

    inline = create_inline_tile_copy_postcomputed_attrs(
        INLINE_ATTR_DECISION_HELPER_ADDR + 3,
        STAGE1_ATOMIC_SETUP_ADDR,
        STAGE1_ATOMIC_WRAP_ADDR,
        STAGE1_HAZARD_PURE_MAP_ADDR,
        STAGE1_SOURCE_GENERATION_RST,
    )
    assert len(inline) == 188
    assert bytes.fromhex("CB 70 20") in inline

    semantic = build_arena_attr_semantic_decider()
    assert tuple(map(len, semantic)) == (35, 36, 31, 0, 31)
    assert bytes.fromhex("CB B0 CB 4C 28 02 CB F0") in semantic[2]
    installer, _ = build_oam_wram_copy_tail(postcomputed_attrs=True)
    assert len(installer) == 22

    penta_tail_offset = bank_offset(1, PENTA_SAFE_RETURN_ADDR)
    penta_tail_before = bytes(rom[penta_tail_offset:penta_tail_offset + 9])

    regions = [
        replace_region(
            rom,
            name="bank1_postcomputed_copier",
            bank=1,
            address=INLINE_ADDR,
            capacity=INLINE_CAPACITY,
            payload=inline,
        ),
        replace_region(
            rom,
            name="arena_semantic_runtime_source_a",
            bank=13,
            address=ARENA_ATTR_SEMANTIC_SIG_A_ADDR,
            capacity=ARENA_ATTR_SEMANTIC_FRAGMENT_SIZE,
            payload=semantic[1],
        ),
        replace_region(
            rom,
            name="arena_semantic_runtime_source_b",
            bank=13,
            address=ARENA_ATTR_SEMANTIC_SIG_B_ADDR,
            capacity=ARENA_ATTR_SEMANTIC_FRAGMENT_SIZE,
            payload=semantic[2],
        ),
        replace_region(
            rom,
            name="arena_semantic_cold_installer",
            bank=13,
            address=OAM_WRAM_COPY_TAIL_ADDR,
            capacity=ARENA_ATTR_SEMANTIC_FRAGMENT_SIZE,
            payload=installer,
        ),
    ]

    penta_tail_after = bytes(rom[penta_tail_offset:penta_tail_offset + 9])
    assert penta_tail_after == penta_tail_before
    assert rom[:0x014E] == original[:0x014E]
    assert rom[0x0150:0x42A7] == original[0x0150:0x42A7]
    checksum = global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    receipt = {
        "status": "PASS",
        "base": str(args.base),
        "base_sha256": base_sha,
        "output": str(args.output),
        "output_sha256": sha256(rom),
        "regions": regions,
        "penta_safe_return_preserved": True,
        "penta_safe_return_sha256": sha256(penta_tail_after),
        "global_checksum": f"{checksum:04x}",
        "total_changed_bytes": sum(len(region["changed_offsets"]) for region in regions),
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
