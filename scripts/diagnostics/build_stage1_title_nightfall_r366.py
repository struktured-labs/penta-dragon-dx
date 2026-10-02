#!/usr/bin/env python3
"""Build r366: restore the reviewed Nightfall title treatment on exact r365.

r365 retains the safe monochrome title path, while the separately reviewed
Nightfall prototype was never composed onto the Stage-1 repair chain.  Bank 21
is now owned by Stage-1 helpers, so this builder relocates the unchanged title
attribute image/palette service to virgin bank 23.  It also preserves the
existing scene-transition service and adds a tiny old-title rearm wrapper so
the title attributes are cleared before the following story or game route.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_title_color_prototype as title  # noqa: E402


BANK_SIZE = 0x4000
BASE = TMP / "stage1-sara-priority-clear-r365/candidate.gb"
BASE_RECEIPT = TMP / "stage1-sara-priority-clear-r365/build-receipt.json"
BASE_SHA256 = "4243fa84946bc0325ff46b510103c1e1c4213f0879e40b5aff77d026bf69ea88"
BASE_RECEIPT_SHA256 = (
    "30afd4763be9f42ad1b8100d43a4da8c54c9becf50dc2f0e324a60ea875f411b"
)
DEFAULT_OUTPUT = TMP / "stage1-title-nightfall-r366/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-title-nightfall-r366/build-receipt.json"
EXPECTED_CANDIDATE_SHA256 = (
    "0ebfe1d5f2d920459c8b9edfd4759f171c4afd4307de1b7e54855da1f2fff6ba"
)

LIVE_BANK = 13
CODE_BANK = 23
ATTR_IMAGE_ADDR = 0x6000
PAL_DATA_ADDR = 0x6240
SERVICE_ADDR = 0x6C80
TITLE_SCENE = 0x01

CLEANER_TAIL_ADDR = 0x6E4E
CLEANER_TAIL_PREIMAGE = bytes.fromhex("AF E0 4F F1 E0")
CLEANER_TAIL_PATCH = bytes((0x3E, CODE_BANK, 0xCD, 0x47, 0x08))

# These are live NOP pads, not dead caves.  Their first JR preserves ordinary
# fallthrough while the private entry behind it is reached only by CALL.
REARM_WRAPPER_PAD_ADDR = 0x6E60
REARM_WRAPPER_PAD_SIZE = 11
REARM_WRAPPER_ADDR = REARM_WRAPPER_PAD_ADDR + 2
CLEAR_HELPER_PAD_ADDR = 0x6E9D
CLEAR_HELPER_PAD_SIZE = 9
CLEAR_HELPER_ADDR = CLEAR_HELPER_PAD_ADDR + 2
TRANSITION_CRYSTAL_CALL_ADDR = 0x7D01
TRANSITION_CRYSTAL_CALL_PREIMAGE = bytes.fromhex("CD DF 6B")

CHECKSUM_OFFSETS = frozenset((0x014D, 0x014E, 0x014F))


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def bank_offset(bank: int, address: int) -> int:
    require(0x4000 <= address < 0x8000, f"invalid banked address ${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    checksum = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = checksum.to_bytes(2, "big")


def checked_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    require(resolved != TMP.resolve() and TMP.resolve() in resolved.parents,
            f"{label} must be below repository tmp/")
    return resolved


def build_title_service() -> bytes:
    """Paint Nightfall inside the existing LCD-off two-map cleaner."""
    code = bytearray((0xFA, 0x80, 0xD8, 0x3D, 0x20, 0x00))
    code += bytes((0x3E, 0x88, 0xE0, 0x68))
    code += bytes((0x21, PAL_DATA_ADDR & 0xFF, PAL_DATA_ADDR >> 8))
    code += bytes((0x06, 48))
    code += bytes((0x2A, 0xE0, 0x69, 0x05, 0x20, 0xFA))
    code += bytes((0x3E, 0x01, 0xE0, 0x4F))
    blocks = (title.IMAGE_ROWS * title.MAP_STRIDE) // 16
    for destination in (
        title.MAP_BASE + title.IMAGE_FIRST_ROW * title.MAP_STRIDE,
        title.MAP_BASE + 0x400 + title.IMAGE_FIRST_ROW * title.MAP_STRIDE,
    ):
        for register, value in (
            (0x51, (ATTR_IMAGE_ADDR >> 8) & 0xFF),
            (0x52, ATTR_IMAGE_ADDR & 0xF0),
            (0x53, ((destination - 0x8000) >> 8) & 0x1F),
            (0x54, destination & 0xF0),
            (0x55, blocks - 1),
        ):
            code += bytes((0x3E, value, 0xE0, register))
    restore = len(code)
    code[5] = (restore - 6) & 0xFF
    # Displaced cleaner tail: VBK=0, restore saved LCDC, then return bank 13
    # in A for the fixed-bank $0847 trampoline.
    code += bytes.fromhex("AF E0 4F F1 E0 40")
    code += bytes((0x3E, LIVE_BANK, 0xC9))
    return bytes(code)


def build_rearm_pads() -> tuple[bytes, bytes]:
    """Return the two fenced live-pad images used by scene transitions."""
    # Entry $6E62: old scene is [HL], new scene is B.  Leaving old $01 calls
    # the five-byte clear leaf, then tail-jumps to the original $6BDF helper.
    wrapper = bytes.fromhex("7E 3D CC 9F 6E 78 C3 DF 6B")
    wrapper_pad = bytes((0x18, len(wrapper))) + wrapper
    require(len(wrapper_pad) == REARM_WRAPPER_PAD_SIZE,
            "title rearm wrapper pad size changed")

    clear = bytes.fromhex("AF EA 08 DF C9")
    skip = CLEAR_HELPER_PAD_SIZE - 2
    clear_pad = bytes((0x18, skip)) + clear + bytes(
        CLEAR_HELPER_PAD_SIZE - 2 - len(clear)
    )
    require(len(clear_pad) == CLEAR_HELPER_PAD_SIZE,
            "title clear helper pad size changed")
    return wrapper_pad, clear_pad


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == 32 * BANK_SIZE, "r365 base size changed")
    require(digest(source) == BASE_SHA256,
            f"wrong exact r365 base: {digest(source)}")
    require(digest(receipt_bytes) == BASE_RECEIPT_SHA256,
            "r365 receipt identity drifted")
    base_receipt = json.loads(receipt_bytes)
    require(base_receipt.get("schema")
            == "penta-stage1-sara-priority-clear-r365-build-v1",
            "r365 receipt schema drifted")
    require(base_receipt.get("candidate_sha256") == BASE_SHA256,
            "r365 receipt names another candidate")
    require(title.ACTIVE_SCHEME == "Nightfall",
            "palette YAML no longer selects reviewed Nightfall")

    records = title.parse_title_list(source)
    attr_image, coverage = title.build_attribute_image(records)
    palettes = title.build_palette_block(title.SCHEMES["Nightfall"])
    service = build_title_service()
    wrapper_pad, clear_pad = build_rearm_pads()

    require(set(source[CODE_BANK * BANK_SIZE:(CODE_BANK + 1) * BANK_SIZE])
            == {0xFF}, "bank 23 is no longer virgin expansion space")
    cleaner = bank_offset(LIVE_BANK, CLEANER_TAIL_ADDR)
    require(source[cleaner:cleaner + len(CLEANER_TAIL_PREIMAGE)]
            == CLEANER_TAIL_PREIMAGE, "cleaner tail preimage changed")
    wrapper = bank_offset(LIVE_BANK, REARM_WRAPPER_PAD_ADDR)
    require(source[wrapper:wrapper + REARM_WRAPPER_PAD_SIZE]
            == bytes(REARM_WRAPPER_PAD_SIZE),
            "rearm wrapper live NOP pad changed")
    clear = bank_offset(LIVE_BANK, CLEAR_HELPER_PAD_ADDR)
    require(source[clear:clear + CLEAR_HELPER_PAD_SIZE]
            == bytes(CLEAR_HELPER_PAD_SIZE),
            "clear-helper live NOP pad changed")
    transition = bank_offset(LIVE_BANK, TRANSITION_CRYSTAL_CALL_ADDR)
    require(source[
        transition:transition + len(TRANSITION_CRYSTAL_CALL_PREIMAGE)
    ] == TRANSITION_CRYSTAL_CALL_PREIMAGE,
        "scene-transition crystal call changed")

    rom = bytearray(source)
    owned: set[int] = set()

    def install(bank: int, address: int, data: bytes) -> None:
        offset = bank_offset(bank, address)
        rom[offset:offset + len(data)] = data
        owned.update(range(offset, offset + len(data)))

    install(CODE_BANK, ATTR_IMAGE_ADDR, bytes(attr_image))
    install(CODE_BANK, PAL_DATA_ADDR, palettes)
    install(CODE_BANK, SERVICE_ADDR, service)
    install(LIVE_BANK, CLEANER_TAIL_ADDR, CLEANER_TAIL_PATCH)
    install(LIVE_BANK, REARM_WRAPPER_PAD_ADDR, wrapper_pad)
    install(LIVE_BANK, CLEAR_HELPER_PAD_ADDR, clear_pad)
    install(
        LIVE_BANK,
        TRANSITION_CRYSTAL_CALL_ADDR,
        bytes((0xCD, REARM_WRAPPER_ADDR & 0xFF,
               REARM_WRAPPER_ADDR >> 8)),
    )
    update_checksums(rom)
    candidate = bytes(rom)

    changed = {
        index
        for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    }
    require(changed <= owned | CHECKSUM_OFFSETS,
            f"r366 escaped owned bytes: {sorted(changed - owned - CHECKSUM_OFFSETS)}")
    require(candidate[0x1199:0x119B] == bytes.fromhex("CB BF"),
            "r365 Sara priority clear was not preserved")

    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {candidate_sha}")
    receipt: dict[str, object] = {
        "schema": "penta-stage1-title-nightfall-r366-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_r365_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": candidate_sha,
        "title": {
            "scheme": "Nightfall",
            "palette_source": str(title.PALETTE_YAML),
            "palette_source_sha256": digest(title.PALETTE_YAML.read_bytes()),
            "attribute_cells": coverage,
            "expansion_bank": CODE_BANK,
            "attribute_image": f"bank{CODE_BANK}:${ATTR_IMAGE_ADDR:04X}",
            "palette_block": f"bank{CODE_BANK}:${PAL_DATA_ADDR:04X}",
            "service": f"bank{CODE_BANK}:${SERVICE_ADDR:04X}",
        },
        "transition_contract": {
            "paint": "inside existing LCD-off two-map neutral cleaner",
            "leave_title": "old scene $01 rearms DF08 before stock transition helper",
            "non_title": "restores displaced VBK/LCDC tail without painting",
            "steady_gameplay_cost": 0,
        },
        "required_live_gates": base_receipt["required_live_gates"] + [
            "cold and returned Nightfall title raster/attribute roles",
            "title leave to opening, GAME START, splash, and Stage 1",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = checked_output(args.output, "candidate")
    receipt_path = checked_output(args.receipt, "receipt")
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "candidate_sha256": receipt["candidate_sha256"],
        "output": str(output),
        "status": receipt["status"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
