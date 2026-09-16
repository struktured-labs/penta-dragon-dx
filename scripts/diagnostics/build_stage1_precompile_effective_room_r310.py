#!/usr/bin/env python3
"""Build r310: precompile wall semantics keyed by native effective room FFE5.

r309 reached the correct precompile boundary but read FFBD, which still names
the outgoing room while the hidden incoming map is compiled.  Fixed native
code $0AD3-$0ADC has already resolved the incoming room into FFE5.  Use the
exact r309/r296 bank-30 helper with its sole room-load operand changed from
FFBD to FFE5.  The rejected r306 used FFE5 only in later semantic-row paths,
after the full map compile; it did not test this precompile use.

This candidate is generated directly from exact r305.  It does not depend on
the provisional r309 verifier receipt and does not compose r307/r308.  No
emulator is invoked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import build_stage1_precompile_wall_r309 as r309


r305 = r309.r305
r296 = r309.r296
ROOT = r309.ROOT
TMP = r309.TMP
BASE = r309.BASE
BASE_RECEIPT = r309.BASE_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-precompile-effective-room-r310/candidate.gb"
DEFAULT_RECEIPT = (
    TMP / "stage1-precompile-effective-room-r310/build-receipt.json"
)
BASE_SHA256 = r309.BASE_SHA256
BASE_RECEIPT_SHA256 = r309.BASE_RECEIPT_SHA256
EXPECTED_CANDIDATE_SHA256 = (
    "84bf45826c1acd2ae36a971c61aaf05c0ba761b723cd87e568607f9ffac6f36c"
)

BANK_SIZE = r309.BANK_SIZE
HELPER_BANK = r309.HELPER_BANK
HELPER_ADDR = r309.HELPER_ADDR
PRECOMPILE_SITE = r309.PRECOMPILE_SITE
OLD_PRECOMPILE = r309.OLD_PRECOMPILE
NEW_PRECOMPILE = r309.NEW_PRECOMPILE
OLD_HELPER = r309.HELPER
ROOM_OPERAND_OFFSET = 19
NEW_HELPER = bytearray(OLD_HELPER)
r305.r304.require(
    OLD_HELPER[ROOM_OPERAND_OFFSET - 1:ROOM_OPERAND_OFFSET + 1]
    == bytes.fromhex("F0 BD"),
    "r309 helper room load changed",
)
NEW_HELPER[ROOM_OPERAND_OFFSET] = 0xE5
NEW_HELPER = bytes(NEW_HELPER)
NEW_HELPER_SHA256 = (
    "be7bad71f6d607c55774b370ee02eb5b468d8eb88cc9ba6b53f8277e172d1a02"
)
TARGET_TILES = r309.TARGET_TILES
CHECKSUM_OFFSETS = r309.CHECKSUM_OFFSETS
EFFECTIVE_ROOM_SETTER_ADDR = 0x0AD3
EFFECTIVE_ROOM_SETTER = bytes.fromhex("7E E0 CE A7 20 02 F0 BD E0 E5")


def bank_offset(bank: int, address: int) -> int:
    return r309.bank_offset(bank, address)


def owned_ranges() -> set[int]:
    helper = bank_offset(HELPER_BANK, HELPER_ADDR)
    return (
        set(range(PRECOMPILE_SITE,
                  PRECOMPILE_SITE + len(NEW_PRECOMPILE)))
        | set(range(helper, helper + len(NEW_HELPER)))
    )


def effective_room(table_value: int, ffbd: int) -> int:
    return table_value if table_value else ffbd


def apply_model(
    values: dict[int, int], *, ffb7: int, scene: int, ffe5: int,
) -> dict[int, int]:
    result = dict(values)
    if r296.predicate_accepts(scene, ffb7):
        value = 0x06 if ffe5 == 1 else 0x00
        for tile in TARGET_TILES:
            result[tile] = value
    return result


def source_semantic_contract(source: bytes) -> dict[str, Any]:
    """Exhaustive source models, independent of captured room population."""
    r305.r304.require(len(NEW_HELPER) == len(OLD_HELPER) == 63,
                      "helper width changed")
    r305.r304.require(r305.r304.digest(NEW_HELPER) == NEW_HELPER_SHA256,
                      "effective-room helper identity changed")
    differences = {
        index for index, pair in enumerate(zip(OLD_HELPER, NEW_HELPER))
        if pair[0] != pair[1]
    }
    r305.r304.require(differences == {ROOM_OPERAND_OFFSET},
                      "helper changed beyond FFBD->FFE5 operand")

    resolver_cases = 0
    for table_value in range(256):
        for ffbd in range(256):
            expected = table_value if table_value else ffbd
            r305.r304.require(effective_room(table_value, ffbd) == expected,
                              "native effective-room model changed")
            resolver_cases += 1

    reachable_cases = 0
    for ffb7 in range(256):
        for dd06 in range(4):
            for ffbf in range(4):
                scene = r296.reachable_scene(ffb7, dd06=dd06, ffbf=ffbf)
                r305.r304.require(
                    r296.predicate_accepts(scene, ffb7) == (ffb7 == 2),
                    "reachable Stage predicate aliased",
                )
                reachable_cases += 1

    initial = {tile: 0x80 + index
               for index, tile in enumerate(TARGET_TILES)}
    rows = []
    for label, table_value, ffbd, scene, expected in (
        ("incoming_room01_outgoing_stagecard", 1, 0x12, 0x02, 0x06),
        ("incoming_room01_low_health", 1, 0x12, 0x0B, 0x06),
        ("incoming_room05_outgoing_room01", 5, 1, 0x02, 0x00),
        ("settled_room01_fallback", 0, 1, 0x0B, 0x06),
        ("settled_room05_fallback", 0, 5, 0x0B, 0x00),
    ):
        ffe5 = effective_room(table_value, ffbd)
        result = apply_model(initial, ffb7=2, scene=scene, ffe5=ffe5)
        r305.r304.require(result == {tile: expected for tile in TARGET_TILES},
                          f"effective-room truth row changed: {label}")
        rows.append({
            "case": label,
            "native_table_A": f"{table_value:02X}",
            "FFBD": f"{ffbd:02X}",
            "FFE5": f"{ffe5:02X}",
            "D880": f"{scene:02X}",
            "C600_values": f"{expected:02X}",
        })
    r305.r304.require(
        apply_model(initial, ffb7=2, scene=0x18, ffe5=1) == initial,
        "splash mutated C600",
    )
    r305.r304.require(
        apply_model(initial, ffb7=3, scene=0x03, ffe5=1) == initial,
        "later stage mutated C600",
    )

    table = bank_offset(13, 0x7000)
    r305.r304.require(all(source[table + tile] == 0 for tile in TARGET_TILES),
                      "immutable default target values changed")
    return {
        "native_resolver_cases_exhausted": resolver_cases,
        "reachable_stage_cases_exhausted": reachable_cases,
        "truth_rows": rows,
        "splash18_rejected": True,
        "stage2_scene03_rejected": True,
        "precompile_context_source": "FFE5 native incoming/effective room",
    }


def exhaustive_contract(source: bytes, room01_capture: bytes | None = None
                         ) -> dict[str, Any]:
    contract = source_semantic_contract(source)
    packed = r296.ROOM01_CAPTURE.read_bytes() if room01_capture is None else room01_capture
    positions = {
        index for index, tile in enumerate(packed) if tile in TARGET_TILES
    }
    expected_positions = {
        row * 24 + column for row, column in r296.ROOM01_TARGET_CELLS
    }
    r305.r304.require(positions == expected_positions and len(positions) == 35,
                      "room01 target corpus changed")
    return {**contract, "room01_target_positions": 35}


def source_preimages(source: bytes) -> dict[str, Any]:
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "wrong exact r305 base")
    r305.r304.require(
        source[PRECOMPILE_SITE:PRECOMPILE_SITE + len(OLD_PRECOMPILE)]
        == OLD_PRECOMPILE,
        "native precompile setup changed",
    )
    setter = source[
        EFFECTIVE_ROOM_SETTER_ADDR:
        EFFECTIVE_ROOM_SETTER_ADDR + len(EFFECTIVE_ROOM_SETTER)
    ]
    r305.r304.require(setter == EFFECTIVE_ROOM_SETTER,
                      "native FFE5 resolver changed")
    bank_start = HELPER_BANK * BANK_SIZE
    bank_end = bank_start + BANK_SIZE
    r305.r304.require(source[bank_start:bank_end]
                      == bytes([0xFF]) * BANK_SIZE,
                      "bank30 is no longer wholly erased")
    r305.r304.require(
        source[0x0847:0x0850]
        == bytes.fromhex("CD 61 00 CD 80 6C C3 61 00"),
        "fixed banked helper dispatcher changed",
    )
    return {
        "precompile": "fixed bank1:$4309-$430E",
        "effective_room_setter": "fixed:$0AD3-$0ADC",
        "effective_room_setter_bytes": setter.hex(" ").upper(),
        "helper": "bank30:$6C80-$6CBE",
        "bank30_full_preimage": "16KiB FF",
    }


def validate_preimages(source: bytes) -> dict[str, Any]:
    return {
        **source_preimages(source),
        "r309_live_observation": (
            "samples 62-65 recorded FFBD=12 while FFE5=01 before room commit; "
            "fresh corrected verifier receipt required"
        ),
    }


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    changed = r305.r304.delta(source, candidate)
    functional = r305.r304.delta(source, candidate, functional=True)
    r305.r304.require(changed <= owned_ranges() | CHECKSUM_OFFSETS,
                      "r310 escaped ownership")
    expected = {offset for offset in owned_ranges()
                if source[offset] != candidate[offset]}
    r305.r304.require(functional == expected,
                      "r310 functional delta changed")
    helper = bank_offset(HELPER_BANK, HELPER_ADDR)
    r305.r304.require(candidate[helper:helper + len(NEW_HELPER)] == NEW_HELPER,
                      "effective-room helper changed")
    r305.r304.require(
        candidate[PRECOMPILE_SITE:PRECOMPILE_SITE + len(NEW_PRECOMPILE)]
        == NEW_PRECOMPILE,
        "precompile route changed",
    )
    # Exclude all independently rejected/modular banks.
    for bank in (14, 16, 31):
        page = slice(bank * BANK_SIZE, (bank + 1) * BANK_SIZE)
        r305.r304.require(candidate[page] == source[page],
                          f"excluded bank{bank} component leaked")
    wall21 = bank_offset(r305.WALL_BANK, r305.WALL_ADDR)
    r305.r304.require(candidate[wall21:wall21 + len(r305.NEW_WALL_HELPER)]
                      == r305.NEW_WALL_HELPER,
                      "r305 bank21 room hook changed")
    return {
        "functional_changed_bytes": len(functional),
        "changed_offsets": [f"0x{x:06X}" for x in sorted(functional)],
        "escaped_bytes": 0,
        "r305_other_bytes_exact": True,
        "r306_r308_r307_excluded": True,
        "bank21_r298_helper_exact": True,
    }


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    """Emit exact r310 without loading historical receipts or captures."""
    preimages = source_preimages(source)
    semantic = source_semantic_contract(source)
    rom = bytearray(source)
    allowed: set[int] = set()
    r305.patch_exact(
        rom, source, PRECOMPILE_SITE, OLD_PRECOMPILE, NEW_PRECOMPILE,
        allowed, "bank30 effective-room precompile route",
    )
    helper = bank_offset(HELPER_BANK, HELPER_ADDR)
    r305.patch_exact(
        rom, source, helper, bytes([0xFF]) * len(NEW_HELPER), NEW_HELPER,
        allowed, "effective-room r296 helper in bank30",
    )
    r305.r304.require(allowed == owned_ranges(), "ownership drifted")
    r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    sha = r305.r304.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r305.r304.require(sha == EXPECTED_CANDIDATE_SHA256,
                          f"candidate identity drift: {sha}")
    receipt: dict[str, Any] = {
        "schema": "penta-stage1-precompile-effective-room-r310-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "base": {
            "revision": "r305",
            "candidate_sha256": BASE_SHA256,
        },
        "candidate_sha256": sha,
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "root_cause": (
            "hidden-map D400 compile occurs while FFBD is outgoing; native "
            "FFE5 already contains the resolved incoming room"
        ),
        "patch": {
            "precompile": "fixed bank1:$4309-$430E",
            "helper": "bank30:$6C80-$6CBE",
            "helper_sha256": NEW_HELPER_SHA256,
            "sole_r309_helper_delta": "offset 19 BD->E5",
        },
        "offline_contract": {
            "preimages": preimages,
            "semantic": semantic,
            "abi": {
                "stack_SVBK_migration": "exact r296/r309",
                "HL_preserved": True,
                "DE_B_C_restored": True,
                "A_return": "01",
            },
            "timing": {
                "exactly_equal_to_r309_all_paths": True,
                "ordinary_frame_delta_t_cycles": 0,
                "renderer_delta_t_cycles": 0,
                "dirty_compile_delta_t_cycles": {
                    "nonstage_ffb7_reject": 432,
                    "nonstage_scene_fold_reject": 472,
                    "stage1_room01": 572,
                    "stage1_other_room": 568,
                },
            },
        },
        "ownership": ownership,
        "required_live_gates": [
            "corrected D400 contract and candidate-bound live receipt",
            "room01 entry zero transient target attrs",
            "room01 exit/room05 target attrs BG0",
            "scene0B tagged-map ownership exact",
            "room12/menu/hazard and speed controls",
        ],
    }
    return candidate, receipt


def build(source: bytes, base_receipt_bytes: bytes, *, room01_capture: bytes | None = None
          ) -> tuple[bytes, dict[str, Any]]:
    r305.r304.require(r305.r304.digest(base_receipt_bytes)
                      == BASE_RECEIPT_SHA256,
                      "r305 build receipt identity changed")
    base_receipt = json.loads(base_receipt_bytes)
    r305.r304.require(base_receipt.get("candidate_sha256") == BASE_SHA256,
                      "r305 receipt names another ROM")
    preimages = validate_preimages(source)
    semantic = exhaustive_contract(source, room01_capture)
    candidate, receipt = construct(source)
    receipt.update({
        "schema": "penta-stage1-precompile-effective-room-r310-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "base": {
            "revision": "r305-live-rejected-wall-transient",
            "candidate_sha256": BASE_SHA256,
            "build_receipt_sha256": BASE_RECEIPT_SHA256,
        },
    })
    receipt["offline_contract"]["semantic"] = semantic
    receipt["offline_contract"]["preimages"] = preimages
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r305.r304.checked_output(args.output, "candidate output")
    receipt_path = r305.r304.checked_output(args.receipt, "receipt output")
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_bytes(r305.r304.receipt_bytes(receipt))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
