#!/usr/bin/env python3
"""Build r309: update contextual wall semantics immediately precompile.

r305's room hook updates C600 and invalidates both map keys, but a later
atomic publication can still compile the four dual-use wall IDs from stale
room context.  r306's later semantic-row selector and r308's postcompile map
writer both failed live causal gates.

Reuse the exact r296 wall-only precompile helper.  Fixed bank 1:$4309 maps an
otherwise wholly erased expansion bank 30 and calls its $6C80 entry before
the native D400 compiler.  The helper updates C624/C627/C630/C633 for the
exact reachable Stage-1 scenes, migrates the two mapper return frames from
SVBK1 to the compiler's required SVBK3, restores DE/B/C, and resumes stock at
$430E.  All r305 scene gates and its bank-21 room hook remain byte-exact.
Rejected r306/r308 and modular r307 are excluded.  No emulator is invoked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import build_stage1_room01_wall_scene0b_r296 as r296
import build_stage1_unified_scene0b_r305 as r305


ROOT = r305.ROOT
TMP = r305.TMP
BASE = r305.DEFAULT_OUTPUT
BASE_RECEIPT = r305.DEFAULT_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-precompile-wall-r309/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-precompile-wall-r309/build-receipt.json"

BASE_SHA256 = r305.EXPECTED_CANDIDATE_SHA256
BASE_RECEIPT_SHA256 = (
    "71a3a477a2be2fad9f0f83e24b9bdf6cacd940c7d772a546658bbaca1166c450"
)
R305_LIVE_REJECTION = BASE.parent / "live-scene0b-dcbb40/receipt.json"
R305_LIVE_REJECTION_SHA256 = (
    "7ceca21f33dabaf91437934549ba1fa1960f42bd4b03b901370b67f445a513b7"
)
R306_LIVE_REJECTION = (
    TMP / "stage1-effective-room-trampolines-r306/"
    "live-scene0b-dcbb40/receipt.json"
)
R306_LIVE_REJECTION_SHA256 = (
    "9e1f6d683202f8fc5847fb851b0cc615a7d7bf1ff1aa2ae7e134232314884452"
)
R308_LIVE_REJECTION = (
    TMP / "stage1-completed-map-wall-r308/live-scene0b-dcbb40/receipt.json"
)
R308_LIVE_REJECTION_SHA256 = (
    "2cdd1f522e9f8e3ef871181657ecc765685e097cacd8cd140235f9273b3968c0"
)
EXPECTED_CANDIDATE_SHA256 = (
    "212c97c35b27772ed29329d818e71ac186dda861fcc67bd168ce47fa229c5a25"
)

BANK_SIZE = r296.BANK_SIZE
HELPER_BANK = 30
HELPER_ADDR = r296.WALL_HELPER_ADDR
PRECOMPILE_SITE = r296.PRECOMPILE_SITE
OLD_PRECOMPILE = r296.OLD_PRECOMPILE
NEW_PRECOMPILE = bytes.fromhex("3E 1E CD 47 08 00")
HELPER = r296.build_wall_helper()
HELPER_SHA256 = (
    "ca21a115a20435a3b7d3166b39e71b6f7203c0f03f4b189dd9e55d7106078933"
)
TARGET_TILES = r296.TARGET_TILES
CHECKSUM_OFFSETS = r305.CHECKSUM_OFFSETS


def bank_offset(bank: int, address: int) -> int:
    return r305.r304.bank_offset(bank, address)


def owned_ranges() -> set[int]:
    helper = bank_offset(HELPER_BANK, HELPER_ADDR)
    return (
        set(range(PRECOMPILE_SITE,
                  PRECOMPILE_SITE + len(NEW_PRECOMPILE)))
        | set(range(helper, helper + len(HELPER)))
    )


def apply_model(
    values: dict[int, int], *, ffb7: int, scene: int, room: int,
) -> dict[int, int]:
    return r296.apply_wall_model(
        values, scene=scene, ffb7=ffb7, room=room
    )


def exhaustive_contract(source: bytes) -> dict[str, Any]:
    r305.r304.require(len(HELPER) == 63, "r296 helper width changed")
    r305.r304.require(r305.r304.digest(HELPER) == HELPER_SHA256,
                      "r296 helper identity changed")
    reachable_cases = 0
    accepted_scenes: set[int] = set()
    for ffb7 in range(256):
        for dd06 in range(4):
            for ffbf in range(4):
                scene = r296.reachable_scene(ffb7, dd06=dd06, ffbf=ffbf)
                accepted = r296.predicate_accepts(scene, ffb7)
                expected = ffb7 == 0x02
                r305.r304.require(accepted == expected,
                                  "reachable Stage predicate aliased")
                if accepted:
                    accepted_scenes.add(scene)
                reachable_cases += 1
    r305.r304.require(accepted_scenes == {0x02, 0x0A, 0x0B},
                      "accepted reachable scenes changed")
    r305.r304.require(not r296.predicate_accepts(0x18, 0x02),
                      "Stage-card splash admitted")
    r305.r304.require(not r296.predicate_accepts(0x03, 0x03),
                      "Stage2 admitted")

    initial = {tile: 0x80 + index
               for index, tile in enumerate(TARGET_TILES)}
    rows = []
    for label, ffb7, scene, room, expected in (
        ("room01_normal", 2, 0x02, 1, 0x06),
        ("room01_low_health", 2, 0x0B, 1, 0x06),
        ("room05_normal", 2, 0x02, 5, 0x00),
        ("room05_low_health", 2, 0x0B, 5, 0x00),
    ):
        result = apply_model(initial, ffb7=ffb7, scene=scene, room=room)
        r305.r304.require(result == {tile: expected for tile in TARGET_TILES},
                          f"wall model changed: {label}")
        rows.append({
            "case": label,
            "FFB7": f"{ffb7:02X}",
            "D880": f"{scene:02X}",
            "FFBD": f"{room:02X}",
            "C600_values": f"{expected:02X}",
        })
    for label, ffb7, scene in (
        ("splash", 2, 0x18), ("stage2", 3, 0x03),
    ):
        r305.r304.require(
            apply_model(initial, ffb7=ffb7, scene=scene, room=1) == initial,
            f"nonstage model mutated C600: {label}",
        )

    packed = r296.ROOM01_CAPTURE.read_bytes()
    expected_positions = {
        row * 24 + column for row, column in r296.ROOM01_TARGET_CELLS
    }
    actual_positions = {
        index for index, tile in enumerate(packed) if tile in TARGET_TILES
    }
    r305.r304.require(actual_positions == expected_positions
                      and len(actual_positions) == 35,
                      "room01 target position oracle changed")
    table = bank_offset(13, 0x7000)
    r305.r304.require(all(source[table + tile] == 0 for tile in TARGET_TILES),
                      "immutable default LUT target changed")
    return {
        "reachable_cases_exhausted": reachable_cases,
        "accepted_reachable_scenes": ["02", "0A", "0B"],
        "splash18_rejected": True,
        "stage2_scene03_rejected": True,
        "truth_rows": rows,
        "room01_target_positions": 35,
        "immutable_default_LUT_values": "00",
        "write_order": "C600 update immediately before native D400 compiler",
    }


def validate_live_rejections() -> dict[str, Any]:
    result: dict[str, Any] = {}
    sources = (
        ("r305", R305_LIVE_REJECTION, R305_LIVE_REJECTION_SHA256,
         BASE_SHA256, 56, 75),
        ("r306", R306_LIVE_REJECTION, R306_LIVE_REJECTION_SHA256,
         "8e170f2eaf3f718c924f47ac3be0c7dec1b5433ffd3975a5f5e299a7a60fb06d",
         56, 75),
        ("r308", R308_LIVE_REJECTION, R308_LIVE_REJECTION_SHA256,
         "5656241b51558b59c7a708754da32f7f7c9e9601a0719c91268f860f4f13c088",
         160, 73),
    )
    for revision, path, receipt_sha, rom_sha, total, first in sources:
        payload = path.read_bytes()
        r305.r304.require(r305.r304.digest(payload) == receipt_sha,
                          f"{revision} live rejection identity changed")
        receipt = json.loads(payload)
        mismatches = receipt.get("hazard_mismatch_frames", {})
        r305.r304.require(
            receipt.get("rom_sha256") == rom_sha
            and receipt.get("passed") is False
            and mismatches.get("total") == total
            and mismatches.get("first", {}).get("sample") == first,
            f"{revision} live rejection signature changed",
        )
        result[revision] = {
            "receipt_sha256": receipt_sha,
            "rom_sha256": rom_sha,
            "mismatch_frames": total,
            "first_mismatch_sample": first,
        }
    return result


def validate_preimages(source: bytes) -> dict[str, Any]:
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "wrong exact r305 base")
    r305.r304.require(
        source[PRECOMPILE_SITE:PRECOMPILE_SITE + len(OLD_PRECOMPILE)]
        == OLD_PRECOMPILE,
        "native precompile setup changed",
    )
    helper = bank_offset(HELPER_BANK, HELPER_ADDR)
    bank_start = HELPER_BANK * BANK_SIZE
    bank_end = bank_start + BANK_SIZE
    r305.r304.require(source[bank_start:bank_end]
                      == bytes([0xFF]) * BANK_SIZE,
                      "bank30 is no longer wholly erased")
    r305.r304.require(source[helper:helper + len(HELPER)]
                      == bytes([0xFF]) * len(HELPER),
                      "bank30 helper preimage changed")
    route_patterns = {
        "call_mapper": bytes.fromhex("3E 1E CD 61 00"),
        "jump_mapper": bytes.fromhex("3E 1E C3 61 00"),
        "fixed_dispatch": bytes.fromhex("3E 1E CD 47 08"),
    }
    for label, pattern in route_patterns.items():
        r305.r304.require(pattern not in source,
                          f"bank30 already has a route: {label}")
    r305.r304.require(
        source[0x0847:0x0850] == bytes.fromhex(
            "CD 61 00 CD 80 6C C3 61 00"
        ),
        "fixed banked helper dispatcher changed",
    )
    return {
        "precompile": "fixed bank1:$4309-$430E",
        "precompile_old": OLD_PRECOMPILE.hex(" ").upper(),
        "helper": "bank30:$6C80-$6CBE",
        "bank30_full_preimage": "16KiB FF",
        "prior_bank30_routes": 0,
        "fixed_dispatcher": "$0847 maps A, CALL $6C80, maps returned A",
    }


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    r305.r304.require(len(source) == len(candidate) == r305.r304.ROM_SIZE,
                      "ROM size changed")
    changed = r305.r304.delta(source, candidate)
    functional = r305.r304.delta(source, candidate, functional=True)
    allowed = owned_ranges() | CHECKSUM_OFFSETS
    r305.r304.require(changed <= allowed,
                      f"r309 escaped ownership: {sorted(changed-allowed)[:8]}")
    expected = {offset for offset in owned_ranges()
                if source[offset] != candidate[offset]}
    r305.r304.require(functional == expected,
                      "r309 functional delta differs from reviewed patch")
    r305.r304.require(
        candidate[PRECOMPILE_SITE:PRECOMPILE_SITE + len(NEW_PRECOMPILE)]
        == NEW_PRECOMPILE,
        "bank30 precompile route changed",
    )
    helper = bank_offset(HELPER_BANK, HELPER_ADDR)
    r305.r304.require(candidate[helper:helper + len(HELPER)] == HELPER,
                      "bank30 wall helper changed")

    # All other r305 owners are exact, including the existing bank21 r298
    # helper and bank31 mux.  Causal diagnostics/hardening are absent.
    wall21 = bank_offset(r305.WALL_BANK, r305.WALL_ADDR)
    r305.r304.require(candidate[wall21:wall21 + len(r305.NEW_WALL_HELPER)]
                      == source[wall21:wall21 + len(r305.NEW_WALL_HELPER)]
                      == r305.NEW_WALL_HELPER,
                      "r305 bank21 room hook changed")
    mux31 = bank_offset(r305.BANK31, r305.MUX_ADDR)
    r305.r304.require(candidate[mux31:mux31 + len(r305.MUX)]
                      == source[mux31:mux31 + len(r305.MUX)] == r305.MUX,
                      "r305 bank31 mux changed")
    for bank in (14, 16, 31):
        page = slice(bank * BANK_SIZE, (bank + 1) * BANK_SIZE)
        r305.r304.require(candidate[page] == source[page],
                          f"excluded bank{bank} component leaked into r309")
    return {
        "functional_changed_bytes": len(functional),
        "changed_offsets": [f"0x{x:06X}" for x in sorted(functional)],
        "escaped_bytes": 0,
        "r305_other_bytes_exact": True,
        "bank21_r298_helper_exact": True,
        "bank31_mux_exact": True,
        "rejected_r306_r308_excluded": True,
        "modular_r307_excluded": True,
        "native_bank14_exact": True,
    }


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    r305.r304.require(r305.r304.digest(base_receipt_bytes)
                      == BASE_RECEIPT_SHA256,
                      "r305 build receipt identity changed")
    base_receipt = json.loads(base_receipt_bytes)
    r305.r304.require(base_receipt.get("candidate_sha256") == BASE_SHA256,
                      "r305 receipt names another ROM")
    preimages = validate_preimages(source)
    semantic = exhaustive_contract(source)
    rejections = validate_live_rejections()

    rom = bytearray(source)
    allowed: set[int] = set()
    r305.patch_exact(
        rom, source, PRECOMPILE_SITE, OLD_PRECOMPILE, NEW_PRECOMPILE,
        allowed, "bank30 precompile helper route",
    )
    helper = bank_offset(HELPER_BANK, HELPER_ADDR)
    r305.patch_exact(
        rom, source, helper, bytes([0xFF]) * len(HELPER), HELPER,
        allowed, "exact r296 wall-only helper in bank30",
    )
    r305.r304.require(allowed == owned_ranges(),
                      "ownership construction drifted")
    r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    sha = r305.r304.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r305.r304.require(sha == EXPECTED_CANDIDATE_SHA256,
                          f"candidate identity drift: {sha}")

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-precompile-wall-r309-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base": {
            "revision": "r305-live-rejected-wall-transient",
            "candidate_sha256": BASE_SHA256,
            "build_receipt_sha256": BASE_RECEIPT_SHA256,
        },
        "candidate_sha256": sha,
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "causal_rejections": rejections,
        "root_cause": (
            "contextual C600 values must be selected immediately before each "
            "dirty D400 attribute compile, not at room hook or postpublication"
        ),
        "patch": {
            "precompile": "fixed bank1:$4309-$430E",
            "precompile_bytes": NEW_PRECOMPILE.hex(" ").upper(),
            "helper": "bank30:$6C80-$6CBE",
            "helper_bytes": len(HELPER),
            "helper_sha256": HELPER_SHA256,
            "target_C600": [f"$C6{tile:02X}" for tile in TARGET_TILES],
        },
        "offline_contract": {
            "preimages": preimages,
            "semantic": semantic,
            "abi": {
                "entry_stack_SVBK1": "[084D,430E,deeper bank1 frames]",
                "exit_stack_SVBK3": "[084D,430E,deeper frames untouched]",
                "mapper_shadow_DC09_written_before_SVBK3": True,
                "HL_preserved": True,
                "DE_restored": "C1A0",
                "B_restored": "C6",
                "C_preserved_via_FFE0": True,
                "A_return": "01 for stock bank1 restore",
            },
            "timing": {
                "ordinary_frame_delta_t_cycles": 0,
                "renderer_delta_t_cycles": 0,
                "scope": "dirty attribute compilations only",
                "original_setup_t_cycles": 28,
                "new_shell_excluding_helper_t_cycles": 252,
                "helper_t_cycles": {
                    "nonstage_ffb7_reject": 208,
                    "nonstage_scene_fold_reject": 248,
                    "stage1_room01": 348,
                    "stage1_other_room": 344,
                },
                "delta_t_cycles": {
                    "nonstage_ffb7_reject": 432,
                    "nonstage_scene_fold_reject": 472,
                    "stage1_room01": 572,
                    "stage1_other_room": 568,
                },
            },
        },
        "ownership": ownership,
        "required_live_gates": [
            "room01 entry has zero target attr transient frames",
            "room01 exit/room05 target IDs compile to BG0",
            "scene0B publications retain tagged-map ownership",
            "room12 seam and hazard-menu controls remain exact",
            "full reported-regression and speed gates",
        ],
    }
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
