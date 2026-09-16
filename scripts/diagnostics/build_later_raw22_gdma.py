#!/usr/bin/env python3
"""Build an immutable-LUT 20x22 later-dungeon compiler with bounded GDMA.

Diagnostic only until the full Stage 2-7 ownership and visual suite passes.
The stock expander's populated C1A0 region is exactly 20 rows by 22 columns;
the remaining staging bytes are initialized to zero once per physical map.
Every dirty publication recompiles those 440 live cells through a stage-local
ROM attribute LUT. The LUT stores YAML palette *slots*, not RGB colors, so
palette-YAML edits remain authoritative while transient C600 resets cannot
erase lava, material, or pickup attributes.
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
    NATIVE_DIRTY_TAIL,
    Asm,
    checksum,
)


SIGNATURE = bytes.fromhex("50 44 52 16")
HELPER_ADDR = 0x4301
HOOK_ADDR = 0x42FC
DECIDER_WRAM_ADDR = 0xDB00
DECIDER_SENTINEL_ADDR = 0xDB7F
DECIDER_SENTINEL = 0xA7
DECIDER_SOURCE_ADDR = 0x5000
STAGE_LUT_SOURCE_ADDR = 0x5100
SIGNATURE_A = (444, 149, 19, 251)
SIGNATURE_B = (0, 59, 333, 201)
SIGNATURE_CONTEXT = (185, 51, 403, 432)
DECISION_HRAM = 0xE0


def add_hl(a: Asm, amount: int) -> None:
    a.db(0x7D, 0xC6, amount, 0x6F, 0x30, 0x01, 0x24)


def add_de(a: Asm, amount: int) -> None:
    a.db(0x7B, 0xC6, amount, 0x5F, 0x30, 0x01, 0x14)


def build_expanded_decider() -> bytes:
    a = Asm(DECIDER_WRAM_ADDR)
    a.db(0xC5, 0xD5, 0xE5, 0xB7)
    a.jr(0x28, "signature_zero")
    a.db(0x00, 0x00, 0x00, 0xAF)           # established Stage 3-7 phase
    a.label("signature_zero")
    a.db(0xE0, DECISION_HRAM)
    # H is the exact $98/$9C map. Select its three-byte DF53/DF57 record.
    a.db(0x7C, 0xEE, 0xCB, 0x5F, 0x16, 0xDF)

    for destination, samples in ((0x47, SIGNATURE_A), (0x4F, SIGNATURE_B)):
        first = 0xC1A0 + samples[0]
        a.db(0xFA, first & 0xFF, first >> 8)
        for offset in samples[1:]:
            source = 0xC1A0 + offset
            a.db(0x21, source & 0xFF, source >> 8, 0xAE)
        a.db(destination)

    # Reuse the existing third cache byte, but make it layout-sensitive while
    # retaining room identity. All four offsets are stable within an identical
    # semantic plane in the combined fail-closed corpus.
    a.db(0xF0, 0xBD)
    for offset in SIGNATURE_CONTEXT:
        source = 0xC1A0 + offset
        a.db(0x21, source & 0xFF, source >> 8, 0xAE)
    a.db(0x6F)                              # L = room/layout context

    a.db(0x1A, 0xB8)
    a.jr(0x20, "changed")
    a.db(0x13, 0x1A, 0xB9)
    a.jr(0x20, "changed_one")
    a.db(0x13, 0x1A, 0xBD)
    a.jr(0x20, "changed_two")
    a.label("restore")
    a.db(0xE1, 0xD1, 0xC1, 0xC9)
    a.label("changed_two")
    a.db(0x1B)
    a.label("changed_one")
    a.db(0x1B)
    a.label("changed")
    a.db(
        0x78, 0x12, 0x13,
        0x79, 0x12, 0x13,
        0x7D, 0x12,
        0x3E, 0x01, 0xE0, DECISION_HRAM,
    )
    a.jr(0x18, "restore")
    code = a.finish()
    if len(code) > DECIDER_SENTINEL_ADDR - DECIDER_WRAM_ADDR:
        raise AssertionError("expanded decider overlaps its validity sentinel")
    return code


def build_helper(decider_length: int) -> bytes:
    a = Asm(HELPER_ADDR)
    # Enter only after the exact native tile loop and its palette-scheduler
    # window have completed. Atomic setup already owns the tagged destination
    # and saved caller IE; this helper merely closes the dirty publication.
    a.db(0xF3)
    # Install the expanded collision-free key on the first real dirty copy.
    # Source and helper share bank 21; destination is proven-zero WRAM1.
    a.db(0xFA, DECIDER_SENTINEL_ADDR & 0xFF,
         DECIDER_SENTINEL_ADDR >> 8, 0xFE, DECIDER_SENTINEL)
    a.jr(0x28, "decider_ready")
    a.db(
        0x21, DECIDER_SOURCE_ADDR & 0xFF, DECIDER_SOURCE_ADDR >> 8,
        0x11, DECIDER_WRAM_ADDR & 0xFF, DECIDER_WRAM_ADDR >> 8,
        0x0E, decider_length,
    )
    a.label("install_decider")
    a.db(0x2A, 0x12, 0x13, 0x0D)
    a.jr(0x20, "install_decider")
    # Redirect only after the complete body is resident.
    for address, value in (
        (0xDA60, 0xC3), (0xDA61, DECIDER_WRAM_ADDR & 0xFF),
        (0xDA62, DECIDER_WRAM_ADDR >> 8),
        (DECIDER_SENTINEL_ADDR, DECIDER_SENTINEL),
    ):
        a.db(0x3E, value, 0xEA, address & 0xFF, address >> 8)
    a.label("decider_ready")
    # Odd tagged destination -> exact map and dedicated persistent plane bank.
    a.db(0xF0, 0xA5, 0x3D, 0xE0, 0xE2, 0xFE, 0x98, 0x3E, 0x02)
    a.jr(0x28, "bank_selected")
    a.db(0x3C)
    a.label("bank_selected")
    a.db(0xE0, 0x70)

    for index, value in enumerate(SIGNATURE):
        a.db(0xFA, (0xD3FC + index) & 0xFF, 0xD3, 0xFE, value)
        a.jr(0x20, "initialize")
    a.jr(0x18, "compile")
    a.label("initialize")
    # Initialize all 24x32 staging bytes once. Every later compile overwrites
    # the full populated 20x22 region; untouched padding therefore stays zero.
    a.db(0x21, 0x00, 0xD0, 0x06, 0x03, 0xAF)
    a.label("clear_page")
    a.db(0x0E, 0x00)
    a.label("clear_byte")
    a.db(0x22, 0x0D)
    a.jr(0x20, "clear_byte")
    a.db(0x05)
    a.jr(0x20, "clear_page")
    for index, value in enumerate(SIGNATURE):
        a.db(0x3E, value, 0xEA, (0xD3FC + index) & 0xFF, 0xD3)

    a.label("compile")
    # FFBA is the stable one-based Stage 2..7 selector. Six page-aligned ROM
    # tables at $5100-$56FF make each lookup identical in cost to C600 while
    # removing the mutable-LUT ownership race observed in the 8,000-frame
    # Stage-7 soak.
    a.db(
        0x11, 0xA0, 0xC1,
        0x21, 0x00, 0xD0,
        0xF0, 0xBA, 0xC6, (STAGE_LUT_SOURCE_ADDR >> 8) - 1, 0x47,
    )
    # Fully unroll 20x22. INC E is cycle-cheaper than INC DE; the generated
    # page-crossing INC D sites are derived from the exact C1A0+row*24 layout.
    source_low = 0xA0
    for row in range(20):
        for column in range(22):
            a.db(0x1A, 0x1C)               # A=[DE]; INC E
            source_low = (source_low + 1) & 0xFF
            if source_low == 0:
                a.db(0x14)                 # exact 256-byte source crossing
            a.db(0x4F, 0x0A, 0x22)         # C=tile; A=ROM LUT[tile]; [HL+]=A
        add_de(a, 2)                        # packed source row stride 24
        source_low = (source_low + 2) & 0xFF
        add_hl(a, 10)                       # padded output row stride 32

    # Publish the complete offscreen attribute plane with one bounded GDMA.
    a.db(0xF0, 0xE2, 0x67, 0xE0, 0x53, 0xAF, 0x6F, 0xE0, 0x54)
    a.db(0x3E, 0x01, 0xE0, 0x4F, 0x3E, 0xD0, 0xE0, 0x51, 0xAF, 0xE0, 0x52)
    a.db(0x3E, 0x2F, 0xE0, 0x55)
    a.label("gdma_wait")
    a.db(0xF0, 0x55, 0xCB, 0x7F)
    a.jr(0x28, "gdma_wait")
    a.db(0xAF, 0xE0, 0x4F)

    a.db(0x3E, 0x01, 0xE0, 0x70)
    a.db(0x3E, 0x01, 0x01, NATIVE_DIRTY_TAIL & 0xFF,
         NATIVE_DIRTY_TAIL >> 8, 0xC5, 0xC3, MAPPER & 0xFF, MAPPER >> 8)
    return a.finish()


def verify_trace(trace: Path, result: Path) -> dict:
    dirty = set(json.loads(result.read_text())["compiler_tile_copy_indices"])
    lines = trace.read_text().splitlines()
    checked = 0
    for event_index in dirty:
        raw = bytes.fromhex(lines[event_index - 1].split("\t")[29])
        if len(raw) != 576:
            raise ValueError("invalid raw-plane trace")
        # All semantic content must fit the stock expander's 20x22 region.
        # The actual values remain runtime C600 lookups, not receipt constants.
        for row in range(24):
            for column in range(24):
                if (row >= 20 or column >= 22) and raw[row * 24 + column] != 0:
                    raise ValueError(
                        f"nonzero raw padding event={event_index} row={row} col={column}"
                    )
        checked += 1
    if len(lines) != 819 or len(dirty) != 303 or checked != 303:
        raise ValueError("Stage 7 trace/compiler cardinality changed")
    return {"events": len(lines), "dirty_publications": checked}


def verify_key_corpus(paths: list[Path]) -> dict:
    observed = []
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
        observed.extend(signature_audit.parse_layout_trace(path))
    records = [
        (stage, room, features,
         signature_audit.desired_plane(stage, features[:576]))
        for stage, room, features in sorted(set(observed))
    ]
    collisions, variants = signature_audit.metrics(
        records, SIGNATURE_A, SIGNATURE_B, SIGNATURE_CONTEXT
    )
    if len(records) != 1218 or collisions != 0:
        raise ValueError(
            f"expanded-key corpus drift: records={len(records)} "
            f"collisions={collisions}"
        )
    return {
        "records": len(records),
        "sha256": digest.hexdigest(),
        "collisions": collisions,
        "false_variants": variants,
        "a": SIGNATURE_A,
        "b": SIGNATURE_B,
        "context": SIGNATURE_CONTEXT,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("trace", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--layout-trace", action="append", type=Path, required=True)
    parser.add_argument("--lut-proof", action="append", type=Path, required=True)
    parser.add_argument("--wram-proof", action="append", type=Path, required=True)
    args = parser.parse_args()
    source = args.base.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != BASE_SHA256:
        raise SystemExit(f"wrong exact r120 base: {digest}")
    trace_receipt = verify_trace(args.trace, args.result)
    key_receipt = verify_key_corpus(args.layout_trace)
    if len(args.wram_proof) != 6:
        raise SystemExit("exactly six Stage 2-7 WRAM ownership proofs are required")
    wram_hashes = {}
    for proof in args.wram_proof:
        payload = proof.read_bytes()
        if len(payload) != 0x80 or payload != bytes(0x80):
            raise SystemExit(f"WRAM DB00-DB7F ownership proof failed: {proof}")
        wram_hashes[str(proof)] = hashlib.sha256(payload).hexdigest()
    decider = build_expanded_decider()
    helper = build_helper(len(decider))
    if len(args.lut_proof) != 6:
        raise SystemExit("exactly six Stage 2-7 LUT proofs are required")
    lut_hashes = {}
    lut_pages = []
    for stage, proof in zip(range(2, 8), args.lut_proof):
        payload = proof.read_bytes()
        if len(payload) != 0x100 or any(value > 7 for value in payload):
            raise SystemExit(f"invalid Stage {stage} immutable LUT proof: {proof}")
        semantic = signature_audit.semantic_lut(stage)
        for tile, expected in enumerate(semantic):
            if expected and payload[tile] != expected:
                raise SystemExit(
                    f"Stage {stage} LUT lost semantic tile ${tile:02X}: "
                    f"{payload[tile]} != {expected}"
                )
        lut_pages.append(payload)
        lut_hashes[str(proof)] = hashlib.sha256(payload).hexdigest()
    stage_luts = b"".join(lut_pages)
    if len(stage_luts) != 6 * 0x100:
        raise AssertionError("later-stage immutable LUT image is not six pages")
    rom = bytearray(source)
    if rom[HOOK_ADDR:HOOK_ADDR + 5] != bytes.fromhex("F0 E0 FE 03 28"):
        raise SystemExit("dirty post-copy preimage moved")
    if rom[0x4354:0x435A] != bytes.fromhex("CD F1 DB C3 DF DB"):
        raise SystemExit("native dirty tail moved")
    offset = HELPER_BANK * BANK_SIZE + HELPER_ADDR - 0x4000
    if rom[offset:offset + len(helper)] != bytes([0xFF]) * len(helper):
        raise SystemExit("bank-21 live-LUT helper cave is not erased")
    decider_offset = HELPER_BANK * BANK_SIZE + DECIDER_SOURCE_ADDR - 0x4000
    if rom[decider_offset:decider_offset + len(decider)] != bytes([0xFF]) * len(decider):
        raise SystemExit("bank-21 expanded-decider source cave is not erased")
    lut_offset = HELPER_BANK * BANK_SIZE + STAGE_LUT_SOURCE_ADDR - 0x4000
    if rom[lut_offset:lut_offset + len(stage_luts)] != bytes([0xFF]) * len(stage_luts):
        raise SystemExit("bank-21 immutable later-stage LUT cave is not erased")
    rom[offset:offset + len(helper)] = helper
    rom[decider_offset:decider_offset + len(decider)] = decider
    rom[lut_offset:lut_offset + len(stage_luts)] = stage_luts
    rom[HOOK_ADDR:HOOK_ADDR + 5] = bytes.fromhex("3E 15 CD 61 00")
    checksum(rom)
    output = bytes(rom)
    report = {
        "schema": "penta-later-raw22-gdma-v1",
        "status": "later-stage-diagnostic-full-qualification-required",
        "base_sha256": digest,
        "trace_sha256": hashlib.sha256(args.trace.read_bytes()).hexdigest(),
        "result_sha256": hashlib.sha256(args.result.read_bytes()).hexdigest(),
        "candidate_sha256": hashlib.sha256(output).hexdigest(),
        "helper": f"bank{HELPER_BANK}:${HELPER_ADDR:04X}, {len(helper)} bytes",
        "expanded_decider": (
            f"bank{HELPER_BANK}:${DECIDER_SOURCE_ADDR:04X} -> "
            f"WRAM1:${DECIDER_WRAM_ADDR:04X}, {len(decider)} bytes"
        ),
        "immutable_stage_luts": (
            f"bank{HELPER_BANK}:${STAGE_LUT_SOURCE_ADDR:04X}, "
            f"{len(stage_luts)} bytes"
        ),
        "trace_contract": trace_receipt,
        "key_contract": key_receipt,
        "immutable_stage_lut_sha256": lut_hashes,
        "wram_ownership_sha256": wram_hashes,
        "contracts": {
            "live_c600_palette_lut": False,
            "immutable_yaml_slot_luts": True,
            "palette_rgb_remains_yaml_owned": True,
            "direct_raw_overlay_ownership": True,
            "compiled_cells_per_dirty_publication": 440,
            "staging_bytes": 768,
            "persistent_zero_padding_per_physical_map": True,
            "bounded_gdma_blocks": 48,
            "stock_width_tile_copier": True,
            "native_tile_copier_byte_exact": True,
            "postcopy_relocation_only": True,
            "postcopy_calls_per_dirty_publication": 1,
            "expanded_key_installed_before_redirect": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
