#!/usr/bin/env python3
"""Isolate Stage-1 loading retirement from the shared bank-31 dispatcher."""
import argparse
import hashlib
import json
from pathlib import Path
import build_stage_card_blank_trial_r535 as shared

ROOT = Path(__file__).resolve().parents[2]
BASE_SHA = shared.BASE_SHA
HOOK = 0x4146
ENTRY = 0x6C80
BANK = 20
CAVE = BANK * 0x4000 + ENTRY - 0x4000


def helper() -> bytes:
    # All branches in the proven black-retirement body are relative. It has
    # no calls or absolute jumps into its former bank-31 location.
    return shared.payloads()[1]


def build(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError("requires exact menu/title tile-retirement trial")
    if source[HOOK:HOOK+5] != bytes.fromhex("21 85 DC 06 28"):
        raise ValueError("cold loader setup preimage differs")
    body = helper()
    if len(body) > 0x55 or source[CAVE:CAVE+len(body)] != b"\xff" * len(body):
        raise ValueError("private bank-20 entry is not wholly erased slack")
    # A neighboring contextual-return trampoline is an existing live owner.
    # Explicitly protect it as well as all bytes outside the claimed cave.
    neighbor = BANK * 0x4000 + 0x6CDF - 0x4000
    if source[neighbor:neighbor+5] != bytes.fromhex("3E 13 CD 61 00"):
        raise ValueError("adjacent contextual trampoline differs")
    rom = bytearray(source)
    rom[HOOK:HOOK+5] = bytes.fromhex("3E 14 CD 47 08")
    rom[CAVE:CAVE+len(body)] = body
    rom[0x14E:0x150] = ((sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF).to_bytes(2, "big")
    owned = set(range(HOOK, HOOK+5)) | set(range(CAVE, CAVE+len(body))) | {0x14E, 0x14F}
    if any(i not in owned for i, (x, y) in enumerate(zip(source, rom, strict=True)) if x != y):
        raise ValueError("private retirement escaped its two owned regions")
    return bytes(rom)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    out = args.output.resolve()
    if out.exists() or (ROOT / "tmp").resolve() not in out.parents:
        p.error("output must be fresh below repository tmp/")
    try:
        rom = build(args.source.read_bytes())
    except ValueError as error:
        p.error(str(error))
    receipt = dict(schema="penta-stage-card-private-r535-trial-v1", release_qualified=False,
                   source_sha256=BASE_SHA, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   source_tools={str(path.resolve()):hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in (Path(__file__), Path(shared.__file__))},
                   private_bank=BANK, private_entry=f"{ENTRY:04X}", helper_bytes=len(helper()),
                   bank31_dispatch_unchanged=True)
    out.mkdir(parents=True)
    (out / "candidate.gb").write_bytes(rom)
    (out / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
