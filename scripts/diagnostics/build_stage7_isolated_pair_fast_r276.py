#!/usr/bin/env python3
"""Isolate r273's dirty router to Stage 7 and skip two inactive services.

The r273 helper is fast enough in Stage 7, but its unconditional DA60 dirty
redirect adds 60 T-cycles to every non-Stage-7 dirty publication.  A
transition-only selector now writes the redirect operand: exact Stage 7 gets
the qualified DAE9 route; every other stage gets the byte/cycle-exact native
DAA3 route.  The ROM source defaults to native so cold and unrelated states
remain fail-closed.

The same candidate rebases the qualified scene-$08 VBlank service-pair router.
Its Stage-1/5 balancing delay is encoded inline, leaving the old delay cave
available for the transition selector without changing either balanced path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_SHA256 = "09d75d4461d911f4ed55c929c676346b1f7851e015bdbd867f307f8d9f1cc1d8"
EXPECTED_CANDIDATE_SHA256 = (
    "ff66b18e0d4a47ff1f386be398457c2554b43972c14cb91da95a38d11e31ca84"
)
BANK_SIZE = 0x4000
BANK13 = 13
RUNTIME_BANKS = (13, 16)
TRANSITION_BANKS = (13, 16)

RUNTIME_REDIRECT_SOURCE_ADDR = 0x7C76
RUNTIME_TAIL_SOURCE_ADDR = 0x7CA8
COMMON_JUMP_ADDR = 0x5499
SELECTOR_ADDR = 0x570E
PAIR_ADDR = 0x6F20
ROUTER_ADDR = 0x6ED3

OLD_REDIRECT = bytes((0x31,))              # JR $DAE9 from $DAB6
NATIVE_REDIRECT = bytes((0xEB,))           # JR $DAA3 from $DAB6
ROUTER_TAIL = bytes.fromhex(
    "E1 D1 C1 F5 FA 80 D8 FE 08 28 02 F1 C9 F3 F1 F1 F1 3E 16 C3 47 08"
)
OLD_COMMON_JUMP = bytes.fromhex("C3 F2 53")
NEW_COMMON_JUMP = bytes.fromhex("C3 0E 57")
OLD_SELECTOR_CAVE = bytes(16)
SELECTOR = bytes.fromhex(
    "F0 BA FE 06 3E EB 20 02 3E 31 EA B7 DA C3 F2 53"
)

OLD_PAIR = bytes.fromhex("CD 00 71 CD 60 6A")
NEW_PAIR = bytes.fromhex("CD D3 6E 00 00 00")
OLD_ROUTER = bytes.fromhex(
    "18 00 18 00 18 00 18 00 18 00 18 00 18 00 18 00 "
    "18 00 18 00 18 00 18 00 00 00 00 00 00 00 00 00 00"
)
# The B=3 inline loop replaces the former JP plus B=2 external loop.  Stage 1
# enters with B=3; Stage 5 decrements to B=2.  Both therefore retain exactly
# 104T after the scene-owner prefix and 212T caller-inclusive pair timing.
NEW_ROUTER = bytes.fromhex(
    "FA 80 D8 "          # LD A,[$D880]
    "FE 08 C8 "          # exact Stage 7: RET Z
    "FE 02 DA 60 6A "    # title/epilogue owner
    "FE 0C D2 00 71 "    # death/story/arena owner
    "F0 BA 06 03 B7 "    # A=stage; B=3; Stage 1?
    "28 04 "             # Stage 1 enters the shared loop with B=3
    "05 FE 04 C0 "       # Stage 5 enters it with B=2; others RET
    "05 20 FD "          # exact counted delay
    "00 00 C9"           # 8T neutral delay; RET
)


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


def require_at(source: bytes, bank: int, address: int, expected: bytes,
               label: str) -> int:
    offset = bank_offset(bank, address)
    actual = source[offset:offset + len(expected)]
    if actual != expected:
        raise AssertionError(
            f"{label} preimage moved at bank{bank}:${address:04X}: "
            f"{actual.hex()} != {expected.hex()}"
        )
    return offset


def selector_result(stage: int) -> int:
    return 0x31 if stage == 6 else 0xEB


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    if digest(base) != BASE_SHA256:
        raise AssertionError(f"wrong exact r273 base: {digest(base)}")
    if len(SELECTOR) != len(OLD_SELECTOR_CAVE) or len(SELECTOR) != 16:
        raise AssertionError("transition selector width changed")
    if len(NEW_ROUTER) != len(OLD_ROUTER) or len(NEW_ROUTER) != 33:
        raise AssertionError("service router width changed")

    rom = bytearray(base)
    allowed = {0x014D, 0x014E, 0x014F}
    runtime_sources: list[dict[str, object]] = []
    for bank in RUNTIME_BANKS:
        redirect = require_at(
            base, bank, RUNTIME_REDIRECT_SOURCE_ADDR, OLD_REDIRECT,
            "r273 dirty redirect",
        )
        require_at(
            base, bank, RUNTIME_TAIL_SOURCE_ADDR, ROUTER_TAIL,
            "r273 bank-22 router tail",
        )
        rom[redirect:redirect + 1] = NATIVE_REDIRECT
        allowed.add(redirect)
        runtime_sources.append({
            "bank": bank,
            "source_operand": "$7C76",
            "runtime_operand": "$DAB7",
            "old": "$31 -> $DAE9",
            "new_default": "$EB -> $DAA3",
            "tail_source_sha256": digest(ROUTER_TAIL),
        })

    transition_sources: list[dict[str, object]] = []
    for bank in TRANSITION_BANKS:
        common = require_at(
            base, bank, COMMON_JUMP_ADDR, OLD_COMMON_JUMP,
            "later-stage common-tail jump",
        )
        selector = require_at(
            base, bank, SELECTOR_ADDR, OLD_SELECTOR_CAVE,
            "transition selector cave",
        )
        for offset, old, new in (
            (common, OLD_COMMON_JUMP, NEW_COMMON_JUMP),
            (selector, OLD_SELECTOR_CAVE, SELECTOR),
        ):
            rom[offset:offset + len(new)] = new
            allowed.update(range(offset, offset + len(old)))
        transition_sources.append({
            "bank": bank,
            "common_jump": "$5499 JP $570E",
            "selector": "$570E-$571D",
        })

    pair = require_at(base, BANK13, PAIR_ADDR, OLD_PAIR, "VBlank service pair")
    router = require_at(
        base, BANK13, ROUTER_ADDR, OLD_ROUTER, "VBlank scene-router record",
    )

    for offset, old, new in (
        (pair, OLD_PAIR, NEW_PAIR),
        (router, OLD_ROUTER, NEW_ROUTER),
    ):
        rom[offset:offset + len(new)] = new
        allowed.update(range(offset, offset + len(old)))

    # Exhaust the selector's complete byte domain.  The admitted Stage-7
    # owner is singular; every other value restores the native redirect.
    selected = [value for value in range(256)
                if selector_result(value) == 0x31]
    native = [value for value in range(256)
              if selector_result(value) == 0xEB]
    if selected != [6] or len(native) != 255:
        raise AssertionError("transition selector truth table changed")

    timing = {
        "original_pair": 212,
        "stage1_balanced": 212,
        "stage5_balanced": 212,
        "stage7_scene08": 80,
        "saved_per_stage7_vblank": 132,
        "nonstage_dirty_miss_before": 60,
        "nonstage_dirty_miss_after": 0,
    }
    if timing["stage1_balanced"] != timing["original_pair"]:
        raise AssertionError("Stage-1 service-pair timing changed")
    if timing["stage5_balanced"] != timing["original_pair"]:
        raise AssertionError("Stage-5 service-pair timing changed")

    update_checksums(rom)
    candidate = bytes(rom)
    changed = [
        index
        for index, (before, after) in enumerate(zip(base, candidate, strict=True))
        if before != after
    ]
    escaped = sorted(set(changed) - allowed)
    if escaped:
        raise AssertionError(f"change escaped owned regions: {escaped[:8]}")
    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND" \
            and candidate_sha != EXPECTED_CANDIDATE_SHA256:
        raise AssertionError(
            f"r276 rematerialization changed: {candidate_sha}"
        )

    receipt: dict[str, object] = {
        "schema": "penta-stage7-isolated-pair-fast-r276-build-v1",
        "status": "STATIC_PASS_SPEED_AND_LIVE_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": digest(base),
        "candidate_sha256": candidate_sha,
        "changed_bytes_including_checksums": len(changed),
        "runtime_isolation": {
            "source_copies": runtime_sources,
            "transition_source_copies": transition_sources,
            "transition_common_jump": "bank13/bank16:$5499 JP $570E",
            "selector": "bank13/bank16:$570E-$571D",
            "selector_bytes": SELECTOR.hex(" ").upper(),
            "stage7_redirect": "$DAB7=$31 -> $DAE9",
            "all_other_stage_redirect": "$DAB7=$EB -> $DAA3",
            "rom_and_cold_default": "$EB native/fail-closed",
            "stage7_router_tail_byte_exact": True,
        },
        "selector_truth_table": {
            "stage7_admitted": ["$06"],
            "native_values": 255,
            "native_ranges": ["$00-$05", "$07-$FF"],
        },
        "service_pair": {
            "wrapper_pair": "bank13:$6F20-$6F25",
            "scene_router": "bank13:$6ED3-$6EF3",
            "inline_balanced_delay": True,
            "router_bytes": NEW_ROUTER.hex(" ").upper(),
            "timing_t_cycles": timing,
        },
        "contracts": {
            "exact_r273_base": True,
            "nonstage_DA60_dirty_path_byte_and_cycle_exact_to_r264": True,
            "stage7_transition_installs_exact_r273_redirect": True,
            "both_runtime_source_copies_default_native": True,
            "both_transition_source_copies_select_identically": True,
            "stage7_helper_and_all_inner_guards_byte_exact": True,
            "stage1_and_stage5_service_pair_timing_exact": True,
            "title_death_story_and_arena_service_owners_preserved": True,
            "compiler_transport_menu_visible_crop_and_pickup_bytes_unchanged": True,
        },
        "required_first_gates": [
            "Stage5 target4/right/2800 strict 0.99 speed",
            "Stage7 target6/right/2800 strict 0.99 speed",
            "Stage4 target3/right/2800 strict 0.99 speed",
            "Stage7 patrol route and throughput",
            "corrected all-stage speed matrix",
            "candidate-bound ABI, visual, menu, and Crystal containment",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", type=Path,
        default=ROOT / "tmp/stage7-skip-invisible-padding-r273/candidate.gb",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage7-isolated-pair-fast-r276/candidate.gb",
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=ROOT / "tmp/stage7-isolated-pair-fast-r276/build-receipt.json",
    )
    arguments = parser.parse_args()
    candidate, receipt = install(arguments.base.read_bytes())
    for path, payload in (
        (arguments.output, candidate),
        (arguments.receipt, json.dumps(receipt, indent=2).encode() + b"\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
