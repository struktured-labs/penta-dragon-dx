#!/usr/bin/env python3
"""Splice the receipt-isolated postcomputed attribute copier into a candidate.

The normal and ``--buffered-stage1-attrs`` builds must differ only inside the
fixed bank-1 map copier (plus checksums). This tool proves that contract, copies
the buffered implementation onto an already-expanded candidate, and repairs
the cartridge checksums. It lets the changed-layout transport be measured
without rebuilding or perturbing the candidate's Ted/Stage-1 expansion banks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


INLINE_START = 0x42A7
INLINE_END = 0x436E
RST30_START = 0x0030
RST30_END = 0x0033
CHECKSUM_BYTES = {0x014D, 0x014E, 0x014F}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def header_checksum(data: bytes) -> int:
    value = 0
    for byte in data[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def global_checksum(data: bytes) -> int:
    return sum(data[:0x014E] + data[0x0150:]) & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("default_build", type=Path)
    parser.add_argument("postcomputed_build", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    candidate = args.candidate.read_bytes()
    default = args.default_build.read_bytes()
    postcomputed = args.postcomputed_build.read_bytes()
    if len(candidate) != 512 * 1024:
        parser.error(f"candidate is {len(candidate)} bytes, expected 512 KiB")
    if len(default) != len(postcomputed) or len(default) != 256 * 1024:
        parser.error("donor builds must both be 256 KiB")

    donor_differences = {
        index for index, (before, after) in enumerate(zip(default, postcomputed))
        if before != after
    }
    allowed = (
        set(range(INLINE_START, INLINE_END))
        | set(range(RST30_START, RST30_END))
        | CHECKSUM_BYTES
    )
    unexpected = sorted(donor_differences - allowed)
    if unexpected:
        parser.error(
            "postcomputed donor has changes outside isolated copier: "
            + ", ".join(f"${offset:06X}" for offset in unexpected[:16])
        )
    if not donor_differences - CHECKSUM_BYTES:
        parser.error("postcomputed donor does not change the inline copier")

    patched = bytearray(candidate)
    patched[RST30_START:RST30_END] = postcomputed[RST30_START:RST30_END]
    patched[INLINE_START:INLINE_END] = postcomputed[INLINE_START:INLINE_END]
    patched[0x014D] = header_checksum(patched)
    checksum = global_checksum(patched)
    patched[0x014E:0x0150] = checksum.to_bytes(2, "big")

    changed = [
        index for index, (before, after) in enumerate(zip(candidate, patched))
        if before != after
    ]
    allowed_candidate = (
        set(range(INLINE_START, INLINE_END))
        | set(range(RST30_START, RST30_END))
        | CHECKSUM_BYTES
    )
    assert not (set(changed) - allowed_candidate)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    report = {
        "status": "pass",
        "candidate": str(args.candidate),
        "candidate_sha256": sha256(candidate),
        "default_donor": str(args.default_build),
        "default_donor_sha256": sha256(default),
        "postcomputed_donor": str(args.postcomputed_build),
        "postcomputed_donor_sha256": sha256(postcomputed),
        "output": str(args.output),
        "output_sha256": sha256(patched),
        "inline_range": [f"{INLINE_START:04X}", f"{INLINE_END - 1:04X}"],
        "rst30_range": [f"{RST30_START:04X}", f"{RST30_END - 1:04X}"],
        "donor_changed_bytes": len(donor_differences),
        "candidate_changed_bytes": len(changed),
        "checksums": {
            "header": f"{patched[0x014D]:02X}",
            "global": f"{checksum:04X}",
        },
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
