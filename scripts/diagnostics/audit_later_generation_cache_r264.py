#!/usr/bin/env python3
"""Fail-closed audit of a generation-keyed later-dungeon cache on exact r264.

The tempting design redirects bank-0:$12DA through a small WRAM1 wrapper that
calls the stock $1399 packed-map expander, then increments $DF56 for dungeon
indices $FFBA=1..6.  A DA60 decider could then compare generation, validity,
and room in O(1).

This script deliberately cannot build a ROM.  It binds the proposed wrapper,
the current WRAM runtime, known direct C1A0 writers, entry invalidation, and the
exact Stage 7 patrol receipt.  The result is a blocker receipt: not every map
mutation flows through $12DA, the proposed generation changes at every normal
map publication, and DA60 is shared by Crystal Dragon.

No emulator is imported, invoked, or needed.  The only output is JSON under
the repository-local ignored ``tmp/`` directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_SHA256 = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
BASE_MD5 = "cd025fd5c3ccdf49ac5a9ebebceff8e5"
RUNTIME_SHA256 = "765d22df24f270dd5210500f05ae101278edab35ee0c8707bed26738f90c8b5a"

BANK_SIZE = 0x4000
RAW_SIZE = 24 * 24

# (name, bank, inclusive start, exclusive end, sha256)
PREIMAGES = (
    ("normal_expander_then_publisher", 0, 0x12D0, 0x12E4,
     "83fec7ce4af6fc64b99a845ec76a8b4cb9d3a47c8a82c29121054a7e0814911c"),
    ("packed_map_expander", 0, 0x1399, 0x13E5,
     "e1c954fd0cf06857c532fa13105c955d47105648fac4e60e611ad3a2eac7d899"),
    ("direct_rect_clear_caller", 0, 0x363E, 0x3650,
     "d1a90a308d72d99692e6dc6d4dc3612326c03041d835ca92fc7b914d9beca87a"),
    ("direct_rect_clear_and_publish", 0, 0x0FD8, 0x1005,
     "701194ef6006bd1a013a82bfc1d336452e2ef06adac31091a824ab68eaa63e75"),
    ("c1a0_clear_helpers", 1, 0x4422, 0x4467,
     "8df8c573a61fdf20a34ce876e509c08cc7cc2654e68580d68e18680ab7da2475"),
    ("direct_generator_then_publisher", 0, 0x0AB2, 0x0AC0,
     "f322820f2152956c77e2d283b903847639eee3039a3068501265d8e5a40ce7a4"),
    ("direct_c1a0_generator", 0, 0x309B, 0x3130,
     "591c3961af28a5b1415b7c7bf1ab1cbb043dfa2c9fcab8d0c39166ec550d809c"),
    ("ending_scene_negative_control", 0, 0x3A90, 0x3AE0,
     "8003cf6bec21833cd155a87a3fc2848247ae5c4e5232c3e3328f7e5d72ede665"),
    ("ending_direct_c1a0_writer", 0, 0x1238, 0x1260,
     "d1b9758754dd1a41dfcf5a5015a7fd7630ed84873f617ef0fc82e23fa38d362c"),
)

SOURCE_A = 0x7BB2
SOURCE_A_SIZE = 46
SOURCE_B = 0x7C4D
SOURCE_B_SIZE = 114
RUNTIME_BASE = 0xDA60
DISPATCH_OFFSET = 0x59
WRAPPER_OFFSET = 0x89

EXPECTED_NORMAL_CALL = bytes.fromhex("CD 99 13")
EXPECTED_NORMAL_PATH = bytes.fromhex("21 A0 C1 CD 99 13 CD 95 42")
EXPECTED_EXPANDER_TAIL = bytes.fromhex("CD D6 09 EF C9")
EXPECTED_DISPATCHER = bytes.fromhex(
    "06 05 FA 80 D8 D6 03 FE 06 38 10 D6 09 FE 09 38 02 AF C9 "
    "FE 02 CA 60 DA C3 A4 DB C3 60 DA"
)
EXPECTED_ENTRY_INVALIDATION = bytes.fromhex("3E FF EA 55 DF EA 59 DF")

# CALL $1399; preserve AF; normalize FFBA-1; accept only 0..5; increment DF56;
# restore AF; RET.  BC/DE/HL and FFE0 are untouched by wrapper instructions.
PROPOSED_WRAPPER = bytes.fromhex(
    "CD 99 13 F5 F0 BA 3D FE 06 30 07 FA 56 DF 3C EA 56 DF F1 C9"
)


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if bank == 0:
        if not 0 <= address < 0x4000:
            raise AssertionError((bank, address))
        return address
    if not 0x4000 <= address < 0x8000:
        raise AssertionError((bank, address))
    return bank * BANK_SIZE + address - 0x4000


def occurrences(payload: bytes, needle: bytes) -> list[int]:
    return [
        index for index in range(len(payload) - len(needle) + 1)
        if payload.startswith(needle, index)
    ]


def logical_address(offset: int) -> str:
    bank = offset // BANK_SIZE
    address = offset if bank == 0 else 0x4000 + offset % BANK_SIZE
    return f"bank{bank}:${address:04X}"


def require_preimages(payload: bytes) -> list[dict[str, object]]:
    checked = []
    for name, bank, start, end, expected in PREIMAGES:
        blob = payload[bank_offset(bank, start):bank_offset(bank, start) + end - start]
        actual = sha256(blob)
        if actual != expected:
            raise AssertionError(
                f"{name} changed at bank{bank}:${start:04X}-${end - 1:04X}: "
                f"{actual} != {expected}"
            )
        checked.append({
            "name": name,
            "bank": bank,
            "range": f"${start:04X}-${end - 1:04X}",
            "length": end - start,
            "sha256": actual,
        })
    return checked


def require_runtime(payload: bytes) -> tuple[bytes, dict[str, object]]:
    fragments = []
    for bank in (13, 16):
        first = payload[
            bank_offset(bank, SOURCE_A):bank_offset(bank, SOURCE_A) + SOURCE_A_SIZE
        ]
        second = payload[
            bank_offset(bank, SOURCE_B):bank_offset(bank, SOURCE_B) + SOURCE_B_SIZE
        ]
        fragments.append(first + second)
    if fragments[0] != fragments[1]:
        raise AssertionError("bank13/bank16 DA60 source mirrors differ")
    runtime = fragments[0]
    if len(runtime) != 160 or sha256(runtime) != RUNTIME_SHA256:
        raise AssertionError("DA60 runtime preimage changed")
    if runtime[DISPATCH_OFFSET:DISPATCH_OFFSET + len(EXPECTED_DISPATCHER)] != EXPECTED_DISPATCHER:
        raise AssertionError("DAB9 dispatcher preimage changed")
    if runtime[WRAPPER_OFFSET:] != bytes(23):
        raise AssertionError("DAE9-DAFF is not the expected 23-byte zero cave")
    return runtime, {
        "source_mirrors": [13, 16],
        "source_fragments": [
            "$7BB2-$7BDF -> $DA60-$DA8D",
            "$7C4D-$7CBE -> $DA8E-$DAFF",
        ],
        "sha256": sha256(runtime),
        "dispatcher": {
            "range": "$DAB9-$DAD6",
            "bytes": EXPECTED_DISPATCHER.hex(" ").upper(),
            "crystal_route": (
                "D880=$0E reaches $DA60; other arena scenes reach $DBA4"
            ),
        },
        "wrapper_cave": {
            "range": "$DAE9-$DAFF",
            "available_bytes": 23,
            "all_zero": True,
        },
    }


def stage7_plane(raw: bytes) -> bytes:
    lut = bytearray(256)
    for tile in (0xA0, 0xA1, 0xB0, 0xB1):
        lut[tile] = 4
    for tile in (0x19, 0x1A):
        lut[tile] = 5
    return bytes(lut[tile] for tile in raw)


def patrol_metrics(result_path: Path, trace_path: Path) -> dict[str, object]:
    result = json.loads(result_path.read_text())
    rows: list[tuple[str, bytes]] = []
    for number, line in enumerate(trace_path.read_text().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) < 30:
            raise AssertionError(f"{trace_path}:{number}: malformed attr event")
        raw = bytes.fromhex(fields[-1])
        if len(raw) != RAW_SIZE:
            raise AssertionError(f"{trace_path}:{number}: raw length {len(raw)}")
        rows.append((fields[2], stage7_plane(raw)))

    last: dict[str, bytes] = {}
    cold = changes = 0
    for physical_map, plane in rows:
        if physical_map not in last:
            cold += 1
        elif last[physical_map] != plane:
            changes += 1
        last[physical_map] = plane

    compiles = len(result["compiler_tile_copy_indices"])
    exact = {
        "stage": result["stage"],
        "scene": result["expected_scene"],
        "frames": result["frames"],
        "main_loop_hits": result["main_loop_hits"],
        "scroll_changes": result["scroll_changes"],
        "publications": result["tile_copy_hits"],
        "compiler_hits": compiles,
        "cold_physical_maps": cold,
        "genuine_per_map_semantic_changes_after_cold": changes,
        "minimum_perfect_semantic_compiles_including_cold": cold + changes,
        "avoidable_current_compiles": compiles - (cold + changes),
        "perfect_key_compiler_reduction_percent": round(
            100 * (compiles - cold - changes) / compiles, 4
        ),
        "adjacent_same_physical_map_publications": sum(
            left[0] == right[0] for left, right in zip(rows, rows[1:])
        ),
        "physical_map_publications": {
            physical_map: sum(row[0] == physical_map for row in rows)
            for physical_map in sorted(last)
        },
    }
    expected = {
        "stage": 7,
        "scene": 8,
        "frames": 2800,
        "main_loop_hits": 726,
        "scroll_changes": 725,
        "publications": 846,
        "compiler_hits": 351,
        "cold_physical_maps": 2,
        "genuine_per_map_semantic_changes_after_cold": 308,
        "minimum_perfect_semantic_compiles_including_cold": 310,
        "avoidable_current_compiles": 41,
        "perfect_key_compiler_reduction_percent": 11.6809,
        "adjacent_same_physical_map_publications": 120,
        "physical_map_publications": {"98": 424, "9C": 422},
    }
    if exact != expected:
        raise AssertionError(f"Stage 7 patrol evidence changed: {exact}")
    return {
        **exact,
        "result": str(result_path.relative_to(ROOT)),
        "result_sha256": sha256(result_path.read_bytes()),
        "attr_trace": str(trace_path.relative_to(ROOT)),
        "attr_trace_sha256": sha256(trace_path.read_bytes()),
        "deterministic_pair": (
            "stage7-dx-b-patrol has the same compiler indices and counters"
        ),
    }


def wrapper_contract() -> dict[str, object]:
    if len(PROPOSED_WRAPPER) != 20:
        raise AssertionError("proposed wrapper no longer fits 23-byte cave")
    if PROPOSED_WRAPPER[:3] != EXPECTED_NORMAL_CALL:
        raise AssertionError("wrapper does not call the original expander first")
    if PROPOSED_WRAPPER[-2:] != bytes.fromhex("F1 C9"):
        raise AssertionError("wrapper does not restore AF before return")
    if bytes.fromhex("E0 E0") in PROPOSED_WRAPPER:
        raise AssertionError("wrapper unexpectedly writes FFE0")
    return {
        "entry": "$DAE9",
        "length": len(PROPOSED_WRAPPER),
        "cave_length": 23,
        "bytes": PROPOSED_WRAPPER.hex(" ").upper(),
        "call_site_replacement": "bank0:$12DA CD 99 13 -> CD E9 DA",
        "ordering": (
            "CALL $1399 completes all C1A0 writes and its bank restore before "
            "$DF56 is incremented"
        ),
        "abi": {
            "AF": "exactly preserved with PUSH/POP AF",
            "BC_DE_HL": "wrapper instructions do not touch them",
            "FFE0": "not read or written",
            "stage1": "FFBA=0 is outside normalized 0..5 range; no increment",
        },
    }


def mutation_controls(payload: bytes) -> dict[str, bool]:
    controls: dict[str, bool] = {}
    for name, bank, start, _end, _digest in PREIMAGES:
        mutant = bytearray(payload)
        mutant[bank_offset(bank, start)] ^= 1
        try:
            require_preimages(bytes(mutant))
        except AssertionError:
            controls[f"mutated_{name}_rejected"] = True
        else:
            raise AssertionError(f"mutated {name} escaped preimage gate")

    mutant = bytearray(payload)
    mutant[bank_offset(13, SOURCE_A)] ^= 1
    try:
        require_runtime(bytes(mutant))
    except AssertionError:
        controls["mutated_runtime_mirror_rejected"] = True
    else:
        raise AssertionError("mutated runtime escaped mirror/hash gate")

    bad_wrapper = bytearray(PROPOSED_WRAPPER)
    bad_wrapper[-2] = 0x00
    try:
        if bytes(bad_wrapper)[-2:] != bytes.fromhex("F1 C9"):
            raise AssertionError("AF restore removed")
    except AssertionError:
        controls["mutated_wrapper_af_restore_rejected"] = True
    else:
        raise AssertionError("bad wrapper escaped ABI gate")
    return controls


def audit(payload: bytes, result_path: Path, trace_path: Path) -> dict[str, object]:
    digest = sha256(payload)
    if digest != BASE_SHA256:
        raise AssertionError(f"not exact repaired r264: {digest}")
    if hashlib.md5(payload).hexdigest() != BASE_MD5:
        raise AssertionError("exact r264 MD5 preimage changed")

    preimages = require_preimages(payload)
    runtime, runtime_receipt = require_runtime(payload)
    if payload[0x12DA:0x12DD] != EXPECTED_NORMAL_CALL:
        raise AssertionError("sole proposed CALL preimage changed")
    if payload[0x12D7:0x12E0] != EXPECTED_NORMAL_PATH:
        raise AssertionError("normal expander/publication ordering changed")
    if payload[0x13E0:0x13E5] != EXPECTED_EXPANDER_TAIL:
        raise AssertionError("expander completion tail changed")

    invalidations = occurrences(payload, EXPECTED_ENTRY_INVALIDATION)
    expected_invalidations = [0x3548C, 0x4148C]
    if invalidations != expected_invalidations:
        raise AssertionError(
            f"DF55/DF59 invalidation sites changed: {invalidations}"
        )

    # Prove the bypasses structurally, without making an unbounded reachability
    # claim.  These instructions mutate C1A0 and publish without CALL $1399.
    rect = payload[0x0FD8:0x1005]
    if bytes.fromhex("CD 2C 44") not in rect or bytes.fromhex("CD A7 42") not in rect:
        raise AssertionError("rectangle writer/publication bypass changed")
    if bytes.fromhex("CD 22 44 26 98 C3 A7 42") not in rect:
        raise AssertionError("full-clear/final-publication bypass changed")
    direct = payload[0x0AB2:0x0AC0]
    if direct[:9] != bytes.fromhex("CD 9B 30 CD 95 42 CD 7B 30"):
        raise AssertionError("direct generator/publication bypass changed")
    generator = payload[0x309B:0x3130]
    if bytes.fromhex("11 A0 C1") not in generator or bytes.fromhex("2A 12 13") not in generator:
        raise AssertionError("direct C1A0 writer proof changed")

    patrol = patrol_metrics(result_path, trace_path)
    projected_generation_compiles = patrol["main_loop_hits"]
    projected_extra = projected_generation_compiles - patrol["compiler_hits"]
    if projected_extra != 375:
        raise AssertionError("generation-cache projection changed")

    wrapper = wrapper_contract()
    controls = mutation_controls(payload)
    return {
        "schema": "penta-later-generation-cache-r264-static-blocker-v1",
        "status": "NO-STATIC-SAFE-CANDIDATE",
        "promotable": False,
        "candidate_written": False,
        "emulator_invoked": False,
        "base": {"sha256": digest, "md5": hashlib.md5(payload).hexdigest()},
        "strict_r264_preimages": preimages,
        "runtime": runtime_receipt,
        "proposed_wrapper": wrapper,
        "invalidation": {
            "later_stage_entry": {
                "status": "PASS",
                "operation": "DF55=FF and DF59=FF",
                "exact_sites": [logical_address(offset) for offset in invalidations],
                "source_mirrors": [13, 16],
            },
            "menu_or_other_direct_writer": {
                "status": "FAIL_CLOSED",
                "finding": (
                    "The two entry-helper mirrors are the only exact joint "
                    "DF55/DF59 invalidations in r264; direct C1A0 mutation and "
                    "publication paths do not pass the proposed counter hook."
                ),
            },
        },
        "writer_ownership": {
            "status": "FAIL_CLOSED",
            "normal_path": (
                "bank0:$12D7 loads HL=C1A0, calls $1399, then immediately "
                "calls $4295; counter-to-publication ordering is exact."
            ),
            "bypasses": [
                {
                    "path": "$3648 -> $0FD8 -> $442C/$4422 -> $42A7",
                    "effect": (
                        "$442C clears rectangles inside C1A0 and $4422 clears "
                        "all C1A0-C3DF; both publications bypass $12DA/$1399."
                    ),
                },
                {
                    "path": "$0AB2 -> $309B -> $4295",
                    "effect": (
                        "$309B initializes DE=C1A0 and its nested loop writes "
                        "through LD [DE],A; it bypasses $12DA/$1399."
                    ),
                },
            ],
            "negative_control": (
                "$3A9B sets D880=$1B before calling the direct $1238 C1A0 "
                "writer, so that ending route is explicitly outside dungeons."
            ),
            "scope_gap": (
                "Archived writer traces cover only Stages 4, 5, and 7 and only "
                "observed $1399 PCs; they cannot prove Stages 2, 3, and 6 or "
                "exclude the exact direct paths above."
            ),
        },
        "modulo_and_ordering": {
            "canonical_same_map_generation_gap": 2,
            "wrap_safe": True,
            "reason": (
                "$4295 alternates $9800/$9C00 via DC0B after every normal "
                "expansion, so consecutive uses of one physical map differ by "
                "two generations, far below 256."
            ),
            "source_completion_before_increment": True,
            "counter_publication_problem": (
                "The same ordering means each canonical source generation is "
                "immediately published and therefore necessarily dirty."
            ),
        },
        "arena_isolation": {
            "status": "FAIL_CLOSED",
            "finding": (
                "DAB9 routes Crystal Dragon scene $0E through the same DA60 "
                "cache. A dungeon-only DF56 replacement would stale-hit Crystal "
                "or require a separate arena generation/invalidation contract."
            ),
            "other_arenas": "route to $DBA4 and are not the DA60 blocker",
            "df56_existing_owner": (
                "DF56 is also shared with specialized arena/Ted cache state; "
                "generic reassignment is not arena-byte-exact."
            ),
        },
        "stage7_patrol": patrol,
        "performance_outlook": {
            "status": "REGRESSION_EXPECTED_NOT_TRACE_PROVEN",
            "projected_generation_compiles": projected_generation_compiles,
            "current_compiles": patrol["compiler_hits"],
            "projected_extra_compiles": projected_extra,
            "projected_compiler_increase_percent": round(
                100 * projected_extra / patrol["compiler_hits"], 4
            ),
            "basis": (
                "The exact patrol has 726 main-loop hits and 725 scroll changes; "
                "the canonical bank0 path performs one expansion followed by one "
                "publication. The archived trace did not breakpoint $12DA, so "
                "726 is an evidence-backed projection, not an exact call count."
            ),
            "perfect_semantic_ceiling": (
                "Independent per-physical-map semantic tracking needs 310 "
                "compiles. The current key's 351 is only 41 (11.6809%) above "
                "that lower bound, so a cache-key change alone cannot recover "
                "the Stage 7 deficit."
            ),
        },
        "mutation_controls": controls,
        "decision": (
            "Do not emit or emulator-run this generation-cache design. A safe "
            "successor must either hook every source mutation and isolate "
            "Crystal, or optimize the unavoidable compiler/publication transport "
            "instead of treating every source generation as a cache miss."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", type=Path,
        default=ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb",
    )
    parser.add_argument(
        "--result", type=Path,
        default=(
            ROOT / "tmp/stage1-menu-hidden-repair-r264/"
            "stage7-speed-patrol-profile-r1/stage7-dx-a-patrol/result.json"
        ),
    )
    parser.add_argument(
        "--trace", type=Path,
        default=(
            ROOT / "tmp/stage1-menu-hidden-repair-r264/"
            "stage7-speed-patrol-profile-r1/stage7-dx-a-patrol/attr-events.tsv"
        ),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=ROOT / "tmp/later-generation-cache-r264/blocker-receipt.json",
    )
    args = parser.parse_args()
    receipt = audit(args.base.read_bytes(), args.result, args.trace)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
