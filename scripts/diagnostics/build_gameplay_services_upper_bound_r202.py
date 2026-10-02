#!/usr/bin/env python3
"""Build exact-r199 per-frame gameplay-service attribution controls.

Every output is non-promotable.  Calls are replaced in place with NOPs so the
guarded speed matrix can bound each wrapper service's cost without moving the
joypad sampler, wrapper teardown, or VBlank hook ABI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ALLOWED_BASES = {
    "0ebae52b5c74ecb5e0cd2bbee11c4ee4fa6aca118aeb0515333722e0273518e8": (
        "r199-window-safe"
    ),
    # Non-promotable stock-emitter upper bound used only to compose another
    # attribution control; all wrapper preimages remain exact r199 bytes.
    "d0ea1c4a1a920d8d64fd22128609ce37a15fd808f276320b11259ed92f15d3b4": (
        "r203-stock-oam-upper-bound"
    ),
    # Exact visual-safe r210.  This keeps the older attribution controls
    # reproducible while allowing current performance work to measure the
    # actual Pocket-qualified lineage instead of extrapolating from r199.
    "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273": (
        "r210-pocket-visual-safe"
    ),
    "1e51c4801bfbc8ff961b81e09958e7ce4ba55de0ec4f8644e36f897d6aebc09c": (
        "r231-pocket-visual-qualified-xflip"
    ),
}
BANK = 13
BANK_SIZE = 0x4000

GROUPS = {
    "death": (
        (0x6F20, bytes.fromhex("CD 00 71"), "death/story dispatcher"),
    ),
    "title": (
        (0x6F23, bytes.fromhex("CD 60 6A"), "title palette service"),
    ),
    "death-title": (
        (0x6F20, bytes.fromhex("CD 00 71"), "death/story dispatcher"),
        (0x6F23, bytes.fromhex("CD 60 6A"), "title palette service"),
    ),
    "palette": (
        (0x6F31, bytes.fromhex("CD 90 6C"), "pending palette scheduler"),
        (0x6F3A, bytes.fromhex("CC 90 6C"), "idle palette probe"),
    ),
    "prelude": (
        (0x6F6B, bytes.fromhex("C4 80 6E"), "color prelude"),
    ),
    "render-tail": (
        (0x6F7A, bytes.fromhex("CD 00 6E"), "full BG colorizer"),
        (0x6F7F, bytes.fromhex("CD 00 6B"), "fast OBJ colorizer"),
        (0x6F82, bytes.fromhex("CD A7 6D"), "glyph service"),
        (0x6F89, bytes.fromhex("C4 0E 6A"), "live hazard loader"),
    ),
    "full-bg": (
        (0x6F7A, bytes.fromhex("CD 00 6E"), "full BG colorizer"),
    ),
    "fast-obj": (
        (0x6F7F, bytes.fromhex("CD 00 6B"), "fast OBJ colorizer"),
    ),
    "glyph": (
        (0x6F82, bytes.fromhex("CD A7 6D"), "glyph service"),
    ),
    "glyph-prelude": (
        (0x6F6B, bytes.fromhex("C4 80 6E"), "color prelude"),
        (0x6F82, bytes.fromhex("CD A7 6D"), "glyph service"),
    ),
    "prelude-death-title": (
        (0x6F20, bytes.fromhex("CD 00 71"), "death/story dispatcher"),
        (0x6F23, bytes.fromhex("CD 60 6A"), "title palette service"),
        (0x6F6B, bytes.fromhex("C4 80 6E"), "color prelude"),
    ),
    "prelude-palette": (
        (0x6F31, bytes.fromhex("CD 90 6C"), "pending palette scheduler"),
        (0x6F3A, bytes.fromhex("CC 90 6C"), "idle palette probe"),
        (0x6F6B, bytes.fromhex("C4 80 6E"), "color prelude"),
    ),
    "prelude-full-bg": (
        (0x6F6B, bytes.fromhex("C4 80 6E"), "color prelude"),
        (0x6F7A, bytes.fromhex("CD 00 6E"), "full BG colorizer"),
    ),
    "prelude-live-loader": (
        (0x6F6B, bytes.fromhex("C4 80 6E"), "color prelude"),
        (0x6F89, bytes.fromhex("C4 0E 6A"), "live hazard loader"),
    ),
    "live-loader": (
        (0x6F89, bytes.fromhex("C4 0E 6A"), "live hazard loader"),
    ),
    "inactive-gameplay": (
        (0x6F20, bytes.fromhex("CD 00 71"), "death/story dispatcher"),
        (0x6F23, bytes.fromhex("CD 60 6A"), "title palette service"),
        (0x6F82, bytes.fromhex("CD A7 6D"), "glyph service"),
    ),
}


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def offset(address: int) -> int:
    return BANK * BANK_SIZE + address - 0x4000


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument(
        "--group", choices=(*GROUPS, "all"), default="all",
    )
    args = parser.parse_args()

    source = args.base.read_bytes()
    source_sha = digest(source)
    if source_sha not in ALLOWED_BASES:
        raise SystemExit(f"wrong qualified attribution base: {source_sha}")
    selected = GROUPS.keys() if args.group == "all" else (args.group,)
    patches = [item for group in selected for item in GROUPS[group]]

    rom = bytearray(source)
    changed = []
    services = []
    for address, preimage, name in patches:
        start = offset(address)
        if rom[start:start + len(preimage)] != preimage:
            raise SystemExit(f"{name} preimage moved at bank13:${address:04X}")
        rom[start:start + len(preimage)] = bytes(len(preimage))
        changed.extend(range(start, start + len(preimage)))
        services.append(name)
    update_checksums(rom)
    output = bytes(rom)

    report = {
        "schema": "penta-gameplay-services-upper-bound-r202-v1",
        "status": "NON_PROMOTABLE_ATTRIBUTION_ONLY",
        "promotable": False,
        "group": args.group,
        "base_sha256": source_sha,
        "base_profile": ALLOWED_BASES[source_sha],
        "candidate_sha256": digest(output),
        "disabled_services": services,
        "functional_bytes_changed": len(changed),
        "joypad_sampler_preserved": True,
        "wrapper_teardown_preserved": True,
        "warning": "visual/palette services are deliberately disabled",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
