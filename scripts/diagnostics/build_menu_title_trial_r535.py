#!/usr/bin/env python3
"""Compose the disjoint operator-menu and outgoing-title experiments on r534."""
import argparse
import hashlib
import json
from pathlib import Path
import build_stage1_menu_close_trial_r535 as menu
import build_title_exit_defer_trial_r535 as title

ROOT = Path(__file__).resolve().parents[2]


def build(source: bytes) -> bytes:
    variants = (menu.build(source, True, True), title.build(source, True, True))
    result, owned = bytearray(source), set()
    for variant in variants:
        delta = {i for i,(a,b) in enumerate(zip(source,variant,strict=True)) if a != b} - {0x14E,0x14F}
        if delta & owned:
            raise ValueError("menu/title patch ownership overlaps")
        for offset in delta:
            result[offset] = variant[offset]
        owned |= delta
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 0xFFFF).to_bytes(2,"big")
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() or (ROOT / "tmp").resolve() not in out.parents:
        parser.error("output must be fresh below repository tmp/")
    result = build(args.source.read_bytes())
    out.mkdir(parents=True)
    (out / "candidate.gb").write_bytes(result)
    receipt = dict(schema="penta-menu-title-r535-trial-v1", release_qualified=False,
                   source_sha256=menu.BASE_SHA, candidate_sha256=hashlib.sha256(result).hexdigest(),
                   source_tools={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (Path(__file__), Path(menu.__file__), Path(title.__file__))})
    (out / "build-receipt.json").write_text(json.dumps(receipt,indent=2) + "\n")
    print(json.dumps(receipt,indent=2))


if __name__ == "__main__":
    main()
