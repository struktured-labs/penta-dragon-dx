#!/usr/bin/env python3
"""Experimental local title rearm on the exact cold-dispatch r535 trial."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_SHA = "69ff940ace8e73e82aa5331dde39282d191814c4ca1b814afb19a13fbb6dc197"
BANK13 = 13 * 0x4000 - 0x4000
WRAPPER = BANK13 + 0x76D7
LEAF = BANK13 + 0x53D1
LOCAL_LEAF = bytes.fromhex("FA 4C DF FE A0 C8 C3 9F 6E")


def build(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError("requires exact cold-dispatch r535 trial")
    # Both paths through the replacement selector entry jump to $6F01.
    # Its retired clear body therefore has no fallthrough from $53C2.
    front = BANK13 + 0x53C2
    if source[front:front+15] != bytes.fromhex(
            "FA FD DC B7 CA 01 6F 3E A0 EA 4C DF C3 01 6F"):
        raise ValueError("selector entry no longer retires its old clear body")
    if source[LEAF:LEAF+9] != bytes.fromhex("E0 4F 21 00 98 AF 22 7C FE"):
        raise ValueError("retired clear body preimage differs")
    if source[WRAPPER:WRAPPER+14] != bytes.fromhex(
            "3E 1F CD 47 08 78 3D CC 9F 6E 78 C3 DF 6B"):
        raise ValueError("title wrapper preimage differs")
    result = bytearray(source)
    # Restore the original non-title instruction path. Only old scene 01
    # calls the marker guard; new-title entry retains its unconditional rearm.
    result[WRAPPER:WRAPPER+5] = bytes.fromhex("7E 3D CC D1 53")
    result[LEAF:LEAF+9] = LOCAL_LEAF
    result[0x14E:0x150] = (
        (sum(result[:0x14E]) + sum(result[0x150:])) & 0xFFFF
    ).to_bytes(2, "big")
    owned = set(range(WRAPPER, WRAPPER+5)) | set(range(LEAF, LEAF+9)) | {0x14E, 0x14F}
    if any(i not in owned for i, (a, b) in enumerate(zip(source, result)) if a != b):
        raise ValueError("local rearm escaped its owned bytes")
    return bytes(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or (ROOT / "tmp").resolve() not in output.parents:
        parser.error("output must be fresh below repository tmp/")
    try:
        rom = build(args.source.read_bytes())
    except ValueError as error:
        parser.error(str(error))
    receipt = dict(schema="penta-title-local-rearm-r535-trial-v1",
                   release_qualified=False, source_sha256=BASE_SHA,
                   candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    output.mkdir(parents=True)
    (output / "candidate.gb").write_bytes(rom)
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
