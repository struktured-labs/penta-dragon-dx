#!/usr/bin/env python3
"""Route ordinary live Stage 1 through a bank-18 native copier clone.

r534 already owns the complete later-stage cadence and the hardened Stage-1
semantic/menu paths.  Its live map-decision RST reaches the bank-31 mux for
normal gameplay.  Change only the existing ``D880 != $0B`` branch to a small
selector in the adjacent authenticated zero cave:

* ``FFBA == 0`` discards the mux and RST synthetic frames, then enters an exact
  native copier clone at ``$42A7`` in the already-mapped bank 31.  The clone
  records the completed destination in ``FFC4``, restores bank 1, and returns
  through the common ``EI; RET`` at ``$42F9``.  Returning at either ``$42B1``
  or ``$13B3`` would dispatch a second full tile copy.  The reserved-gold
  experiment deliberately bypasses the semantic hazard scan; its live gates
  determine whether page ownership and the already-published hazard plane are
  sufficient.
* every later stage reaches r534's original ``$6D4D`` hot-resume bytes.
* scene ``$0B`` never takes the changed branch and therefore keeps the full
  transactional self-heal/menu path byte-exact.
* prerecorded demo publication never reaches this mux and remains byte-exact.

The overlay also applies the already-audited reserved-pickup-gold art policy.
That policy has zero runtime cost and operates on r534's current source art,
so the semantic rotating-hazard variants remain the input rather than being
replaced with an older tileset.

This remains an experimental exact-base overlay.  Live validation decides
whether the native terrain substitution is useful before it enters a
maintained builder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v302_title_fix import (  # noqa: E402
    BANK13,
    STAGE1_HIGH_TILE_GFX_OFFSET,
    STAGE1_LOW_TILE_GFX_OFFSET,
    TITLE_PALETTE_SOURCE_ADDR,
    apply_stage1_reserved_pickup_gold,
)

DEFAULT_BASE = ROOT / "tmp/stage4-cache-key-r534/candidate.gb"
DEFAULT_OUTPUT = ROOT / "tmp/r534-stage1-live-native/candidate.gb"
DEFAULT_RECEIPT = ROOT / "tmp/r534-stage1-live-native/build-receipt.json"
NATIVE_ROM = ROOT / "rom/Penta Dragon (J).gb"

BANK_SIZE = 0x4000
BASE_SHA256 = (
    "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b"
)
NATIVE_COPY_SHA256 = (
    "c574a103da0ec1e282967b6f25727085dff89db5a013d25d374019dc834cc3c4"
)

NATIVE_BANK = 31
NATIVE_ENTRY = 0x42A7
NATIVE_END = 0x436E
NATIVE_COMPLETION = NATIVE_END - 1
POSTCOPY_CONTINUATION = 0x42F9
SELECTOR_BANK = 31
SELECTOR_ADDR = 0x6D38
SELECTOR_END = 0x6D4D
HOT_RESUME = SELECTOR_END
MUX_SCENE_BRANCH = 0x6CF9
MUX_SCENE_BRANCH_PREIMAGE = bytes.fromhex("20 52")
MUX_SCENE_BRANCH_PATCH = bytes.fromhex("20 3D")

MAPPER_CORE = 0x0061
MAPPER_PREIMAGE = bytes.fromhex("EA 09 DC C3 BE 09")
POP_RET = 0x03A1
POP_RET_PREIMAGE = bytes.fromhex("E1 D1 C1 F1 C9")
FIXED_MUX_STUB = 0x0013
FIXED_MUX_STUB_PREIMAGE = bytes.fromhex("3E 1F C3 47 08")
MUX_ENTRY = 0x6C80
MUX_ENTRY_PREIMAGE = bytes.fromhex("E5 F8 04 7E FE E1")
DECISION_CALL = 0x42AE
DECISION_CALL_PREIMAGE = bytes.fromhex("CD 85 34 28 10")

CHECKSUM_OFFSETS = frozenset((0x014D, 0x014E, 0x014F))
STAGE1_TILE_HALF_SIZE = 0x800
# The builder's high-half constant is the signed-tile base: tile $80 begins
# another $800 bytes into that address calculation.
STAGE1_HIGH_TILE_GFX_START = (
    STAGE1_HIGH_TILE_GFX_OFFSET + STAGE1_TILE_HALF_SIZE
)
STAGE1_BG0_COLOR1_OFFSET = (
    BANK13 + TITLE_PALETTE_SOURCE_ADDR - 0x4000 + 2
)
STAGE1_RESERVED_LOW_SHA256 = (
    "ee621badf3670fb77e5692bd4e885169975bf49a1d2820dd9fb096a932bc45b2"
)
STAGE1_RESERVED_HIGH_SHA256 = (
    "0e06fe32f85620ec591ef3d0eb620ec7c34fad0709a73f87891de255e82d6f3d"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if not 0x4000 <= address < 0x8000:
        raise ValueError(f"switchable address out of range: ${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    rom[0x014E] = 0
    rom[0x014F] = 0
    total = sum(rom) & 0xFFFF
    rom[0x014E] = total >> 8
    rom[0x014F] = total & 0xFF


def build_selector() -> bytes:
    """Classify FFBA while preserving r534's later-stage continuation.

    Entry stack is ``[saved HL, $084D, $3493, $42B1, caller...]``.  The
    Stage-1 arm restores HL, removes the two synthetic return words plus the
    original ``$42B1`` decision return, pushes the common ``EI; RET``, and
    jumps into the same-address clone already resident in bank 31.  Nonzero
    FFBA branches directly to the untouched hot resume.
    """
    code = bytes([
        0xF0, 0xBA,                         # LDH A,[$FFBA]
        0xB7,                               # OR A
        0x20, HOT_RESUME - (SELECTOR_ADDR + 5),  # JR NZ,$6D4D
        0xE1,                               # POP HL (map destination)
        0xE8, 0x06,                         # ADD SP,+6 (084D,3493,42B1)
        0x01, POSTCOPY_CONTINUATION & 0xFF,
        POSTCOPY_CONTINUATION >> 8,         # BC = semantic post-copy entry
        0xC5,                               # PUSH BC
        0xC3, NATIVE_ENTRY & 0xFF,
        NATIVE_ENTRY >> 8,                  # already-mapped bank-31 clone
    ])
    assert len(code) == 15
    assert SELECTOR_ADDR + len(code) <= SELECTOR_END
    return code


def build_completion() -> bytes:
    """Record the destination, restore bank 1/registers, and RET to $42F9."""
    return bytes([
        0x7C, 0xE0, 0xC4,                   # FFC4 = completed destination H
        0xF5, 0xC5, 0xD5, 0xE5,             # PUSH AF/BC/DE/HL
        0x21, POP_RET & 0xFF, POP_RET >> 8,
        0xE5,                               # mapper RET -> fixed epilogue
        0x3E, 0x01,
        0xC3, MAPPER_CORE & 0xFF, MAPPER_CORE >> 8,
    ])


def build(source: bytes, native: bytes) -> tuple[bytes, dict[str, object]]:
    if digest(source) != BASE_SHA256:
        raise ValueError("requires exact r534 base")
    if len(source) != 32 * BANK_SIZE:
        raise ValueError("requires expanded 512 KiB r534 image")
    if len(native) != 16 * BANK_SIZE:
        raise ValueError("requires exact 256 KiB native ROM")

    native_copy = native[NATIVE_ENTRY:NATIVE_END]
    if digest(native_copy) != NATIVE_COPY_SHA256:
        raise AssertionError("native $42A7-$436D copier identity changed")
    if native_copy[-1:] != bytes((0xC9,)):
        raise AssertionError("native copier no longer ends in RET")

    checks = (
        (MAPPER_CORE, MAPPER_PREIMAGE, "fixed mapper"),
        (POP_RET, POP_RET_PREIMAGE, "fixed POP/RET epilogue"),
        (FIXED_MUX_STUB, FIXED_MUX_STUB_PREIMAGE, "bank-31 mapper stub"),
        (DECISION_CALL, DECISION_CALL_PREIMAGE, "live decision call"),
    )
    for offset, preimage, label in checks:
        if source[offset:offset + len(preimage)] != preimage:
            raise AssertionError(f"{label} preimage changed")

    mux_entry = bank_offset(SELECTOR_BANK, MUX_ENTRY)
    if source[mux_entry:mux_entry + len(MUX_ENTRY_PREIMAGE)] \
            != MUX_ENTRY_PREIMAGE:
        raise AssertionError("bank-31 mux entry changed")
    branch = bank_offset(SELECTOR_BANK, MUX_SCENE_BRANCH)
    if source[branch:branch + 2] != MUX_SCENE_BRANCH_PREIMAGE:
        raise AssertionError("bank-31 normal-scene branch changed")

    selector = build_selector()
    selector_off = bank_offset(SELECTOR_BANK, SELECTOR_ADDR)
    selector_capacity = SELECTOR_END - SELECTOR_ADDR
    if source[selector_off:selector_off + selector_capacity] \
            != bytes(selector_capacity):
        raise AssertionError("bank-31 selector cave is not exact zero")

    clone_off = bank_offset(NATIVE_BANK, NATIVE_ENTRY)
    completion = build_completion()
    clone_end = bank_offset(
        NATIVE_BANK, NATIVE_COMPLETION + len(completion)
    )
    if source[clone_off:clone_end] != bytes([0xFF]) * (clone_end - clone_off):
        raise AssertionError("bank-18 native clone range is not exact $FF")

    rom = bytearray(source)
    rom[branch:branch + 2] = MUX_SCENE_BRANCH_PATCH
    rom[selector_off:selector_off + len(selector)] = selector
    rom[clone_off:clone_off + len(native_copy)] = native_copy
    completion_off = bank_offset(NATIVE_BANK, NATIVE_COMPLETION)
    rom[completion_off:completion_off + len(completion)] = completion
    apply_stage1_reserved_pickup_gold(rom, native)

    low_art = rom[
        STAGE1_LOW_TILE_GFX_OFFSET:
        STAGE1_LOW_TILE_GFX_OFFSET + STAGE1_TILE_HALF_SIZE
    ]
    high_art = rom[
        STAGE1_HIGH_TILE_GFX_START:
        STAGE1_HIGH_TILE_GFX_START + STAGE1_TILE_HALF_SIZE
    ]
    if digest(low_art) != STAGE1_RESERVED_LOW_SHA256:
        raise AssertionError("r534 reserved-gold low tile art identity changed")
    if digest(high_art) != STAGE1_RESERVED_HIGH_SHA256:
        raise AssertionError("r534 reserved-gold high tile art identity changed")
    update_checksums(rom)

    changed = {index for index, pair in enumerate(zip(source, rom))
               if pair[0] != pair[1]}
    allowed = set(CHECKSUM_OFFSETS)
    allowed.update(range(branch, branch + 2))
    allowed.update(range(selector_off, selector_off + len(selector)))
    allowed.update(range(clone_off, clone_off + len(native_copy)))
    allowed.update(range(completion_off, completion_off + len(completion)))
    allowed.update(range(
        STAGE1_LOW_TILE_GFX_OFFSET,
        STAGE1_LOW_TILE_GFX_OFFSET + STAGE1_TILE_HALF_SIZE,
    ))
    allowed.update(range(
        STAGE1_HIGH_TILE_GFX_START,
        STAGE1_HIGH_TILE_GFX_START + STAGE1_TILE_HALF_SIZE,
    ))
    allowed.update(range(STAGE1_BG0_COLOR1_OFFSET, STAGE1_BG0_COLOR1_OFFSET + 2))
    if not changed <= allowed:
        raise AssertionError(
            f"overlay changed bytes outside ownership: {sorted(changed - allowed)[:8]}"
        )

    report: dict[str, object] = {
        "schema": "penta.r534-stage1-live-native-build.v6",
        "experimental": True,
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": digest(rom),
        "native_copy_sha256": NATIVE_COPY_SHA256,
        "native_bank": NATIVE_BANK,
        "native_entry": f"${NATIVE_ENTRY:04X}",
        "selector_bank": SELECTOR_BANK,
        "selector_range": (
            f"${SELECTOR_ADDR:04X}-${SELECTOR_ADDR + len(selector) - 1:04X}"
        ),
        "scene0b_path_unchanged": True,
        "demo_path_unchanged": True,
        "stage1_semantic_postcopy_skipped": True,
        "stage1_destination_latch_published": True,
        "stage1_postcopy_continuation": f"${POSTCOPY_CONTINUATION:04X}",
        "stage1_clone_uses_current_mux_bank": True,
        "stage1_extra_bank_switches": 0,
        "stage1_pickup_art_mode": "reserved-pickup-gold",
        "stage1_reserved_low_art_sha256": digest(low_art),
        "stage1_reserved_high_art_sha256": digest(high_art),
        "later_stage_hot_resume": f"${HOT_RESUME:04X}",
        "later_stage_added_machine_cycles": 6,
        "changed_bytes": len(changed),
    }
    return bytes(rom), report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--native-rom", type=Path, default=NATIVE_ROM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()

    result, report = build(args.base.read_bytes(), args.native_rom.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != result:
        raise SystemExit(f"immutable candidate collision: {args.output}")
    args.output.write_bytes(result)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
