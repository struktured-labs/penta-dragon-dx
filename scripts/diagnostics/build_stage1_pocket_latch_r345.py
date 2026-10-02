#!/usr/bin/env python3
"""Build r345: move the publication latch off Pocket-visible serial SB.

r344 stores the exact $9800/$9C00 publication destination in FF01 (SB).
The corrected natural-menu mutation control proves that changing SB at the
real bank-1:$4328 read boundary recreates the Pocket report: the former item
Window page is published with red/green attributes until another map repair.

This diagnostic overlay changes every audited publication-latch LDH operand
from FF01 to the byte-wide CGB scratch register FF73.  Opcodes, instruction
widths, and cycles are unchanged.  FF73 also has a later Ted sanitizer owner,
so this candidate is deliberately non-promotable until the complete Ted and
all-stage gates prove those lifetimes do not overlap.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage4-delay-trim-r344/candidate.gb"
BASE_SHA256 = "3b35f1c938b4fefc1c6f6c02408494f4a6663be50f564b4476b502399c1f714e"
DEFAULT_OUTPUT = TMP / "stage1-pocket-latch-r345/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-pocket-latch-r345/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = "TO_BE_BOUND"

BANK_SIZE = 0x4000
ROM_SIZE = 32 * BANK_SIZE
CHECKSUM_OFFSETS = frozenset({0x014D, 0x014E, 0x014F})
OLD_OPERAND = 0x01
DEFAULT_NEW_OPERAND = 0x73


@dataclass(frozen=True)
class Site:
    bank: int
    address: int
    opcode: int
    owner: str

    @property
    def offset(self) -> int:
        if self.bank == 0:
            return self.address
        return self.bank * BANK_SIZE + self.address - 0x4000

    @property
    def label(self) -> str:
        return f"bank{self.bank}:${self.address:04X}"


SITES = (
    Site(1, 0x42AA, 0xE0, "atomic-destination"),
    Site(1, 0x42ED, 0xF0, "atomic-destination"),
    Site(1, 0x4328, 0xF0, "atomic-destination"),
    Site(13, 0x5836, 0xE0, "stage1-atomic-route"),
    Site(13, 0x7B15, 0xE0, "resident-installer-mirror"),
    Site(16, 0x5563, 0xE0, "stage2-atomic-route"),
    Site(16, 0x7B15, 0xE0, "resident-installer-mirror"),
    Site(19, 0x6C51, 0xE0, "stage1-row-helper"),
    Site(19, 0x6CCE, 0xF0, "stage1-row-helper"),
    Site(21, 0x4307, 0xF0, "stage7-publication"),
    Site(21, 0x4B0A, 0xF0, "stage7-publication"),
    Site(21, 0x580B, 0xF0, "stage7-publication"),
    Site(22, 0x7120, 0xF0, "later-stage-publication"),
    Site(22, 0x7171, 0xF0, "later-stage-publication"),
    Site(22, 0x719C, 0xF0, "later-stage-publication"),
    Site(22, 0x71A2, 0xE0, "later-stage-publication"),
    Site(22, 0x71C6, 0xF0, "later-stage-publication"),
    Site(22, 0x71CC, 0xE0, "later-stage-publication"),
    Site(22, 0x720C, 0xF0, "later-stage-publication"),
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def checked_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved != scratch and scratch in resolved.parents,
            f"{label} must be below repository tmp/")
    return resolved


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def build(source: bytes, new_operand: int = DEFAULT_NEW_OPERAND) -> tuple[bytes, dict[str, object]]:
    require(len(source) == ROM_SIZE, "r344 base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256,
            f"wrong exact r344 base: {digest(source)}")
    require(len(SITES) == 19, "publication-latch site count drift")
    require(len({(site.bank, site.address) for site in SITES}) == len(SITES),
            "duplicate publication-latch site")
    require(new_operand in {0x72, 0x73, 0x74},
            "replacement must be FF72, FF73, or FF74")
    for site in SITES:
        actual = source[site.offset:site.offset + 2]
        require(actual == bytes((site.opcode, OLD_OPERAND)),
                f"preimage drift at {site.label}: {actual.hex(' ')}")

    rom = bytearray(source)
    for site in SITES:
        rom[site.offset + 1] = new_operand
    update_checksums(rom)
    candidate = bytes(rom)

    changed = {
        index for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    operands = {site.offset + 1 for site in SITES}
    functional = changed - CHECKSUM_OFFSETS
    require(functional == operands,
            f"r345 escaped audited operands: {sorted(functional ^ operands)}")
    require(changed <= operands | CHECKSUM_OFFSETS,
            "r345 escaped operand/checksum ownership")
    for site in SITES:
        require(candidate[site.offset:site.offset + 2]
                == bytes((site.opcode, new_operand)),
                f"wrong r345 operand at {site.label}")

    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {candidate_sha}")
    receipt: dict[str, object] = {
        "schema": "penta-stage1-pocket-latch-r345-build-v1",
        "status": "STATIC_PASS_LIVE_CONFLICT_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r344_sha256": BASE_SHA256,
        "candidate_sha256": candidate_sha,
        "root_control": {
            "candidate": BASE_SHA256,
            "fault": "FF01 99->9D at bank1:$4328 read boundary",
            "result": "57 post-close bad frames; first has 27 mismatched cells",
            "receipt": (
                "tmp/hardware-incidents/r344-menu-exit-red-green/"
                "ff01-read-negative-control/report.txt"
            ),
        },
        "patch": {
            "old_register": "FF01/SB",
            "new_register": f"FF{new_operand:02X}/CGB scratch",
            "sites": [
                {"site": site.label, "access": "write" if site.opcode == 0xE0 else "read",
                 "owner": site.owner, "operand_offset": f"0x{site.offset + 1:06X}"}
                for site in SITES
            ],
            "functional_changed_bytes": len(functional),
            "opcode_changes": 0,
            "instruction_width_delta_bytes": 0,
            "instruction_cycle_delta_t": 0,
        },
        "known_conflict_to_disprove": (
            f"FF{new_operand:02X} already has a relocated arena owner; exact "
            "live gates must prove publication and arena lifetimes never overlap"
        ),
        "required_live_gates": [
            "natural Stage1 menu-close exact visible-page oracle",
            "corrected FF73 read-boundary mutation is rejected",
            "rotating-spike semantic and rendered continuity",
            "Stage7/Ted dual-plane ABI, visuals, and containment",
            "all-stage speed and audio cadence telemetry",
            "Analogue Pocket hardware confirmation before promotion",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument(
        "--register", choices=("72", "73", "74"), default="73",
        help="low byte of the candidate CGB scratch register",
    )
    args = parser.parse_args()
    output = checked_output(args.output, "candidate")
    receipt_path = checked_output(args.receipt, "receipt")
    candidate, receipt = build(args.base.read_bytes(), int(args.register, 16))
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
