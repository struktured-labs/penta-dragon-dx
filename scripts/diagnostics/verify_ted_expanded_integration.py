#!/usr/bin/env python3
"""Fail-closed static contract for the production expanded-bank Ted path."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))

from scripts import build_v302_title_fix as build  # noqa: E402
from scripts import menu_icon_colorization as menu_icons  # noqa: E402
from scripts.arena_semantic_key import (  # noqa: E402
    HELPER_BANK as ARENA_SEMANTIC_HELPER_BANK,
    HELPER_ENTRY as ARENA_SEMANTIC_HELPER_ENTRY,
    PENTA_SEAM_ENTRY,
    build_arena_postcopy_dispatcher,
    build_helper as build_arena_semantic_helper,
    build_penta_seam_helper,
)
from prototype_ted_expanded_bank import (  # noqa: E402
    BANK_SIZE,
    EXPANDED_BANK,
    EXPANDED_ENTRY,
    LATER_PUBLISH_DISPATCH_STUB,
    LATER_PUBLISH_ENTRY,
    LATER_PUBLISH_RETURN,
    LATER_SCROLL_BANK,
    NATIVE_POSE_BANK,
    NON_PUBLISHABLE_POSES,
    POSE_COUNT,
    TED_CALL_SITE,
    TED_ENTRY,
    TED_SPARSE_ENTRY,
    TED_SPARSE_SETUP,
    TRAMPOLINE_FRONT,
    TRAMPOLINE_TAIL,
    bank_offset,
    build_later_scroll_edge_bank,
    build_native_pose_bank,
    decode_poses,
    global_checksum,
    header_checksum,
)
from ted_native_sparse_pose_data import (  # noqa: E402
    SOURCE_RECORDS,
    SOURCE_SHA256,
)


SCHEMA = "penta-ted-expanded-integration-v1"
EXPECTED_SOURCE_SHA256 = (
    "1e61ad967b7b9714ae285f911bb483634dfdfde4bc65bcc44476840ab57df7cd"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def exact(rom: bytes, offset: int, expected: bytes) -> bool:
    return rom[offset:offset + len(expected)] == expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--shalamar-native-exact-class",
        type=lambda value: int(value, 0),
        choices=range(16),
        help=(
            "expect the optional content-selected Shalamar native-copy "
            "cadence class (0..15)"
        ),
    )
    parser.add_argument(
        "--menu-icon-colors",
        action="store_true",
        help="expect the isolated bank-20 item-menu attribute publisher",
    )
    args = parser.parse_args()

    rom = args.rom.resolve().read_bytes()
    native_bank = build_native_pose_bank()
    poses = decode_poses()
    envelope = build.build_ted_inside_envelope_rom()[1]
    angela = bytes(build._bg_table_angela())

    call_site = bytes([
        0xCD, TRAMPOLINE_FRONT & 0xFF, TRAMPOLINE_FRONT >> 8,
    ])
    front = bytes([
        0xFA, 0x80, 0xD8,
        0xFE, 0x10,
        0xC2, 0x95, 0x42,
        0xC3, TRAMPOLINE_TAIL & 0xFF, TRAMPOLINE_TAIL >> 8,
    ])
    tail = bytes([
        0x3E, EXPANDED_BANK,
        0x21, EXPANDED_ENTRY & 0xFF, EXPANDED_ENTRY >> 8,
        0xE5,
        0xC3, 0x61, 0x00,
    ])
    expanded_entry = bytes([
        0xF3,
        0x01, 0x08, 0x00,
        0x11, 0xE0, 0xC3,
        0xC3, TED_ENTRY & 0xFF, TED_ENTRY >> 8,
    ])
    sparse_entry = bytes([
        0xC5, 0xD5, 0xE5,
        0xC3, TED_SPARSE_SETUP & 0xFF, TED_SPARSE_SETUP >> 8,
    ])
    sparse_setup = bytes([
        0x3E, NATIVE_POSE_BANK,
        0xCD, 0x61, 0x00,
    ])

    bank16 = rom[EXPANDED_BANK * BANK_SIZE:(EXPANDED_BANK + 1) * BANK_SIZE]
    bank17 = rom[
        NATIVE_POSE_BANK * BANK_SIZE:(NATIVE_POSE_BANK + 1) * BANK_SIZE
    ]
    bank18 = rom[
        LATER_SCROLL_BANK * BANK_SIZE:(LATER_SCROLL_BANK + 1) * BANK_SIZE
    ]
    bank16_envelope_offset = (
        build.TED_ENVELOPE_ROW_TABLE_ROM_ADDR - 0x4000
    )
    production_angela_offset = (
        13 * BANK_SIZE + build.ANGELA_TABLE_ADDR - 0x4000
    )
    arena_helper = build_arena_semantic_helper(
        shalamar_native_exact_class=args.shalamar_native_exact_class,
    )
    penta_seam_helper = build_penta_seam_helper()
    arena_postcopy_dispatcher = build_arena_postcopy_dispatcher()
    arena_helper_bank = rom[
        ARENA_SEMANTIC_HELPER_BANK * BANK_SIZE:
        (ARENA_SEMANTIC_HELPER_BANK + 1) * BANK_SIZE
    ]
    arena_helper_offset = ARENA_SEMANTIC_HELPER_ENTRY - 0x4000
    penta_seam_offset = PENTA_SEAM_ENTRY - 0x4000
    expected_arena_bank = bytearray([0xFF]) * BANK_SIZE
    expected_arena_bank[
        arena_helper_offset:arena_helper_offset + len(arena_helper)
    ] = arena_helper
    expected_arena_bank[
        penta_seam_offset:penta_seam_offset + len(penta_seam_helper)
    ] = penta_seam_helper
    if args.menu_icon_colors:
        canonical_offset = bank_offset(13, 0x7000)
        canonical_lut = rom[canonical_offset:canonical_offset + 0x100]
        expected_arena_bank = bytearray(menu_icons.expected_bank20(
            canonical_lut, bytes(expected_arena_bank)
        ))
    blank_tail = rom[(ARENA_SEMANTIC_HELPER_BANK + 1) * BANK_SIZE:]
    native_fixed_stub = bytes.fromhex("7F CD 7B FE FF")
    native_bank1_entry = bytes.fromhex(
        "FA 0B DC 3C E6 01 EA 0B DC 28 05 "
        "26 9C C3 A7 42 26 98"
    )

    checks = {
        "rom_is_512k_32_banks": len(rom) == 32 * BANK_SIZE,
        "mapper_is_mbc5_ram_battery": len(rom) > 0x0148
            and rom[0x0147] == 0x1B,
        "header_declares_512k": len(rom) > 0x0148 and rom[0x0148] == 0x04,
        "header_checksum": len(rom) >= 0x150
            and rom[0x014D] == header_checksum(bytearray(rom)),
        "global_checksum": len(rom) >= 0x150
            and int.from_bytes(rom[0x014E:0x0150], "big")
                == global_checksum(bytearray(rom)),
        "fixed_call_routes_only_ted": exact(rom, TED_CALL_SITE, call_site),
        "scene_gated_front_trampoline": exact(
            rom, bank_offset(1, TRAMPOLINE_FRONT), front
        ),
        "bank_safe_tail_trampoline": exact(
            rom, bank_offset(1, TRAMPOLINE_TAIL), tail
        ),
        "expanded_bank_entry_abi": exact(
            rom, EXPANDED_BANK * BANK_SIZE, expanded_entry
        ),
        "native_sparse_entry_abi": exact(
            rom,
            EXPANDED_BANK * BANK_SIZE + TED_SPARSE_ENTRY - 0x4000,
            sparse_entry,
        ),
        "bank17_mapper_call": exact(
            rom,
            EXPANDED_BANK * BANK_SIZE + TED_SPARSE_SETUP - 0x4000,
            sparse_setup,
        ),
        "native_pose_bank_exact": bank17 == native_bank,
        # IDs 128-135 need a 9-bit byte offset into the 16-bit command-pointer
        # table.  RL D consumes the carry from ADD A,A; omitting it wraps the
        # late 44->45 transition to command zero and creates a 159-cell pose.
        "late_transition_pointer_carry": native_bank.count(bytes.fromhex(
            "7E 87 5F 16 00 CB 12 21"
        )) == 1,
        "retired_later_stage_bank_is_empty": (
            bank18 == bytes([0xFF]) * BANK_SIZE
        ),
        "native_fixed_selector_retained": exact(
            rom, LATER_PUBLISH_DISPATCH_STUB, native_fixed_stub
        ),
        "native_bank1_selector_retained": exact(
            rom, 0x4295, native_bank1_entry
        ),
        "later_stage_return_stub_address": (
            LATER_PUBLISH_ENTRY == LATER_PUBLISH_RETURN == 0x4298
        ),
        "arena_semantic_helper_exact": (
            arena_helper_bank == expected_arena_bank
        ),
        "arena_postcopy_dispatcher_exact": exact(
            rom,
            bank_offset(13, build.LAVA_ATTR_DECIDER_ADDR),
            arena_postcopy_dispatcher,
        ),
        "arena_postcopy_banked_entry_exact": exact(
            rom,
            bank_offset(13, build.STAGE1_HAZARD_BANKED_ENTRY_ADDR),
            bytes([
                0xC3,
                build.LAVA_ATTR_DECIDER_ADDR & 0xFF,
                build.LAVA_ATTR_DECIDER_ADDR >> 8,
            ]),
        ),
        "arena_atomic_wrap_exact": exact(
            rom,
            build.STAGE1_ATOMIC_WRAP_ADDR,
            build.build_stage1_atomic_wrap(),
        ),
        "arena_atomic_wrap_tail_exact": exact(
            rom,
            build.STAGE1_ATOMIC_WRAP_TAIL_ADDR,
            build.build_stage1_atomic_wrap_tail(),
        ),
        "penta_only_completion_gate": exact(
            rom,
            build.STAGE1_HAZARD_BANK0_MAP_ADDR,
            bytes.fromhex("FE 14 C0 3E 0D"),
        ),
        "penta_postcopy_seam_helper_exact": (
            arena_helper_bank[
                penta_seam_offset:penta_seam_offset + len(penta_seam_helper)
            ] == penta_seam_helper
        ),
        "unused_expansion_banks_are_ff": bool(blank_tail)
            and blank_tail == bytes([0xFF]) * len(blank_tail),
        "pose_source_pin": SOURCE_SHA256 == EXPECTED_SOURCE_SHA256,
        "pose_source_records": SOURCE_RECORDS == 626,
        "pose_classifier_states": len(poses) == POSE_COUNT == 49,
        "publishable_pose_count": (
            POSE_COUNT - len(NON_PUBLISHABLE_POSES) == 47
            and tuple(NON_PUBLISHABLE_POSES) == (13, 14)
        ),
        "private_envelope_table_exact": (
            bank16[
                bank16_envelope_offset:
                bank16_envelope_offset + len(envelope)
            ] == envelope
        ),
        "production_angela_lut_isolated": (
            rom[
                production_angela_offset:
                production_angela_offset + 0x100
            ] == angela
            and angela[0xBB:0xBB + len(envelope)] != envelope
        ),
    }
    if args.menu_icon_colors:
        checks.update({
            "menu_first_entry_exact": exact(
                rom,
                menu_icons.MENU_FIXED_FIRST,
                menu_icons._fixed_wrapper(
                    menu_icons.MENU_FIRST_ENTRY,
                    len(menu_icons.MENU_FIRST_PREIMAGE),
                ),
            ),
            "menu_interactive_entry_exact": exact(
                rom,
                menu_icons.MENU_FIXED_INTERACTIVE,
                menu_icons._fixed_wrapper(
                    menu_icons.MENU_INTERACTIVE_ENTRY,
                    len(menu_icons.MENU_INTERACTIVE_PREIMAGE),
                ),
            ),
            "menu_relative_redraw_edges_exact": all(
                rom[address] == expected[0]
                and rom[address + 1] == (
                    menu_icons.MENU_FIXED_INTERACTIVE - (address + 2)
                ) & 0xFF
                for address, expected in menu_icons.RELATIVE_LOOP_PREIMAGES
            ),
            "menu_absolute_redraw_edges_exact": all(
                rom[address] == expected[0]
                and rom[address + 1:address + 3]
                    == menu_icons.MENU_FIXED_INTERACTIVE.to_bytes(2, "little")
                for address, expected in menu_icons.ABSOLUTE_LOOP_PREIMAGES
            ),
            "menu_window_prelude_exact": exact(
                rom,
                bank_offset(
                    menu_icons.MENU_PRELUDE_BANK,
                    menu_icons.MENU_PRELUDE_ADDR,
                ),
                menu_icons._menu_owned_prelude(
                    build.build_colorize_prelude()
                ),
            ),
        })
    status = all(checks.values())
    receipt = {
        "schema": SCHEMA,
        "status": "pass" if status else "fail",
        "rom": str(args.rom.resolve()),
        "rom_sha256": sha256(rom),
        "checks": checks,
        "failing_checks": sorted(name for name, passed in checks.items() if not passed),
        "architecture": {
            "mapper": "MBC5+RAM+battery",
            "rom_banks": len(rom) // BANK_SIZE,
            "private_runtime_bank": EXPANDED_BANK,
            "native_pose_bank": NATIVE_POSE_BANK,
            "native_pose_bank_sha256": sha256(bank17),
            "expected_native_pose_bank_sha256": sha256(native_bank),
            "later_stage_bank": LATER_SCROLL_BANK,
            "later_stage_bank_sha256": sha256(bank18),
            "arena_semantic_helper_bank": ARENA_SEMANTIC_HELPER_BANK,
        "arena_semantic_helper_entry": f"{ARENA_SEMANTIC_HELPER_ENTRY:04X}",
        "shalamar_native_exact_class": args.shalamar_native_exact_class,
            "penta_seam_helper_entry": f"{PENTA_SEAM_ENTRY:04X}",
            "arena_semantic_helper_sha256": sha256(arena_helper_bank),
            "menu_icon_colors": args.menu_icon_colors,
            "classifier_states": POSE_COUNT,
            "non_publishable_states": list(NON_PUBLISHABLE_POSES),
            "publishable_poses": POSE_COUNT - len(NON_PUBLISHABLE_POSES),
            "source_records": SOURCE_RECORDS,
            "source_sha256": SOURCE_SHA256,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if status else 2


if __name__ == "__main__":
    raise SystemExit(main())
