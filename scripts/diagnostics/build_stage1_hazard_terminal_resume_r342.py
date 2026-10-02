#!/usr/bin/env python3
"""Build r342: migrate stale scene-$0B terminal attrs during admission.

r341 corrects every ROM-owned Stage-1 LUT and the cold entry publication.  An
authenticated pre-r341 scene-$0B state, however, already contains the four
right-wall pole terminal attributes as BG6 in both physical VRAM maps.  The
existing r336 admission transaction restores code and signed wall art but
deliberately preserves the captured runtime tables, so those four pixels stay
gray until a later full room publication.

This patch extends only that stale-runtime admission transaction.  Immediately
after its audited VBlank GDMA completes, it checks the exact four endpoint tile
IDs in each physical map and writes BG5 only when the expected terminal tile is
present.  Nonmatching cells (including the corrupted-wall operator capture)
are untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_hazard_terminal_caps_r341 as r341


ROOT = r341.ROOT
BASE = r341.OUTPUT
BASE_RECEIPT = r341.RECEIPT
OUTPUT = ROOT / "tmp/stage1-hazard-terminal-resume-r342/candidate.gb"
RECEIPT = ROOT / "tmp/stage1-hazard-terminal-resume-r342/build-receipt.json"
BASE_SHA256 = "30ba055bc4cdd7468994d8dbe017a9c73ec82d09184f792e690ffd22a95e73cf"
R342_SHA256 = "84bf020e4a9006e0ce9a3e79fec6687a281620108d5337ab8fddb99d0093dd1f"

R331 = r341.r336.r335.r331
CAVE_ADDR = R331.CAVE_ADDR
ART_PAYLOAD_ADDR = R331.r325.r324.ART_PAYLOAD_ADDR
PATCH_HELPER_ADDR = 0x6FE0
TERMINAL_CELLS = (
    (0x98A2, 0x6B),
    (0x98AD, 0x6F),
    (0x98C2, 0x7B),
    (0x98CD, 0x7F),
    (0x9CA2, 0x6B),
    (0x9CAD, 0x6F),
    (0x9CC2, 0x7B),
    (0x9CCD, 0x7F),
)
RUNTIME_LUT_TILES = (0x6B, 0x6F, 0x7B, 0x7F)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank31_offset(address: int) -> int:
    return R331.o(address)


def patch_helper() -> bytes:
    # Entry: VBK0, A=expected terminal tile, HL=physical map cell.
    # Exit: write BG5 through VBK1 only on an exact tile match; restore VBK0.
    return bytes.fromhex("BE C0 3E 01 E0 4F 3E 05 77 AF E0 4F C9")


def terminal_repair_stream() -> bytes:
    # Preserve exact entry VBK/flags, migrate the four working C600 LUT
    # entries before the invalidated compiler runs, then repair the already
    # visible maps within the same audited VBlank.
    stream = bytearray(bytes.fromhex("F0 4F F5 3E 05"))
    for tile in RUNTIME_LUT_TILES:
        stream.extend((0xEA, tile, 0xC6))
    stream.extend(bytes.fromhex("AF E0 4F"))
    previous_high = None
    for address, tile in TERMINAL_CELLS:
        high = address >> 8
        if high != previous_high:
            stream.extend((0x21, address & 0xFF, high))  # LD HL,address
            previous_high = high
        else:
            stream.extend((0x2E, address & 0xFF))  # LD L,low
        stream.extend((0x3E, tile, 0xCD))
        stream.extend(PATCH_HELPER_ADDR.to_bytes(2, "little"))
    stream.extend(bytes.fromhex("F1 E0 4F"))
    if len(stream) != 81:
        raise AssertionError("r342 terminal repair stream width changed")
    return bytes(stream)


def repair_runtime_lut_model(lut: bytes) -> bytes:
    if len(lut) != 0x100:
        raise AssertionError("r342 runtime LUT model requires 256 bytes")
    result = bytearray(lut)
    for tile in RUNTIME_LUT_TILES:
        result[tile] = 5
    return bytes(result)


def repair_attr_model(tiles: bytes, attrs: bytes) -> bytes:
    """Pure model of the two-map conditional migration."""
    if len(tiles) != 0x800 or len(attrs) != 0x800:
        raise AssertionError("r342 physical-plane model requires two 1 KiB maps")
    result = bytearray(attrs)
    for address, tile in TERMINAL_CELLS:
        map_index = 0 if address < 0x9C00 else 1
        offset = address - (0x9800 if map_index == 0 else 0x9C00)
        index = map_index * 0x400 + offset
        if tiles[index] == tile:
            result[index] = 5
    return bytes(result)


def construct(source: bytes) -> tuple[bytes, dict[str, object]]:
    if digest(source) != BASE_SHA256:
        raise AssertionError("r342 base is not the exact r341 candidate")

    chunks = r341.r336.r335.selected_regions()
    original_cave_size = 1 + 14 * len(chunks) + R331.REPAIR_SIZE + 3
    r336_cave_size = original_cave_size + 5
    tail_size = R331.REPAIR_SIZE + 3
    art_call_offset = original_cave_size - tail_size
    insertion = art_call_offset + 5
    cave_offset = bank31_offset(CAVE_ADDR)
    old_cave = source[cave_offset:cave_offset + r336_cave_size]
    art_helper = R331.r325.r324.ART_HELPER_ADDR
    expected_art_call = (
        bytes((0xCD,)) + art_helper.to_bytes(2, "little")
        + bytes((0x20, 0xFB))
    )
    if old_cave[art_call_offset:insertion] != expected_art_call:
        raise AssertionError("r342 r336 admission-art call preimage changed")

    repair = terminal_repair_stream()
    new_cave = old_cave[:insertion] + repair + old_cave[insertion:]
    new_cave_end = CAVE_ADDR + len(new_cave)
    if new_cave_end > PATCH_HELPER_ADDR:
        raise AssertionError("r342 admission cave overlaps terminal helper")
    helper = patch_helper()
    if PATCH_HELPER_ADDR + len(helper) > ART_PAYLOAD_ADDR:
        raise AssertionError("r342 terminal helper overlaps signed art payload")

    rom = bytearray(source)
    extension = rom[
        cave_offset + r336_cave_size:cave_offset + len(new_cave)
    ]
    if extension != bytes([0xFF]) * len(extension):
        raise AssertionError("r342 admission cave extension preimage changed")
    helper_offset = bank31_offset(PATCH_HELPER_ADDR)
    if rom[helper_offset:helper_offset + len(helper)] != bytes([0xFF]) * len(helper):
        raise AssertionError("r342 terminal helper preimage changed")
    rom[cave_offset:cave_offset + len(new_cave)] = new_cave
    rom[helper_offset:helper_offset + len(helper)] = helper
    r341.r336.r335.r331.r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)

    functional = {
        index for index, pair in enumerate(zip(source, candidate))
        if pair[0] != pair[1] and index not in {0x14D, 0x14E, 0x14F}
    }
    allowed = (
        set(range(cave_offset, cave_offset + len(new_cave)))
        | set(range(helper_offset, helper_offset + len(helper)))
    )
    if not functional or not functional <= allowed:
        raise AssertionError("r342 functional delta escaped its two owned caves")

    candidate_sha = digest(candidate)
    if candidate_sha != R342_SHA256:
        raise AssertionError("r342 exact candidate identity changed")
    return candidate, {
        "schema": "penta-stage1-hazard-terminal-resume-r342-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": candidate_sha,
        "base_r341_sha256": BASE_SHA256,
        "terminal_cells": [
            {"address": f"{address:04X}", "tile": f"{tile:02X}", "palette": 5}
            for address, tile in TERMINAL_CELLS
        ],
        "admission_cave": f"bank31:${CAVE_ADDR:04X}-${new_cave_end - 1:04X}",
        "conditional_helper": (
            f"bank31:${PATCH_HELPER_ADDR:04X}-"
            f"${PATCH_HELPER_ADDR + len(helper) - 1:04X}"
        ),
        "nonmatching_cells_preserved": True,
        "required_live_gates": list(r341.REQUIRED_LIVE_GATES),
    }


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    if digest(source) != BASE_SHA256:
        raise AssertionError("r342 base is not the exact r341 candidate")
    parent = json.loads(receipt_bytes)
    if parent.get("candidate_sha256") != BASE_SHA256:
        raise AssertionError("r341 build receipt targets another candidate")
    candidate, receipt = construct(source)
    receipt.update({"schema": "penta-stage1-hazard-terminal-resume-r342-build-v1",
                    "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
                    "required_live_gates": parent["required_live_gates"]})
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
