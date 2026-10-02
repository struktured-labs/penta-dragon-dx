#!/usr/bin/env python3
"""Build r365: keep Sara above the Stage-1 background at all times.

The stock fixed-bank attribute helper deliberately sets OBJ attribute bit 7
for hardware OAM slots 0-3 when FFC2-FFC5 request it.  In colorized Stage 1,
that makes nonzero floor pixels win over opaque pixels in Sara's body, which
looks like gray room tiles bleeding through her sprite.  Change the low-slot
control-active ``SET 7,A`` to ``RES 7,A``.  Every branch, memory access, and
cycle remains exact; the two generated emitters keep calling the same helper.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-menu-close-atomic-hide-r364/candidate.gb"
BASE_RECEIPT = TMP / "stage1-menu-close-atomic-hide-r364/build-receipt.json"
BASE_SHA256 = "3b9f67ea25e65d40cc383e7af319b35bded7083143f3a1efbf2c69c42b48beb2"
BASE_RECEIPT_SHA256 = (
    "3c783ad861af9e91da0c01ca40af2e7a33f55271625c72b0e27c34136991896d"
)
DEFAULT_OUTPUT = TMP / "stage1-sara-priority-clear-r365/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-sara-priority-clear-r365/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = (
    "4243fa84946bc0325ff46b510103c1e1c4213f0879e40b5aff77d026bf69ea88"
)

CHECKSUM_OFFSETS = frozenset({0x014D, 0x014E, 0x014F})
HELPER_START = 0x1188
PRIORITY_SET_OPCODE_OFFSET = 0x119A
HELPER_PREIMAGE = bytes.fromhex(
    "E5 F5 F0 DD FE 04 30 0D 21 C2 FF D7 7E A7 28 05 "
    "F1 CB FF 18 03 F1 CB BF E1 C9"
)
HELPER_POSTIMAGE = bytes.fromhex(
    "E5 F5 F0 DD FE 04 30 0D 21 C2 FF D7 7E A7 28 05 "
    "F1 CB BF 18 03 F1 CB BF E1 C9"
)
CALL_SITES = (0x37B3E, 0x43B3E)
CALL = bytes.fromhex("CD 88 11")


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
    resolved, scratch = path.resolve(), TMP.resolve()
    require(
        resolved != scratch and scratch in resolved.parents,
        f"{label} must be below repository tmp/",
    )
    return resolved


def r364_priority(attr: int, slot: int, control: int) -> int:
    """Model the complete visible result of r364's $1188 helper."""
    if slot >= 4:
        return attr & 0x7F
    return attr | 0x80 if control else attr & 0x7F


def r365_priority(attr: int, slot: int, control: int) -> int:
    """The r365 helper always takes the existing priority-clear tail."""
    del slot, control
    return attr & 0x7F


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == 32 * 0x4000, "r364 base size changed")
    require(digest(source) == BASE_SHA256, f"wrong exact r364 base: {digest(source)}")
    require(
        digest(receipt_bytes) == BASE_RECEIPT_SHA256,
        "r364 receipt identity drifted",
    )
    base_receipt = json.loads(receipt_bytes)
    require(
        base_receipt.get("schema")
        == "penta-stage1-menu-close-atomic-hide-r364-build-v1",
        "r364 receipt schema drifted",
    )
    require(
        base_receipt.get("candidate_sha256") == BASE_SHA256,
        "r364 receipt names another candidate",
    )
    require(
        source[HELPER_START:HELPER_START + len(HELPER_PREIMAGE)]
        == HELPER_PREIMAGE,
        "fixed-bank OBJ-priority helper preimage changed",
    )
    require(
        PRIORITY_SET_OPCODE_OFFSET == HELPER_START + 18
        and source[
            PRIORITY_SET_OPCODE_OFFSET - 1:PRIORITY_SET_OPCODE_OFFSET + 1
        ] == bytes.fromhex("CB FF"),
        "low-slot priority-set opcode boundary changed",
    )
    require(
        [index for index in range(len(source)) if source.startswith(CALL, index)]
        == list(CALL_SITES),
        "CALL $1188 census changed",
    )

    model_cases = 0
    preserved_high_slot_cases = 0
    cleared_low_slot_cases = 0
    for attr in range(0x100):
        for slot in range(0x100):
            for control in (0, 1, 0x7F, 0xFF):
                old = r364_priority(attr, slot, control)
                new = r365_priority(attr, slot, control)
                require(new == attr & 0x7F, "r365 priority-clear model drifted")
                require((old ^ new) & 0x7F == 0, "non-priority attribute bits changed")
                if slot >= 4:
                    require(new == old, "non-Sara helper result changed")
                    preserved_high_slot_cases += 1
                elif control:
                    require(new == old & 0x7F, "Sara priority bit was not cleared")
                    cleared_low_slot_cases += 1
                else:
                    require(new == old, "clear-control Sara result changed")
                model_cases += 1

    rom = bytearray(source)
    # Preserve the exact control-dependent path and timing while making its
    # formerly priority-setting result match the existing clear path.
    rom[PRIORITY_SET_OPCODE_OFFSET] = 0xBF  # SET 7,A -> RES 7,A
    update_checksums(rom)
    candidate = bytes(rom)
    require(
        candidate[HELPER_START:HELPER_START + len(HELPER_POSTIMAGE)]
        == HELPER_POSTIMAGE,
        "fixed-bank OBJ-priority helper postimage changed",
    )
    require(
        [index for index in range(len(candidate)) if candidate.startswith(CALL, index)]
        == list(CALL_SITES),
        "r365 changed the CALL $1188 census",
    )
    changed = {
        index
        for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    require(
        changed <= {PRIORITY_SET_OPCODE_OFFSET} | CHECKSUM_OFFSETS,
        "r365 escaped owned bytes: "
        f"{sorted(changed - {PRIORITY_SET_OPCODE_OFFSET} - CHECKSUM_OFFSETS)}",
    )
    require(
        PRIORITY_SET_OPCODE_OFFSET in changed,
        "r365 did not change the priority-set opcode",
    )

    sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(sha == EXPECTED_CANDIDATE_SHA256, f"candidate identity drift: {sha}")
    required_live_gates = list(base_receipt["required_live_gates"])
    for gate in (
        "natural Stage-1 SELECT roundtrip rejects every Sara bit-7 OAM entry",
        "Stage-1 OBJ visual contract rejects every visible Sara bit-7 OAM entry",
    ):
        if gate not in required_live_gates:
            required_live_gates.append(gate)
    receipt: dict[str, object] = {
        "schema": "penta-stage1-sara-priority-clear-r365-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r364_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": sha,
        "hardware_incident": {
            "platforms": ["Analogue Pocket", "mGBA"],
            "symptom": "gray floor pixels bleed through Sara W's lower body",
            "root_cause": (
                "fixed-bank helper $1188 set OBJ priority bit 7 on OAM slots 0-3"
            ),
        },
        "patch": {
            "address": "$119A",
            "preimage": "SET 7,A",
            "postimage": "RES 7,A",
            "effect": "both low-slot control paths now clear OBJ priority bit 7",
            "changed_logic_bytes": 1,
            "all_path_instruction_and_cycle_contract": "exact",
            "cycle_delta": 0,
        },
        "proof": {
            "exhaustive_model_cases": model_cases,
            "preserved_non_sara_cases": preserved_high_slot_cases,
            "cleared_set_control_sara_cases": cleared_low_slot_cases,
            "non_priority_bits_preserved": True,
            "call_sites_unchanged": [f"0x{site:05X}" for site in CALL_SITES],
        },
        "required_live_gates": required_live_gates,
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
    print(json.dumps({
        "candidate_sha256": receipt["candidate_sha256"],
        "output": str(output),
        "status": receipt["status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
