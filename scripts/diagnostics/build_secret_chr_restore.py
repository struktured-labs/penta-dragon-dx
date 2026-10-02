#!/usr/bin/env python3
"""Issue #23: relocate stock bank-13 graphics out of injected-code storage.

The native $0CBB loader reads pages $74..$7F of bank 13 for tile selectors
$40..$4B. DX reuses those pages for code/LUTs. Give this graphics-only loader
an immutable stock bank at MBC5 bank 32. Its instruction count and data-copy
lengths are unchanged. This is experimental until transition qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT_SHA = "4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5"
STOCK_SHA = "2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30"
GRAPHICS_BANK = 32
LOADER = bytes.fromhex("F5 3E 0D CD 61 00 F1 2E 00 5D F1 01 80 00")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(parent: bytes, stock: bytes) -> bytes:
    if digest(parent) != PARENT_SHA or digest(stock) != STOCK_SHA:
        raise ValueError("requires exact reported parent and original Japanese ROM")
    if len(parent) != 0x80000 or parent[0x147:0x149] != bytes([0x1B, 4]):
        raise ValueError("requires the 512 KiB MBC5 parent")
    if parent[0x0CC5:0x0CC5 + len(LOADER)] != LOADER:
        raise ValueError("native graphics loader preimage differs")
    if parent[0x09BE:0x09C4] != bytes.fromhex("E0 99 EA 00 21 C9"):
        raise ValueError("native full-byte MBC5 bank setter differs")
    if parent[0x0CD5:0x0CE1] != bytes(range(0x74, 0x80)):
        raise ValueError("native graphics page table differs")
    result = bytearray(parent)
    result.extend(b"\xff" * (0x100000 - len(result)))
    # Whole stock bank, not an inferred free cave. Only its final twelve pages
    # are reachable through this loader; the rest stays original as well.
    result[0x80000:0x84000] = stock[13 * 0x4000:14 * 0x4000]
    result[0x0CC7] = GRAPHICS_BANK
    result[0x148] = 5  # 1 MiB, 64 banks; existing MBC5 cartridge type unchanged.
    result[0x14D] = (-sum(result[0x134:0x14D]) - 25) & 255
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 65535).to_bytes(2, "big")
    allowed = {0x0CC7, 0x148, 0x14D, 0x14E, 0x14F}
    if any(a != b and i not in allowed for i, (a, b) in enumerate(zip(parent, result))):
        raise ValueError("unexpected modification inside parent image")
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", type=Path)
    parser.add_argument("--stock", type=Path, default=Path("rom/Penta Dragon (J).gb"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root / "tmp").resolve() not in args.output.resolve().parents:
        parser.error("output must be fresh below repository tmp/")
    result = build(args.parent.read_bytes(), args.stock.read_bytes())
    args.output.mkdir(parents=True)
    (args.output / "candidate.gb").write_bytes(result)
    receipt = dict(issue=23, experimental=True, release_qualified=False,
                   parent_sha256=PARENT_SHA, stock_sha256=STOCK_SHA,
                   candidate_sha256=digest(result), graphics_bank=GRAPHICS_BANK,
                   builder_sha256=digest(Path(__file__).read_bytes()))
    (args.output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
