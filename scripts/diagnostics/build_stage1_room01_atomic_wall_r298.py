#!/usr/bin/env python3
"""Build r298: atomically publish room-context wall attributes on exact r292.

r297 moved the contextual LUT writes off the renderer and produced the right
settled room-01 wall plane, but the live north oracle caught fourteen frames
where the destination map reused its old cached attribute plane.  The r292
split-key decider owns fail-closed semantic sentinels at DF53/DF57.  Invalidate
both from the existing FFBD room hook, after updating C600 and before arming
the bounded repair.  The immediately following native map copy then performs
its existing full compile/GDMA publication instead of exposing stale BG0
attributes while the fallback row repair catches up.

All scene-$0B and cycle-neutral properties from r297 are retained.  This is
still non-promotable until every live gate passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_room01_locked_wall_r297 as r297


ROOT = r297.ROOT
TMP = r297.TMP
BASE = r297.BASE
BASE_RECEIPT = r297.BASE_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-room01-atomic-wall-r298/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-room01-atomic-wall-r298/build-receipt.json"
SEMANTIC_CACHE_ADDRS = (0xDF53, 0xDF57)

# Fail-safe order: contextual LUT -> both destination-cache sentinels ->
# bounded room-repair marker -> stack continuation/bank restore.
WALL_HELPER = bytes.fromhex(
    "E5 "
    "F0 BA B7 20 1E "
    "F8 07 7E 3D 3E 00 20 02 3E 06 "
    "EA 24 C6 EA 27 C6 EA 30 C6 EA 33 C6 "
    "3E FF EA 53 DF EA 57 DF "
    "3E 12 EA 4E DF 3E A6 EA 4F DF "
    "F8 02 36 3E 23 36 08 "
    "F8 05 7E E1 C3 61 00"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def room_hook_model(
    values: dict[int, int],
    caches: dict[int, int],
    *,
    stage: int,
    room: int,
) -> tuple[dict[int, int], dict[int, int]]:
    result_values = r297.wall_values(values, stage=stage, room=room)
    result_caches = dict(caches)
    if stage == 0:
        for address in SEMANTIC_CACHE_ADDRS:
            result_caches[address] = 0xFF
    return result_values, result_caches


def validate_atomic_contract(source: bytes) -> dict[str, object]:
    base_contract = r297.validate_wall_contract(source)
    r297.require(len(WALL_HELPER) == 60, "atomic wall helper width changed")
    helper_offset = r297.bank_offset(
        r297.EXPANSION_BANK, r297.WALL_HELPER_ADDR
    )
    r297.require(
        source[helper_offset:helper_offset + len(WALL_HELPER)]
        == bytes([0xFF]) * len(WALL_HELPER),
        "bank-21 atomic helper ownership changed",
    )
    # Strong cave control: this established bank-21 tail must remain erased.
    tail_start = r297.bank_offset(r297.EXPANSION_BANK, 0x582E)
    tail_end = r297.bank_offset(r297.EXPANSION_BANK, 0x7FFF) + 1
    r297.require(
        source[tail_start:tail_end] == bytes([0xFF]) * (tail_end - tail_start),
        "bank-21 expansion-private erased tail changed",
    )

    values = {
        tile: 0x80 + index
        for index, tile in enumerate(r297.TARGET_TILES)
    }
    caches = {0xDF53: 0x12, 0xDF57: 0x34}
    room01_values, room01_caches = room_hook_model(
        values, caches, stage=0, room=1
    )
    r297.require(
        room01_values == {tile: 0x06 for tile in r297.TARGET_TILES},
        "room01 contextual values changed",
    )
    r297.require(
        room01_caches == {0xDF53: 0xFF, 0xDF57: 0xFF},
        "room01 did not invalidate both physical-map semantic caches",
    )
    room05_values, room05_caches = room_hook_model(
        values, caches, stage=0, room=5
    )
    r297.require(
        room05_values == {tile: 0x00 for tile in r297.TARGET_TILES},
        "room05 contextual values changed",
    )
    r297.require(
        room05_caches == {0xDF53: 0xFF, 0xDF57: 0xFF},
        "room05 did not invalidate both physical-map semantic caches",
    )
    later_values, later_caches = room_hook_model(
        values, caches, stage=1, room=1
    )
    r297.require(later_values == values and later_caches == caches,
                 "later stage aliases Stage1 wall/cache writes")

    # The sentinels are the exact two physical-map semantic keys selected by
    # the private r292 decider.  Phase and hazard cache bytes remain adjacent
    # and intentionally untouched.
    decider = source[
        r297.bank_offset(21, 0x4100):r297.bank_offset(21, 0x4100) + 12
    ]
    r297.require(
        decider == bytes.fromhex("16 DF 7C EE CB 5F 1A 4F F0 42 47 FA"),
        "private decider cache-selection preimage changed",
    )
    result = dict(base_contract)
    result.update({
        "helper_bytes": len(WALL_HELPER),
        "semantic_cache_sentinels": ["DF53", "DF57"],
        "phase_cache_bytes_untouched": ["DF54", "DF58"],
        "hazard_cache_bytes_untouched": ["DF55", "DF59"],
        "context_written_before_cache_invalidation": True,
        "cache_invalidated_before_room_repair_rearm": True,
        "native_full_compile_GDMA_path_retained": True,
        "bank21_erased_tail_preimage": "$582E-$7FFF",
    })
    return result


def install_atomic_wall_patch(
    rom: bytearray, source: bytes, allowed: set[int],
) -> None:
    r297.patch_exact(
        rom, source, r297.RST0_ADDR, r297.OLD_RST0, r297.NEW_RST0,
        allowed, "RST0 room writer",
    )
    r297.patch_exact(
        rom, source, r297.ROOM_STUB_ADDR, r297.OLD_ROOM_STUB,
        r297.NEW_ROOM_STUB, allowed, "fixed room mapper stub",
    )
    helper_offset = r297.bank_offset(
        r297.EXPANSION_BANK, r297.WALL_HELPER_ADDR
    )
    r297.patch_exact(
        rom, source, helper_offset, bytes([0xFF]) * len(WALL_HELPER),
        WALL_HELPER, allowed, "bank21 atomic contextual wall helper",
    )


def build(
    source: bytes,
    base_receipt_bytes: bytes,
    *,
    variant: str = "full",
) -> tuple[bytes, dict[str, object]]:
    r297.require(variant in {"full", "wall-only", "scene-only"},
                 f"unknown diagnostic variant {variant!r}")
    r297.require(len(source) == r297.ROM_SIZE,
                 "base is not exactly 512 KiB")
    r297.require(digest(source) == r297.BASE_SHA256,
                 "wrong exact r292 base")
    r297.require(digest(base_receipt_bytes) == r297.BASE_RECEIPT_SHA256,
                 "r292 receipt identity changed")
    r297.require(
        json.loads(base_receipt_bytes)["candidate_sha256"] == r297.BASE_SHA256,
        "r292 receipt names another candidate",
    )

    wall_contract = validate_atomic_contract(source)
    scene_contract = r297.validate_scene_contract(source)
    rom = bytearray(source)
    allowed: set[int] = {0x014D, 0x014E, 0x014F}
    wall_installed = variant in {"full", "wall-only"}
    scene_installed = variant in {"full", "scene-only"}
    if wall_installed:
        install_atomic_wall_patch(rom, source, allowed)
    if scene_installed:
        r297.install_scene_patch(rom, source, allowed)

    r297.require(rom[0x4303:0x4319] == source[0x4303:0x4319],
                 "native attribute compiler entry changed")
    lut_offset = r297.bank_offset(13, 0x7000)
    r297.require(
        rom[lut_offset:lut_offset + 0x100]
        == source[lut_offset:lut_offset + 0x100],
        "immutable Stage1 LUT changed",
    )
    r297.require(
        all(rom[lut_offset + tile] == 0 for tile in r297.TARGET_TILES),
        "room05/default target LUT entries changed",
    )
    r297.require(
        rom[14 * r297.BANK_SIZE:15 * r297.BANK_SIZE]
        == source[14 * r297.BANK_SIZE:15 * r297.BANK_SIZE],
        "native bank14 isolation violated",
    )
    r297.require(rom[r297.bank_offset(r297.ROW_BANK, 0x6BAB)] == 0x47,
                 "row helper LD B,A changed")

    r297.update_checksums(rom)
    candidate = bytes(rom)
    changed = {
        offset
        for offset, (old, new) in enumerate(zip(source, candidate, strict=True))
        if old != new
    }
    r297.require(changed <= allowed,
                 "candidate escaped owned code/checksum ranges")
    functional = sorted(offset for offset in changed if offset >= 0x0150)
    r297.require(functional, "candidate has no functional changes")

    receipt: dict[str, object] = {
        "schema": "penta-stage1-room01-atomic-wall-r298-build-v1",
        "diagnostic_variant": variant,
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": r297.BASE_SHA256,
        "base_receipt_sha256": r297.BASE_RECEIPT_SHA256,
        "candidate_sha256": digest(candidate),
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "root_causes": {
            "locked_room_blank_walls": (
                "D880=$0B took the attribute gateway rejection path"
            ),
            "room01_wrong_wall_edges": (
                "four tile IDs require room-local BG6/BG0 context"
            ),
            "room01_entry_transient": (
                "the destination map reused a valid pre-room semantic cache "
                "until the 18-row fallback repair reached those cells"
            ),
        },
        "wall_patch": {
            "installed": wall_installed,
            "trigger": "existing four native FFBD room-write hooks",
            "helper": "bank21:$6C80-$6CBB",
            "target_tiles": [f"${tile:02X}" for tile in r297.TARGET_TILES],
            "room01_value": "$06",
            "other_stage1_value": "$00",
            "semantic_cache_invalidation": ["$DF53", "$DF57"],
            "later_stage_action": "no C600/cache writes",
            "hot_renderer_delta_t_cycles": 0,
        },
        "scene0b_patch": {
            "installed": scene_installed,
            "attr_gateway_mirrors": ["bank13:$7C96", "bank16:$7C96"],
            "row_mask": "bank19:$6BAD $F7->$F6; native LD B,A retained",
            "transition_mask": "bank19:$55C7 $F7->$F6",
            "art_and_BG7_gates": "byte-exact r292; live oracle decides necessity",
        },
        "offline_contract": {
            "wall": wall_contract,
            "scene": scene_contract,
        },
        "ownership": {
            "functional_changed_bytes": len(functional),
            "changed_offsets": [f"0x{offset:06X}" for offset in sorted(changed)],
            "immutable_bank13_stage1_LUT_byte_exact": True,
            "native_bank14_byte_exact": True,
            "renderer_4303_4318_byte_exact": True,
            "bank21_preimage": "exact erased $582E-$7FFF tail",
        },
        "r297_live_rejection": {
            "receipt": "tmp/stage1-room01-locked-wall-r297/north-r1/receipt.json",
            "mismatch_frames": 14,
            "mismatch_cells": 476,
            "first_mismatch": (
                "gameplay frame 46 room01 tile $27 attr00 expected06"
            ),
            "settled_room01_oracle_was_exact": True,
        },
        "required_gates": [
            "independent room01 north transition oracle with zero transient attrs",
            "room05 patterned-floor attr00 control",
            "two sequential replays of both operator scene0B menu states",
            "blank-SRAM Stage1 handoff has no cyan/partial frame",
            "hazard trail/gray-spike/menu artifact rendered continuity",
            "release speed matrix: Stage1 >=95%, Stages2-7 strict 99%",
        ],
    }
    return candidate, receipt


def checked_output(path: Path, label: str) -> Path:
    return r297.checked_output(path, label)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument(
        "--variant", choices=("full", "wall-only", "scene-only"),
        default="full", help="build full candidate or diagnostic isolation",
    )
    args = parser.parse_args()
    output = checked_output(args.output, "candidate output")
    receipt_path = checked_output(args.receipt, "receipt output")
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes(),
        variant=args.variant,
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
