#!/usr/bin/env python3
"""Build r355: compensate r354's global VBlank service cost in Stages 4/7.

The r354 VBlank publication hook is intentionally global so Stage-1 map
commits happen only during blanking.  Recover its small later-stage throughput
cost without touching that publication contract:

* Stage 4 enters the existing immutable delay body one NOP later, saving 4 T
  per private page-pair helper call.
* Stage 7 uses the already-proven terminal-E row marker in its private helper,
  replacing the per-row HRAM decrement loop and saving 308 T per admitted
  publication.  The helper's renderer, transport, router, and lifecycle paths
  remain byte-exact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-postcommit-hram-target-r354/candidate.gb"
BASE_RECEIPT = TMP / "stage1-postcommit-hram-target-r354/build-receipt.json"
BASE_SHA256 = "3759f8ad10e6841f7705d13ee76f4b45478460b1bf782acb8507b4f70414e71f"
BASE_RECEIPT_SHA256 = "0cc07e1a3fe2b56f7f348fc254e4b361b7d7bbed1d63e547eb6c46cdf699d3d0"
DEFAULT_OUTPUT = TMP / "r354-stage47-speed-compensation-r355/candidate.gb"
DEFAULT_RECEIPT = TMP / "r354-stage47-speed-compensation-r355/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = (
    "23368ae6f5ee08371b1f72c528fa8ca704ddf8e62b8671d49291129a110e871b"
)

BANK_SIZE = 0x4000
ROM_SIZE = 32 * BANK_SIZE
CHECKSUM_OFFSETS = frozenset({0x014D, 0x014E, 0x014F})

STAGE4_BANK = 22
STAGE4_CALL_ADDR = 0x6338
STAGE4_OLD_CALL = bytes.fromhex("CD 0F DB")
STAGE4_NEW_CALL = bytes.fromhex("CD 10 DB")
STAGE4_DELAY_ADDR = 0x630D
STAGE4_DELAY = bytes.fromhex("00 00 00 00 00 00 C9")

STAGE7_MARKER_ADDR = 0x6D04
STAGE7_OLD_MARKER = bytes.fromhex("F0 E0 3D E0 E0 20 ED")
STAGE7_NEW_MARKER = bytes.fromhex("7B EE 80 20 EF E0 E0")


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address < 0x8000,
            f"invalid banked address bank{bank}:${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


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


def build(
    source: bytes,
    receipt_bytes: bytes,
) -> tuple[bytes, dict[str, object]]:
    require(len(source) == ROM_SIZE, "r354 base size changed")
    require(digest(source) == BASE_SHA256,
            f"wrong exact r354 base: {digest(source)}")
    require(digest(receipt_bytes) == BASE_RECEIPT_SHA256,
            "r354 receipt identity drifted")
    base_receipt = json.loads(receipt_bytes)
    require(base_receipt.get("schema")
            == "penta-stage1-postcommit-hram-target-r354-build-v1",
            "r354 receipt schema drifted")
    require(base_receipt.get("candidate_sha256") == BASE_SHA256,
            "r354 receipt names another candidate")

    delay_offset = bank_offset(STAGE4_BANK, STAGE4_DELAY_ADDR)
    call_offset = bank_offset(STAGE4_BANK, STAGE4_CALL_ADDR)
    require(source[delay_offset:delay_offset + len(STAGE4_DELAY)]
            == STAGE4_DELAY, "Stage-4 delay body moved")
    require(source[call_offset:call_offset + len(STAGE4_OLD_CALL)]
            == STAGE4_OLD_CALL, "Stage-4 delay call preimage changed")
    require(STAGE4_DELAY[3:] == bytes.fromhex("00 00 00 C9"),
            "Stage-4 new entry is not three NOPs plus RET")

    rom = bytearray(source)
    rom[call_offset:call_offset + len(STAGE4_NEW_CALL)] = STAGE4_NEW_CALL
    owned = set(range(call_offset, call_offset + len(STAGE4_NEW_CALL)))

    marker_offset = bank_offset(STAGE4_BANK, STAGE7_MARKER_ADDR)
    require(source[marker_offset:marker_offset + len(STAGE7_OLD_MARKER)]
            == STAGE7_OLD_MARKER, "Stage-7 marker preimage changed")
    rom[marker_offset:marker_offset + len(STAGE7_NEW_MARKER)] = (
        STAGE7_NEW_MARKER
    )
    owned.update(range(marker_offset, marker_offset + len(STAGE7_NEW_MARKER)))

    # The private helper reads 24 bytes from ten odd source records.  E after
    # each row advances by $18 and reaches exactly $80 on the terminal row.
    # Both the old DEC-to-zero counter and XOR-$80 marker therefore leave
    # A=0 and Z=1 at the unchanged exit.
    post_row_e = [
        (0xB8 + row * 0x18) & 0xFF for row in range(20)
    ]
    require(post_row_e[-1] == 0x80
            and all(value != 0x80 for value in post_row_e[:-1]),
            "Stage-7 terminal-E proof changed")

    update_checksums(rom)
    candidate = bytes(rom)
    changed = {
        index for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    require(changed <= owned | CHECKSUM_OFFSETS,
            f"r355 escaped owned bytes: {sorted(changed - owned - CHECKSUM_OFFSETS)}")
    functional = changed - CHECKSUM_OFFSETS
    marker_changed = {
        marker_offset + index
        for index, pair in enumerate(zip(
            STAGE7_OLD_MARKER, STAGE7_NEW_MARKER, strict=True
        ))
        if pair[0] != pair[1]
    }
    expected_functional = {call_offset + 1} | marker_changed
    require(functional == expected_functional,
            f"r355 functional delta changed: {sorted(functional)}")
    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {candidate_sha}")

    receipt: dict[str, object] = {
        "schema": "penta-r354-stage47-speed-compensation-r355-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r354_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": candidate_sha,
        "stage4": {
            "call": f"bank{STAGE4_BANK}:${STAGE4_CALL_ADDR:04X}",
            "old_target": "$DB0F",
            "new_target": "$DB10",
            "saved_t_per_helper_hit": 4,
        },
        "stage7": {
            "marker": f"bank{STAGE4_BANK}:${STAGE7_MARKER_ADDR:04X}",
            "old": STAGE7_OLD_MARKER.hex(" ").upper(),
            "new": STAGE7_NEW_MARKER.hex(" ").upper(),
            "saved_t_per_admitted_publication": 308,
            "terminal_e": "$80",
            "nonterminal_e": [
                f"${value:02X}" for value in post_row_e[:-1]
            ],
        },
        "isolation": {
            "r354_vblank_publication_bytes_changed": 0,
            "stage1_hazard_bytes_changed": 0,
            "stage4_functional_bytes_changed": 1,
            "stage7_marker_functional_bytes_changed": len(marker_changed),
        },
        "required_live_gates": [
            "all-stage speed and exact route coverage",
            "Stage-1 menu/timer cadence",
            "Stage-1 rotating-hazard every-frame raster",
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
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes(),
    )
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
