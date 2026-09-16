#!/usr/bin/env python3
"""Move the Stage-1 palette arm to r209's exact atomic map flip.

The native scene byte becomes gameplay several frames before the completed
dungeon map replaces the STAGE card.  r208/r209 arm the complete gameplay
palette deck at that earlier scene edge, permitting Pocket/SameBoy to repaint
the outgoing card purple.  This exact diagnostic preserves the entry gate's
instruction timing but defers the DF4C arm to the existing map-flip helper.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from build_later_gdma_upper_bound import update_checksums

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from stage_card_palette_handoff import (
    PRIVATE_OFFSET,
    STAGE1_BG0_OFFSET,
    STAGE1_ENTRY_GATE_OFFSET,
    TITLE_BG0_OFFSET,
    _build_private_helper,
    _choose_discriminator,
)


BASE_SHA256 = "83b2f90f87e3dafcdc168bd85a89104cd60b59483dd2f46666affd35020a9a68"
OLD_ENTRY_GATE = bytes.fromhex("FA FD DC E0 91 3E 11 EA 4C DF C3 E5 55")
# Freeze the exact r210 recipe. The shared production gate subsequently added
# a DF5B reset; importing that newer constant silently changes this historical
# candidate. LD A,$11; JR +0; NOP preserves the old LD A/$DF4C-store timing
# without publishing DF4C at the outgoing Stage-card edge.
DEFERRED_ENTRY_GATE = bytes.fromhex("FA FD DC E0 91 3E 11 18 00 00 C3 E5 55")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    if sha256(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r209 base: {sha256(source)}")

    stage1_bg0 = source[STAGE1_BG0_OFFSET:STAGE1_BG0_OFFSET + 8]
    title_bg0 = source[TITLE_BG0_OFFSET:TITLE_BG0_OFFSET + 8]
    discriminator = _choose_discriminator(stage1_bg0, title_bg0)
    old_helper = _build_private_helper(
        stage1_bg0,
        discriminator,
        title_bg0[discriminator],
        arm_palette_phase=False,
    )
    new_helper = _build_private_helper(
        stage1_bg0,
        discriminator,
        title_bg0[discriminator],
        arm_palette_phase=True,
    )
    if len(new_helper) != len(old_helper) + 5:
        raise SystemExit("deferred helper did not grow by the exact phase arm")

    rom = bytearray(source)
    if rom[
        STAGE1_ENTRY_GATE_OFFSET:
        STAGE1_ENTRY_GATE_OFFSET + len(OLD_ENTRY_GATE)
    ] != OLD_ENTRY_GATE:
        raise SystemExit("old Stage-1 entry palette arm preimage moved")
    if rom[PRIVATE_OFFSET:PRIVATE_OFFSET + len(old_helper)] != old_helper:
        raise SystemExit("old Stage-card private helper preimage moved")
    if rom[
        PRIVATE_OFFSET + len(old_helper):
        PRIVATE_OFFSET + len(new_helper)
    ] != bytes([0xFF]) * (len(new_helper) - len(old_helper)):
        raise SystemExit("Stage-card helper growth tail is no longer erased")

    rom[
        STAGE1_ENTRY_GATE_OFFSET:
        STAGE1_ENTRY_GATE_OFFSET + len(DEFERRED_ENTRY_GATE)
    ] = DEFERRED_ENTRY_GATE
    rom[PRIVATE_OFFSET:PRIVATE_OFFSET + len(new_helper)] = new_helper
    update_checksums(rom)
    candidate = bytes(rom)
    receipt = {
        "schema": "penta-stage1-deferred-palette-r210-v1",
        "status": "STATIC_PASS_EMULATOR_AND_HARDWARE_REQUIRED",
        "promotable": False,
        "base_sha256": sha256(source),
        "candidate_sha256": sha256(candidate),
        "entry_gate": "$6A33",
        "entry_gate_timing_preserved": True,
        "palette_phase_write_removed_from_scene_edge": True,
        "palette_phase_write_added_to_atomic_map_flip": True,
        "stage1_palette_phase": "$11",
        "private_helper_old_size": len(old_helper),
        "private_helper_new_size": len(new_helper),
        "required_first_gates": [
            "Stage-card temporal stability",
            "3600-frame native no-bleed",
            "current-ROM menu/item/low-health hazard",
            "strict Stage-1 speed",
            "Pocket/SameBoy physical confirmation",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    candidate, receipt = build(args.base.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
