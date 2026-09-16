#!/usr/bin/env python3
"""Exact-parent diagnostic repair for Penta's late visible-seam VRAM access."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_SHA = "fe14b0e3c392b3d822208684636e1017cb093613d28e6ca477999535df164576"
HOOK = 13 * 0x4000 + 0x1734
HELPER = 20 * 0x4000 + 0x2250
PREIMAGE = bytes.fromhex("21 2F 99 7E 6F 26 C6 7E 47 21 2F 99 3E 01 E0 4F 70")
WAIT = bytes.fromhex("F0 41 E6 02 20 FA")


def payloads():
    # The original scene-14 condition remains at $572C. Stack the bank-13
    # continuation and bank-20 entry for the fixed mapper's RET; no return
    # instruction is fetched from a bank that has just been unmapped.
    stub = bytes.fromhex("21 45 57 E5 21 50 62 E5 3E 14 C3 61 00")
    stub += bytes(len(PREIMAGE) - len(stub))
    helper = (bytes.fromhex("21 2F 99") + WAIT
              + bytes.fromhex("7E 6F 26 C6 7E 47 21 2F 99 3E 01 E0 4F")
              + WAIT + bytes.fromhex("70 3E 0D C3 61 00"))
    # Return at $5745 with HL=$992F, B=the LUT result, and VBK=1, just as
    # the original write did. Its retained tail restores VBK=0 and dispatches
    # the original lava override. C/DE and interrupt state are untouched.
    return stub, helper


def build(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError("requires exact r535 black-retirement parent")
    stub, helper = payloads()
    patches = ((HOOK, PREIMAGE, stub), (HELPER, b"\xff" * len(helper), helper))
    result = bytearray(source)
    owned = {0x14E, 0x14F}
    for offset, before, after in patches:
        if source[offset:offset + len(before)] != before:
            raise ValueError(f"seam repair preimage differs at {offset:06X}")
        assert len(before) == len(after)
        result[offset:offset + len(after)] = after
        owned.update(range(offset, offset + len(after)))
    result[0x14E:0x150] = (
        (sum(result[:0x14E]) + sum(result[0x150:])) & 0xFFFF
    ).to_bytes(2, "big")
    assert all(i in owned for i, (a, b) in enumerate(zip(source, result, strict=True)) if a != b)
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or (ROOT / "tmp").resolve() not in output.parents:
        parser.error("output must be fresh below repository tmp/")
    try:
        candidate = build(args.source.read_bytes())
    except ValueError as error:
        parser.error(str(error))
    receipt = dict(schema="penta-seam-vram-r536-trial-v1", release_qualified=False,
                   source_sha256=BASE_SHA,
                   candidate_sha256=hashlib.sha256(candidate).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output.mkdir(parents=True)
    (output / "candidate.gb").write_bytes(candidate)
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
