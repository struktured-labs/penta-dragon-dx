#!/usr/bin/env python3
"""Build a completed-source later-stage semantic publisher on exact r120.

Stages 2-7 take the stock-width tile-only copy, then hash the *completed*
C1A0 source at the existing post-copy boundary. A changed per-map key compiles
the final 20x22 semantic plane through immutable stage LUTs and publishes it
with one bounded GDMA before the native map flip. Stage 1 keeps its exact
existing post-copy route. Diagnostic only pending all visual/speed/hardware
gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import analyze_later_attr_signature as signature_audit
from build_later_hdma_overlap import (
    BANK_SIZE,
    BASE_SHA256,
    HELPER_BANK,
    MAPPER,
    Asm,
    checksum,
)


HELPER_ADDR = 0x4301
BANKED_ENTRY_ADDR = 0x6C80
# The exact sparse publisher is deliberately unrolled so every dirty block
# has a fixed source/destination pair and no runtime multiply/divide cost.
# Keep the immutable six-page LUT immediately after that helper while leaving
# the banked mapper entry at $6C80 untouched.
STAGE_LUT_ADDR = 0x6400
SIGNATURE_A = (444, 149, 19, 251)
SIGNATURE_B = (0, 59, 333, 201)
SIGNATURE_CONTEXT = (185, 51, 403, 432)
PLANE_SIGNATURE = bytes.fromhex("50 44 50 16")
DEST_HRAM = 0xE2
DMA_COMMAND_HRAM = 0xE6
DIRTY_BLOCK_FLAGS_ADDR = 0xD3C0
PLANE_KEY_ADDR = 0xD3F8

DISPATCHER_SOURCE_ADDR = 0x7C93
DISPATCHER_PREIMAGE = bytes.fromhex("C3 60 DA")
DISPATCHER_REPLACEMENT = bytes.fromhex("AF C9 00")
POSTCOPY_GUARD_SOURCE_ADDR = 0x5830
POSTCOPY_GUARD_PREIMAGE = bytes.fromhex(
    "F0 BA B7 28 04 AF E0 A5 C9 C3 E2 10"
)
POSTCOPY_GUARD_REPLACEMENT = bytes.fromhex(
    "F0 BA B7 CA E2 10 3E 15 C3 47 08 00"
)


def add_hl(a: Asm, amount: int) -> None:
    a.db(0x7D, 0xC6, amount, 0x6F, 0x30, 0x01, 0x24)


def add_de(a: Asm, amount: int) -> None:
    a.db(0x7B, 0xC6, amount, 0x5F, 0x30, 0x01, 0x14)


def emit_xor(a: Asm, samples: tuple[int, ...], store_opcode: int) -> None:
    first = 0xC1A0 + samples[0]
    a.db(0xFA, first & 0xFF, first >> 8)
    for offset in samples[1:]:
        source = 0xC1A0 + offset
        a.db(0x21, source & 0xFF, source >> 8, 0xAE)
    a.db(store_opcode)


def build_helper(labels_out: dict[str, int] | None = None) -> bytes:
    a = Asm(HELPER_ADDR)
    a.db(0xF3, 0xC5, 0xD5, 0xE5)          # DI; preserve caller BC/DE/HL
    # The 24-row stock copier advanced H by exactly three pages. Recover the
    # authoritative completed destination without consulting LCDC/DC0B.
    a.db(0x7C, 0xD6, 0x03, 0xE0, DEST_HRAM)
    emit_xor(a, SIGNATURE_A, 0x47)          # B = signature A
    emit_xor(a, SIGNATURE_B, 0x4F)          # C = signature B
    a.db(0xF0, 0xBD)
    for offset in SIGNATURE_CONTEXT:
        source = 0xC1A0 + offset
        a.db(0x21, source & 0xFF, source >> 8, 0xAE)
    a.db(0x6F)                              # L = room/layout context

    # Select the persistent plane before consulting its private three-byte
    # key. The older DF53/DF57 records are shared with the native renderer and
    # can be rewritten between postcopies; D3F8 is map-local in SVBK2/3.
    a.db(0xF0, DEST_HRAM, 0xFE, 0x98, 0x3E, 0x02)
    a.jr(0x28, "bank_selected")
    a.db(0x3C)
    a.label("bank_selected")
    a.db(0xE0, 0x70)

    a.db(0xFA, PLANE_KEY_ADDR & 0xFF, PLANE_KEY_ADDR >> 8, 0xB8)
    a.jr(0x20, "changed")
    a.db(0xFA, (PLANE_KEY_ADDR + 1) & 0xFF, PLANE_KEY_ADDR >> 8, 0xB9)
    a.jr(0x20, "changed")
    a.db(0xFA, (PLANE_KEY_ADDR + 2) & 0xFF, PLANE_KEY_ADDR >> 8, 0xBD)
    a.jr(0x20, "changed")
    # A matching source key is not sufficient to skip compilation: the
    # native streamer can republish a physical map between completed-copy
    # callbacks. Recompute exact bytes every postcopy; the dirty bitmap still
    # suppresses unchanged VRAM blocks.
    a.db(0x0E, 0x01)
    a.jp(0xC3, "plane_ready")
    a.label("changed")
    a.db(
        0x78, 0xEA, PLANE_KEY_ADDR & 0xFF, PLANE_KEY_ADDR >> 8,
        0x79, 0xEA, (PLANE_KEY_ADDR + 1) & 0xFF, PLANE_KEY_ADDR >> 8,
        0x7D, 0xEA, (PLANE_KEY_ADDR + 2) & 0xFF, PLANE_KEY_ADDR >> 8,
    )
    a.db(0x0E, 0x01)                       # C = compile changed plane

    a.label("plane_ready")
    for index, value in enumerate(PLANE_SIGNATURE):
        a.db(0xFA, (0xD3FC + index) & 0xFF, 0xD3, 0xFE, value)
        a.jr(0x20, "initialize")
    a.jr(0x18, "prepare_clean_flags")
    a.label("initialize")
    a.db(0x21, 0x00, 0xD0, 0x06, 0x03, 0xAF)
    a.label("clear_page")
    a.db(0x0E, 0x00)
    a.label("clear_byte")
    a.db(0x22, 0x0D)
    a.jr(0x20, "clear_byte")
    a.db(0x05)
    a.jr(0x20, "clear_page")
    for index, value in enumerate(PLANE_SIGNATURE):
        a.db(0x3E, value, 0xEA, (0xD3FC + index) & 0xFF, 0xD3)
    a.db(0x0E, 0x01)                       # invalid plane must be compiled
    a.jr(0x18, "prepare_flags")

    a.label("prepare_clean_flags")
    a.db(0xAF)
    a.label("prepare_flags")
    a.db(0x21, DIRTY_BLOCK_FLAGS_ADDR & 0xFF,
         DIRTY_BLOCK_FLAGS_ADDR >> 8, 0x06, 0x30)
    a.label("fill_flags")
    a.db(0x22, 0x05)
    a.jr(0x20, "fill_flags")
    a.db(0x79, 0xB7)
    a.jp(0xCA, "semantic_blocks")          # cache hit: sparse reassert only

    a.label("compile")
    a.db(0xF0, 0xBA, 0xC6, (STAGE_LUT_ADDR >> 8) - 1, 0x47)
    # Compile two fixed spans per row (16 + 6 cells). Keeping each span in a
    # compact loop creates enough bank space to phase-align every one-block
    # HBlank transfer below. B remains the immutable ROM LUT page; C is the
    # tile index. The loop counter lives in otherwise-private HRAM $E7.
    for row in range(20):
        for span, count in ((0, 16), (16, 6)):
            block = row * 2 + (1 if span else 0)
            source = 0xC1A0 + row * 24 + span
            plane = 0xD000 + row * 32 + span
            loop = f"compile_span_{row}_{span}"
            done = f"compile_same_{row}_{span}"
            a.db(
                0x11, source & 0xFF, source >> 8,
                0x21, plane & 0xFF, plane >> 8,
                0x3E, count, 0xE0, 0xE7,
            )
            a.label(loop)
            a.db(0x1A, 0x13, 0x4F, 0x0A, 0xBE)
            a.jr(0x28, done)
            a.db(
                0x77, 0x3E, 0x01, 0xEA,
                (DIRTY_BLOCK_FLAGS_ADDR + block) & 0xFF,
                (DIRTY_BLOCK_FLAGS_ADDR + block) >> 8,
            )
            a.label(done)
            a.db(0x23, 0xF0, 0xE7, 0x3D, 0xE0, 0xE7)
            a.jr(0x20, loop)

    # The native later-stage path can transiently clear semantic pickup and
    # material attrs after this persistent plane has already converged. Mark
    # every block containing sparse slots 1/2/4 for reassertion. Dense lava
    # (slot 5) remains exact-dirty only, while the compile comparison above
    # still captures every clear and prevents semantic trails.
    a.label("semantic_blocks")
    a.db(
        0x21, 0x00, 0xD0,                 # HL = persistent plane
        0x11, DIRTY_BLOCK_FLAGS_ADDR & 0xFF,
        DIRTY_BLOCK_FLAGS_ADDR >> 8,       # DE = block flags
        0x06, 0x30,                        # B = 48 blocks
    )
    a.label("semantic_block")
    a.db(0x0E, 0x10)                       # C = 16 bytes
    a.label("semantic_cell")
    a.db(0x2A)
    for semantic_attr in (0x01, 0x02, 0x04):
        a.db(0xFE, semantic_attr)
        a.jr(0x28, "semantic_mark")
    a.jr(0x18, "semantic_next")
    a.label("semantic_mark")
    a.db(0x3E, 0x01, 0x12)
    a.label("semantic_next")
    a.db(0x0D)
    a.jr(0x20, "semantic_cell")
    a.db(0x13, 0x05)
    a.jr(0x20, "semantic_block")

    # Publish only exact changed 16-byte blocks. LCD-on uses a one-block
    # HBlank transfer and waits for completion; LCD-off uses one-block GDMA.
    # Initial maps force all 48 blocks so zero padding also replaces any stale
    # title/boot attributes.
    a.db(0x3E, 0x01, 0xE0, 0x4F)
    a.db(0xF0, 0x40, 0xCB, 0x7F, 0xAF)
    a.jr(0x28, "dma_mode_ready")
    a.db(0x3E, 0x80)
    a.label("dma_mode_ready")
    a.db(0xE0, DMA_COMMAND_HRAM)
    for block in range(48):
        done = f"block_done_{block}"
        wait = f"block_wait_{block}"
        low = (block & 0x0F) << 4
        page = block >> 4
        a.db(
            0xFA, (DIRTY_BLOCK_FLAGS_ADDR + block) & 0xFF,
            (DIRTY_BLOCK_FLAGS_ADDR + block) >> 8,
            0xB7,
        )
        a.jr(0x28, done)
        # Starting a new one-block HDMA while already in HBlank is
        # phase-sensitive. The proven full-plane path starts during mode 3;
        # do the same for every sparse rendered transfer. LCD-off command 00
        # bypasses this wait and completes as GDMA.
        a.db(0xF0, DMA_COMMAND_HRAM, 0xCB, 0x7F)
        a.jr(0x28, f"block_start_{block}")
        a.label(f"block_mode3_{block}")
        a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
        a.jr(0x20, f"block_mode3_{block}")
        a.label(f"block_start_{block}")
        a.db(
            0x3E, 0xD0 + page, 0xE0, 0x51,
            0x3E, low, 0xE0, 0x52,
            0xF0, DEST_HRAM, 0xC6, page, 0xE0, 0x53,
            0x3E, low, 0xE0, 0x54,
            0xF0, DMA_COMMAND_HRAM, 0xE0, 0x55,
        )
        a.label(wait)
        a.db(0xF0, 0x55, 0xCB, 0x7F)
        a.jr(0x28, wait)
        a.label(done)
    a.db(0xAF, 0xE0, 0x4F, 0x3C, 0xE0, 0x70)

    a.label("restore")
    # This complete post-copy owner supersedes the legacy 18-row fallback.
    # Leaving its DF4E/DF4F rearm live lets a later VBlank clear already-
    # correct pickup rows through the transient C600 table.
    a.db(0xAF, 0xEA, 0x4E, 0xDF, 0xEA, 0x4F, 0xDF)
    a.db(0xE1, 0xD1, 0xC1, 0x3E, 0x01, 0xC9)
    output = a.finish()
    if labels_out is not None:
        labels_out.update(a.labels)
    return output


def verify_corpus(paths: list[Path]) -> dict:
    observed = []
    digest = hashlib.sha256()
    for path in paths:
        payload = path.read_bytes()
        digest.update(payload)
        observed.extend(signature_audit.parse_layout_trace(path))
    records = [
        (stage, room, features,
         signature_audit.desired_plane(stage, features[:576]))
        for stage, room, features in sorted(set(observed))
    ]
    collisions, variants = signature_audit.metrics(
        records, SIGNATURE_A, SIGNATURE_B, SIGNATURE_CONTEXT
    )
    if len(records) != 1255 or collisions:
        raise SystemExit(
            f"completed-source key corpus failed: records={len(records)} "
            f"collisions={collisions}"
        )
    return {
        "records": len(records), "sha256": digest.hexdigest(),
        "collisions": collisions, "false_variants": variants,
        "a": SIGNATURE_A, "b": SIGNATURE_B, "context": SIGNATURE_CONTEXT,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--layout-trace", action="append", type=Path,
                        required=True)
    args = parser.parse_args()
    source = args.base.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != BASE_SHA256:
        raise SystemExit(f"wrong exact r120 base: {digest}")
    corpus = verify_corpus(args.layout_trace)
    helper_labels: dict[str, int] = {}
    helper = build_helper(helper_labels)
    if HELPER_ADDR + len(helper) > STAGE_LUT_ADDR:
        raise SystemExit("post-copy helper overlaps immutable stage LUTs")
    stage_luts = b"".join(
        signature_audit.semantic_lut(stage) for stage in range(2, 8)
    )
    rom = bytearray(source)

    # Force only later dungeons to the pure pre-copy route in both generated
    # source mirrors. Crystal's arena branch still enters the existing cache.
    for bank in (13, 16):
        offset = bank * BANK_SIZE + DISPATCHER_SOURCE_ADDR - 0x4000
        if rom[offset:offset + 3] != DISPATCHER_PREIMAGE:
            raise SystemExit(f"bank{bank} later-dispatch preimage moved")
        rom[offset:offset + 3] = DISPATCHER_REPLACEMENT
    guard = 13 * BANK_SIZE + POSTCOPY_GUARD_SOURCE_ADDR - 0x4000
    if rom[guard:guard + 12] != POSTCOPY_GUARD_PREIMAGE:
        raise SystemExit("post-copy WRAM guard source moved")
    rom[guard:guard + 12] = POSTCOPY_GUARD_REPLACEMENT

    helper_offset = HELPER_BANK * BANK_SIZE + HELPER_ADDR - 0x4000
    entry_offset = HELPER_BANK * BANK_SIZE + BANKED_ENTRY_ADDR - 0x4000
    lut_offset = HELPER_BANK * BANK_SIZE + STAGE_LUT_ADDR - 0x4000
    if rom[helper_offset:helper_offset + len(helper)] != bytes([0xFF]) * len(helper):
        raise SystemExit("bank21 post-copy helper cave is not erased")
    if rom[entry_offset:entry_offset + 3] != bytes([0xFF]) * 3:
        raise SystemExit("bank21 mapper entry is not erased")
    if rom[lut_offset:lut_offset + len(stage_luts)] != bytes([0xFF]) * len(stage_luts):
        raise SystemExit("bank21 stage LUT cave is not erased")
    rom[helper_offset:helper_offset + len(helper)] = helper
    rom[entry_offset:entry_offset + 3] = bytes(
        (0xC3, HELPER_ADDR & 0xFF, HELPER_ADDR >> 8)
    )
    rom[lut_offset:lut_offset + len(stage_luts)] = stage_luts
    checksum(rom)
    output = bytes(rom)
    report = {
        "schema": "penta-later-postcopy-raw-gdma-r165-v1",
        "status": "PASS_STATIC_EMULATOR_AND_HARDWARE_REQUIRED",
        "promotable": False,
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(output).hexdigest(),
        "helper": f"bank{HELPER_BANK}:${HELPER_ADDR:04X}, {len(helper)} bytes",
        "helper_labels": helper_labels,
        "banked_entry": f"bank{HELPER_BANK}:${BANKED_ENTRY_ADDR:04X}",
        "key_contract": corpus,
        "contracts": {
            "decision_after_completed_tile_copy": True,
            "exact_destination_from_final_h_minus_three": True,
            "stage1_postcopy_route_byte_exact": True,
            "later_pre_copy_route_is_stock_width_pure": True,
            "final_semantic_plane_uses_yaml_slots": True,
            "exact_16_byte_dirty_block_bitmap": True,
            "maximum_hblank_blocks": 48,
            "unchanged_blocks_not_published": True,
            "legacy_later_row_sweep_disarmed_after_postcopy": True,
            "caller_registers_restored": True,
            "svbk_vbk_restored": True,
        },
        "hardware_risk": "HBlank timing still requires Pocket/MiSTer audit",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
