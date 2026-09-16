#!/usr/bin/env python3
"""Build r341: color the four reported right-wall hazard terminal cells."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v301_gdma import _bg_table  # noqa: E402
from build_v302_title_fix import (  # noqa: E402
    BANK13,
    STAGE1_ENTRY_PATCH_FINISH_ADDR,
    STAGE1_ENTRY_PATCH_TAIL_ADDR,
    build_stage1_entry_attr_patch,
)
from stage1_hazard_art import load_stage1_hazard_config  # noqa: E402
from stage1_hazard_semantic_row import (  # noqa: E402
    HELPER_BANK,
    LUT_ADDR,
    build_lut,
)
import build_stage1_room01_semantic_row_r300 as room01  # noqa: E402
import build_stage1_scene0b_admission_art_repair_r336 as r336  # noqa: E402


BASE = ROOT / "tmp/stage1-scene0b-admission-art-repair-r336/candidate.gb"
BASE_RECEIPT = (
    ROOT / "tmp/stage1-scene0b-admission-art-repair-r336/build-receipt.json"
)
OUTPUT = ROOT / "tmp/stage1-hazard-terminal-caps-r341/candidate.gb"
RECEIPT = ROOT / "tmp/stage1-hazard-terminal-caps-r341/build-receipt.json"
BASE_SHA256 = "484cd678bd6724f7ab9c128a985a0a50db1c523ad406103a8f57bd84784f4611"
TERMINAL_TILES = frozenset({0x6B, 0x6F, 0x7B, 0x7F})
BG_TABLE_OFFSET = 13 * 0x4000 + 0x3000
SEMANTIC_LUT_OFFSET = HELPER_BANK * 0x4000 + LUT_ADDR - 0x4000
ROOM01_LUT_OFFSET = (
    HELPER_BANK * 0x4000 + room01.ROOM01_LUT_ADDR - 0x4000
)
ENTRY_TAIL_OFFSET = BANK13 + STAGE1_ENTRY_PATCH_TAIL_ADDR - 0x4000
ENTRY_FINISH_OFFSET = BANK13 + STAGE1_ENTRY_PATCH_FINISH_ADDR - 0x4000
R336_ENTRY_TAIL = bytes.fromhex("2E8B772E91772EA422772EAB77C3706E")
R336_ENTRY_FINISH = bytes.fromhex("2EB02277E0913EFFEA0DDFC30A560000")
REQUIRED_LIVE_GATES = (
    "all four rendered phases show 6B/6F/7B/7F through BG5",
    "menu hold and stationary post-close retain terminal BG5",
    "both physical BG maps retain exact terminal attributes",
    "Stage-1 speed remains at or above the accepted 95% floor",
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def changed_offsets(before: bytes, after: bytes) -> list[int]:
    if len(before) != len(after):
        raise AssertionError("compared LUT sizes differ")
    return [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]


def construct(source: bytes) -> tuple[bytes, dict[str, object]]:
    if digest(source) != BASE_SHA256:
        raise AssertionError("r341 base is not the exact accepted r336 candidate")

    config = load_stage1_hazard_config()
    if config.terminal_tiles != TERMINAL_TILES or config.terminal_palette != 5:
        raise AssertionError("terminal-cap YAML contract changed")

    rom = bytearray(source)
    old_table = bytes(rom[BG_TABLE_OFFSET : BG_TABLE_OFFSET + 0x100])
    new_table = bytes(_bg_table())
    if changed_offsets(old_table, new_table) != sorted(TERMINAL_TILES):
        raise AssertionError("r341 immutable table delta is not terminal-only")

    old_semantic = bytes(rom[SEMANTIC_LUT_OFFSET : SEMANTIC_LUT_OFFSET + 0x100])
    new_semantic = build_lut(new_table)
    if changed_offsets(old_semantic, new_semantic) != sorted(TERMINAL_TILES):
        raise AssertionError("r341 semantic LUT delta is not terminal-only")

    old_room01 = bytes(rom[ROOM01_LUT_OFFSET : ROOM01_LUT_OFFSET + 0x100])
    new_room01 = room01.build_room01_lut(new_semantic)
    if changed_offsets(old_room01, new_room01) != sorted(TERMINAL_TILES):
        raise AssertionError("r341 room-$01 LUT delta is not terminal-only")

    _, entry_tail, entry_finish, _ = build_stage1_entry_attr_patch(new_table)
    if bytes(rom[ENTRY_TAIL_OFFSET : ENTRY_TAIL_OFFSET + len(entry_tail)]) != R336_ENTRY_TAIL:
        raise AssertionError("r336 Stage-1 entry tail preimage changed")
    if bytes(rom[ENTRY_FINISH_OFFSET : ENTRY_FINISH_OFFSET + len(entry_finish)]) != R336_ENTRY_FINISH:
        raise AssertionError("r336 Stage-1 entry finish preimage changed")

    rom[BG_TABLE_OFFSET : BG_TABLE_OFFSET + 0x100] = new_table
    rom[SEMANTIC_LUT_OFFSET : SEMANTIC_LUT_OFFSET + 0x100] = new_semantic
    rom[ROOM01_LUT_OFFSET : ROOM01_LUT_OFFSET + 0x100] = new_room01
    rom[ENTRY_TAIL_OFFSET : ENTRY_TAIL_OFFSET + len(entry_tail)] = entry_tail
    rom[ENTRY_FINISH_OFFSET : ENTRY_FINISH_OFFSET + len(entry_finish)] = entry_finish
    r336.r335.r331.r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    byte_deltas = [
        index for index, pair in enumerate(zip(source, candidate)) if pair[0] != pair[1]
    ]
    expected_functional_deltas = sorted(
        [BG_TABLE_OFFSET + tile for tile in TERMINAL_TILES]
        + [SEMANTIC_LUT_OFFSET + tile for tile in TERMINAL_TILES]
        + [ROOM01_LUT_OFFSET + tile for tile in TERMINAL_TILES]
        + [
            ENTRY_TAIL_OFFSET + index
            for index in changed_offsets(R336_ENTRY_TAIL, entry_tail)
        ]
        + [
            ENTRY_FINISH_OFFSET + index
            for index in changed_offsets(R336_ENTRY_FINISH, entry_finish)
        ]
    )
    functional_deltas = [
        offset for offset in byte_deltas if offset not in {0x14D, 0x14E, 0x14F}
    ]
    if functional_deltas != expected_functional_deltas:
        raise AssertionError(
            "r341 changed unexpected functional ROM bytes: "
            f"expected {expected_functional_deltas}, got {functional_deltas}"
        )

    candidate_sha = digest(candidate)
    return candidate, {
        "schema": "penta-stage1-hazard-terminal-caps-r341-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": candidate_sha,
        "base_r336_sha256": BASE_SHA256,
        "terminal_tiles": [f"{tile:02X}" for tile in sorted(TERMINAL_TILES)],
        "terminal_palette": 5,
        "native_art_preserved": True,
        "patched_luts": {
            "immutable_bg_table": f"{BG_TABLE_OFFSET:05X}",
            "semantic_stage1": f"{SEMANTIC_LUT_OFFSET:05X}",
            "semantic_room01": f"{ROOM01_LUT_OFFSET:05X}",
            "cold_entry_tail": f"{ENTRY_TAIL_OFFSET:05X}",
            "cold_entry_finish": f"{ENTRY_FINISH_OFFSET:05X}",
        },
        "byte_delta_count_including_checksums": len(byte_deltas),
        "required_live_gates": list(REQUIRED_LIVE_GATES),
    }


def build(source: bytes, base_receipt: bytes) -> tuple[bytes, dict[str, object]]:
    if digest(source) != BASE_SHA256:
        raise AssertionError("r341 base is not the exact accepted r336 candidate")
    parent = json.loads(base_receipt)
    if parent.get("candidate_sha256") != BASE_SHA256:
        raise AssertionError("r336 build receipt targets another candidate")
    candidate, receipt = construct(source)
    receipt.update({"schema": "penta-stage1-hazard-terminal-caps-r341-build-v1",
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
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
