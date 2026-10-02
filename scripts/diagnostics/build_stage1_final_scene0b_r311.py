#!/usr/bin/env python3
"""Build r311: exact r310 behavior plus the audited bank-16 installer mirror.

r310 is the live-passing Stage-1 scene-$0B/wall candidate.  Its only remaining
static cold-start risk is the independently reviewed r307 finding: the shared
WRAM installer can execute while ROM bank 16 is mapped, but that mirror still
contains stale/zero source fragments and publishes DF51=$A8 before installing
DBF1-DBFC.

This composition starts from the exact r310 ROM and applies only r307's four
bank-16 source/continuation replacements.  Every r310 behavioral byte remains
identical; the bank-16 installer is then simulated exhaustively against the
canonical bank-13 image.  No emulator is invoked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import build_stage1_bank16_installer_mirror_r307 as r307
import build_stage1_precompile_effective_room_r310 as r310


r305 = r310.r305
ROOT = r310.ROOT
TMP = r310.TMP
BASE = r310.DEFAULT_OUTPUT
BASE_RECEIPT = r310.DEFAULT_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-final-scene0b-r311/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-final-scene0b-r311/build-receipt.json"

BASE_SHA256 = r310.EXPECTED_CANDIDATE_SHA256
BASE_RECEIPT_SHA256 = (
    "ddc5edeb0113edc78b913a3187a201fb86f0f31b3271915621fd5eb6c4d970df"
)
BASE_SCHEMA = "penta-stage1-precompile-effective-room-r310-build-v1"
R310_LIVE_RECEIPT = (
    TMP / "stage1-precompile-effective-room-r310/"
    "publication-owned-oracle-r2/receipt.json"
)
R310_LIVE_RECEIPT_SHA256 = (
    "b7b93403fa901d8a5b7652740197bcd3302377356ef3d1f0c7f3493d33b62fd4"
)
R307_CANDIDATE = r307.DEFAULT_OUTPUT
R307_RECEIPT = r307.DEFAULT_RECEIPT
R307_CANDIDATE_SHA256 = r307.EXPECTED_CANDIDATE_SHA256
R307_RECEIPT_SHA256 = (
    "a36bc024705b9df3388b83e008f6add576a590db35a92e36110d2935a8b50bc5"
)
EXPECTED_CANDIDATE_SHA256 = (
    "be8e78761470b811111e74d47c1cbb9923e34d136c420ccb76314a6be22ab84d"
)

CHECKSUM_OFFSETS = r305.r304.CHECKSUM_OFFSETS
MIRROR_BANK = r307.MIRROR_BANK
COLD_EXTENSION_BYTES = r307.EXTENSION_REGION[2]
# Prefix: LD DE,d16 + LD HL,d16 + LD C,d8 + CALL = 12+12+8+24T.
# fixed:$09B3 copy is 52*n+40T, including PUSH AF=16T, POP AF=12T,
# RET=16T, and the final untaken JR=8T.
COLD_EXTENSION_PREFIX_T = 56
COLD_COPY_T = 52 * COLD_EXTENSION_BYTES + 40
COLD_INSTALLER_DELTA_T = COLD_EXTENSION_PREFIX_T + COLD_COPY_T

# r310 inherits r296's deliberately tiny stack-migration scratch lifetime.
# Keep the dependency explicit in the final receipt: FFE0 is shared HRAM, not
# an allocation that another caller may safely extend or reuse concurrently.
FFE0_SCRATCH_ENTRY = bytes.fromhex("79 E0 E0")
FFE0_SCRATCH_RESTORE = bytes.fromhex("F0 E0 4F")
PRECOMPILE_DI_ADDR = 0x4302
NATIVE_FFE0_REINIT_ADDR = 0x430E
NATIVE_FFE0_REINIT = bytes.fromhex("00 3E 18 E0 E0 CD 00 D4")


def source_release_caveats(candidate: bytes) -> dict[str, Any]:
    """Pin scratch lifetime and contextual palette policy without captures."""
    helper = r310.bank_offset(r310.HELPER_BANK, r310.HELPER_ADDR)
    helper_blob = candidate[helper:helper + len(r310.NEW_HELPER)]
    r305.r304.require(helper_blob.startswith(FFE0_SCRATCH_ENTRY),
                      "r310 FFE0 scratch writer changed")
    r305.r304.require(FFE0_SCRATCH_RESTORE in helper_blob,
                      "r310 FFE0 scratch restore changed")
    r305.r304.require(candidate[PRECOMPILE_DI_ADDR] == 0xF3,
                      "precompile DI ownership changed")
    r305.r304.require(
        candidate[
            NATIVE_FFE0_REINIT_ADDR:
            NATIVE_FFE0_REINIT_ADDR + len(NATIVE_FFE0_REINIT)
        ] == NATIVE_FFE0_REINIT,
        "native FFE0 row-counter reinitialization changed",
    )

    immutable_lut = r310.bank_offset(13, 0x7000)
    r305.r304.require(
        all(candidate[immutable_lut + tile] == 0
            for tile in r310.TARGET_TILES),
        "default/same-ID BG0 corpus changed",
    )
    room_oracle = json.loads(r310.r296.ROOM_ORACLE_FIXTURE.read_text())
    room05 = room_oracle["room05_patterned_floor_control"]
    r305.r304.require(
        int(room05["expected_attr"]) == 0
        and set(map(int, room05["patterned_floor_tile_ids"]))
        == {0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x3A, 0x3B, 0x3C, 0x3D},
        "independent room05 BG0 control changed",
    )

    return {
        "FFE0_shared_scratch": {
            "classification": (
                "inherited r296/r310 shared-HRAM lifetime dependency; "
                "r311 does not alter it"
            ),
            "save_restore": (
                "bank30:$6C80 saves native C with 79 E0 E0 and restores it "
                "with F0 E0 4F"
            ),
            "bounded_atomic_window": (
                "fixed bank1:$4302 DI precedes the banked helper; stock "
                "$430E-$4315 writes FFE0=$18 before the first D400 row call"
            ),
            "fragility": (
                "safe only while the exact DI callsite, mapper return, and "
                "immediate native overwrite remain pinned; any asynchronous "
                "or relocated reuse requires dedicated scratch and a new ABI audit"
            ),
        },
        "global_BG6_policy_rejected": {
            "proposal": (
                "set immutable Stage-1 LUT IDs $24/$27/$30/$33 to BG6 globally"
            ),
            "default_and_room05_controls": (
                "bank13:$7000 keeps all four same-ID defaults at BG0; the "
                "room05 same-ID oracle accepts BG0 and rejects BG6, and the "
                "independent $2A-$2E/$3A-$3D room05 floor class is also BG0"
            ),
            "publication_epoch_correction": (
                "a room commit without a new physical-map publication retains "
                "the prior publication's attributes; that retained BG6 is not "
                "evidence for a global LUT mutation or an active-map clear"
            ),
            "decision": (
                "retain immutable BG0 defaults and select BG6 only for the "
                "FFE5==01 precompile context"
            ),
        },
    }


def reviewed_release_caveats(candidate: bytes, room01_capture: bytes | None = None
                             ) -> dict[str, Any]:
    contract = source_release_caveats(candidate)
    packed = r310.r296.ROOM01_CAPTURE.read_bytes() if room01_capture is None else room01_capture
    target_positions = {
        index for index, tile in enumerate(packed)
        if tile in r310.TARGET_TILES
    }
    reviewed_positions = {
        row * 24 + column for row, column in r310.r296.ROOM01_TARGET_CELLS
    }
    r305.r304.require(
        len(target_positions) == 35 and target_positions == reviewed_positions,
        "room01 contextual BG6 corpus changed",
    )
    contract["global_BG6_policy_rejected"]["room01_corpus"] = (
        "the pinned 24x24 room01 capture contains exactly 35 target-ID "
        "cells, all at reviewed wall-companion positions requiring BG6"
    )
    return contract


def owned_ranges() -> set[int]:
    return r307.owned_ranges()


def composition_contract(
    source: bytes, r307_candidate: bytes, candidate: bytes, *, reference: bytes | None = None,
) -> dict[str, Any]:
    r305_ranges = r310.owned_ranges()
    r307_ranges = owned_ranges()
    r305.r304.require(not (r305_ranges & r307_ranges),
                      "r310 and r307 functional ownership overlaps")
    r305.r304.require(
        all(offset // r305.r304.BANK_SIZE == MIRROR_BANK
            for offset in r307_ranges),
        "r307 ownership escaped bank16",
    )

    r305_base = r310.BASE.read_bytes() if reference is None else reference
    r305.r304.require(r305.r304.digest(r305_base) == r310.BASE_SHA256,
                      "r310's exact r305 base changed")
    r307_delta = r305.r304.delta(
        r305_base, r307_candidate, functional=True
    )
    expected_r307_delta = {
        offset for offset in r307_ranges
        if r305_base[offset] != r307_candidate[offset]
    }
    r305.r304.require(r307_delta == expected_r307_delta,
                      "pinned r307 artifact has an unexpected delta")

    r310_delta = r305.r304.delta(r305_base, source, functional=True)
    expected_r310_delta = {
        offset for offset in r305_ranges
        if r305_base[offset] != source[offset]
    }
    r305.r304.require(r310_delta == expected_r310_delta,
                      "exact r310 behavioral delta changed")
    r305.r304.require(not (r310_delta & r307_delta),
                      "r310/r307 changed-byte sets overlap")

    # Byte-for-byte union proof: r311 takes r307's reviewed byte wherever its
    # overlay differs from r305 and exact r310 everywhere else.
    combined = bytearray(source)
    for offset in r307_delta:
        combined[offset] = r307_candidate[offset]
    r305.r304.update_checksums(combined)
    r305.r304.require(bytes(combined) == candidate,
                      "candidate is not the exact r310+r307 union")

    for offset in range(len(candidate)):
        if offset in r307_delta or offset in CHECKSUM_OFFSETS:
            continue
        r305.r304.require(candidate[offset] == source[offset],
                          f"r310 byte changed at 0x{offset:06X}")
    for offset in r307_ranges:
        r305.r304.require(candidate[offset] == r307_candidate[offset],
                          f"r307 overlay byte changed at 0x{offset:06X}")

    return {
        "r310_functional_changed_bytes_from_r305": len(r310_delta),
        "r307_functional_changed_bytes_from_r305": len(r307_delta),
        "r310_r307_overlap_bytes": 0,
        "r311_union_exact": True,
        "r310_bytes_exact_outside_r307_and_checksums": True,
        "r307_owned_bytes_equal_pinned_r307": True,
        "r307_owned_bank": MIRROR_BANK,
    }


def validate_preimages(
    source: bytes,
    base_receipt_bytes: bytes,
    r307_candidate: bytes,
    r307_receipt_bytes: bytes,
    live_receipt_bytes: bytes,
) -> dict[str, Any]:
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "wrong exact r310 base")
    r305.r304.require(
        r305.r304.digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
        "r310 build receipt identity changed",
    )
    base_receipt = json.loads(base_receipt_bytes)
    r305.r304.require(base_receipt.get("schema") == BASE_SCHEMA,
                      "r310 build receipt schema changed")
    r305.r304.require(base_receipt.get("candidate_sha256") == BASE_SHA256,
                      "r310 receipt names another ROM")

    r305.r304.require(
        r305.r304.digest(r307_candidate) == R307_CANDIDATE_SHA256,
        "r307 candidate identity changed",
    )
    r305.r304.require(
        r305.r304.digest(r307_receipt_bytes) == R307_RECEIPT_SHA256,
        "r307 receipt identity changed",
    )
    r307_receipt = json.loads(r307_receipt_bytes)
    r305.r304.require(
        r307_receipt.get("schema")
        == "penta-stage1-bank16-installer-mirror-r307-build-v1",
        "r307 receipt schema changed",
    )
    r305.r304.require(
        r307_receipt.get("candidate_sha256") == R307_CANDIDATE_SHA256,
        "r307 receipt names another ROM",
    )

    r305.r304.require(
        r305.r304.digest(live_receipt_bytes) == R310_LIVE_RECEIPT_SHA256,
        "r310 corrected live receipt identity changed",
    )
    live = json.loads(live_receipt_bytes)
    r305.r304.require(live.get("rom_sha256") == BASE_SHA256,
                      "r310 live receipt names another ROM")
    r305.r304.require(live.get("passed") is True,
                      "r310 corrected live gate did not pass")
    checks = live.get("checks", {})
    r305.r304.require(checks and all(checks.values()),
                      "r310 corrected live receipt contains a failed check")
    publications = live.get("hazard_publication_counters", {})
    r305.r304.require(
        publications.get("expected_plane_promotions") == 40
        and publications.get("expected_plane_invalid_promotions") == 0
        and publications.get("expected_plane_pending") == 0,
        "r310 publication-owned oracle evidence changed",
    )
    r305.r304.require(
        live.get("maximum_unexpected_lut_mismatches") == 0,
        "r310 live receipt contains an unexpected attribute mismatch",
    )

    # r310 deliberately excluded bank16, so all r307 structural preimages
    # must still be exact before composition.
    mirror_preimages = r307.validate_structural_preimages(source)
    return {
        "r310_candidate_sha256": BASE_SHA256,
        "r310_build_receipt_sha256": BASE_RECEIPT_SHA256,
        "r310_corrected_live_receipt_sha256": R310_LIVE_RECEIPT_SHA256,
        "r310_live_checks_all_pass": True,
        "r310_live_expected_plane_promotions": 40,
        "r310_live_unexpected_attr_mismatches": 0,
        "r307_candidate_sha256": R307_CANDIDATE_SHA256,
        "r307_receipt_sha256": R307_RECEIPT_SHA256,
        "r307_structural_preimages": mirror_preimages,
    }


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    r305.r304.require(
        len(source) == len(candidate) == r305.r304.ROM_SIZE,
        "candidate size changed",
    )
    changed = r305.r304.delta(source, candidate)
    functional = r305.r304.delta(source, candidate, functional=True)
    expected = {
        offset for offset in owned_ranges()
        if source[offset] != candidate[offset]
    }
    r305.r304.require(functional == expected,
                      "r311 delta differs from exact r307 overlay")
    r305.r304.require(changed <= owned_ranges() | CHECKSUM_OFFSETS,
                      "r311 escaped bank16/checksum ownership")

    # The exact r310 behavior component remains byte-identical.
    precompile = r310.PRECOMPILE_SITE
    helper = r310.bank_offset(r310.HELPER_BANK, r310.HELPER_ADDR)
    r305.r304.require(
        candidate[precompile:precompile + len(r310.NEW_PRECOMPILE)]
        == r310.NEW_PRECOMPILE,
        "r310 precompile route changed",
    )
    r305.r304.require(
        candidate[helper:helper + len(r310.NEW_HELPER)] == r310.NEW_HELPER,
        "r310 effective-room helper changed",
    )
    wall = r310.bank_offset(r305.WALL_BANK, r305.WALL_ADDR)
    r305.r304.require(
        candidate[wall:wall + len(r305.NEW_WALL_HELPER)]
        == r305.NEW_WALL_HELPER,
        "r305/r310 room lifecycle helper changed",
    )
    mux = r310.bank_offset(r305.BANK31, r305.MUX_ADDR)
    r305.r304.require(candidate[mux:mux + len(r305.MUX)] == r305.MUX,
                      "r305/r310 bank31 mux changed")

    return {
        "functional_changed_bytes_from_r310": len(functional),
        "changed_offsets_from_r310": [
            f"0x{offset:06X}" for offset in sorted(functional)
        ],
        "owned_ranges": [
            "bank16:$5546-$5569",
            "bank16:$56E1-$56ED",
            "bank16:$56FA-$56FE",
            "bank16:$7B13-$7B20",
        ],
        "escaped_bytes": 0,
        "r310_precompile_route_exact": True,
        "r310_effective_room_helper_exact": True,
        "r310_room_lifecycle_helper_exact": True,
        "r310_bank31_mux_exact": True,
    }


def construct(source: bytes, *, reference: bytes) -> tuple[bytes, dict[str, Any]]:
    """Compose exact r311 using a generated r307 branch, not live evidence."""
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "wrong exact r310 base")
    r307_candidate, _ = r307.construct(reference)
    r305.r304.require(r305.r304.digest(r307_candidate) == R307_CANDIDATE_SHA256,
                      "r307 candidate identity changed")
    preimages = {
        "r310_candidate_sha256": BASE_SHA256,
        "r307_candidate_sha256": R307_CANDIDATE_SHA256,
        "r307_structural_preimages": r307.validate_structural_preimages(source),
    }

    rom = bytearray(source)
    for offset, old, new, label in r307.patch_regions():
        r305.r304.require(rom[offset:offset + len(old)] == old,
                          f"{label} changed before r311 composition")
        r305.r304.require(len(old) == len(new),
                          f"{label} width changed")
        rom[offset:offset + len(new)] = new
    r305.r304.update_checksums(rom)
    candidate = bytes(rom)

    ownership = validate_candidate(source, candidate)
    composition = composition_contract(source, r307_candidate, candidate, reference=reference)
    installer = r307.installer_contract(candidate)
    release_caveats = source_release_caveats(candidate)
    sha = r305.r304.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r305.r304.require(sha == EXPECTED_CANDIDATE_SHA256,
                          f"r311 candidate identity drift: {sha}")

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-final-scene0b-r311-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "base": {
            "revision": "r310",
            "candidate_sha256": BASE_SHA256,
        },
        "overlay": {
            "revision": "r307-source-bank16-installer-mirror",
            "candidate_sha256": R307_CANDIDATE_SHA256,
        },
        "candidate_sha256": sha,
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "root_cause": (
            "bank16's bank-relative cold installer could publish DF51=A8 "
            "after stale DA13 and missing DBDF-DBFC source copies"
        ),
        "patch": {
            "functional_scope": "exact four r307 bank16 ranges only",
            "behavioral_base": "exact r310 everywhere else",
            "cold_extension_bytes": COLD_EXTENSION_BYTES,
        },
        "preimage_contract": preimages,
        "ownership": ownership,
        "composition_contract": composition,
        "installer_contract": installer,
        "reviewed_release_caveats": release_caveats,
        "timing_t_cycles": {
            "renderer_delta_from_r310": 0,
            "ordinary_frame_delta_from_r310": 0,
            "scene0b_hot_path_delta_from_r310": 0,
            "bank13_installer_delta_from_r310": 0,
            "bank16_cold_installer_delta_from_r310": COLD_INSTALLER_DELTA_T,
            "bank16_cold_delta_derivation": (
                "56T prefix + (52*12+40)T AF-preserving fixed:$09B3 copy"
            ),
        },
        "required_live_gates": [
            "candidate-bound publication-owned scene0B/wall oracle",
            "fresh/cold bank16 installer emits canonical DA00-DAFF and DB80-DBFC",
            "menu roundtrip and rendered hazard continuity",
            "release speed matrix",
        ],
        "decision": "CONSTRUCTION_ONLY_LIVE_GATES_REQUIRED",
    }
    return candidate, receipt


def build(
    source: bytes,
    base_receipt_bytes: bytes,
    r307_candidate: bytes,
    r307_receipt_bytes: bytes,
    live_receipt_bytes: bytes,
    *, room01_capture: bytes | None = None, reference: bytes | None = None,
) -> tuple[bytes, dict[str, Any]]:
    preimages = validate_preimages(
        source, base_receipt_bytes, r307_candidate,
        r307_receipt_bytes, live_receipt_bytes,
    )
    r305_base = r310.BASE.read_bytes() if reference is None else reference
    candidate, receipt = construct(source, reference=r305_base)
    # Keep the audit of the supplied branch, not just its generated counterpart.
    composition = composition_contract(source, r307_candidate, candidate, reference=r305_base)
    release_caveats = reviewed_release_caveats(candidate, room01_capture)
    receipt.update({
        "schema": "penta-stage1-final-scene0b-r311-build-v1",
        "status": "STATIC_PASS_R311_LIVE_GATES_REQUIRED",
        "base": {
            "revision": "r310-live-pass-publication-owned-oracle",
            "candidate_sha256": BASE_SHA256,
            "build_receipt_sha256": BASE_RECEIPT_SHA256,
            "live_receipt_sha256": R310_LIVE_RECEIPT_SHA256,
        },
        "overlay": {
            "revision": "r307-static-pass-bank16-installer-mirror",
            "candidate_sha256": R307_CANDIDATE_SHA256,
            "build_receipt_sha256": R307_RECEIPT_SHA256,
        },
        "preimage_contract": preimages,
        "composition_contract": composition,
        "reviewed_release_caveats": release_caveats,
        "decision": "STATIC_FINAL_COMPOSITION_LIVE_GATES_REQUIRED",
    })
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--r307-candidate", type=Path, default=R307_CANDIDATE)
    parser.add_argument("--r307-receipt", type=Path, default=R307_RECEIPT)
    parser.add_argument("--r310-live-receipt", type=Path,
                        default=R310_LIVE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r305.r304.checked_output(args.output, "candidate output")
    receipt_path = r305.r304.checked_output(args.receipt, "receipt output")
    candidate, receipt = build(
        args.base.read_bytes(),
        args.base_receipt.read_bytes(),
        args.r307_candidate.read_bytes(),
        args.r307_receipt.read_bytes(),
        args.r310_live_receipt.read_bytes(),
    )
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
