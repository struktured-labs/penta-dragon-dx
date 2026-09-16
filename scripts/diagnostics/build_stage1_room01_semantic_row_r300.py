#!/usr/bin/env python3
"""Build r300: room-local Stage-1 semantic hazard rows on exact r292.

r297 correctly leaves the four room-$01 wall companion values at $06 in the
live C600 table.  The rotating-hazard publisher bypasses C600, however: its
bank-20 helper resolves every tile through the immutable page at $4400, where
the four dual-use IDs must remain $00 for room $05.  r299 does not touch that
helper, its four return trampolines, or the immutable semantic page, so it
cannot repair the observed $27/$33 writes.

This diagnostic build keeps r297's room/scene repairs and adds a ROM-local,
room-selected semantic page.  Each existing bank-20 return trampoline checks
FFBD once per published row.  Room $01 enters a byte-for-byte helper clone
whose lookup page differs only for tiles $24/$27/$30/$33; every other room
enters the original helper and original table.  The per-cell lookup, LCD
guard, STAT waits, VBK writes, return bridge, and tooth attributes retain
their exact r292 instruction cadence.

No emulator is invoked by this builder.  The result remains non-promotable
until the live visual, mutation, room-$05, and speed gates pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import build_stage1_room01_locked_wall_r297 as r297


ROOT = r297.ROOT
sys.path.insert(0, str(ROOT / "scripts"))

import stage1_hazard_semantic_row as semantic  # noqa: E402


TMP = r297.TMP
BASE = r297.BASE
BASE_RECEIPT = r297.BASE_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-room01-semantic-row-r300/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-room01-semantic-row-r300/build-receipt.json"

SEMANTIC_BANK = semantic.HELPER_BANK
PRIMARY_HELPER_ADDR = semantic.HELPER_ENTRY
PRIMARY_LUT_ADDR = semantic.LUT_ADDR
ROOM01_HELPER_ADDR = 0x4500
ROOM01_LUT_ADDR = 0x4600
TRAMPOLINE_ADDRS = semantic.CALLER_RETURNS
TARGET_TILES = r297.TARGET_TILES

PRIMARY_TRAMPOLINE = bytes.fromhex("C3 00 43")
TRAMPOLINE_PREIMAGE = PRIMARY_TRAMPOLINE + bytes([0xFF]) * 6
# A/F are already dead at the original JP: the helper immediately executes
# LDH A,[$FF40] / BIT 7,A.  All other registers and the stack are untouched.
CONTEXT_TRAMPOLINE = bytes.fromhex("F0 BD 3D C2 00 43 C3 00 45")


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_room01_helper(primary: bytes) -> bytes:
    """Clone the helper while rebasing CALLs and selecting LUT page $46."""
    r297.require(primary == semantic.build_helper(),
                 "bank20 semantic helper generator changed")
    helper = bytearray(primary)
    lookup_signature = bytes.fromhex("E5 6F 26 44 7E E1 C9")
    lookup_offset = primary.rfind(lookup_signature)
    r297.require(lookup_offset >= 0, "primary semantic lookup signature moved")
    old_lookup = PRIMARY_HELPER_ADDR + lookup_offset
    new_lookup = ROOM01_HELPER_ADDR + lookup_offset
    rebased_calls = 0
    for index in range(len(helper) - 2):
        if (helper[index] == 0xCD
                and helper[index + 1] == (old_lookup & 0xFF)
                and helper[index + 2] == (old_lookup >> 8)):
            helper[index + 1] = new_lookup & 0xFF
            helper[index + 2] = new_lookup >> 8
            rebased_calls += 1
    r297.require(rebased_calls == 4,
                 "semantic helper no longer has four lookup calls")
    helper[lookup_offset + 3] = ROOM01_LUT_ADDR >> 8
    r297.require(
        bytes(helper[lookup_offset:lookup_offset + len(lookup_signature)])
        == bytes.fromhex("E5 6F 26 46 7E E1 C9"),
        "room01 lookup is not the exact page-$46 clone",
    )
    return bytes(helper)


def build_room01_lut(primary: bytes) -> bytes:
    """Copy the semantic LUT and change only the four reviewed wall IDs."""
    r297.require(len(primary) == 0x100, "semantic LUT width changed")
    result = bytearray(primary)
    r297.require(all(result[tile] == 0x00 for tile in TARGET_TILES),
                 "primary room05 controls are no longer BG0")
    for tile in TARGET_TILES:
        result[tile] = 0x06
    changed = {
        index for index, pair in enumerate(zip(primary, result, strict=True))
        if pair[0] != pair[1]
    }
    r297.require(changed == set(TARGET_TILES),
                 "room01 semantic page changed outside four target IDs")
    return bytes(result)


def semantic_attr(room: int, tile: int, primary_lut: bytes) -> int:
    """Model the ROM-local dispatcher; this never consults mutable C600."""
    table = build_room01_lut(primary_lut) if room == 1 else primary_lut
    return table[tile]


def validate_semantic_contract(source: bytes) -> dict[str, object]:
    """Pin the active helper, tables, erased storage, ABI, and cycle delta."""
    scanner_entry = r297.bank_offset(r297.ROW_BANK, 0x6BE3)
    r297.require(
        source[scanner_entry:scanner_entry + 4]
        == bytes.fromhex("F3 AF E0 4F"),
        "semantic scanner no longer enters under DI with VBK0",
    )
    primary_helper = semantic.build_helper()
    helper_offset = semantic.bank_offset(SEMANTIC_BANK, PRIMARY_HELPER_ADDR)
    r297.require(
        source[helper_offset:helper_offset + len(primary_helper)]
        == primary_helper,
        "active bank20 semantic helper preimage changed",
    )
    stage1_lut_offset = r297.bank_offset(
        semantic.STAGE1_TABLE_BANK, semantic.STAGE1_TABLE_ADDR
    )
    stage1_lut = source[stage1_lut_offset:stage1_lut_offset + 0x100]
    primary_lut = semantic.build_lut(stage1_lut)
    primary_lut_offset = semantic.bank_offset(
        SEMANTIC_BANK, PRIMARY_LUT_ADDR
    )
    r297.require(
        source[primary_lut_offset:primary_lut_offset + 0x100] == primary_lut,
        "active bank20 semantic LUT preimage changed",
    )
    r297.require(
        all(primary_lut[tile] == 0x00 for tile in TARGET_TILES),
        "room05/default semantic controls changed",
    )
    r297.require(
        all(primary_lut[tile] == 0x0F for tile in semantic.TOOTH_TILES),
        "primary tooth attributes are no longer palette7/VRAM-bank1",
    )

    for address in TRAMPOLINE_ADDRS:
        offset = semantic.bank_offset(SEMANTIC_BANK, address)
        r297.require(
            source[offset:offset + len(TRAMPOLINE_PREIMAGE)]
            == TRAMPOLINE_PREIMAGE,
            f"bank20 semantic trampoline ${address:04X} padding changed",
        )

    room_helper = build_room01_helper(primary_helper)
    room_lut = build_room01_lut(primary_lut)
    room_helper_offset = semantic.bank_offset(
        SEMANTIC_BANK, ROOM01_HELPER_ADDR
    )
    room_lut_offset = semantic.bank_offset(SEMANTIC_BANK, ROOM01_LUT_ADDR)
    r297.require(
        source[room_helper_offset:room_helper_offset + len(room_helper)]
        == bytes([0xFF]) * len(room_helper),
        "room01 semantic helper storage is not erased",
    )
    r297.require(
        source[room_lut_offset:room_lut_offset + len(room_lut)]
        == bytes([0xFF]) * len(room_lut),
        "room01 semantic LUT storage is not erased",
    )

    helper_differences = {
        index for index, pair in enumerate(
            zip(primary_helper, room_helper, strict=True)
        ) if pair[0] != pair[1]
    }
    # Four CALL high bytes rebase $4363->$4563; the lookup's H immediate
    # changes $44->$46. Low bytes and every executed opcode remain exact.
    r297.require(len(helper_differences) == 5,
                 "room01 helper differs beyond four CALLs and LUT page")
    r297.require(
        all(primary_helper[index] in (0x43, 0x44)
            and room_helper[index] in (0x45, 0x46)
            for index in helper_differences),
        "room01 helper clone changed an opcode or relative operand",
    )
    r297.require(
        bytes(value for index, value in enumerate(primary_helper)
              if index not in helper_differences)
        == bytes(value for index, value in enumerate(room_helper)
                 if index not in helper_differences),
        "room01 helper instruction stream drifted",
    )

    room_lut_differences = {
        index for index, pair in enumerate(
            zip(primary_lut, room_lut, strict=True)
        ) if pair[0] != pair[1]
    }
    r297.require(room_lut_differences == set(TARGET_TILES),
                 "room01 LUT divergence escaped the reviewed wall IDs")
    for tile in range(0x100):
        expected_room01 = 0x06 if tile in TARGET_TILES else primary_lut[tile]
        r297.require(semantic_attr(1, tile, primary_lut) == expected_room01,
                     f"room01 semantic model drifted at ${tile:02X}")
        r297.require(semantic_attr(5, tile, primary_lut) == primary_lut[tile],
                     f"room05 semantic model drifted at ${tile:02X}")

    return {
        "r299_bank20_bypass_root_cause": (
            "r299 leaves helper $4300 lookup page $4400 and all four "
            "semantic return trampolines unchanged; target entries remain $00"
        ),
        "semantic_dispatches_per_published_row": 1,
        "context_source": "FFBD room byte; no C600 dependency",
        "scanner_entry_DI_and_VBK0_exact": True,
        "room01_helper": "$4500-$4569",
        "room01_lut": "$4600-$46FF",
        "room01_lut_differences": [f"{tile:02X}" for tile in TARGET_TILES],
        "room05_uses_original_helper_and_lut": True,
        "tooth_attributes_0F_preserved": True,
        "per_cell_opcodes_and_t_cycles_exact": True,
        "stat_wait_and_vbk_write_sequence_exact": True,
        "return_bridge_exact": True,
        "trampoline_t_cycles": {
            "r292": 16,
            "r300_room01": 44,
            "r300_other_room": 32,
            "room01_delta_per_published_row": 28,
            "other_room_delta_per_published_row": 16,
        },
        "register_contract": (
            "A/F dead at entry; BC/DE/HL/SP unchanged before exact helper"
        ),
    }


def install_semantic_patch(
    rom: bytearray, source: bytes, allowed: set[int]
) -> None:
    """Install only the bank-20 contextual semantic-row component."""
    primary_helper_offset = semantic.bank_offset(
        SEMANTIC_BANK, PRIMARY_HELPER_ADDR
    )
    primary_helper = source[
        primary_helper_offset:primary_helper_offset + len(semantic.build_helper())
    ]
    primary_lut_offset = semantic.bank_offset(
        SEMANTIC_BANK, PRIMARY_LUT_ADDR
    )
    primary_lut = source[primary_lut_offset:primary_lut_offset + 0x100]
    room_helper = build_room01_helper(primary_helper)
    room_lut = build_room01_lut(primary_lut)

    for address in TRAMPOLINE_ADDRS:
        r297.patch_exact(
            rom, source, semantic.bank_offset(SEMANTIC_BANK, address),
            TRAMPOLINE_PREIMAGE, CONTEXT_TRAMPOLINE, allowed,
            f"room-local semantic trampoline ${address:04X}",
        )
    r297.patch_exact(
        rom, source,
        semantic.bank_offset(SEMANTIC_BANK, ROOM01_HELPER_ADDR),
        bytes([0xFF]) * len(room_helper), room_helper, allowed,
        "room01 semantic helper clone",
    )
    r297.patch_exact(
        rom, source,
        semantic.bank_offset(SEMANTIC_BANK, ROOM01_LUT_ADDR),
        bytes([0xFF]) * len(room_lut), room_lut, allowed,
        "room01 semantic LUT clone",
    )


def construct(source: bytes) -> tuple[bytes, dict[str, object]]:
    r297.require(len(source) == r297.ROM_SIZE,
                 "base is not exactly 512 KiB")
    r297.require(digest(source) == r297.BASE_SHA256,
                 "wrong exact r292 base")
    semantic_contract = validate_semantic_contract(source)
    r297_candidate, r297_receipt = r297.construct(source, variant="full")
    # r297 is intentionally isolated from bank20; starting from its exact
    # generated bytes is safer than treating an unpinned on-disk ROM as base.
    r297.require(
        r297_candidate[
            SEMANTIC_BANK * r297.BANK_SIZE:
            (SEMANTIC_BANK + 1) * r297.BANK_SIZE
        ]
        == source[
            SEMANTIC_BANK * r297.BANK_SIZE:
            (SEMANTIC_BANK + 1) * r297.BANK_SIZE
        ],
        "r297 unexpectedly changed bank20",
    )
    rom = bytearray(r297_candidate)
    allowed: set[int] = {0x014D, 0x014E, 0x014F}
    install_semantic_patch(rom, source, allowed)
    r297.update_checksums(rom)
    candidate = bytes(rom)

    semantic_delta = {
        offset for offset, pair in enumerate(
            zip(r297_candidate, candidate, strict=True)
        ) if pair[0] != pair[1]
    }
    r297.require(semantic_delta <= allowed,
                 "r300 semantic component escaped owned ranges")
    functional = sorted(offset for offset in semantic_delta if offset >= 0x0150)
    r297.require(functional, "r300 semantic component has no functional changes")

    primary_helper_offset = semantic.bank_offset(
        SEMANTIC_BANK, PRIMARY_HELPER_ADDR
    )
    primary_lut_offset = semantic.bank_offset(
        SEMANTIC_BANK, PRIMARY_LUT_ADDR
    )
    r297.require(
        candidate[primary_helper_offset:
                  primary_helper_offset + len(semantic.build_helper())]
        == source[primary_helper_offset:
                  primary_helper_offset + len(semantic.build_helper())],
        "original semantic helper changed",
    )
    r297.require(
        candidate[primary_lut_offset:primary_lut_offset + 0x100]
        == source[primary_lut_offset:primary_lut_offset + 0x100],
        "original semantic LUT changed",
    )
    r297.require(
        candidate[14 * r297.BANK_SIZE:15 * r297.BANK_SIZE]
        == source[14 * r297.BANK_SIZE:15 * r297.BANK_SIZE],
        "native bank14 isolation violated",
    )

    receipt: dict[str, object] = {
        "schema": "penta-stage1-room01-semantic-row-r300-construction-v1",
        "status": "construction-only",
        "promotable": False,
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "base_sha256": r297.BASE_SHA256,
        "r297_generated_sha256": r297_receipt["candidate_sha256"],
        "candidate_sha256": digest(candidate),
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "root_cause": (
            "bank20:$4363 resolves hazard-published tiles through immutable "
            "$4400, bypassing correct room-local C600 values; shifted spans "
            "therefore rewrite room01 $27/$33 cells as $00"
        ),
        "r299_rejection": {
            "can_fix_observed_writes": False,
            "reason": (
                "r299 bank20 is byte-identical to r292: lookup page $4400, "
                "four return trampolines, and target semantic entries remain "
                "unchanged"
            ),
        },
        "components": {
            "r297_full": r297_receipt,
            "semantic_row": {
                "bank": SEMANTIC_BANK,
                "trampolines": [f"${address:04X}" for address in TRAMPOLINE_ADDRS],
                "room01_helper": "$4500-$4569",
                "room01_lut": "$4600-$46FF",
                "target_tiles": [f"${tile:02X}" for tile in TARGET_TILES],
                "other_rooms": "exact original helper $4300 and LUT $4400",
                "C600_dependency": False,
            },
        },
        "offline_contract": semantic_contract,
        "ownership": {
            "semantic_functional_changed_bytes": len(functional),
            "semantic_changed_offsets": [
                f"0x{offset:06X}" for offset in sorted(semantic_delta)
            ],
            "original_helper_4300_4369_byte_exact": True,
            "original_lut_4400_44FF_byte_exact": True,
            "native_bank14_byte_exact": True,
            "bank21_semantic_delta_bytes": 0,
        },
        "required_gates": [
            "hazard-menu replay: zero room01 target attr mismatches",
            "hazard attr-write trace: $9905/$9965/$9D05/$9D65 write $06",
            "room05 same-ID and patterned-floor controls remain $00",
            "gray-tooth mutation still rejects and every tooth stays $0F",
            "scene0B captured menu roundtrip and invalidation gate",
            "release speed matrix: Stage1 >=95%, Stages2-7 strict 99%",
        ],
    }
    return candidate, receipt


def build(source: bytes, base_receipt_bytes: bytes, *, room01_capture: bytes | None = None
          ) -> tuple[bytes, dict[str, object]]:
    r297.require(len(source) == r297.ROM_SIZE, "base is not exactly 512 KiB")
    r297.require(digest(source) == r297.BASE_SHA256, "wrong exact r292 base")
    r297.require(digest(base_receipt_bytes) == r297.BASE_RECEIPT_SHA256,
                 "r292 receipt identity changed")
    r297.require(json.loads(base_receipt_bytes)["candidate_sha256"] == r297.BASE_SHA256,
                 "r292 receipt names another candidate")
    _, historical_component = r297.build(source, base_receipt_bytes, variant="full",
                                         room01_capture=room01_capture)
    candidate, receipt = construct(source)
    receipt.pop("historical_evidence_consumed")
    receipt.pop("fresh_live_qualification")
    receipt.update({"schema": "penta-stage1-room01-semantic-row-r300-build-v1",
                    "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
                    "base_receipt_sha256": r297.BASE_RECEIPT_SHA256})
    receipt["components"]["r297_full"] = historical_component
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r297.checked_output(args.output, "candidate output")
    receipt_path = r297.checked_output(args.receipt, "receipt output")
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes()
    )
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
