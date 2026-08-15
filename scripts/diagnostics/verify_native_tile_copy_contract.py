#!/usr/bin/env python3
"""Prove a diagnostic ROM restores every fixed-bank native tile-copy range."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

SCHEMA = "penta-native-tile-copy-contract-v1"
RANGES = {
    "rst30_entry": (0x0030, 0x0033),
    "native_emitter_tail": (0x3482, 0x34A3),
    "native_24x24_copier": (0x42A0, 0x436E),
}

def compare(candidate: bytes, original: bytes):
    rows = {}
    for name, (start, end) in RANGES.items():
        mismatches = sum(a != b for a, b in zip(candidate[start:end], original[start:end]))
        rows[name] = {"start": f"{start:04X}", "end_exclusive": f"{end:04X}",
            "bytes": end - start, "mismatches": mismatches, "status": "pass" if not mismatches else "fail"}
    return rows

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path); parser.add_argument("--original", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    candidate, original = args.rom.read_bytes(), args.original.read_bytes()
    rows = compare(candidate, original)
    control = bytearray(candidate); control[0x3482] ^= 0xFF
    negative = compare(bytes(control), original)["native_emitter_tail"]["status"] == "fail"
    passed = all(row["status"] == "pass" for row in rows.values()) and negative
    receipt = {"schema": SCHEMA, "status": "pass" if passed else "fail",
        "rom_sha256": hashlib.sha256(candidate).hexdigest(), "ranges": rows,
        "negative_control": {"mutated_emitter_tail_rejected": negative}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True)); return 0 if passed else 1

if __name__ == "__main__": raise SystemExit(main())
