#!/usr/bin/env python3
"""Build r354: retain r353's FFC4 target until its VBlank commit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-hram-target-vblank-r353/candidate.gb"
BASE_RECEIPT = TMP / "stage1-hram-target-vblank-r353/build-receipt.json"
BASE_SHA256 = "45502bf1914f9d8b365978296e2186ce122fe513e400ca4996dbaa744e5f0f67"
BASE_RECEIPT_SHA256 = "b3e1f754c2a653a38327373374ff9a88725dfb659b056bc2c6ab0d7ed52adae5"
DEFAULT_OUTPUT = TMP / "stage1-postcommit-hram-target-r354/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-postcommit-hram-target-r354/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = (
    "3759f8ad10e6841f7705d13ee76f4b45478460b1bf782acb8507b4f70414e71f"
)

ROW_CLEAR_OFFSET = 19 * 0x4000 + 0x6C51 - 0x4000
ROW_CLEAR_OLD = bytes.fromhex("E0 C4")
ROW_CLEAR_NEW = bytes.fromhex("00 00")
CHECKSUM_OFFSETS = frozenset({0x014D, 0x014E, 0x014F})


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def checked_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved != scratch and scratch in resolved.parents,
            f"{label} must be below repository tmp/")
    return resolved


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == 32 * 0x4000, "r353 base size changed")
    require(digest(source) == BASE_SHA256,
            f"wrong exact r353 base: {digest(source)}")
    require(digest(receipt_bytes) == BASE_RECEIPT_SHA256,
            "r353 receipt identity drifted")
    base_receipt = json.loads(receipt_bytes)
    require(base_receipt.get("schema")
            == "penta-stage1-hram-target-vblank-r353-build-v1",
            "r353 receipt schema drifted")
    require(base_receipt.get("candidate_sha256") == BASE_SHA256,
            "r353 receipt names another candidate")
    require(source[ROW_CLEAR_OFFSET:ROW_CLEAR_OFFSET + 2] == ROW_CLEAR_OLD,
            "pre-commit FFC4 clear preimage drifted")
    require(source[0x37424:0x37427] == bytes.fromhex("AF E0 C4"),
            "r353 VBlank FFC4 clear drifted")

    rom = bytearray(source)
    rom[ROW_CLEAR_OFFSET:ROW_CLEAR_OFFSET + 2] = ROW_CLEAR_NEW
    update_checksums(rom)
    candidate = bytes(rom)
    require(candidate[0x37424:0x37427] == bytes.fromhex("AF E0 C4"),
            "VBlank helper lost its FFC4 clear")
    changed = {i for i, pair in enumerate(zip(source, candidate, strict=True))
               if pair[0] != pair[1]}
    require(changed <= {ROW_CLEAR_OFFSET, ROW_CLEAR_OFFSET + 1} | CHECKSUM_OFFSETS,
            f"r354 escaped owned bytes: {sorted(changed)}")
    sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {sha}")
    receipt: dict[str, object] = {
        "schema": "penta-stage1-postcommit-hram-target-r354-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r353_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": sha,
        "lifecycle_change": {
            "removed_clear": "bank19:$6C50 XOR A; $6C51-$6C52 NOP NOP",
            "sole_owned_clear": "bank13:$7424 XOR A; LDH ($FFC4),A in VBlank helper",
            "reason": "retain completed physical target through fixed publisher",
            "pending_authority": "DF5C",
        },
        "timing": {
            "row_return_delta_t_vs_r353": -8,
            "map_compiler_delta_t_vs_r345": 0,
            "publisher_wait_cycles": 0,
        },
        "required_live_gates": base_receipt["required_live_gates"],
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
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"],
                      "output": str(output), "status": receipt["status"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
