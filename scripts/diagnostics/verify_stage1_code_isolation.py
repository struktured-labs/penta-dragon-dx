#!/usr/bin/env python3
"""Verify that Stage-1 code no longer overwrites native bank-14 data.

The production ROM historically treated zero-valued spans in native bank 14
as executable caves. Boss layout expansion also reads those zeroes as data.
The safe expanded-ROM contract is therefore:

* candidate bank 14 is byte-exact stock data;
* candidate bank 19 is byte-exact pre-isolation production bank 14;
* only the fixed Stage-1 mapper and the two bank-13/16 art-loader immediates
  change from bank 14 to bank 19;
* the native layout mapper at fixed $30D8 remains bank 14; and
* every other non-checksum byte remains byte-exact production baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BANK_SIZE = 0x4000
NATIVE_LAYOUT_BANK = 14
STAGE1_CODE_BANK = 19
NATIVE_LAYOUT_MAPPER = 0x30D8
STAGE1_BANK_IMMEDIATES = (0x10E3, 0x36A23, 0x42A23)
CHECKSUM_BYTES = (0x014E, 0x014F)
KNOWN_COLLISION_ADDR = 0x6C88


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bank(data: bytes, number: int) -> bytes:
    start = number * BANK_SIZE
    return data[start:start + BANK_SIZE]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stock", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    stock = args.stock.read_bytes()
    baseline = args.baseline.read_bytes()
    candidate = args.candidate.read_bytes()
    failures: list[str] = []

    if len(stock) != 16 * BANK_SIZE:
        failures.append(f"stock size is {len(stock)}, expected {16 * BANK_SIZE}")
    if len(baseline) != 32 * BANK_SIZE:
        failures.append(
            f"baseline size is {len(baseline)}, expected {32 * BANK_SIZE}"
        )
    if len(candidate) != len(baseline):
        failures.append(
            f"candidate size {len(candidate)} != baseline {len(baseline)}"
        )

    if not failures:
        stock_bank14 = bank(stock, NATIVE_LAYOUT_BANK)
        baseline_bank14 = bank(baseline, NATIVE_LAYOUT_BANK)
        candidate_bank14 = bank(candidate, NATIVE_LAYOUT_BANK)
        candidate_bank19 = bank(candidate, STAGE1_CODE_BANK)
        if candidate_bank14 != stock_bank14:
            failures.append("candidate bank 14 is not byte-exact stock")
        if candidate_bank19 != baseline_bank14:
            failures.append("candidate bank 19 is not byte-exact baseline bank 14")
        if candidate[NATIVE_LAYOUT_MAPPER:NATIVE_LAYOUT_MAPPER + 5] != bytes.fromhex(
            "3E 0E CD 61 00"
        ):
            failures.append("native fixed mapper no longer selects bank 14")

        for site in STAGE1_BANK_IMMEDIATES:
            if baseline[site] != NATIVE_LAYOUT_BANK:
                failures.append(
                    f"baseline Stage-1 immediate ${site:06X} is "
                    f"${baseline[site]:02X}, expected $0E"
                )
            if candidate[site] != STAGE1_CODE_BANK:
                failures.append(
                    f"candidate Stage-1 immediate ${site:06X} is "
                    f"${candidate[site]:02X}, expected $13"
                )

        native_collision = (
            NATIVE_LAYOUT_BANK * BANK_SIZE
            + KNOWN_COLLISION_ADDR - 0x4000
        )
        stage1_collision = (
            STAGE1_CODE_BANK * BANK_SIZE
            + KNOWN_COLLISION_ADDR - 0x4000
        )
        if candidate[native_collision] != stock[native_collision]:
            failures.append("known bank-14 collision byte was not restored")
        if candidate[stage1_collision] != baseline[native_collision]:
            failures.append("known Stage-1 opcode was not preserved in bank 19")

        allowed = set(CHECKSUM_BYTES) | set(STAGE1_BANK_IMMEDIATES)
        allowed.update(range(14 * BANK_SIZE, 15 * BANK_SIZE))
        allowed.update(range(19 * BANK_SIZE, 20 * BANK_SIZE))
        unexpected = [
            offset
            for offset, (before, after) in enumerate(zip(baseline, candidate))
            if before != after and offset not in allowed
        ]
        if unexpected:
            preview = ", ".join(f"${offset:06X}" for offset in unexpected[:12])
            failures.append(
                f"{len(unexpected)} unexpected byte differences: {preview}"
            )

    report = {
        "status": "PASS" if not failures else "FAIL",
        "stock": {"path": str(args.stock), "sha256": sha256(stock)},
        "baseline": {"path": str(args.baseline), "sha256": sha256(baseline)},
        "candidate": {"path": str(args.candidate), "sha256": sha256(candidate)},
        "native_layout_bank": NATIVE_LAYOUT_BANK,
        "stage1_code_bank": STAGE1_CODE_BANK,
        "stage1_bank_immediates": [f"0x{site:06X}" for site in STAGE1_BANK_IMMEDIATES],
        "failures": failures,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
