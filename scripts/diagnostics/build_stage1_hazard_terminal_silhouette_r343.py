#!/usr/bin/env python3
"""Build r343: keep fire-colored terminals without detached yellow spill.

r342 correctly moves the four right-wall cylinder terminal cells from BG6 to
BG5, fixing the gray free tip and wall collar.  Operator review identified a
separate pixel-art consequence: stock free-tip tiles 6B/7B contain Dungeon
floor shade-1 pixels outside their diagonal black outline.  BG6 rendered those
pixels blue-gray; BG5 turns them yellow and makes them protrude from the tip.

r343 applies the YAML-owned diagonal masks only to 6B/7B, collapsing pixels
outside the cap silhouette to neutral index 0.  Cold Stage-1 uploads read the
corrected source art directly.  The authenticated scene-$0B admission route
also uploads the exact two corrected 16-byte tiles with two one-block GDMAs,
so a stale pre-r343 savestate cannot retain the old yellow spill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_hazard_terminal_resume_r342 as r342
from stage1_hazard_art import (
    compile_stage1_hazard_terminal_variants,
    load_stage1_hazard_config,
)


ROOT = r342.ROOT
BASE = r342.OUTPUT
BASE_RECEIPT = r342.RECEIPT
OUTPUT = ROOT / "tmp/stage1-hazard-terminal-silhouette-r343/candidate.gb"
RECEIPT = ROOT / "tmp/stage1-hazard-terminal-silhouette-r343/build-receipt.json"
STOCK = ROOT / "rom/Penta Dragon (J).gb"

BASE_SHA256 = r342.R342_SHA256
R343_SHA256 = "df359624edb86adfdc88d78e81b4a9d7c8e251956fb29512e2a0402b6c604d48"

FREE_TIP_TILES = (0x6B, 0x7B)
WALL_TERMINAL_TILES = (0x6F, 0x7F)
ART_HELPER_ADDR = 0x71F0
ART_PAYLOAD_ADDR = 0x7250
ART_PAYLOAD_BYTES = 0x20
VRAM_DESTINATIONS = {
    0x6B: 0x96B0,
    0x7B: 0x97B0,
}


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank31_offset(address: int) -> int:
    return r342.bank31_offset(address)


def _gdma_one_block(source: int, destination: int) -> bytes:
    if source & 0x0F or destination & 0x0F:
        raise AssertionError("r343 one-block GDMA endpoints must be aligned")
    return bytes((
        0x3E, source >> 8, 0xE0, 0x51,
        0x3E, source & 0xF0, 0xE0, 0x52,
        0x3E, (destination >> 8) & 0x1F, 0xE0, 0x53,
        0x3E, destination & 0xF0, 0xE0, 0x54,
        0xAF, 0xE0, 0x55,
        0xF0, 0x55, 0xFE, 0xFF,
    ))


def art_helper() -> bytes:
    """Upload corrected 6B/7B while the admission transaction owns VBlank."""
    first_source = ART_PAYLOAD_ADDR
    second_source = ART_PAYLOAD_ADDR + 0x10
    helper = (
        bytes.fromhex("AF E0 4F")
        + _gdma_one_block(first_source, VRAM_DESTINATIONS[0x6B])
        + bytes((0xC0,))
        + _gdma_one_block(second_source, VRAM_DESTINATIONS[0x7B])
        + bytes((0xC9,))
    )
    if len(helper) != 51:
        raise AssertionError("r343 art helper width changed")
    return helper


def admission_call() -> bytes:
    # Retry the exact helper until both completed GDMAs report FF55=$FF.
    return bytes((0xCD,)) + ART_HELPER_ADDR.to_bytes(2, "little") + bytes((0x20, 0xFB))


def _r342_cave_layout() -> tuple[int, int, int]:
    chunks = r342.r341.r336.r335.selected_regions()
    original_size = 1 + 14 * len(chunks) + r342.R331.REPAIR_SIZE + 3
    r336_size = original_size + 5
    tail_size = r342.R331.REPAIR_SIZE + 3
    stream_start = original_size - tail_size + 5
    r342_size = r336_size + len(r342.terminal_repair_stream())
    return stream_start, r342_size, r342.CAVE_ADDR + r342_size


def construct(source: bytes, *, stock: bytes) -> tuple[bytes, dict[str, object]]:
    if digest(source) != BASE_SHA256:
        raise AssertionError("r343 base is not the exact accepted r342 candidate")

    config = load_stage1_hazard_config()
    if tuple(sorted(config.terminal_row_spans)) != FREE_TIP_TILES:
        raise AssertionError("r343 YAML free-tip ownership changed")
    variants = compile_stage1_hazard_terminal_variants(stock, config)
    if tuple(sorted(variants)) != FREE_TIP_TILES:
        raise AssertionError("r343 terminal compiler emitted another tile set")

    rom = bytearray(source)
    source_art_ranges: list[tuple[int, int]] = []
    for tile in FREE_TIP_TILES:
        start = config.source_offset + tile * 16
        native = stock[start:start + 16]
        if source[start:start + 16] != native:
            raise AssertionError(f"r343 free-tip tile {tile:02X} preimage changed")
        if variants[tile] == native:
            raise AssertionError(f"r343 free-tip tile {tile:02X} has no correction")
        rom[start:start + 16] = variants[tile]
        source_art_ranges.append((start, start + 16))
    for tile in WALL_TERMINAL_TILES:
        start = config.source_offset + tile * 16
        if source[start:start + 16] != stock[start:start + 16]:
            raise AssertionError(f"r343 wall terminal {tile:02X} preimage changed")

    stream_start, r342_cave_size, r342_cave_end = _r342_cave_layout()
    cave_offset = bank31_offset(r342.CAVE_ADDR)
    old_cave = source[cave_offset:cave_offset + r342_cave_size]
    old_stream = r342.terminal_repair_stream()
    stream_end = stream_start + len(old_stream)
    if old_cave[stream_start:stream_end] != old_stream:
        raise AssertionError("r343 r342 terminal stream preimage changed")
    if old_stream[-3:] != bytes.fromhex("F1 E0 4F"):
        raise AssertionError("r343 r342 terminal stream restore tail changed")
    new_stream = old_stream[:-3] + admission_call() + old_stream[-3:]
    new_cave = old_cave[:stream_start] + new_stream + old_cave[stream_end:]
    new_cave_end = r342.CAVE_ADDR + len(new_cave)
    if r342_cave_end != r342.CAVE_ADDR + len(old_cave):
        raise AssertionError("r343 r342 cave-size model drifted")
    if new_cave_end > r342.PATCH_HELPER_ADDR:
        raise AssertionError("r343 admission cave overlaps the r342 helper")
    extension = source[cave_offset + len(old_cave):cave_offset + len(new_cave)]
    if extension != bytes([0xFF]) * len(extension):
        raise AssertionError("r343 admission extension preimage changed")
    rom[cave_offset:cave_offset + len(new_cave)] = new_cave

    helper = art_helper()
    helper_offset = bank31_offset(ART_HELPER_ADDR)
    if source[helper_offset:helper_offset + len(helper)] != bytes([0xFF]) * len(helper):
        raise AssertionError("r343 art helper preimage changed")
    payload = b"".join(variants[tile] for tile in FREE_TIP_TILES)
    if len(payload) != ART_PAYLOAD_BYTES:
        raise AssertionError("r343 terminal payload width changed")
    payload_offset = bank31_offset(ART_PAYLOAD_ADDR)
    if source[payload_offset:payload_offset + len(payload)] != bytes([0xFF]) * len(payload):
        raise AssertionError("r343 art payload preimage changed")
    rom[helper_offset:helper_offset + len(helper)] = helper
    rom[payload_offset:payload_offset + len(payload)] = payload

    r342.r341.r336.r335.r331.r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    candidate_sha = digest(candidate)
    if R343_SHA256 != "TO_BE_PINNED" and candidate_sha != R343_SHA256:
        raise AssertionError("r343 exact candidate identity changed")

    functional = {
        index for index, pair in enumerate(zip(source, candidate))
        if pair[0] != pair[1] and index not in {0x14D, 0x14E, 0x14F}
    }
    allowed: set[int] = set()
    for start, end in source_art_ranges:
        allowed.update(range(start, end))
    allowed.update(range(cave_offset, cave_offset + len(new_cave)))
    allowed.update(range(helper_offset, helper_offset + len(helper)))
    allowed.update(range(payload_offset, payload_offset + len(payload)))
    if not functional or not functional <= allowed:
        raise AssertionError("r343 functional delta escaped its owned ranges")

    return candidate, {
        "schema": "penta-stage1-hazard-terminal-silhouette-r343-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": candidate_sha,
        "base_r342_sha256": BASE_SHA256,
        "free_tip_tiles": [f"{tile:02X}" for tile in FREE_TIP_TILES],
        "wall_terminal_tiles_preserved": [
            f"{tile:02X}" for tile in WALL_TERMINAL_TILES
        ],
        "terminal_palette": config.terminal_palette,
        "outside_silhouette_index": 0,
        "source_art_changed_bytes": sum(
            before != after
            for tile in FREE_TIP_TILES
            for before, after in zip(
                stock[
                    config.source_offset + tile * 16:
                    config.source_offset + (tile + 1) * 16
                ],
                variants[tile],
            )
        ),
        "admission_art_helper": (
            f"bank31:${ART_HELPER_ADDR:04X}-"
            f"${ART_HELPER_ADDR + len(helper) - 1:04X}"
        ),
        "admission_art_payload": (
            f"bank31:${ART_PAYLOAD_ADDR:04X}-"
            f"${ART_PAYLOAD_ADDR + len(payload) - 1:04X}"
        ),
        "admission_gdma_destinations": [
            f"${VRAM_DESTINATIONS[tile]:04X}" for tile in FREE_TIP_TILES
        ],
        "required_live_gates": [
            "all four terminal cells retain fire BG5 across every phase",
            "free-tip pixels outside the reviewed diagonal remain neutral",
            "scene0B stale-state admission restores corrected 6B/7B CHR",
            "menu hold and stationary post-close retain terminal correction",
            "north wall/entrance and Stage-1 speed remain qualified",
        ],
    }


def build(source: bytes, receipt_bytes: bytes, *, stock: bytes | None = None
          ) -> tuple[bytes, dict[str, object]]:
    if digest(source) != BASE_SHA256:
        raise AssertionError("r343 base is not the exact accepted r342 candidate")
    parent = json.loads(receipt_bytes)
    if parent.get("candidate_sha256") != BASE_SHA256:
        raise AssertionError("r342 build receipt targets another candidate")
    if stock is None:
        stock = STOCK.read_bytes()
    candidate, receipt = construct(source, stock=stock)
    receipt.update({"schema": "penta-stage1-hazard-terminal-silhouette-r343-build-v1",
                    "status": "STATIC_PASS_LIVE_GATES_REQUIRED"})
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--receipt", type=Path, default=RECEIPT)
    args = parser.parse_args()
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "candidate_sha256": receipt["candidate_sha256"],
        "output": str(args.output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
