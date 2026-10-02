#!/usr/bin/env python3
"""Static equivalence and no-bypass gate for relocation-only r105."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_stage1_hazard_fast_r101 as r101
import build_stage1_hazard_relocation_only_r105 as r105


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def offset(bank: int, address: int) -> int:
    return r101.bank_offset(bank, address)


def route_r100(c6: bool, c7: bool, c9: bool, c10: bool) -> str:
    if c6 or c7:
        return "left4"
    if c9 or c10:
        return "right8"
    return "tail"


def route_relocated(c6: bool, c7: bool, c9: bool, c10: bool) -> str:
    # Column 6 remains in the unchanged bank-19 front. Only its no-carry arm
    # maps the relocated col7/9/10 classifier.
    if c6:
        return "left4"
    if c7:
        return "left4"
    if c9:
        return "right8"
    if c10:
        return "right8"
    return "tail"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    base = args.base.read_bytes()
    candidate = args.candidate.read_bytes()
    build = json.loads(args.build_receipt.read_text())
    if digest(base) != r105.BASE_SHA256:
        raise SystemExit("base is not exact visual-safe r100")
    if digest(candidate) != build["output_sha256"]:
        raise SystemExit("candidate differs from build receipt")
    if build.get("promotable") is not False:
        raise AssertionError("isolation control must remain non-promotable")

    # The full scanner call is byte-exact. r101's rejected bypass changes this
    # site to JP $6DB5; make that mutation an explicit negative control.
    scan_off = offset(r101.PRIVATE_BANK, 0x6BE3)
    scanner = bytes.fromhex("F3 AF E0 4F CD B7 61 C3 50 6C")
    bypass = bytes.fromhex("F3 AF E0 4F C3 B5 6D 00 00 00")
    if candidate[scan_off:scan_off + len(scanner)] != scanner:
        raise AssertionError("full scanner entry was not retained")
    mutant = bytearray(candidate)
    mutant[scan_off:scan_off + len(bypass)] = bypass
    if mutant[scan_off:scan_off + len(scanner)] == scanner:
        raise AssertionError("scanner-bypass negative control did not fail")

    cases = []
    for values in itertools.product((False, True), repeat=4):
        expected = route_r100(*values)
        actual = route_relocated(*values)
        if actual != expected:
            raise AssertionError((values, expected, actual))
        cases.append((values, actual))

    dispatcher = r101.build_bank20_dispatcher()
    dispatch_off = offset(r101.HELPER_BANK, r101.HELPER_DISPATCH_ADDR)
    if candidate[dispatch_off:dispatch_off + len(dispatcher)] != dispatcher:
        raise AssertionError("relocated dispatcher differs")

    # No bytes from the rejected bypass may be present in its three distinctive
    # dispatch/skip sites. Zero is the relocation's deliberate retired code.
    rejected_sites = {
        0x61A0: bytes.fromhex("FA 21 C3 CD 88 6C C9"),
        0x6D9E: bytes.fromhex("CD A0 61 DA A7 61"),
        0x6CEF: bytes.fromhex("FA 5A C3 FE 01 37 C8"),
    }
    for address, signature in rejected_sites.items():
        off = offset(r101.PRIVATE_BANK, address)
        if candidate[off:off + len(signature)] == signature:
            raise AssertionError(f"rejected bypass present at ${address:04X}")

    receipt = {
        "schema": "penta-stage1-hazard-relocation-only-r105-verifier-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(base),
        "candidate_sha256": digest(candidate),
        "equivalence": {
            "boolean_phase_cases": len(cases),
            "routes": sorted({route for _, route in cases}),
            "column6_bank19_front_retained": True,
            "columns7_9_10_relocated": True,
        },
        "scanner": {
            "full_entry_byte_exact": True,
            "room03_bypass_absent": True,
            "negative_control_rejected": True,
        },
        "first_emulator_gate": (
            "exact current-ROM cold+menu fixture that passes r100 and fails "
            "combined r101; no speed gate before visual equivalence"
        ),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
