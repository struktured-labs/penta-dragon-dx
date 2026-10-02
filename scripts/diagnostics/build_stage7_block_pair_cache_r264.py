#!/usr/bin/env python3
"""Build an isolated r264 Stage-7 complete two-map block-cache candidate.

Only the established Stage-7 scene-entry branch installs the private D400
dispatcher.  Stage 1, Stage 2, Stage 5, and the fixed compiler are unchanged.
The Stage-7 helper scans the completed 24x24 C1A0 source as 12x12 blocks,
updates a destination-owned padded plane, and publishes exact changed 16-byte
blocks before the stock map flip.  Unknown block pairs invalidate that map's
cache and restart the untouched full compiler through a one-shot bypass.
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


BASE_SHA256 = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
BANK_SIZE = 0x4000
BANK = 22
INSTALLER = 0x4100
DISPATCHER_BLOB = 0x4200
HELPER = 0x4300
MULT_TABLE = 0x7300
HASH_TOP = 0x7400
HASH_BOTTOM = 0x7500
HASH_CLASS = 0x7600
QUARTETS = 0x7700

MAPPER = 0x0061
ROW_RUNTIME = 0xD400
ROW_TEMP = 0xD47E
BYPASS = 0xE7
ROW_COUNT = 0xE0
ATOMIC_DEST = 0xA5

PLANE = 0xD000
CACHE = 0xD300
FLAGS = 0xD390
VALID = 0xD3FC
VALID_VALUE = 0xA7
RUN_INDEX = 0xD3C0
RUN_START = 0xD3C1
RUN_LENGTH = 0xD3C2
RUN_MODE = 0xD3C3
RUN_DEST = 0xD3C4

STAGE7_CALL = 0x5407
STAGE7_CALL_PREIMAGE = bytes.fromhex("CD 9C 54 C3 22 54")
TRAMPOLINE = 0x6ED3
TRAMPOLINE_PREIMAGE = bytes.fromhex("18 00") * 12 + bytes(9)
RARE_HELPER = 0x549C


def bank_offset(bank: int, address: int) -> int:
    if not 0x4000 <= address < 0x8000:
        raise AssertionError(address)
    return bank * BANK_SIZE + address - 0x4000


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Asm:
    def __init__(self, base: int) -> None:
        self.base = base
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, str]] = []

    def db(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise AssertionError(name)
        self.labels[name] = self.base + len(self.code)

    def jr(self, opcode: int, label: str) -> None:
        self.db(opcode, 0)
        self.fixups.append((len(self.code) - 1, label, "jr"))

    def jp(self, opcode: int, label: str) -> None:
        self.db(opcode, 0, 0)
        self.fixups.append((len(self.code) - 2, label, "jp"))

    def finish(self) -> bytes:
        for operand, label, kind in self.fixups:
            target = self.labels[label]
            if kind == "jr":
                delta = target - (self.base + operand + 1)
                if not -128 <= delta <= 127:
                    raise AssertionError((label, delta))
                self.code[operand] = delta & 0xFF
            else:
                self.code[operand:operand + 2] = target.to_bytes(2, "little")
        return bytes(self.code)


def map_jump(a: Asm, bank: int, destination: int) -> None:
    a.db(0x01, destination & 0xFF, destination >> 8, 0xC5,
         0x3E, bank, 0xC3, MAPPER & 0xFF, MAPPER >> 8)


def copy_loop(a: Asm, source: int, destination: int,
              length: int, label: str) -> None:
    if not 0 < length <= 0xFF:
        raise AssertionError(length)
    a.db(0x21, source & 0xFF, source >> 8,
         0x11, destination & 0xFF, destination >> 8,
         0x06, length)
    a.label(label)
    a.db(0x2A, 0x12, 0x13, 0x05)
    a.jr(0x20, label)


def corpus_tables(root: Path) -> tuple[dict[str, object], bytes, bytes, bytes,
                                       bytes, bytes]:
    paths = sorted(root.glob("**/stage7.layout-events.tsv"))
    if len(paths) != 24:
        raise AssertionError(f"expected 24 Stage7 corpus files, got {len(paths)}")
    lut = bytes(semantic_lut(7))
    pair_outputs: dict[tuple[int, int], set[tuple[int, ...]]] = defaultdict(set)
    top_outputs: dict[int, set[tuple[int, ...]]] = defaultdict(set)
    bottom_outputs: dict[int, set[tuple[int, ...]]] = defaultdict(set)
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
                    pair = (raw[source + 1], raw[source + 24])
                    quartet = (lut[raw[source]], lut[raw[source + 1]],
                               lut[raw[source + 24]], lut[raw[source + 25]])
                    pair_outputs[pair].add(quartet)
                    top_outputs[pair[0]].add(quartet)
                    bottom_outputs[pair[1]].add(quartet)
    if layouts != 1645 or len(pair_outputs) != 52:
        raise AssertionError((layouts, len(pair_outputs)))
    if any(len(outputs) != 1 for outputs in pair_outputs.values()):
        raise AssertionError("pair signature collision")
    top_collisions = sum(len(v) - 1 for v in top_outputs.values())
    bottom_collisions = sum(len(v) - 1 for v in bottom_outputs.values())
    if not top_collisions or not bottom_collisions:
        raise AssertionError("single-tile negative control disappeared")

    unique_quartets = sorted({next(iter(v)) for v in pair_outputs.values()})
    if len(unique_quartets) > 0x7F:
        raise AssertionError("class IDs no longer fit below unknown bit")
    class_ids = {quartet: index for index, quartet in enumerate(unique_quartets)}
    mult = bytes((38 * value) & 0xFF for value in range(256))
    tops = bytearray([0xFF] * 256)
    bottoms = bytearray([0xFF] * 256)
    classes = bytearray([0xFF] * 256)
    hashes: set[int] = set()
    for pair, outputs in pair_outputs.items():
        hashed = (pair[0] + 38 * pair[1]) & 0xFF
        if hashed in hashes:
            raise AssertionError("perfect hash collision")
        hashes.add(hashed)
        tops[hashed], bottoms[hashed] = pair
        classes[hashed] = class_ids[next(iter(outputs))]
    quartets = b"".join(bytes(q) for q in unique_quartets)
    report = {
        "files": len(paths),
        "layouts": layouts,
        "blocks": layouts * 144,
        "observed_pairs": len(pair_outputs),
        "semantic_classes": len(unique_quartets),
        "pair_collisions": 0,
        "hash_collisions": 0,
        "top_only_collisions": top_collisions,
        "bottom_only_collisions": bottom_collisions,
        "sha256": digest.hexdigest(),
    }
    return report, mult, bytes(tops), bytes(bottoms), bytes(classes), quartets


def original_row_helper_compact(a: Asm, label: str) -> None:
    a.db(0x3E, 0x18, 0xEA, ROW_TEMP & 0xFF, ROW_TEMP >> 8)
    a.label(label)
    a.db(0x1A, 0x13, 0x4F, 0x0A, 0x22,
         0xFA, ROW_TEMP & 0xFF, ROW_TEMP >> 8,
         0x3D, 0xEA, ROW_TEMP & 0xFF, ROW_TEMP >> 8)
    a.jr(0x20, label)


def build_dispatcher() -> bytes:
    a = Asm(ROW_RUNTIME)
    # This blob exists only during Stage7, but every predicate is retained so
    # stale/direct transitions fail to the exact original row semantics.
    a.db(0xF0, 0xBA, 0xFE, 0x06)
    a.jr(0x20, "original")
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x08)
    a.jr(0x20, "original")
    a.db(0xF0, BYPASS, 0xB7)
    a.jr(0x20, "bypass")
    a.db(0xF0, ROW_COUNT, 0xFE, 0x18)
    a.jr(0x20, "original")
    a.db(0xC1)  # discard CALL $D400 return; helper owns compiler completion
    map_jump(a, BANK, HELPER)

    a.label("bypass")
    original_row_helper_compact(a, "bypass_cell")
    # Clear the one-shot restart flag only after the 24th original row.
    a.db(0xF0, ROW_COUNT, 0xFE, 0x01)
    a.jr(0x20, "return")
    a.db(0xAF, 0xE0, BYPASS)
    a.label("return")
    a.db(0xC9)

    a.label("original")
    original_row_helper_compact(a, "original_cell")
    a.db(0xC9)
    code = a.finish()
    if len(code) > 0x100:
        raise AssertionError(len(code))
    return code


def build_installer(dispatcher_length: int) -> bytes:
    a = Asm(INSTALLER)
    a.db(0x3E, 0x03, 0xE0, 0x70)
    copy_loop(a, DISPATCHER_BLOB, ROW_RUNTIME, dispatcher_length, "copy")
    # Both destination-owned caches start invalid. The helper initializes the
    # complete plane and all 48 publication blocks on first use.
    for bank in (2, 3):
        a.db(0x3E, bank, 0xE0, 0x70, 0xAF,
             0xEA, VALID & 0xFF, VALID >> 8)
    a.db(0x3E, 0x01, 0xE0, 0x70, 0xAF, 0xE0, BYPASS)
    # The bank-13 trampoline was entered by CALL; mapper RET consumes that
    # untouched return and resumes the exact dispatcher continuation.
    a.db(0x3E, 0x0D, 0xC3, MAPPER & 0xFF, MAPPER >> 8)
    return a.finish()


def build_helper() -> bytes:
    a = Asm(HELPER)
    # Select the persistent plane/cache belonging to the exact tagged map.
    a.db(0xF0, ATOMIC_DEST, 0xCB, 0x57, 0x3E, 0x02)
    a.jr(0x28, "bank_ready")
    a.db(0x3C)
    a.label("bank_ready")
    a.db(0xE0, 0x70)

    # Initialize D000-D3BF, then turn D300-D38F into invalid class IDs and
    # force all 48 blocks for a physical map's first publication.
    a.db(0xFA, VALID & 0xFF, VALID >> 8, 0xFE, VALID_VALUE)
    a.jr(0x28, "valid")
    a.db(0x21, 0x00, 0xD0, 0x06, 0x03, 0xAF)
    a.label("clear_page")
    a.db(0x0E, 0x00)
    a.label("clear_byte")
    a.db(0x22, 0x0D)
    a.jr(0x20, "clear_byte")
    a.db(0x05)
    a.jr(0x20, "clear_page")
    a.db(0x21, CACHE & 0xFF, CACHE >> 8, 0x06, 0x90, 0x3E, 0xFF)
    a.label("invalidate_cache")
    a.db(0x22, 0x05)
    a.jr(0x20, "invalidate_cache")
    a.db(0x21, FLAGS & 0xFF, FLAGS >> 8, 0x06, 0x30, 0x3E, 0x01)
    a.label("force_flags")
    a.db(0x22, 0x05)
    a.jr(0x20, "force_flags")
    a.db(0x3E, VALID_VALUE, 0xEA, VALID & 0xFF, VALID >> 8)
    a.jr(0x18, "scan")

    a.label("valid")
    a.db(0x21, FLAGS & 0xFF, FLAGS >> 8, 0x06, 0x30, 0xAF)
    a.label("clear_flags")
    a.db(0x22, 0x05)
    a.jr(0x20, "clear_flags")

    a.label("scan")
    for row in range(12):
        for column in range(12):
            number = row * 12 + column
            source = 0xC1A0 + row * 48 + column * 2
            cache = CACHE + number
            output = PLANE + row * 64 + column * 2
            half = 0 if column < 8 else 1
            flag_a = FLAGS + row * 4 + half
            flag_b = FLAGS + row * 4 + 2 + half
            done = f"block_{number}_done"
            # D/E retain the exact observed pair for fail-closed hash lookup.
            a.db(0xFA, (source + 1) & 0xFF, (source + 1) >> 8, 0x57,
                 0xFA, (source + 24) & 0xFF, (source + 24) >> 8, 0x5F,
                 0x4F, 0x06, MULT_TABLE >> 8, 0x0A, 0x82, 0x4F,
                 0x06, HASH_TOP >> 8, 0x0A, 0xBA)
            a.jp(0xC2, "unknown")
            a.db(0x06, HASH_BOTTOM >> 8, 0x0A, 0xBB)
            a.jp(0xC2, "unknown")
            a.db(0x06, HASH_CLASS >> 8, 0x0A,
                 0x21, cache & 0xFF, cache >> 8, 0xBE)
            a.jr(0x28, done)
            a.db(0x77, 0x87, 0x87, 0x6F, 0x26, 0x00,
                 0x11, QUARTETS & 0xFF, QUARTETS >> 8, 0x19,
                 0x2A, 0xEA, output & 0xFF, output >> 8,
                 0x2A, 0xEA, (output + 1) & 0xFF, (output + 1) >> 8,
                 0x2A, 0xEA, (output + 32) & 0xFF, (output + 32) >> 8,
                 0x7E, 0xEA, (output + 33) & 0xFF, (output + 33) >> 8,
                 0x3E, 0x01,
                 0xEA, flag_a & 0xFF, flag_a >> 8,
                 0xEA, flag_b & 0xFF, flag_b >> 8)
            a.label(done)
    a.jp(0xC3, "publish")

    a.label("unknown")
    # No VRAM write has occurred. Discard the partial private shadow, arm the
    # D400 byte-exact bypass, and restart the untouched compiler at $42FC.
    a.db(0xAF, 0xEA, VALID & 0xFF, VALID >> 8,
         0x3C, 0xE0, BYPASS,
         0x3E, 0x01, 0xE0, 0x70)
    map_jump(a, 1, 0x42FC)

    a.label("publish")
    # Coalesce adjacent dirty blocks into one bounded DMA run. This does not
    # weaken atomicity: every run still completes before the native map flip,
    # and active-LCD commands retain bit 7 (HBlank mode).
    a.db(0xF0, ATOMIC_DEST, 0xE6, 0xFE,
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
    a.db(0x23, 0xFA, RUN_INDEX & 0xFF, RUN_INDEX >> 8,
         0x3C, 0xEA, RUN_INDEX & 0xFF, RUN_INDEX >> 8)
    a.jr(0x18, "find_run")

    a.label("run_start")
    a.db(0xFA, RUN_INDEX & 0xFF, RUN_INDEX >> 8,
         0xEA, RUN_START & 0xFF, RUN_START >> 8,
         0xAF, 0xEA, RUN_LENGTH & 0xFF, RUN_LENGTH >> 8)
    a.label("extend_run")
    a.db(0x7E, 0xB7)
    a.jr(0x28, "run_ready")
    a.db(0x23,
         0xFA, RUN_INDEX & 0xFF, RUN_INDEX >> 8,
         0x3C, 0xEA, RUN_INDEX & 0xFF, RUN_INDEX >> 8,
         0xFA, RUN_LENGTH & 0xFF, RUN_LENGTH >> 8,
         0x3C, 0xEA, RUN_LENGTH & 0xFF, RUN_LENGTH >> 8,
         0xFA, RUN_INDEX & 0xFF, RUN_INDEX >> 8, 0xFE, 0x30)
    a.jr(0x20, "extend_run")

    a.label("run_ready")
    # SWAP isolates both start nibbles: low*16 is HDMA2/4 and high is the
    # source/destination page increment.
    a.db(0xFA, RUN_START & 0xFF, RUN_START >> 8,
         0xCB, 0x37, 0xE6, 0xF0, 0x47,
         0xFA, RUN_START & 0xFF, RUN_START >> 8,
         0xCB, 0x37, 0xE6, 0x0F, 0x4F,
         0x79, 0xC6, 0xD0, 0xE0, 0x51,
         0x78, 0xE0, 0x52,
         0xFA, RUN_DEST & 0xFF, RUN_DEST >> 8,
         0x81, 0xE0, 0x53,
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
    a.db(0xAF, 0xE0, 0x4F,
         0x3C, 0xE0, 0x70)
    map_jump(a, 1, 0x4354)
    return a.finish()


def install(base: bytes, corpus_root: Path) -> tuple[bytes, dict[str, object]]:
    if sha256(base) != BASE_SHA256:
        raise AssertionError(f"wrong exact r264 base: {sha256(base)}")
    corpus, mult, tops, bottoms, classes, quartets = corpus_tables(corpus_root)
    dispatcher = build_dispatcher()
    installer = build_installer(len(dispatcher))
    helper = build_helper()
    if HELPER + len(helper) > MULT_TABLE:
        raise AssertionError(
            f"helper overlaps tables: ${HELPER + len(helper):04X} > ${MULT_TABLE:04X}"
        )

    rom = bytearray(base)
    call_off = bank_offset(13, STAGE7_CALL)
    if rom[call_off:call_off + len(STAGE7_CALL_PREIMAGE)] != STAGE7_CALL_PREIMAGE:
        raise AssertionError("Stage7 rare-helper call preimage moved")
    trampoline_off = bank_offset(13, TRAMPOLINE)
    if rom[trampoline_off:trampoline_off + len(TRAMPOLINE_PREIMAGE)] \
            != TRAMPOLINE_PREIMAGE:
        raise AssertionError("Stage7 trampoline record preimage moved")

    trampoline = Asm(TRAMPOLINE)
    trampoline.db(0xCD, RARE_HELPER & 0xFF, RARE_HELPER >> 8)
    map_jump(trampoline, BANK, INSTALLER)
    trampoline_code = trampoline.finish()
    if len(trampoline_code) > len(TRAMPOLINE_PREIMAGE):
        raise AssertionError("Stage7 trampoline overflow")

    regions = (
        (INSTALLER, installer),
        (DISPATCHER_BLOB, dispatcher),
        (HELPER, helper),
        (MULT_TABLE, mult),
        (HASH_TOP, tops),
        (HASH_BOTTOM, bottoms),
        (HASH_CLASS, classes),
        (QUARTETS, quartets),
    )
    for address, payload in regions:
        off = bank_offset(BANK, address)
        if rom[off:off + len(payload)] != bytes([0xFF]) * len(payload):
            raise AssertionError(f"bank22 cave not erased at ${address:04X}")
        rom[off:off + len(payload)] = payload

    rom[call_off:call_off + 3] = bytes(
        (0xCD, TRAMPOLINE & 0xFF, TRAMPOLINE >> 8)
    )
    rom[trampoline_off:trampoline_off + len(TRAMPOLINE_PREIMAGE)] = (
        trampoline_code
        + TRAMPOLINE_PREIMAGE[len(trampoline_code):]
    )
    checksum(rom)
    candidate = bytes(rom)

    changed = [i for i, (before, after) in enumerate(zip(base, candidate))
               if before != after]
    protected = [(0x42A0, 0x436E),
                 (bank_offset(13, 0x53E0), bank_offset(13, 0x5407))]
    if any(start <= index < end for index in changed for start, end in protected):
        raise AssertionError("candidate changed protected compiler/dispatcher bytes")
    receipt = {
        "schema": "penta-stage7-block-pair-cache-r264-build-v1",
        "status": "STATIC_PASS_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": sha256(base),
        "candidate_sha256": sha256(candidate),
        "changed_bytes_including_checksums": len(changed),
        "corpus": corpus,
        "helper": f"bank22:${HELPER:04X}-${HELPER + len(helper) - 1:04X}",
        "helper_size": len(helper),
        "dispatcher_size": len(dispatcher),
        "installer_size": len(installer),
        "trampoline": "bank13:$6ED3 calls original $549C then bank22:$4100",
        "contracts": {
            "fixed_bank1_compiler_byte_exact": True,
            "stage1_stage2_stage5_dispatch_byte_exact": True,
            "stage7_original_rare_helper_called_first": True,
            "scene7_only_runtime_install": True,
            "destination_owned_svbk2_svbk3_planes": True,
            "complete_24x24_source_and_24x32_plane": True,
            "unknown_pair_restarts_untouched_full_compiler": True,
            "unknown_restart_is_one_shot": True,
            "initial_map_publishes_48_blocks": True,
            "later_map_publishes_exact_changed_blocks": True,
            "active_lcd_gdma_forbidden": True,
            "mapper_stack_return_abi_preserved": True,
        },
        "required_first_gate": (
            "Stage7 target6/right/2800 strict speed plus route-distance contract"
        ),
        "required_visual_gates_after_speed": [
            "Stage7 8000-frame four-room display/semantic soak interval1",
            "Stage7 patrol and stationary semantic fingerprints",
            "Stage7 menu/pickup interaction and map-flip trail audit",
            "Stage1 exact menu/item/low-health/north containment",
            "Stage2 semantic soak and strict speed containment",
            "Stage5 strict speed/semantic containment",
            "Pocket and MiSTer HBlank hardware audit",
        ],
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
        default=Path("tmp/stage7-block-pair-cache-r264/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage7-block-pair-cache-r264/build-receipt.json"),
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
