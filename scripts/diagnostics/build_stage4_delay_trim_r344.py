#!/usr/bin/env python3
"""Build r344: trim 8 T-cycles from the Stage-4-only delay call.

r286 deliberately inserted a six-NOP delay in the private Stage-4 page-pair
helper.  On exact r343 the all-stage speed verifier measures 755/764 main-loop
hits, two hits below the Stop gate's strict 0.99 floor.  Keep the delay body,
helper layout, cache behavior, and every Stage-1 byte intact; retarget the
existing CALL from $DB0D to $DB0F so it executes four NOPs instead of six.

This changes one functional ROM byte in bank 22 and saves exactly 8 T-cycles
per Stage-4 helper hit.  No emulator is invoked by this builder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-hazard-terminal-silhouette-r343/candidate.gb"
BASE_SHA256 = "df359624edb86adfdc88d78e81b4a9d7c8e251956fb29512e2a0402b6c604d48"
DEFAULT_OUTPUT = TMP / "stage4-delay-trim-r344/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage4-delay-trim-r344/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = (
    "3b35f1c938b4fefc1c6f6c02408494f4a6663be50f564b4476b502399c1f714e"
)

BANK_SIZE = 0x4000
ROM_SIZE = 32 * BANK_SIZE
OVERLAY_BANK = 22
PAYLOAD_ADDR = 0x6300
DELAY_SOURCE_ADDR = 0x630D
HELPER_SOURCE_ADDR = 0x6326
CALL_SOURCE_ADDR = 0x6338
OLD_DELAY = bytes.fromhex("00 00 00 00 00 00 C9")
OLD_CALL = bytes.fromhex("CD 0D DB")
NEW_CALL = bytes.fromhex("CD 0F DB")
HELPER_PREFIX = bytes.fromhex(
    "C5 D5 E5 AF E0 E0 7C EE CB 5F 16 DF 21 F1 C1 46 24 4E"
)
HELPER_SUFFIX = bytes.fromhex("C3 92 DA")
CHECKSUM_OFFSETS = frozenset({0x014D, 0x014E, 0x014F})


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address < 0x8000,
            f"invalid banked address bank{bank}:${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def checked_output(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved != scratch and scratch in resolved.parents,
            f"{label} must be a child of repository tmp/: {resolved}")
    return resolved


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == ROM_SIZE, "r343 base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256,
            f"wrong exact r343 base: {digest(source)}")

    delay_offset = bank_offset(OVERLAY_BANK, DELAY_SOURCE_ADDR)
    helper_offset = bank_offset(OVERLAY_BANK, HELPER_SOURCE_ADDR)
    call_offset = bank_offset(OVERLAY_BANK, CALL_SOURCE_ADDR)
    require(source[delay_offset:delay_offset + len(OLD_DELAY)] == OLD_DELAY,
            "r343 Stage-4 delay body moved")
    require(source[helper_offset:call_offset] == HELPER_PREFIX,
            "r343 Stage-4 helper prefix moved")
    require(source[call_offset:call_offset + len(OLD_CALL)] == OLD_CALL,
            "r343 Stage-4 delay CALL moved")
    require(
        source[call_offset + len(OLD_CALL):
               call_offset + len(OLD_CALL) + len(HELPER_SUFFIX)]
        == HELPER_SUFFIX,
        "r343 Stage-4 helper suffix moved",
    )

    # $DB0F starts two bytes into the immutable delay payload.  The new path
    # therefore executes four NOPs and the same RET.
    target_delta = NEW_CALL[1] - (DELAY_SOURCE_ADDR & 0xFF)
    require(target_delta == 2, "r344 delay target delta changed")
    require(OLD_DELAY[target_delta:] == bytes.fromhex("00 00 00 00 C9"),
            "r344 target is not four NOPs followed by RET")
    old_delay_t = 24 + 6 * 4 + 16
    new_delay_t = 24 + 4 * 4 + 16
    require((old_delay_t, new_delay_t, old_delay_t - new_delay_t)
            == (64, 56, 8), "r344 timing contract changed")

    rom = bytearray(source)
    rom[call_offset:call_offset + len(NEW_CALL)] = NEW_CALL
    update_checksums(rom)
    candidate = bytes(rom)

    changed = {
        index for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    functional = changed - CHECKSUM_OFFSETS
    require(functional == {call_offset + 1},
            f"r344 functional delta escaped CALL operand: {sorted(functional)}")
    require(changed <= functional | CHECKSUM_OFFSETS,
            f"r344 delta escaped owned bytes: {sorted(changed - functional - CHECKSUM_OFFSETS)}")

    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {candidate_sha}")

    receipt: dict[str, object] = {
        "schema": "penta-stage4-delay-trim-r344-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r343_sha256": BASE_SHA256,
        "candidate_sha256": candidate_sha,
        "patch": {
            "bank": OVERLAY_BANK,
            "address": f"${CALL_SOURCE_ADDR:04X}",
            "rom_offset": f"0x{call_offset:06X}",
            "old": OLD_CALL.hex(" ").upper(),
            "new": NEW_CALL.hex(" ").upper(),
            "functional_changed_offsets": [f"0x{value:06X}" for value in sorted(functional)],
            "functional_changed_bytes": len(functional),
        },
        "timing": {
            "scope": "Stage-4 private page-pair helper hits only",
            "old_delay_t_cycles": old_delay_t,
            "new_delay_t_cycles": new_delay_t,
            "saved_t_cycles_per_hit": old_delay_t - new_delay_t,
        },
        "isolation": {
            "stage1_functional_bytes_changed": 0,
            "stage4_cache_and_menu_logic_changed": False,
            "wram_layout_changed": False,
        },
        "required_live_gates": [
            "Stage-4 strict speed",
            "all-stage speed with approved named-stage floors",
            "exact-candidate Stage-1 visual regressions",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = checked_output(args.output, label="output")
    receipt_path = checked_output(args.receipt, label="receipt")
    candidate, receipt = build(args.base.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "candidate_sha256": receipt["candidate_sha256"],
        "output": str(output),
        "saved_t_cycles_per_hit": 8,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
