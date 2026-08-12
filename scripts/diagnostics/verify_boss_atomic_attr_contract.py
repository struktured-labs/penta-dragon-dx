#!/usr/bin/env python3
"""Verify the production ROM's animated-boss attribute dispatch contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))

from build_v302_title_fix import (  # noqa: E402
    ARENA_ATOMIC_ATTR_STACK_HELPER_ROM_ADDR,
    ARENA_BASE_ADDR,
    ARENA_ATTR_SEMANTIC_DISPATCH_ADDR,
    ARENA_ATTR_SEMANTIC_SIG_A_ADDR,
    ARENA_ATTR_SEMANTIC_SIG_B_ADDR,
    ARENA_ATTR_SEMANTIC_COMPARE_ADDR,
    ARENA_ATTR_SEMANTIC_CHANGED_ADDR,
    ARENA_ATTR_SEMANTIC_FRAGMENT_SIZE,
    ARENA_ATTR_SEMANTIC_RUNTIME_ADDR,
    ARENA_ATTR_SEMANTIC_SENTINEL_ADDR,
    ARENA_TILE_RAW_KEY_SAMPLES,
    PENTA_TILE_RAW_KEY_SAMPLE,
    BANK13,
    LAVA_ATTR_SCENE_DISPATCH_ADDR,
    LAVA_ATTR_STAGE7_RUNTIME_ADDR,
    LAVA_ATTR_STAGE7_SOURCE_A_ADDR,
    LAVA_ATTR_STAGE7_SOURCE_B_ADDR,
    OAM_FREE_EMITTER_ADDR,
    OAM_WRAM_COPY_TAIL_ADDR,
    build_arena_atomic_attr_stack_helper,
    build_arena_attr_semantic_decider,
    build_arena_attr_semantic_runtime,
    build_lava_attr_scene_dispatcher,
    build_lava_attr_stage7_runtime,
    build_oam_wram_copy_tail,
    build_stage1_atomic_attr_stack_vector,
)
from build_v301_teleport import ARENA_ORDER, _table_from_dict  # noqa: E402
from boss_geometry_contract import BOSSES  # noqa: E402


def classify(scene: int) -> str:
    """Model the compact two-range arithmetic in the ROM dispatcher."""
    normalized = (scene - 0x03) & 0xFF
    if normalized < 0x06:
        return "cached_later_dungeon"
    normalized = (normalized - 0x09) & 0xFF
    if normalized < 0x09:
        if scene == 0x0E:
            return "cached_crystal_obj"
        return "repeat_cached_atomic_arena"
    return "neutral"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    args = parser.parse_args()
    rom = args.rom.resolve().read_bytes()

    # The shared RST distinguishes a map-decision call from an in-copy arena
    # sanitizer call by incrementing D and testing Z. The caller therefore
    # must seed D=$FF, not $DF. A wrong discriminator still embeds a perfect
    # dispatcher and LUT set but silently sends every animated boss through
    # the pure tile path, recreating detached/bleeding terrain fragments.
    assert rom[0x42A7:0x42AE] == bytes.fromhex("2E 00 03 0B 16 FF CD"), (
        "shared map copier does not seed the boss-decision RST with D=$FF"
    )
    vector = build_stage1_atomic_attr_stack_vector()
    assert rom[0x0018:0x0020] == vector, (
        "shared boss-decision/arena-sanitizer RST vector differs from source"
    )

    dispatcher = build_lava_attr_scene_dispatcher()
    expected_runtime = build_lava_attr_stage7_runtime()
    dispatcher_offset = (
        LAVA_ATTR_SCENE_DISPATCH_ADDR - LAVA_ATTR_STAGE7_RUNTIME_ADDR
    )
    assert dispatcher and 0 <= dispatcher_offset
    assert dispatcher_offset + len(dispatcher) <= len(expected_runtime)
    assert (
        expected_runtime[
            dispatcher_offset:dispatcher_offset + len(dispatcher)
        ]
        == dispatcher
    )

    first_length = OAM_FREE_EMITTER_ADDR - LAVA_ATTR_STAGE7_SOURCE_A_ADDR
    second_length = len(expected_runtime) - first_length
    first_offset = BANK13 + LAVA_ATTR_STAGE7_SOURCE_A_ADDR - 0x4000
    second_offset = BANK13 + LAVA_ATTR_STAGE7_SOURCE_B_ADDR - 0x4000
    embedded_runtime = (
        rom[first_offset:first_offset + first_length]
        + rom[second_offset:second_offset + second_length]
    )
    assert embedded_runtime == expected_runtime, (
        "ROM's WRAM runtime initializer does not contain the compiled "
        "boss-attribute dispatcher"
    )

    geometry = build_arena_atomic_attr_stack_helper()
    geometry_offset = (
        BANK13 + ARENA_ATOMIC_ATTR_STACK_HELPER_ROM_ADDR - 0x4000
    )
    assert rom[geometry_offset:geometry_offset + len(geometry)] == geometry, (
        "ROM does not embed the compiled atomic arena geometry helper"
    )

    semantic_fragments = build_arena_attr_semantic_decider()
    semantic_addresses = (
        ARENA_ATTR_SEMANTIC_DISPATCH_ADDR,
        ARENA_ATTR_SEMANTIC_SIG_A_ADDR,
        ARENA_ATTR_SEMANTIC_SIG_B_ADDR,
        ARENA_ATTR_SEMANTIC_COMPARE_ADDR,
        ARENA_ATTR_SEMANTIC_CHANGED_ADDR,
    )
    for address, payload in zip(semantic_addresses, semantic_fragments):
        offset = BANK13 + address - 0x4000
        assert rom[offset:offset + len(payload)] == payload, (
            f"arena semantic source fragment ${address:04X} differs from source"
        )
    semantic_runtime = build_arena_attr_semantic_runtime()
    assert len(semantic_runtime) <= (
        ARENA_ATTR_SEMANTIC_SENTINEL_ADDR - ARENA_ATTR_SEMANTIC_RUNTIME_ADDR
    )
    assert len(ARENA_TILE_RAW_KEY_SAMPLES) == 5
    assert 0 <= PENTA_TILE_RAW_KEY_SAMPLE < 0x240
    # POP HL / POP AF / POP AF / RET is the intentional exact-repeat escape:
    # it preserves the caller while discarding only the RST and copier frames.
    assert bytes.fromhex("E1 F1 F1 C9") in semantic_runtime
    assert (
        bytes.fromhex("3E 01 E1 C9") in semantic_runtime
        or bytes.fromhex("3E 01 B7 E1 C9") in semantic_runtime
    ), (
        "changed arena layouts are not forced onto the atomic path"
    )
    tail, _ = build_oam_wram_copy_tail()
    tail_offset = BANK13 + OAM_WRAM_COPY_TAIL_ADDR - 0x4000
    assert rom[tail_offset:tail_offset + len(tail)] == tail, (
        "arena WRAM installer tail differs from source"
    )

    assert len(ARENA_ORDER) == 9
    assert tuple(ARENA_ORDER) == tuple(boss.name for boss in BOSSES)
    assert tuple(boss.scene for boss in BOSSES) == tuple(range(0x0C, 0x15))
    for index, name in enumerate(ARENA_ORDER):
        table = _table_from_dict(name)
        assert len(table) == 0x100 and max(table) <= 7
        table_offset = BANK13 + ARENA_BASE_ADDR - 0x4000 + index * 0x100
        assert rom[table_offset:table_offset + 0x100] == table, (
            f"arena {index} ({name}) ROM table differs from compiled data"
        )

    groups = {scene: classify(scene) for scene in range(0x20)}
    assert {
        scene for scene, route in groups.items()
        if route == "repeat_cached_atomic_arena"
    } == set(range(0x0C, 0x15)) - {0x0E}
    assert groups[0x0E] == "cached_crystal_obj"
    assert {
        scene
        for scene, route in groups.items()
        if route == "cached_later_dungeon"
    } == set(range(0x03, 0x09))
    assert all(
        groups[scene] == "neutral"
        for scene in (0x00, 0x01, 0x02, 0x09, 0x0A, 0x0B, 0x15, 0x17, 0x18, 0x1B)
    )

    print("PASS: boss atomic-attribute dispatch contract")
    print("  map-decision discriminator: D=$FF -> RST decision path")
    print("  eight BG-body arenas: exact repeats skip; every change is atomic")
    print("  Crystal $0E: cached BG path; body is OBJ4-OBJ7")
    print("  later dungeons $03-$08: existing cached path")
    print("  title/gameplay/miniboss/story families: neutral/pure path")
    print(f"  embedded WRAM runtime bytes: {len(embedded_runtime)} exact")
    print(f"  shared geometry helper: {len(geometry)} bytes exact")
    print(
        f"  semantic runtime: {len(semantic_runtime)} bytes, "
        f"five-cell global key {ARENA_TILE_RAW_KEY_SAMPLES}, "
        f"Penta key ({PENTA_TILE_RAW_KEY_SAMPLE},)"
    )
    print("  arena LUT pages: 9/9 exact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
