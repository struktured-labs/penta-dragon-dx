#!/usr/bin/env python3
"""Build the exact-r120 fixed-width later-dungeon cache-key isolation.

This intentionally applies only the collision-audited eight-sample key from
the r164 experiment.  It does not change the attribute compiler, DMA mode,
post-copy ABI, or any timing instruction.  The resulting ROM is diagnostic
until the patrol and long semantic-plane gates pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_key_r164 import BANKS, PATCHES
from build_later_gdma_upper_bound import ALLOWED_BASES, update_checksums


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    digest = sha256(source)
    if digest not in ALLOWED_BASES or ALLOWED_BASES[digest] != "r120":
        raise SystemExit(f"unqualified exact r120 base: {digest}")

    rom = bytearray(source)
    changed: list[int] = []
    for bank in BANKS:
        for cpu, before, after in PATCHES:
            offset = bank * 0x4000 + cpu - 0x4000
            if rom[offset:offset + len(before)] != before:
                raise SystemExit(
                    f"bank{bank}:${cpu:04X} cache-key preimage moved"
                )
            rom[offset:offset + len(after)] = after
            changed.extend(range(offset, offset + len(after)))

    update_checksums(rom)
    output = bytes(rom)
    report = {
        "schema": "penta-later-fixed-key-only-r181-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest,
        "candidate_sha256": sha256(output),
        "functional_payload_bytes_changed": len(set(changed)),
        "runtime_shape_changed": False,
        "runtime_cycle_shape_changed": False,
        "compiler_changed": False,
        "dma_mode_changed": False,
        "postcopy_abi_changed": False,
        "key_contract_source": "r164 1,218-layout collision-free receipt",
        "required_next_gate": "Stage-7 patrol, then long semantic-plane soak",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
