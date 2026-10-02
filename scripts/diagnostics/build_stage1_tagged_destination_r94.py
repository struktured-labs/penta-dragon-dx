#!/usr/bin/env python3
"""Build the static-only corrected tagged-FFA5 destination experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_stage1_carry_dirty_signal import global_checksum  # noqa: E402
from build_v301_gdma import create_inline_tile_copy_postcomputed_attrs
from build_v302_title_fix import (
    STAGE1_ATOMIC_SETUP_ADDR,
    build_stage1_atomic_setup,
    build_stage1_hazard_room_dispatcher,
)


BASE_SHA256 = "9f5e9e2168ca1f4c56864a312f8267ef97fb92c886438a1e779b324886dc6a26"
BANK_SIZE = 0x4000
INLINE_START = 0x42A7
# $4368-$436D is the live atomic-wrapper tail installed after the generated
# copier. Only the preceding 193-byte bank-1 body belongs to this experiment.
INLINE_END = 0x4368
ATOMIC_SOURCE_BANK = 13
ATOMIC_SOURCE_ADDR = 0x7B13
PRIVATE_BANK = 19
DISPATCH_ADDR = 0x6CCE


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    return bank * BANK_SIZE + address - 0x4000


def replace_exact(
    rom: bytearray, offset: int, expected: bytes, replacement: bytes,
    label: str,
) -> dict[str, object]:
    if len(expected) != len(replacement):
        raise AssertionError(f"{label}: width-changing patch")
    actual = bytes(rom[offset:offset + len(expected)])
    if actual != expected:
        raise AssertionError(
            f"{label}: expected {expected.hex(' ')}, got {actual.hex(' ')}"
        )
    rom[offset:offset + len(replacement)] = replacement
    return {
        "label": label,
        "offset": f"0x{offset:05X}",
        "before": expected.hex(" "),
        "after": replacement.hex(" "),
    }


def immediate_hram_census(rom: bytes | bytearray) -> dict[str, object]:
    forms = {
        "ldh_write_e0_a5": bytes.fromhex("E0 A5"),
        "ldh_read_f0_a5": bytes.fromhex("F0 A5"),
        "absolute_write_ea_a5_ff": bytes.fromhex("EA A5 FF"),
        "absolute_read_fa_a5_ff": bytes.fromhex("FA A5 FF"),
    }
    result: dict[str, object] = {}
    for name, pattern in forms.items():
        offsets = [
            index for index in range(len(rom) - len(pattern) + 1)
            if rom[index:index + len(pattern)] == pattern
        ]
        result[name] = [f"0x{offset:05X}" for offset in offsets]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    original = args.base.read_bytes()
    if digest(original) != BASE_SHA256:
        raise SystemExit("base is not exact r90")
    rom = bytearray(original)

    baseline_inline = create_inline_tile_copy_postcomputed_attrs(
        0x3485, STAGE1_ATOMIC_SETUP_ADDR, 0xDBDF, 0xDBF1, 0xDF,
    )
    tagged_inline = create_inline_tile_copy_postcomputed_attrs(
        0x3485, STAGE1_ATOMIC_SETUP_ADDR, 0xDBDF, 0xDBF1, 0xDF,
        tagged_exact_destination=True,
    )
    assert len(baseline_inline) == 192
    assert len(tagged_inline) == 193
    assert bytes(rom[INLINE_START:INLINE_START + len(baseline_inline)]) == (
        baseline_inline
    )
    assert bytes(rom[INLINE_START + len(baseline_inline):INLINE_END]) == bytes(
        INLINE_END - INLINE_START - len(baseline_inline)
    )
    rom[INLINE_START:INLINE_END] = tagged_inline + bytes(
        INLINE_END - INLINE_START - len(tagged_inline)
    )

    # The title RST jumps directly to the generated tail and therefore moves
    # with the reassembled inline body.
    old_title_entry = INLINE_START + len(baseline_inline) - 14
    new_title_entry = INLINE_START + len(tagged_inline) - 14
    title_vector_before = bytes([
        0xC3, old_title_entry & 0xFF, old_title_entry >> 8,
    ])
    title_vector_after = bytes([
        0xC3, new_title_entry & 0xFF, new_title_entry >> 8,
    ])
    patches = [replace_exact(
        rom, 0x0030, title_vector_before, title_vector_after,
        "RST30 title pure entry",
    )]

    atomic_before = build_stage1_atomic_setup()
    atomic_after = build_stage1_atomic_setup(tagged_exact_destination=True)
    assert len(atomic_before) == len(atomic_after) == 14
    atomic_offset = bank_offset(ATOMIC_SOURCE_BANK, ATOMIC_SOURCE_ADDR)
    patches.append(replace_exact(
        rom, atomic_offset, atomic_before, atomic_after,
        "bank13 cold-copy source for DA13 tagged atomic setup",
    ))

    dispatch_before = build_stage1_hazard_room_dispatcher()
    dispatch_after = build_stage1_hazard_room_dispatcher(
        tagged_exact_destination=True
    )
    assert len(dispatch_before) == len(dispatch_after) == 16
    dispatch_offset = bank_offset(PRIVATE_BANK, DISPATCH_ADDR)
    patches.append(replace_exact(
        rom, dispatch_offset, dispatch_before, dispatch_after,
        "bank19 exact-destination postcopy dispatcher",
    ))

    # Static tagged-state contract. Entry always writes an even exact H;
    # changed layouts pass through the DI-before-CALL tagged atomic setup and
    # make it odd. Mapdone uses RRA Carry without modifying FFA5. The compiler
    # and dispatcher mask bit 0 before loading H.
    assert tagged_inline[:10] == bytes.fromhex(
        "2E 00 7C E0 A5 16 FF CD 85 34"
    )
    assert bytes.fromhex("F3 CD 13 DA 00") in tagged_inline
    assert bytes.fromhex("F0 A5 1F 38") in tagged_inline
    assert bytes.fromhex("3E 03 E0 70 F0 A5 3D 67 E0 53") in tagged_inline
    assert bytes.fromhex("AF E0 52 7C E0 53") not in tagged_inline
    assert dispatch_after[:8] == bytes.fromhex("F0 A5 E6 FE 67 C3 A7 6B")
    assert atomic_after[:4] == bytes.fromhex("7C 3C E0 A5")
    assert 0xF3 not in atomic_after[:5]

    census = immediate_hram_census(rom)
    assert census == {
        "ldh_write_e0_a5": [
            "0x042AA",                    # every normal copier entry
            "0x35836",                    # relocated later-stage clear source
            "0x37B15",                    # tagged DA13 cold-copy source
            "0x43B14",                    # inert Ted-private bank clone source
            "0x4EC51",                    # bank19 common exit clear
        ],
        "ldh_read_f0_a5": [
            "0x042ED",                    # mapdone bit-0 decision
            "0x04328",                    # dirty-only compiler normalization
            "0x4ECCE",                    # bank19 exact destination
        ],
        "absolute_write_ea_a5_ff": [],
        "absolute_read_fa_a5_ff": [],
    }
    b5_sequence = {
        "stage1_pure": (
            "entry writes even exact H; B!=5 calls postcopy; bank19 clears"
        ),
        "stage1_dirty": (
            "DA13 writes odd exact H; compiler uses live final H; "
            "postcopy masks bit0; bank19 clears"
        ),
        "later_pure_b5": (
            "entry overwrites even exact H before mapdone; B=5 skips the "
            "dirty compiler and postcopy dispatcher; next normal entry "
            "overwrites before read"
        ),
        "later_dirty": (
            "DA13 writes odd exact H; dirty tail enters later guard and clears"
        ),
        "title_b5": (
            "title bypasses entry but reads only bit0; every persistent "
            "value is zero or an even pure tag because all odd paths clear"
        ),
        "asynchronous_reader": (
            "all-ROM immediate census has no reader outside mapdone, its "
            "dirty-only compiler arm, and the bank19 dispatcher; B=5 pure "
            "never invokes the latter two"
        ),
    }

    checksum = global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    receipt = {
        "status": "PASS_STATIC_EMULATOR_FORBIDDEN_PENDING_COORDINATION",
        "promotable": False,
        "base": str(args.base),
        "base_sha256": digest(original),
        "output": str(args.output),
        "output_sha256": digest(rom),
        "inline": {
            "baseline_size": len(baseline_inline),
            "tagged_size": len(tagged_inline),
            "available": INLINE_END - INLINE_START,
            "title_entry_before": f"0x{old_title_entry:04X}",
            "title_entry_after": f"0x{new_title_entry:04X}",
        },
        "tag_contract": {
            "pure": {"98": "98", "9C": "9C", "bit0": 0},
            "dirty": {"98": "99", "9C": "9D", "bit0": 1},
            "mapdone_test": "LDH A,[FFA5]; RRA; JR C,compile",
            "compiler_normalization": (
                "dirty-only LDH A,[FFA5]; DEC A; LD H,A; publish HDMA3"
            ),
            "dispatcher_normalization": "AND $FE before LD H,A",
            "dc0b_fallback_removed": True,
        },
        "timing": {
            "entry_store_replaces_24T_phase_setup": True,
            "dirty_DI_moved_before_CALL": True,
            "dirty_postcall_JR_replaced_by_NOP": True,
            "dirty_setup_delta_t_cycles": -4,
            "mapdone_test_width_and_cycles_unchanged_vs_r90": True,
            "compiler_destination_normalization_delta_t_cycles": 0,
        },
        "known_static_risk": (
            "neutral/later pure B=5 exits leave the even exact FFA5 value "
            "until the next normal entry overwrites it; title bypasses the "
            "decision and does not consume it"
        ),
        "ffa5_immediate_all_rom_census": census,
        "b5_title_later_sequence": b5_sequence,
        "patches": patches,
        "global_checksum": f"{checksum:04x}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
