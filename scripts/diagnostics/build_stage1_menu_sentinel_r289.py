#!/usr/bin/env python3
"""Invalidate Stage-1 menu-owned maps with the decider's real sentinel.

r287 writes zero to both physical-map semantic caches while SELECT owns the
Window.  Zero is a valid Stage-1 content signature, so a static entrance or
hazard phase can false-hit and display the menu-colored attribute plane until
movement changes the signature.  The private Stage-1 split decider reserves
$FF as its fail-closed sentinel.

This exact-width helper emits $FF only for normalized scene $02.  Scenes
$03..$08 retain r287's zero invalidation, the FFE4-zero hot path is byte exact,
and only the menu-owned target path gains one four-cycle ALU instruction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-cold-art-gold-r288/candidate.gb"
BASE_RECEIPT = TMP / "stage1-cold-art-gold-r288/build-receipt.json"
DEFAULT_OUTPUT = TMP / "stage1-menu-sentinel-r289/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-menu-sentinel-r289/build-receipt.json"
BASE_SHA256 = "a18660d3ed0f883810d0ed542e63598f0a48a09280eb5f91e48aa621d70eb331"
BASE_RECEIPT_SHA256 = "ee7898612ade81fc290c3a707cc4a1a2109e0356f36bc1cad5f2c371a3abc550"
EXPECTED_SHA256 = "559e9aa7a81985dd8639ce70d830b9799faebb4f9e27ceec55e2ce0fb086d905"

BANK_SIZE = 0x4000
BANK = 13
HELPER_ADDR = 0x6A40
OLD = bytes.fromhex(
    "F0 E4 B7 C8 FA 80 D8 D6 02 FE 07 3D D0 "
    "AF EA 53 DF EA 57 DF 3C C9 00"
)
NEW = bytes.fromhex(
    "F0 E4 B7 C8 FA 80 D8 D6 02 FE 07 3D D0 "
    "87 9F EA 53 DF EA 57 DF 3D C9"
)
CALLER_ADDR = 0x6EB1
CALLER = bytes.fromhex(
    "CD 40 6A 28 10 F0 40 CB 77 28 04 CB 9F 18 02 CB DF E0 40"
)
STAGE1_DECIDER_BANK = 21
STAGE1_DECIDER_ADDR = 0x4100
STAGE1_SENTINEL_FRAGMENT = bytes.fromhex("B9 20 17 3C 28 0E")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address < 0x8000, "bad banked address")
    return bank * BANK_SIZE + address - 0x4000


def checked_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    root = TMP.resolve()
    require(resolved != root and root in resolved.parents,
            f"{label} must be inside repository tmp/")
    return resolved


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def helper_model(*, ffe4: int, scene: int) -> tuple[bool, int | None]:
    """Return caller Z and cache value (None when no invalidation)."""
    if ffe4 == 0:
        return True, None
    normalized = (scene - 2) & 0xFF
    if normalized >= 7:
        return False, None
    decremented = (normalized - 1) & 0xFF
    doubled = decremented * 2
    carry = doubled > 0xFF
    sentinel = 0xFF if carry else 0x00  # SBC A,A
    returned = (sentinel - 1) & 0xFF
    return returned == 0, sentinel


def exhaustive_controls() -> dict[str, object]:
    passed = 0
    for ffe4 in range(256):
        for scene in range(256):
            z, value = helper_model(ffe4=ffe4, scene=scene)
            require(z == (ffe4 == 0),
                    f"caller Z drift ffe4={ffe4:02X} scene={scene:02X}")
            expected = None
            if ffe4 != 0 and 2 <= scene <= 8:
                expected = 0xFF if scene == 2 else 0x00
            require(value == expected,
                    f"sentinel drift ffe4={ffe4:02X} scene={scene:02X}")
            passed += 1
    return {
        "state_pairs": 256 * 256,
        "passed": passed,
        "FFE4_zero_returns_Z_without_invalidation": True,
        "scene02_writes_FF": True,
        "scenes03_through08_write_00": True,
        "all_other_nonzero_FFE4_scenes_return_NZ_without_invalidation": True,
    }


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == 32 * BANK_SIZE, "base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256, "wrong exact r288 base")
    require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
            "r288 receipt identity changed")
    base_receipt = json.loads(base_receipt_bytes)
    require(base_receipt.get("candidate_sha256") == BASE_SHA256,
            "r288 receipt names another candidate")

    helper_off = bank_offset(BANK, HELPER_ADDR)
    require(len(OLD) == len(NEW) == 23, "menu helper width changed")
    require(source[helper_off:helper_off + len(OLD)] == OLD,
            "r287/r288 menu helper preimage changed")
    require(source[
        bank_offset(BANK, CALLER_ADDR):
        bank_offset(BANK, CALLER_ADDR) + len(CALLER)
    ] == CALLER, "menu helper caller changed")
    decider_off = bank_offset(STAGE1_DECIDER_BANK, STAGE1_DECIDER_ADDR)
    require(STAGE1_SENTINEL_FRAGMENT in source[decider_off:decider_off + 64],
            "Stage-1 private decider no longer reserves FF")

    rom = bytearray(source)
    rom[helper_off:helper_off + len(NEW)] = NEW
    update_checksums(rom)
    candidate = bytes(rom)
    require(digest(candidate) == EXPECTED_SHA256,
            f"candidate identity drift: {digest(candidate)}")
    require(candidate[0x014D] == 0xF9, "header checksum changed")
    require(candidate[0x014E:0x0150] == bytes.fromhex("41 56"),
            "global checksum changed")

    changed = [
        index for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    ]
    allowed = set(range(helper_off, helper_off + len(NEW))) | {
        0x014D, 0x014E, 0x014F,
    }
    require(set(changed) <= allowed, "r289 escaped helper/checksum ownership")
    require(all(
        source[index] == candidate[index]
        for index in range(len(source))
        if index not in allowed
    ), "r289 changed bytes outside the helper/checksums")

    receipt: dict[str, object] = {
        "schema": "penta-stage1-menu-sentinel-r289-build-v1",
        "status": "STATIC_PASS_EXACT_USER_ROUTE_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": EXPECTED_SHA256,
        "checksums": {"header": "F9", "global": "4156"},
        "patch": {
            "bank": BANK,
            "address": f"${HELPER_ADDR:04X}-${HELPER_ADDR + len(NEW) - 1:04X}",
            "old": OLD.hex(" ").upper(),
            "new": NEW.hex(" ").upper(),
            "changed_offsets": [f"0x{value:06X}" for value in changed],
        },
        "sentinel_contract": {
            "Stage1_scene02": "$FF (private split-decider sentinel)",
            "scenes03_through08": "$00 (r287 behavior preserved)",
            "FFE4_zero": "byte-exact return-Z hot path",
            "non_target_scenes": "instruction/cycle-exact return-NZ path",
            "target_menu_path_t_cycle_delta": 4,
            "steady_gameplay_t_cycle_delta": 0,
        },
        "semantic_controls": exhaustive_controls(),
        "transferred_r288_contracts": {
            "natural_Stage1_DF5B_rearm_exact": True,
            "gold_tooth_palette_mirrors_exact": True,
            "all_speed_optimized_gameplay_code_except_menu_helper_exact": True,
        },
        "required_gates": [
            "untouched blank-SRAM same-process menu then hazard route",
            "stationary post-close active-BG attrs never mismatch",
            "natural bank-1 hazard art has zero mismatched bytes",
            "four user-reported rendered bug classes absent",
            "strict all-stage speed qualification",
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
    output = checked_output(args.output, "candidate")
    receipt_path = checked_output(args.receipt, "receipt")
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
