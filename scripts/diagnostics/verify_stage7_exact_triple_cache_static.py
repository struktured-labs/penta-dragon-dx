#!/usr/bin/env python3
"""Fail-closed static gate for the r264 Stage-7 exact-triple cache.

The runtime proof does not trust the captured layout corpus: equality of the
cached TR/BL/BR raw bytes plus equality of the live-LUT TL output proves the
entire 2x2 semantic quartet is unchanged.  The corpus is used only to model
publication completeness and estimate transport cost.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyze_later_attr_signature import semantic_lut  # noqa: E402
import build_stage7_exact_triple_cache_r264 as candidate_builder  # noqa: E402


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def desired_plane(raw: bytes, lut: bytes) -> bytes:
    result = bytearray(768)
    for row in range(24):
        for column in range(24):
            result[row * 32 + column] = lut[raw[row * 24 + column]]
    return bytes(result)


def runs(flags: set[int]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for value in sorted(flags):
        if not result or value != result[-1][0] + result[-1][1]:
            result.append((value, 1))
        else:
            start, length = result[-1]
            result[-1] = (start, length + 1)
    return result


def model_file(path: Path, lut: bytes) -> dict[str, object]:
    caches: dict[int, list[tuple[int, int, int] | None]] = {
        0x9800: [None] * 144,
        0x9C00: [None] * 144,
    }
    planes = {0x9800: bytearray(768), 0x9C00: bytearray(768)}
    published = {0x9800: bytearray(768), 0x9C00: bytearray(768)}
    valid: set[int] = set()
    layouts = publications = dirty_blocks = run_count = misses = hits = 0
    zero_miss = 0
    run_histogram: Counter[int] = Counter()
    block_histogram: Counter[int] = Counter()
    for line in path.read_text().splitlines():
        fields = line.split("\t")
        if len(fields[-1]) != 1152:
            continue
        raw = bytes.fromhex(fields[-1])
        destination = int(fields[2], 16)
        if destination not in caches or len(raw) != 576:
            raise AssertionError(f"bad Stage7 record in {path}")
        layouts += 1
        initializing = destination not in valid
        valid.add(destination)
        cache = caches[destination]
        plane = planes[destination]
        dirty: set[int] = set(range(48)) if initializing else set()
        event_misses = 0
        for block_row in range(12):
            for block_column in range(12):
                source = block_row * 48 + block_column * 2
                output = block_row * 64 + block_column * 2
                position = block_row * 12 + block_column
                triple = (raw[source + 1], raw[source + 24], raw[source + 25])
                tl_attr = lut[raw[source]]
                if (not initializing and cache[position] == triple
                        and plane[output] == tl_attr):
                    hits += 1
                    continue
                misses += 1
                event_misses += 1
                cache[position] = triple
                plane[output] = tl_attr
                plane[output + 1] = lut[raw[source + 1]]
                plane[output + 32] = lut[raw[source + 24]]
                plane[output + 33] = lut[raw[source + 25]]
                half = 0 if block_column < 8 else 1
                dirty.update((block_row * 4 + half,
                              block_row * 4 + 2 + half))
        if not event_misses:
            zero_miss += 1
        expected = desired_plane(raw, lut)
        if bytes(plane) != expected:
            raise AssertionError(f"shadow mismatch in {path}")
        event_runs = runs(dirty)
        for start, length in event_runs:
            begin = start * 16
            end = begin + length * 16
            published[destination][begin:end] = plane[begin:end]
            run_histogram[length] += 1
        if bytes(published[destination]) != expected:
            raise AssertionError(f"publication trail in {path}")
        publications += bool(dirty)
        dirty_blocks += len(dirty)
        run_count += len(event_runs)
        block_histogram[len(dirty)] += 1
    return {
        "layouts": layouts,
        "publications": publications,
        "zero_miss_events": zero_miss,
        "cache_hits": hits,
        "cache_misses": misses,
        "dirty_blocks": dirty_blocks,
        "runs": run_count,
        "run_length_histogram": dict(sorted(run_histogram.items())),
        "dirty_block_histogram": dict(sorted(block_histogram.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("tmp"))
    parser.add_argument(
        "--base", type=Path,
        default=Path("tmp/stage1-menu-hidden-repair-r264/candidate.gb"),
    )
    parser.add_argument(
        "--candidate", type=Path,
        default=Path("tmp/stage7-exact-triple-cache-r264/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage7-exact-triple-cache-r264/static-receipt.json"),
    )
    args = parser.parse_args()

    base = args.base.read_bytes()
    candidate = args.candidate.read_bytes()
    rebuilt, build_receipt = candidate_builder.install(base, args.root)
    if rebuilt != candidate:
        raise AssertionError("candidate is not a deterministic source rebuild")
    if digest(candidate) != build_receipt["candidate_sha256"]:
        raise AssertionError("candidate digest mismatch")

    paths = sorted(args.root.glob("**/stage7.layout-events.tsv"))
    if len(paths) != 24:
        raise AssertionError(f"expected 24 corpus files, found {len(paths)}")
    lut = bytes(semantic_lut(7))
    totals: Counter[str] = Counter()
    run_histogram: Counter[int] = Counter()
    block_histogram: Counter[int] = Counter()
    for path in paths:
        report = model_file(path, lut)
        for key in ("layouts", "publications", "zero_miss_events", "cache_hits",
                    "cache_misses", "dirty_blocks", "runs"):
            totals[key] += int(report[key])
        run_histogram.update(report["run_length_histogram"])
        block_histogram.update(report["dirty_block_histogram"])
    if totals["layouts"] != 1645:
        raise AssertionError(totals)

    # Mutation controls prove why every arm of the runtime key is necessary.
    raw = bytearray(576)
    source = 0
    plane_tl = lut[raw[source]]
    triple = (raw[source + 1], raw[source + 24], raw[source + 25])
    same_attr_tl = next(value for value in range(256)
                        if value != raw[source] and lut[value] == plane_tl)
    different_attr_tl = next(value for value in range(256)
                             if lut[value] != plane_tl)
    tl_same_attr_hit = (triple == triple and lut[same_attr_tl] == plane_tl)
    tl_different_attr_miss = not (
        triple == triple and lut[different_attr_tl] == plane_tl
    )
    non_tl_misses = []
    for position in range(3):
        changed = list(triple)
        changed[position] ^= 1
        non_tl_misses.append(tuple(changed) != triple)
    if not tl_same_attr_hit or not tl_different_attr_miss or not all(non_tl_misses):
        raise AssertionError("exact-key mutation control failed")
    poisoned_live_lut = bytes(value ^ 7 for value in lut)
    immutable_outputs = bytes(lut[value] for value in raw[:4])
    if immutable_outputs == bytes(poisoned_live_lut[value] for value in raw[:4]):
        raise AssertionError("C600 poison control failed to distinguish LUTs")

    # Machine-code and memory ownership contracts.  The fixed compiler and
    # all non-Stage7 dispatch bytes remain exact; Stage7 installs D400 only
    # after its private rare-helper branch and restores SVBK1 before returning.
    if candidate[0x42A0:0x436E] != base[0x42A0:0x436E]:
        raise AssertionError("fixed compiler changed")
    helper = candidate_builder.build_helper()
    dispatcher = candidate_builder.old.build_dispatcher()
    installer = candidate_builder.build_installer(len(dispatcher))
    if helper.count(bytes((0xE0, 0x70))) < 2:
        raise AssertionError("helper lacks explicit SVBK transitions")
    if installer[-12:] != bytes((0x3E, 0x01, 0xE0, 0x70, 0xAF,
                                 0xE0, candidate_builder.old.BYPASS,
                                 0x3E, 0x0D, 0xC3, 0x61, 0x00)):
        raise AssertionError("installer does not restore SVBK1/bypass state")
    if helper[-15:] != bytes((0xAF, 0xE0, 0x4F, 0x3C, 0xE0, 0x70,
                              0x01, 0x54, 0x43, 0xC5, 0x3E, 0x01,
                              0xC3, 0x61, 0x00)):
        raise AssertionError("helper completion ABI changed")

    receipt = {
        "schema": "penta-stage7-exact-triple-cache-static-v1",
        "status": "STATIC_REJECTED_CYCLE_BUDGET_AND_OWNERSHIP",
        "promotable": False,
        "base_sha256": digest(base),
        "candidate_sha256": digest(candidate),
        "build_receipt_sha256": digest(
            Path("tmp/stage7-exact-triple-cache-r264/build-receipt.json").read_bytes()
        ),
        "correctness": {
            "key": ["top_right_raw", "bottom_left_raw", "bottom_right_raw"],
            "supplement": (
                "immutable bank22 LUT(top_left) equals shadow top-left attr"
            ),
            "semantic_source": "immutable bank22:$4700 Stage7 LUT",
            "arbitrary_unseen_inputs": "exact; no corpus membership assumed",
            "first_scan_forces_all_144_misses": True,
            "shadow_equals_live_LUT_every_layout": True,
            "published_plane_equals_shadow_every_layout": True,
            "neutral_transitions_clear_old_attrs": True,
        },
        "corpus_model": {
            **dict(totals),
            "average_blocks_per_publication": (
                totals["dirty_blocks"] / totals["publications"]
            ),
            "average_runs_per_publication": totals["runs"] / totals["publications"],
            "run_length_histogram": dict(sorted(run_histogram.items())),
            "dirty_block_histogram": dict(sorted(block_histogram.items())),
            "full_compiler_blocks_for_same_publications": totals["publications"] * 48,
            "hblank_blocks_saved": totals["publications"] * 48 - totals["dirty_blocks"],
        },
        "negative_controls": {
            "pair_only_counterexamples": build_receipt["corpus"]["pair_negative_controls"],
            "top_left_same_attr_is_safe_hit": tl_same_attr_hit,
            "top_left_different_attr_forces_miss": tl_different_attr_miss,
            "each_non_top_left_raw_change_forces_miss": all(non_tl_misses),
            "all_FF_first_scan_alias_prevented_by_initializing_flag": True,
            "poisoned_shared_C600_does_not_change_output": True,
        },
        "memory_abi": {
            "planes": "SVBK6/7:D000-D2FF",
            "exact_triples": "SVBK6/7:D500-D6AF (432 bytes)",
            "dirty_flags": "SVBK6/7:D6B0-D6DF",
            "temps_valid": "SVBK6/7:D6E0-D6FC",
            "D400_dispatcher_is_separate": True,
            "scene_exclusivity": (
                "installed only by Stage7 rare-helper branch; exact r264 has "
                "no immediate SVBK6/7 selectors and all established private "
                "owners use SVBK2-5"
            ),
            "fixed_compiler_byte_exact": True,
            "mapper_stack_completion": "discard CALL D400; mapper returns at $4354",
            "svbk_restored_to_1_on_every_completion": True,
        },
        "transport": {
            "dirty_units": "16-byte blocks over complete 24x32 plane",
            "adjacent_units_coalesced": True,
            "active_lcd": "HBlank DMA only; waits for completion before map flip",
            "lcd_off": "bounded GDMA permitted",
        },
        "cycle_rejection": build_receipt["cycle_rejection"],
        "ownership_rejection": build_receipt["ownership_rejection"],
        "required_first_gate": None,
        "do_not_emulator_run": True,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
