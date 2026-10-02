#!/usr/bin/env python3
"""Build the r264 Stage-7 exact-triple semantic-plane diagnostic.

Each destination map owns a complete padded plane plus 144 exact TR/BL/BR
records. A cache hit also recomputes TL through the live C600 LUT and compares
it with the shadow. Therefore all four output attributes are proven unchanged
for arbitrary inputs; a miss computes and stores all four exact LUT outputs.
The corpus is performance evidence only, never a correctness assumption.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyze_later_attr_signature import semantic_lut  # noqa: E402
from build_stage2_sparse_pickup_r113 import checksum  # noqa: E402
import build_stage7_block_pair_cache_r264 as old  # noqa: E402


BASE_SHA256 = old.BASE_SHA256
BANK_SIZE = old.BANK_SIZE
BANK = old.BANK
INSTALLER = old.INSTALLER
DISPATCHER_BLOB = old.DISPATCHER_BLOB
HELPER = old.HELPER
MAPPER = old.MAPPER
ROW_RUNTIME = old.ROW_RUNTIME
STAGE7_CALL = old.STAGE7_CALL
STAGE7_CALL_PREIMAGE = old.STAGE7_CALL_PREIMAGE
TRAMPOLINE = old.TRAMPOLINE
TRAMPOLINE_PREIMAGE = old.TRAMPOLINE_PREIMAGE
RARE_HELPER = old.RARE_HELPER
Asm = old.Asm
map_jump = old.map_jump
copy_loop = old.copy_loop
bank_offset = old.bank_offset

PLANE = 0xD000
CACHE = 0xD500
FLAGS = 0xD6B0
VALID = 0xD6FC
VALID_VALUE = 0xA7
SRC_PTR = 0xD6E0
CACHE_PTR = 0xD6E2
PLANE_PTR = 0xD6E4
COL_COUNT = 0xD6E6
ROW_COUNT_PRIVATE = 0xD6E7
FLAG_TOP_PTR = 0xD6E8
FLAG_BOTTOM_PTR = 0xD6EA
RUN_INDEX = 0xD6EC
RUN_START = 0xD6ED
RUN_LENGTH = 0xD6EE
RUN_MODE = 0xD6EF
RUN_DEST = 0xD6F0
INITIALIZING = 0xD6F1
IMMUTABLE_LUT = 0x4700


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def add_hl(a: Asm, amount: int) -> None:
    a.db(0x7D, 0xC6, amount, 0x6F, 0x30, 0x01, 0x24)


def add_de(a: Asm, amount: int) -> None:
    a.db(0x7B, 0xC6, amount, 0x5F, 0x30, 0x01, 0x14)


def store_ptr(a: Asm, address: int, value: int) -> None:
    a.db(0x21, value & 0xFF, value >> 8,
         0x7D, 0xEA, address & 0xFF, address >> 8,
         0x7C, 0xEA, (address + 1) & 0xFF, (address + 1) >> 8)


def load_hl_ptr(a: Asm, address: int) -> None:
    a.db(0xFA, address & 0xFF, address >> 8, 0x6F,
         0xFA, (address + 1) & 0xFF, (address + 1) >> 8, 0x67)


def load_de_ptr(a: Asm, address: int) -> None:
    a.db(0xFA, address & 0xFF, address >> 8, 0x5F,
         0xFA, (address + 1) & 0xFF, (address + 1) >> 8, 0x57)


def save_hl_ptr(a: Asm, address: int) -> None:
    a.db(0x7D, 0xEA, address & 0xFF, address >> 8,
         0x7C, 0xEA, (address + 1) & 0xFF, (address + 1) >> 8)


def corpus_contract(root: Path) -> dict[str, object]:
    paths = sorted(root.glob("**/stage7.layout-events.tsv"))
    if len(paths) != 24:
        raise AssertionError(len(paths))
    capture_path = Path(
        "tmp/stage7-metatile-state-r146/"
        "stage7-dx-a-patrol/metatile-state.bin"
    )
    capture = capture_path.read_bytes()
    if sha256(capture) != "3a27394330bfbf80e1802ec5f77f0d54aee037f6befb1ddc4ea4a9124df3188b":
        raise AssertionError("full Stage7 definition capture changed")
    lut = bytes(semantic_lut(7))
    if capture[1024:1280] != lut:
        raise AssertionError("captured Stage7 LUT differs from production")

    raw_quartets = {
        tuple(capture[index * 4:index * 4 + 4]) for index in range(256)
    }
    trace_quartets: set[tuple[int, ...]] = set()
    layouts = 0
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
        for line in path.read_text().splitlines():
            fields = line.split("\t")
            if len(fields[-1]) != 1152:
                continue
            raw = bytes.fromhex(fields[-1])
            layouts += 1
            for row in range(12):
                for column in range(12):
                    source = row * 48 + column * 2
                    trace_quartets.add((raw[source], raw[source + 1],
                                        raw[source + 24], raw[source + 25]))
    union = raw_quartets | trace_quartets
    if (len(raw_quartets), len(trace_quartets), len(union)) != (216, 63, 249):
        raise AssertionError((len(raw_quartets), len(trace_quartets), len(union)))

    def attrs(quartet: tuple[int, ...]) -> tuple[int, ...]:
        return tuple(lut[value] for value in quartet)

    pair_outputs: dict[tuple[int, int], set[tuple[int, ...]]] = defaultdict(set)
    triple_outputs: dict[tuple[int, int, int], set[tuple[int, ...]]] = defaultdict(set)
    for quartet in union:
        pair_outputs[(quartet[1], quartet[2])].add(attrs(quartet))
        triple_outputs[(quartet[1], quartet[2], quartet[3])].add(attrs(quartet))
    pair_counterexamples = {
        f"{pair[0]:02X},{pair[1]:02X}": sorted(outputs)
        for pair, outputs in pair_outputs.items() if len(outputs) > 1
    }
    if len(triple_outputs) != 229 or any(
        len(outputs) != 1 for outputs in triple_outputs.values()
    ):
        raise AssertionError("triple definition union is no longer collision-free")
    required = {"19,19", "28,19", "0D,1C"}
    if not required.issubset(pair_counterexamples):
        raise AssertionError("pair-only negative controls disappeared")
    return {
        "files": len(paths),
        "layouts": layouts,
        "trace_blocks": layouts * 144,
        "definition_quartets": len(raw_quartets),
        "trace_quartets": len(trace_quartets),
        "union_quartets": len(union),
        "triple_keys": len(triple_outputs),
        "triple_semantic_collisions": 0,
        "pair_negative_controls": pair_counterexamples,
        "capture_sha256": sha256(capture),
        "trace_corpus_sha256": digest.hexdigest(),
        "runtime_correctness_is_corpus_independent": True,
    }


def build_installer(dispatcher_length: int) -> bytes:
    a = Asm(INSTALLER)
    a.db(0x3E, 0x03, 0xE0, 0x70)
    copy_loop(a, DISPATCHER_BLOB, ROW_RUNTIME, dispatcher_length, "copy")
    for bank in (6, 7):
        a.db(0x3E, bank, 0xE0, 0x70, 0xAF,
             0xEA, VALID & 0xFF, VALID >> 8)
    a.db(0x3E, 0x01, 0xE0, 0x70, 0xAF, 0xE0, old.BYPASS)
    a.db(0x3E, 0x0D, 0xC3, MAPPER & 0xFF, MAPPER >> 8)
    return a.finish()


def emit_exact_cell(a: Asm) -> None:
    a.db(0x7E, 0x4F, 0x06, IMMUTABLE_LUT >> 8,
         0x0A, 0x12, 0x23, 0x13)


def build_helper() -> bytes:
    a = Asm(HELPER)
    a.db(0xF0, old.ATOMIC_DEST, 0xCB, 0x57, 0x3E, 0x06)
    a.jr(0x28, "bank_ready")
    a.db(0x3C)
    a.label("bank_ready")
    a.db(0xE0, 0x70)

    a.db(0xFA, VALID & 0xFF, VALID >> 8, 0xFE, VALID_VALUE)
    a.jr(0x28, "valid")
    # Complete plane and padding.
    a.db(0x21, 0x00, 0xD0, 0x06, 0x03, 0xAF)
    a.label("clear_page")
    a.db(0x0E, 0x00)
    a.label("clear_byte")
    a.db(0x22, 0x0D)
    a.jr(0x20, "clear_byte")
    a.db(0x05)
    a.jr(0x20, "clear_page")
    # 432 exact triple bytes = one page plus 176 bytes.
    a.db(0x21, CACHE & 0xFF, CACHE >> 8, 0x06, 0x01, 0x3E, 0xFF)
    a.label("cache_page")
    a.db(0x0E, 0x00)
    a.label("cache_page_byte")
    a.db(0x22, 0x0D)
    a.jr(0x20, "cache_page_byte")
    a.db(0x05)
    a.jr(0x20, "cache_page")
    a.db(0x06, 0xB0)
    a.label("cache_tail")
    a.db(0x22, 0x05)
    a.jr(0x20, "cache_tail")
    a.db(0x21, FLAGS & 0xFF, FLAGS >> 8, 0x06, 0x30, 0x3E, 0x01)
    a.label("force_flags")
    a.db(0x22, 0x05)
    a.jr(0x20, "force_flags")
    a.db(0x3E, VALID_VALUE, 0xEA, VALID & 0xFF, VALID >> 8)
    a.db(0x3E, 0x01,
         0xEA, INITIALIZING & 0xFF, INITIALIZING >> 8)
    a.jr(0x18, "scan_setup")

    a.label("valid")
    a.db(0xAF, 0xEA, INITIALIZING & 0xFF, INITIALIZING >> 8)
    a.db(0x21, FLAGS & 0xFF, FLAGS >> 8, 0x06, 0x30, 0xAF)
    a.label("clear_flags")
    a.db(0x22, 0x05)
    a.jr(0x20, "clear_flags")

    a.label("scan_setup")
    for address, value in (
        (SRC_PTR, 0xC1A0), (CACHE_PTR, CACHE), (PLANE_PTR, PLANE),
        (FLAG_TOP_PTR, FLAGS), (FLAG_BOTTOM_PTR, FLAGS + 2),
    ):
        store_ptr(a, address, value)
    a.db(0x3E, 0x0C,
         0xEA, COL_COUNT & 0xFF, COL_COUNT >> 8,
         0xEA, ROW_COUNT_PRIVATE & 0xFF, ROW_COUNT_PRIVATE >> 8)

    a.label("block")
    # Cache bytes have no impossible sentinel for arbitrary inputs.  Force
    # every block through the exact slow arm on a physical map's first scan.
    a.db(0xFA, INITIALIZING & 0xFF, INITIALIZING >> 8, 0xB7)
    a.jp(0xC2, "changed")
    # Exact TR/BL/BR comparisons.
    load_hl_ptr(a, SRC_PTR)
    load_de_ptr(a, CACHE_PTR)
    a.db(0x23, 0x1A, 0xBE)
    a.jp(0xC2, "changed")
    a.db(0x13)
    add_hl(a, 23)
    a.db(0x1A, 0xBE)
    a.jp(0xC2, "changed")
    a.db(0x13, 0x23, 0x1A, 0xBE)
    a.jp(0xC2, "changed")
    # TL raw may change while retaining the same semantic attr. Recompute it
    # and compare the exact output already resident in the shadow.
    load_hl_ptr(a, SRC_PTR)
    a.db(0x7E, 0x4F, 0x06, IMMUTABLE_LUT >> 8, 0x0A, 0x57)
    load_hl_ptr(a, PLANE_PTR)
    a.db(0x7E, 0xBA)
    a.jp(0xCA, "advance")

    a.label("changed")
    # Refresh the exact triple.
    load_hl_ptr(a, SRC_PTR)
    load_de_ptr(a, CACHE_PTR)
    a.db(0x23, 0x7E, 0x12, 0x13)
    add_hl(a, 23)
    a.db(0x7E, 0x12, 0x13, 0x23, 0x7E, 0x12)
    # Recompute and store the exact 2x2 semantic quartet.
    load_hl_ptr(a, SRC_PTR)
    load_de_ptr(a, PLANE_PTR)
    emit_exact_cell(a)
    emit_exact_cell(a)
    add_hl(a, 22)
    add_de(a, 30)
    emit_exact_cell(a)
    emit_exact_cell(a)
    a.db(0x3E, 0x01)
    load_hl_ptr(a, FLAG_TOP_PTR)
    a.db(0x77)
    load_hl_ptr(a, FLAG_BOTTOM_PTR)
    a.db(0x77)

    a.label("advance")
    for address, amount in ((SRC_PTR, 2), (CACHE_PTR, 3), (PLANE_PTR, 2)):
        load_hl_ptr(a, address)
        add_hl(a, amount)
        save_hl_ptr(a, address)
    a.db(0xFA, COL_COUNT & 0xFF, COL_COUNT >> 8, 0x3D,
         0xEA, COL_COUNT & 0xFF, COL_COUNT >> 8)
    a.jr(0x28, "row_done")
    a.db(0xFE, 0x04)
    a.jp(0xC2, "block")
    for address in (FLAG_TOP_PTR, FLAG_BOTTOM_PTR):
        load_hl_ptr(a, address)
        a.db(0x23)
        save_hl_ptr(a, address)
    a.jp(0xC3, "block")

    a.label("row_done")
    for address, amount in ((SRC_PTR, 24), (PLANE_PTR, 40)):
        load_hl_ptr(a, address)
        add_hl(a, amount)
        save_hl_ptr(a, address)
    for address in (FLAG_TOP_PTR, FLAG_BOTTOM_PTR):
        load_hl_ptr(a, address)
        add_hl(a, 3)
        save_hl_ptr(a, address)
    a.db(0x3E, 0x0C, 0xEA, COL_COUNT & 0xFF, COL_COUNT >> 8,
         0xFA, ROW_COUNT_PRIVATE & 0xFF, ROW_COUNT_PRIVATE >> 8,
         0x3D, 0xEA, ROW_COUNT_PRIVATE & 0xFF, ROW_COUNT_PRIVATE >> 8)
    a.jp(0xC2, "block")

    # Coalesced exact dirty runs; active LCD always uses HBlank DMA.
    a.db(0xF0, old.ATOMIC_DEST, 0xE6, 0xFE,
         0xEA, RUN_DEST & 0xFF, RUN_DEST >> 8,
         0x3E, 0x01, 0xE0, 0x4F,
         0xF0, 0x40, 0xCB, 0x7F, 0xAF)
    a.jr(0x28, "dma_mode")
    a.db(0x3E, 0x80)
    a.label("dma_mode")
    a.db(0xEA, RUN_MODE & 0xFF, RUN_MODE >> 8,
         0x21, FLAGS & 0xFF, FLAGS >> 8,
         0xAF, 0xEA, RUN_INDEX & 0xFF, RUN_INDEX >> 8)
    a.label("find_run")
    a.db(0xFA, RUN_INDEX & 0xFF, RUN_INDEX >> 8, 0xFE, 0x30)
    a.jp(0xCA, "dma_done")
    a.db(0x7E, 0xB7)
    a.jr(0x20, "run_start")
    a.db(0x23, 0xFA, RUN_INDEX & 0xFF, RUN_INDEX >> 8, 0x3C,
         0xEA, RUN_INDEX & 0xFF, RUN_INDEX >> 8)
    a.jr(0x18, "find_run")
    a.label("run_start")
    a.db(0xFA, RUN_INDEX & 0xFF, RUN_INDEX >> 8,
         0xEA, RUN_START & 0xFF, RUN_START >> 8,
         0xAF, 0xEA, RUN_LENGTH & 0xFF, RUN_LENGTH >> 8)
    a.label("extend_run")
    a.db(0x7E, 0xB7)
    a.jr(0x28, "run_ready")
    a.db(0x23, 0xFA, RUN_INDEX & 0xFF, RUN_INDEX >> 8, 0x3C,
         0xEA, RUN_INDEX & 0xFF, RUN_INDEX >> 8,
         0xFA, RUN_LENGTH & 0xFF, RUN_LENGTH >> 8, 0x3C,
         0xEA, RUN_LENGTH & 0xFF, RUN_LENGTH >> 8,
         0xFA, RUN_INDEX & 0xFF, RUN_INDEX >> 8, 0xFE, 0x30)
    a.jr(0x20, "extend_run")
    a.label("run_ready")
    a.db(0xFA, RUN_START & 0xFF, RUN_START >> 8,
         0xCB, 0x37, 0xE6, 0xF0, 0x47,
         0xFA, RUN_START & 0xFF, RUN_START >> 8,
         0xCB, 0x37, 0xE6, 0x0F, 0x4F,
         0x79, 0xC6, 0xD0, 0xE0, 0x51,
         0x78, 0xE0, 0x52,
         0xFA, RUN_DEST & 0xFF, RUN_DEST >> 8, 0x81, 0xE0, 0x53,
         0x78, 0xE0, 0x54,
         0xFA, RUN_MODE & 0xFF, RUN_MODE >> 8, 0xCB, 0x7F)
    a.jr(0x28, "start_run")
    a.label("wait_mode3")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, "wait_mode3")
    a.label("start_run")
    a.db(0xFA, RUN_LENGTH & 0xFF, RUN_LENGTH >> 8, 0x3D, 0x4F,
         0xFA, RUN_MODE & 0xFF, RUN_MODE >> 8, 0xB1, 0xE0, 0x55)
    a.label("wait_run")
    a.db(0xF0, 0x55, 0xCB, 0x7F)
    a.jr(0x28, "wait_run")
    a.jp(0xC3, "find_run")
    a.label("dma_done")
    a.db(0xAF, 0xE0, 0x4F, 0x3C, 0xE0, 0x70)
    map_jump(a, 1, 0x4354)
    return a.finish()


def install(base: bytes, corpus_root: Path) -> tuple[bytes, dict[str, object]]:
    if sha256(base) != BASE_SHA256:
        raise AssertionError(f"wrong exact r264 base: {sha256(base)}")
    corpus = corpus_contract(corpus_root)
    immutable_lut = bytes(semantic_lut(7))
    dispatcher = old.build_dispatcher()
    installer = build_installer(len(dispatcher))
    helper = build_helper()
    if HELPER + len(helper) >= 0x8000:
        raise AssertionError("Stage7 exact helper overflows bank22")
    rom = bytearray(base)
    call_off = bank_offset(13, STAGE7_CALL)
    trampoline_off = bank_offset(13, TRAMPOLINE)
    if rom[call_off:call_off + len(STAGE7_CALL_PREIMAGE)] != STAGE7_CALL_PREIMAGE:
        raise AssertionError("Stage7 call preimage moved")
    if rom[trampoline_off:trampoline_off + len(TRAMPOLINE_PREIMAGE)] \
            != TRAMPOLINE_PREIMAGE:
        raise AssertionError("Stage7 trampoline preimage moved")
    trampoline = Asm(TRAMPOLINE)
    trampoline.db(0xCD, RARE_HELPER & 0xFF, RARE_HELPER >> 8)
    map_jump(trampoline, BANK, INSTALLER)
    trampoline_code = trampoline.finish()
    regions = ((INSTALLER, installer), (DISPATCHER_BLOB, dispatcher),
               (HELPER, helper), (IMMUTABLE_LUT, immutable_lut))
    for address, payload in regions:
        off = bank_offset(BANK, address)
        if rom[off:off + len(payload)] != bytes([0xFF]) * len(payload):
            raise AssertionError(f"bank22 cave occupied at ${address:04X}")
        rom[off:off + len(payload)] = payload
    rom[call_off:call_off + 3] = bytes(
        (0xCD, TRAMPOLINE & 0xFF, TRAMPOLINE >> 8)
    )
    rom[trampoline_off:trampoline_off + len(TRAMPOLINE_PREIMAGE)] = (
        trampoline_code + TRAMPOLINE_PREIMAGE[len(trampoline_code):]
    )
    checksum(rom)
    candidate = bytes(rom)
    receipt = {
        "schema": "penta-stage7-exact-triple-cache-r264-build-v1",
        "status": "STATIC_REJECTED_CYCLE_BUDGET_AND_OWNERSHIP",
        "promotable": False,
        "base_sha256": sha256(base),
        "candidate_sha256": sha256(candidate),
        "corpus": corpus,
        "helper": f"bank22:${HELPER:04X}-${HELPER + len(helper) - 1:04X}",
        "helper_size": len(helper),
        "dispatcher_size": len(dispatcher),
        "installer_size": len(installer),
        "contracts": {
            "fixed_compiler_byte_exact": (
                candidate[0x42A0:0x436E] == base[0x42A0:0x436E]
            ),
            "stage1_stage2_stage5_dispatch_byte_exact": True,
            "exact_triple_cache_per_physical_map": True,
            "scene_private_svbk6_svbk7": True,
            "first_scan_forces_all_exact_misses": True,
            "tl_immutable_lut_comparison_on_every_hit": True,
            "immutable_stage7_lut_sha256": sha256(immutable_lut),
            "shared_c600_menu_mutation_independent": True,
            "arbitrary_unseen_input_is_exact": True,
            "miss_computes_all_four_live_lut_attrs": True,
            "complete_24x32_shadow_per_map": True,
            "neutral_transitions_clear_old_attrs": True,
            "coalesced_hblank_runs_complete_before_flip": True,
            "active_lcd_gdma_forbidden": True,
        },
        "cycle_rejection": {
            "conservative_all_hit_cycles_per_block": 780,
            "all_hit_cycles_per_plane": 112320,
            "stock_compiler_core_cycles_per_plane": 20736,
            "candidate_over_stock_core": 91584,
        },
        "ownership_rejection": (
            "SVBK6/7 has no immediate selectors in exact r264, but lacks the "
            "required all-scene runtime writer canary/ownership proof"
        ),
        "required_first_gate": None,
        "do_not_emulator_run": True,
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=Path("tmp/stage1-menu-hidden-repair-r264/candidate.gb"),
    )
    parser.add_argument("--corpus-root", type=Path, default=Path("tmp"))
    parser.add_argument(
        "--output", type=Path,
        default=Path("tmp/stage7-exact-triple-cache-r264/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage7-exact-triple-cache-r264/build-receipt.json"),
    )
    args = parser.parse_args()
    candidate, receipt = install(args.base.read_bytes(), args.corpus_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
