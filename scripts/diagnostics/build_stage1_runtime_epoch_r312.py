#!/usr/bin/env python3
"""Build r312: invalidate stale serialized Stage-1 WRAM runtimes.

The exact r311 operator replays proved that ROM-CRC-only retargeting can keep
an older, ABI-incompatible DA00-DAFF payload resident while DF51 still carries
the historical ready value $A8.  All three lazy-installer gates consequently
skip the candidate-owned copy.  In particular, old SVBK1:$DAD7 jumps directly
to $DAB9 for scene $0B, bypassing the repaired split-key consumer and every
physical attribute publication.

This overlay changes only the runtime epoch byte: the three installer compares
and the post-copy publication in both source banks move from $A8 to $A9.  Any
old savestate therefore installs the complete candidate payload once; a
current runtime remains on the zero-cost skip path.  No emulator is invoked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import build_stage1_final_scene0b_r311 as r311


r305 = r311.r305
ROOT = r311.ROOT
TMP = r311.TMP
BASE = r311.DEFAULT_OUTPUT
BASE_RECEIPT = r311.DEFAULT_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-runtime-epoch-r312/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-runtime-epoch-r312/build-receipt.json"

BASE_SHA256 = r311.EXPECTED_CANDIDATE_SHA256
BASE_RECEIPT_SHA256 = (
    "5db65ed067ed1bda36e933c466e77f88aba51a6212b8baa7c96938f800587130"
)
BASE_SCHEMA = "penta-stage1-final-scene0b-r311-build-v1"
REJECTED_LIVE_RECEIPT = (
    TMP / "stage1-final-scene0b-r311/live-scene0b-r1/receipt.json"
)
REJECTED_LIVE_RECEIPT_SHA256 = (
    "c1960e14637ce4e5d2dcd554411a1112c9d396ca5b3e158a04395352d6bba8c9"
)
EXPECTED_CANDIDATE_SHA256 = (
    "dca72f535850d4445fc8f27d032628e63b1a9b7dee0f8012fbfee9b69c4a1951"
)

BANKS = (13, 16)
OLD_EPOCH = 0xA8
NEW_EPOCH = 0xA9
GATE_STARTS = (0x6B10, 0x6B19, 0x6B80)
OLD_GATE = bytes.fromhex("FA 51 DF FE A8 C4 BF 7C")
NEW_GATE = bytes.fromhex("FA 51 DF FE A9 C4 BF 7C")
GATE_EPOCH_INDEX = 4
FINALIZER_ADDR = 0x5551
OLD_FINALIZER = bytes.fromhex("CD 16 55 3E A8 EA 51 DF E1 D1 C1 C9")
NEW_FINALIZER = bytes.fromhex("CD 16 55 3E A9 EA 51 DF E1 D1 C1 C9")
FINALIZER_EPOCH_INDEX = 4
CHECKSUM_OFFSETS = r311.CHECKSUM_OFFSETS

# Both authenticated r311 source captures contain this exact stale DAD7 image.
# Only bytes 7-9 differ from the r311 candidate source: JP NZ,$DAB9 became the
# fixed-bank CALL that admits scene $0B and then continues into bank21:$4100.
CAPTURED_STALE_DAD7 = bytes.fromhex(
    "FA 80 D8 E6 F7 FE 02 C2 B9 DA 3E 15 CD 61 00 C3 00 41 "
    "E1 D1 C1 F5 FA 80 D8 FE 08 28 02 18 00 F3 F1 F1 F1 "
    "3E 16 C3 47 08 00"
)


def bank_offset(bank: int, address: int) -> int:
    return r305.r304.bank_offset(bank, address)


def owned_ranges() -> set[int]:
    result = {
        bank_offset(bank, address) + GATE_EPOCH_INDEX
        for bank in BANKS
        for address in GATE_STARTS
    }
    result |= {
        bank_offset(bank, FINALIZER_ADDR) + FINALIZER_EPOCH_INDEX
        for bank in BANKS
    }
    return result


def desired_dad7(payload: bytes, bank: int) -> bytes:
    start = bank_offset(bank, r305.ATTR_GATEWAY_ADDR)
    return payload[start:start + r305.RUNTIME_LENGTH]


def validate_preimages(
    source: bytes, base_receipt_bytes: bytes, rejected_receipt_bytes: bytes,
) -> dict[str, Any]:
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "r312 requires exact r311")
    r305.r304.require(
        r305.r304.digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
        "r311 build receipt identity changed",
    )
    base_receipt = json.loads(base_receipt_bytes)
    r305.r304.require(base_receipt.get("schema") == BASE_SCHEMA,
                      "r311 build receipt schema changed")
    r305.r304.require(base_receipt.get("candidate_sha256") == BASE_SHA256,
                      "r311 build receipt names another candidate")

    r305.r304.require(
        r305.r304.digest(rejected_receipt_bytes)
        == REJECTED_LIVE_RECEIPT_SHA256,
        "r311 rejected live receipt identity changed",
    )
    rejected = json.loads(rejected_receipt_bytes)
    r305.r304.require(
        rejected.get("schema")
        == "penta-stage1-scene0b-live-menu-roundtrip-v1",
        "r311 rejected live receipt schema changed",
    )
    r305.r304.require(rejected.get("candidate_sha256") == BASE_SHA256,
                      "r311 rejected live receipt names another candidate")
    r305.r304.require(rejected.get("status") == "FAIL",
                      "r311 live receipt is no longer the rejected evidence")
    failed = {name for name, passed in rejected.get("checks", {}).items()
              if passed is False}
    r305.r304.require(failed == {
        "wall edges and visible attributes are clean in every live phase",
        "reported yellow-trail and gray-spike signatures are absent",
    }, "r311 rejected live symptom set changed")

    source_contract = source_preimages(source)
    canonical = desired_dad7(source, BANKS[0])
    differences = {
        index for index, pair in enumerate(
            zip(CAPTURED_STALE_DAD7, canonical, strict=True)
        ) if pair[0] != pair[1]
    }
    r305.r304.require(differences == {7, 8, 9},
                      "captured/current DAD7 ABI difference changed")
    r305.r304.require(CAPTURED_STALE_DAD7[7:10]
                      == bytes.fromhex("C2 B9 DA"),
                      "captured DAD7 reject transfer changed")
    return {
        "r311_build_receipt_sha256": BASE_RECEIPT_SHA256,
        "r311_rejected_live_receipt_sha256": REJECTED_LIVE_RECEIPT_SHA256,
        "r311_failed_checks": sorted(failed),
        "captured_DAD7_sha256": r305.r304.digest(CAPTURED_STALE_DAD7),
        "candidate_DAD7_sha256": source_contract["candidate_DAD7_sha256"],
        "DAD7_changed_indices": sorted(differences),
        "captured_transfer": "JP NZ,$DAB9",
        "candidate_transfer": "CALL NZ,fixed:$0013",
    }


def source_preimages(source: bytes) -> dict[str, Any]:
    """Validate epoch and canonical runtime sources, not old captures."""
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "r312 requires exact r311")

    for bank in BANKS:
        for address in GATE_STARTS:
            start = bank_offset(bank, address)
            r305.r304.require(
                source[start:start + len(OLD_GATE)] == OLD_GATE,
                f"bank{bank}:${address:04X} runtime epoch gate changed",
            )
        start = bank_offset(bank, FINALIZER_ADDR)
        r305.r304.require(
            source[start:start + len(OLD_FINALIZER)] == OLD_FINALIZER,
            f"bank{bank} runtime epoch finalizer changed",
        )

    canonical = desired_dad7(source, BANKS[0])
    mirror = desired_dad7(source, BANKS[1])
    r305.r304.require(
        len(canonical) == r305.RUNTIME_LENGTH and canonical == mirror,
        "r311 DAD7 source mirrors differ",
    )
    r305.r304.require(canonical[7:10] == bytes.fromhex("C4 13 00"),
                      "candidate DAD7 fixed-bridge transfer changed")
    return {
        "candidate_DAD7_sha256": r305.r304.digest(canonical),
        "source_mirrors_equal": True,
        "candidate_transfer": "CALL NZ,fixed:$0013",
    }


def epoch_contract(candidate: bytes) -> dict[str, Any]:
    decisions = {value: value != NEW_EPOCH for value in range(256)}
    r305.r304.require(sum(decisions.values()) == 255,
                      "runtime epoch gate is not an exact equality gate")
    r305.r304.require(decisions[OLD_EPOCH],
                      "historical A8 runtime would not reinstall")
    r305.r304.require(not decisions[NEW_EPOCH],
                      "current A9 runtime would reinstall")

    installed = r311.r307.simulate_installer(candidate, BANKS[0])
    mirrored = r311.r307.simulate_installer(candidate, BANKS[1])
    r305.r304.require(installed == mirrored,
                      "r312 bank13/bank16 installer output differs")
    runtime = installed["DA8E-DAFF"]
    offset = r305.RUNTIME_RELOCATED_ADDR - 0xDA8E
    installed_dad7 = runtime[offset:offset + r305.RUNTIME_LENGTH]
    r305.r304.require(installed_dad7 == desired_dad7(candidate, BANKS[0]),
                      "installer does not publish candidate DAD7")
    r305.r304.require(installed_dad7[7:10]
                      == bytes.fromhex("C4 13 00"),
                      "installed DAD7 still bypasses scene0B mux")

    # First observation of a legacy A8 epoch must copy and publish A9; the
    # next observation is the unchanged hot skip. This is the entire state
    # transition introduced by r312.
    epoch = OLD_EPOCH
    first_installs = decisions[epoch]
    if first_installs:
        epoch = NEW_EPOCH
    second_installs = decisions[epoch]
    r305.r304.require(first_installs and not second_installs,
                      "legacy-to-current epoch transition is not one-shot")
    return {
        "values_exhausted": 256,
        "installing_values": 255,
        "skip_value": f"{NEW_EPOCH:02X}",
        "legacy_A8_first_gate_installs": first_installs,
        "second_gate_skips": not second_installs,
        "bank13_bank16_installer_images_equal": True,
        "installed_DAD7_sha256": r305.r304.digest(installed_dad7),
        "scene0B_route_after_install": (
            "DAD7 CALL NZ,$0013 -> bank31 attr mux -> bank21:$4100"
        ),
    }


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    r305.r304.require(
        len(source) == len(candidate) == r305.r304.ROM_SIZE,
        "r312 candidate size changed",
    )
    functional = r305.r304.delta(source, candidate, functional=True)
    expected = {offset for offset in owned_ranges()
                if source[offset] != candidate[offset]}
    r305.r304.require(functional == expected == owned_ranges(),
                      "r312 functional delta is not the exact epoch patch")
    changed = r305.r304.delta(source, candidate)
    r305.r304.require(changed <= owned_ranges() | CHECKSUM_OFFSETS,
                      "r312 escaped epoch/checksum ownership")
    for bank in BANKS:
        for address in GATE_STARTS:
            start = bank_offset(bank, address)
            r305.r304.require(
                candidate[start:start + len(NEW_GATE)] == NEW_GATE,
                f"bank{bank}:${address:04X} new epoch gate changed",
            )
        start = bank_offset(bank, FINALIZER_ADDR)
        r305.r304.require(
            candidate[start:start + len(NEW_FINALIZER)] == NEW_FINALIZER,
            f"bank{bank} new epoch finalizer changed",
        )
    return {
        "functional_changed_bytes": len(functional),
        "changed_offsets": [f"0x{offset:06X}" for offset in sorted(functional)],
        "owned_ranges": [
            "bank13/16:$6B14,$6B1D,$6B84 compare immediates",
            "bank13/16:$5555 installed-epoch immediate",
        ],
        "escaped_bytes": 0,
        "all_non_epoch_r311_bytes_exact": True,
    }


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    preimages = source_preimages(source)
    rom = bytearray(source)
    for bank in BANKS:
        for address in GATE_STARTS:
            offset = bank_offset(bank, address)
            r305.r304.require(rom[offset:offset + len(OLD_GATE)] == OLD_GATE,
                              "epoch gate changed before patch")
            rom[offset + GATE_EPOCH_INDEX] = NEW_EPOCH
        offset = bank_offset(bank, FINALIZER_ADDR)
        r305.r304.require(
            rom[offset:offset + len(OLD_FINALIZER)] == OLD_FINALIZER,
            "epoch finalizer changed before patch",
        )
        rom[offset + FINALIZER_EPOCH_INDEX] = NEW_EPOCH
    r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    semantic = epoch_contract(candidate)
    sha = r305.r304.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r305.r304.require(sha == EXPECTED_CANDIDATE_SHA256,
                          f"r312 candidate identity drift: {sha}")

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-runtime-epoch-r312-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "base": {
            "revision": "r311",
            "candidate_sha256": BASE_SHA256,
        },
        "candidate_sha256": sha,
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "root_cause": (
            "a legacy DF51=A8 epoch must not skip installation of the "
            "current DA00-DAFF runtime and fixed-bank scene0B gateway"
        ),
        "patch": {
            "runtime_epoch": "DF51 A8->A9",
            "functional_scope": "eight immediate bytes only",
            "gate_sites": {
                f"bank{bank}": [f"${address + GATE_EPOCH_INDEX:04X}"
                                 for address in GATE_STARTS]
                for bank in BANKS
            },
            "publication_sites": {
                f"bank{bank}": f"${FINALIZER_ADDR + FINALIZER_EPOCH_INDEX:04X}"
                for bank in BANKS
            },
        },
        "preimage_contract": preimages,
        "offline_contract": semantic,
        "ownership": ownership,
        "timing_t_cycles": {
            "current_runtime_hot_path_delta": 0,
            "legacy_runtime_one_time_install": "exact existing installer cost",
            "renderer_delta_after_install": 0,
        },
        "required_live_gates": [
            "exact two-capture scene0B menu roundtrip with cache audit",
            "zero wall/red-green/weird-edge/yellow-trail/gray-spike frames",
            "both physical maps publish candidate-owned attributes",
            "release speed matrix",
        ],
        "decision": "CONSTRUCTION_ONLY_LIVE_GATES_REQUIRED",
    }
    return candidate, receipt


def build(
    source: bytes, base_receipt_bytes: bytes, rejected_receipt_bytes: bytes,
) -> tuple[bytes, dict[str, Any]]:
    preimages = validate_preimages(source, base_receipt_bytes, rejected_receipt_bytes)
    candidate, receipt = construct(source)
    receipt.update({
        "schema": "penta-stage1-runtime-epoch-r312-build-v1",
        "status": "STATIC_PASS_R312_LIVE_GATES_REQUIRED",
        "base": {
            "revision": "r311-live-rejected-stale-runtime",
            "candidate_sha256": BASE_SHA256,
            "build_receipt_sha256": BASE_RECEIPT_SHA256,
            "rejected_live_receipt_sha256": REJECTED_LIVE_RECEIPT_SHA256,
        },
        "root_cause": (
            "operator states retained pre-r305 DAD7 while DF51=A8 falsely "
            "declared the changed DA00-DAFF runtime current; stale DAD7 "
            "rejected scene0B before the split-key consumer"
        ),
        "preimage_contract": preimages,
        "decision": "STATIC_DIAGNOSIS_AND_PATCH_LIVE_GATES_REQUIRED",
    })
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--rejected-live-receipt", type=Path,
                        default=REJECTED_LIVE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r305.r304.checked_output(args.output, "candidate output")
    receipt_path = r305.r304.checked_output(args.receipt, "receipt output")
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes(),
        args.rejected_live_receipt.read_bytes(),
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
