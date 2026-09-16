#!/usr/bin/env python3
"""Experimental menu repair plus cycle-identical outgoing-title tile clear."""
import argparse
import hashlib
import json
from pathlib import Path
import build_stage1_menu_close_trial_r535 as menu

ROOT = Path(__file__).resolve().parents[2]
VBK_IMMEDIATE = 13 * 0x4000 + 0x13D0
FRONT = VBK_IMMEDIATE - 14
OLD_FRONT = bytes.fromhex(
    "FA FD DC B7 CA 01 6F F0 40 47 AF E0 40 3E 01 E0 4F "
    "21 00 98 AF 22 7C FE A0 20 F9 EA 4C DF E0 4F C3 FE 6E")


def build(source: bytes) -> bytes:
    # The existing builder authenticates the exact rejected r534 source and
    # scopes the independent menu repair before this single title operand.
    repaired_menu = menu.build(source, True, True)
    if source[FRONT:FRONT+len(OLD_FRONT)] != OLD_FRONT:
        raise ValueError("selector clear preimage differs")
    result = bytearray(repaired_menu)
    # Same instructions, iteration count, LCD writes, marker, registers and
    # continuation. Clear VBK=0 title tilemaps instead of their attributes.
    # The original scene cleanup still owns subsequent attribute clearing.
    result[VBK_IMMEDIATE] = 0
    result[0x14E:0x150] = (
        (sum(result[:0x14E]) + sum(result[0x150:])) & 0xFFFF
    ).to_bytes(2, "big")
    delta = {i for i, (a, b) in enumerate(zip(repaired_menu, result, strict=True)) if a != b}
    if delta - {VBK_IMMEDIATE, 0x14E, 0x14F}:
        raise ValueError("tile retirement escaped its single operand")
    return bytes(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() or (ROOT / "tmp").resolve() not in out.parents:
        parser.error("output must be fresh below repository tmp/")
    try:
        result = build(args.source.read_bytes())
    except ValueError as error:
        parser.error(str(error))
    receipt = dict(schema="penta-title-tile-retire-r535-trial-v1", release_qualified=False,
                   source_sha256=menu.BASE_SHA, candidate_sha256=hashlib.sha256(result).hexdigest(),
                   source_tools={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (Path(__file__), Path(menu.__file__))})
    out.mkdir(parents=True)
    (out / "candidate.gb").write_bytes(result)
    (out / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
