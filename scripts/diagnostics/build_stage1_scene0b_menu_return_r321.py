#!/usr/bin/env python3
"""Build r321: isolate the r314 Scene-$0B transaction return regression.

r320's scroll-first publisher fixes the independently observed page/SCY tear.
The inherited r314 Scene-$0B delayed-commit return chain, however, commits
once and then never returns to the native menu input mux in the authenticated
menu-close replay.  This candidate retains every r320 publisher byte and
restores only r313's known-good self-heal handler prefix.  The old r314 suffix
is deliberately inert: r313 always leaves through the mapper before it.

This is a diagnostic release candidate, not a promotion.  Its required live
gate decides whether the r314 stack transaction is the regression boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import build_stage1_atomic_presentation_commit_r320 as r320
import build_stage1_scene0b_runtime_selfheal_r313 as r313


ROOT = r320.ROOT
TMP = r320.TMP
BASE = r320.DEFAULT_OUTPUT
BASE_RECEIPT = r320.DEFAULT_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-scene0b-menu-return-r321/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-scene0b-menu-return-r321/build-receipt.json"

BASE_SHA256 = r320.EXPECTED_CANDIDATE_SHA256
BASE_RECEIPT_SHA256 = "9ed345f166f16eae4d94fc69d06ddef51fdbdf195dad4ca50b106aa110c2018b"
BASE_SCHEMA = "penta-stage1-atomic-presentation-commit-r320-build-v1"
EXPECTED_CANDIDATE_SHA256 = "TO_BE_PINNED"

HANDLER_BANK = r313.MUX_BANK
HANDLER_ADDR = r313.HANDLER_ADDR
HANDLER = r313.HANDLER
CHECKSUM_OFFSETS = r320.CHECKSUM_OFFSETS


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    return r320.bank_offset(bank, address)


def handler_offset() -> int:
    return bank_offset(HANDLER_BANK, HANDLER_ADDR)


def functional_offsets(source: bytes, candidate: bytes) -> set[int]:
    return {
        offset for offset, (before, after) in enumerate(
            zip(source, candidate, strict=True)
        ) if before != after and offset not in CHECKSUM_OFFSETS
    }


def source_preimages(source: bytes) -> dict[str, Any]:
    r320.require(digest(source) == BASE_SHA256,
                 f"wrong exact r320 base: {digest(source)}")
    offset = handler_offset()
    r320.require(source[offset:offset + len(HANDLER)] != HANDLER,
                 "r320 unexpectedly already contains r313 return handler")
    r320.require(source[r320.PRIMARY_ADDR:r320.PRIMARY_END] == r320.NEW_PRIMARY,
                 "r320 atomic publisher preimage changed")
    return {"candidate_sha256": BASE_SHA256}


def validate_preimages(source: bytes, receipt_bytes: bytes) -> dict[str, Any]:
    contract = source_preimages(source)
    r320.require(digest(receipt_bytes) == BASE_RECEIPT_SHA256,
                 "r320 receipt identity changed")
    receipt = json.loads(receipt_bytes)
    r320.require(receipt.get("schema") == BASE_SCHEMA,
                 "r320 receipt schema changed")
    r320.require(receipt.get("candidate_sha256") == BASE_SHA256,
                 "r320 receipt names another ROM")
    r320.require(receipt.get("emulator_invoked") is False,
                 "r320 build unexpectedly invoked emulator")
    return {**contract, "receipt_sha256": BASE_RECEIPT_SHA256}


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    r320.require(len(candidate) == len(source), "r321 changed ROM size")
    r320.require(candidate[r320.PRIMARY_ADDR:r320.PRIMARY_END] == r320.NEW_PRIMARY,
                 "r321 changed r320 atomic publisher")
    offset = handler_offset()
    r320.require(candidate[offset:offset + len(HANDLER)] == HANDLER,
                 "r321 r313 menu-return handler mismatch")
    changed = functional_offsets(source, candidate)
    expected = {
        offset + index for index, (before, after) in enumerate(
            zip(source[offset:offset + len(HANDLER)], HANDLER, strict=True)
        ) if before != after
    }
    r320.require(changed == expected, "r321 functional delta escaped handler")
    checksummed = bytearray(candidate)
    r320.r319.r318.r317.r305.r304.update_checksums(checksummed)
    r320.require(bytes(checksummed) == candidate, "r321 checksums not canonical")
    return {
        "functional_changed_bytes_from_r320": len(changed),
        "handler": f"bank31:${HANDLER_ADDR:04X}-${HANDLER_ADDR + len(HANDLER) - 1:04X}",
        "atomic_r320_publisher_exact": True,
        "escaped_bytes": 0,
    }


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    preimages = source_preimages(source)
    rom = bytearray(source)
    offset = handler_offset()
    rom[offset:offset + len(HANDLER)] = HANDLER
    r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r320.require(sha == EXPECTED_CANDIDATE_SHA256,
                     f"r321 candidate identity drift: {sha}")
    return candidate, {
        "schema": "penta-stage1-scene0b-menu-return-r321-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "base": preimages,
        "root_cause_hypothesis": (
            "r314's private delayed-commit stack continuation commits but does "
            "not return to the native menu input mux; r313's direct mapper "
            "return supplies the fixed mapper continuation used by this recipe"
        ),
        "patch": {
            "r320_atomic_publisher": "unchanged",
            "scene0b_handler": "r314 prefix replaced by exact r313 handler",
            "scope": f"bank31:${HANDLER_ADDR:04X}-${HANDLER_ADDR + len(HANDLER) - 1:04X}",
        },
        "ownership": ownership,
        "required_live_gates": [
            "scene0B menu open/close/reopen acknowledgement",
            "hazard/menu dense visual replay",
            "north every-frame page/attribute verifier",
            "stage1 release speed at least 95%",
        ],
    }


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    preimages = validate_preimages(source, receipt_bytes)
    candidate, receipt = construct(source)
    receipt.update({
        "schema": "penta-stage1-scene0b-menu-return-r321-build-v1",
        "status": "STATIC_PASS_DIAGNOSTIC_LIVE_GATE_REQUIRED",
        "base": preimages,
        "root_cause_hypothesis": (
            "r314's private delayed-commit stack continuation commits but does "
            "not return to the native menu input mux; r313's direct mapper "
            "return is the last known-good live control flow"
        ),
    })
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"],
                      "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
