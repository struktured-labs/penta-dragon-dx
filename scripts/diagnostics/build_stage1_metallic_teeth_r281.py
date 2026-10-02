#!/usr/bin/env python3
"""Replace Stage-1 tooth gold with a neutral metallic scene-local row.

The rotating tooth tile cells contain stock in-between silhouettes while the
cylinder extends and retracts.  Highlighting every silhouette with gold makes
those legitimate animation cells read as detached trails.  This candidate
changes only the Stage-1-only BG7 source row in the two exact runtime mirrors;
the red/gold cylinder body, tile art, attributes, code, and timing are intact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_SHA256 = "649dab3b8895e680ff9e64005641de89b3ac1f66bcb417d6a1c42ce98bc30a9d"
EXPECTED_CANDIDATE_SHA256 = (
    "6b2bb22129011d06a1d5f5eb07a34c04f5dc09c35d9df65afa4a000546a8cf49"
)
BANK_SIZE = 0x4000
MIRROR_BANKS = (13, 16)
PALETTE_SOURCE_ADDR = 0x68C8
OLD_ROW = bytes.fromhex("FF 7F 94 7E FF 03 00 00")
NEW_ROW = bytes.fromhex("FF 7F 94 7E 4A 29 00 00")


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if bank <= 0 or not 0x4000 <= address < 0x8000:
        raise AssertionError((bank, address))
    return bank * BANK_SIZE + address - 0x4000


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    base_sha = digest(base)
    if base_sha != BASE_SHA256:
        raise AssertionError(f"wrong exact r279 base: {base_sha}")

    rom = bytearray(base)
    allowed = {0x014D, 0x014E, 0x014F}
    mirrors: list[dict[str, object]] = []
    for bank in MIRROR_BANKS:
        offset = bank_offset(bank, PALETTE_SOURCE_ADDR)
        actual = base[offset:offset + len(OLD_ROW)]
        if actual != OLD_ROW:
            raise AssertionError(
                f"bank{bank} Stage-1 tooth row changed: {actual.hex(' ')}"
            )
        rom[offset:offset + len(NEW_ROW)] = NEW_ROW
        allowed.update(range(offset, offset + len(NEW_ROW)))
        mirrors.append({
            "bank": bank,
            "address": f"${PALETTE_SOURCE_ADDR:04X}-${PALETTE_SOURCE_ADDR + 7:04X}",
            "old_row": OLD_ROW.hex(" ").upper(),
            "new_row": NEW_ROW.hex(" ").upper(),
        })

    update_checksums(rom)
    candidate = bytes(rom)
    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND" \
            and candidate_sha != EXPECTED_CANDIDATE_SHA256:
        raise AssertionError(
            f"candidate identity drift: {candidate_sha} != "
            f"{EXPECTED_CANDIDATE_SHA256}"
        )
    changed = [
        index for index, (before, after) in enumerate(zip(base, candidate))
        if before != after
    ]
    unexpected = sorted(set(changed) - allowed)
    if unexpected:
        raise AssertionError(
            "unexpected changed offsets: "
            + ", ".join(f"0x{value:X}" for value in unexpected)
        )

    receipt: dict[str, object] = {
        "schema": "penta-stage1-metallic-teeth-r281-build-v1",
        "status": "STATIC_PASS_VISUAL_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": base_sha,
        "candidate_sha256": candidate_sha,
        "changed_bytes_including_checksums": len(changed),
        "palette_mirrors": mirrors,
        "contracts": {
            "exact_r279_base": True,
            "only_scene_local_tooth_palette_rows_changed": True,
            "tile_art_and_attributes_unchanged": True,
            "red_gold_cylinder_body_palette_unchanged": True,
            "code_and_timing_unchanged": True,
            "stage7_lifecycle_patch_unchanged": True,
        },
        "required_gates": [
            "candidate-bound Stage-1 hazard/menu phase montage",
            "candidate-bound pickup and north/entrance visual gates",
            "Stage-1 speed transfer or replay",
            "Pocket hardware signoff",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", type=Path,
        default=ROOT / "tmp/stage7-lazy-disarm-r279/candidate.gb",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage1-metallic-teeth-r281/candidate.gb",
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=ROOT / "tmp/stage1-metallic-teeth-r281/build-receipt.json",
    )
    args = parser.parse_args()
    candidate, receipt = install(args.base.read_bytes())
    for path, payload in (
        (args.output, candidate),
        (args.receipt, json.dumps(receipt, indent=2).encode() + b"\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
