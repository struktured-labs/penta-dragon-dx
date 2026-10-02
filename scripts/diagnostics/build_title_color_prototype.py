#!/usr/bin/env python3
"""Colorize the Penta Dragon DX title screen (standalone prototype).

This is diagnostic tooling, never a release builder.  It takes an already
built candidate ROM, installs a title-only CGB attribute + palette service,
and writes the result somewhere else.  It never touches
``rom/working/penta_dragon_dx_FIXED.gb``.

Why the title is still DMG-style in the shipping candidate
---------------------------------------------------------
* Every title tile uses only colour indices 0 and 3, and every YAML BG row
  has ``7FFF`` at index 0 and ``0000`` at index 3.  Assigning attributes
  alone therefore cannot change a single pixel: new CRAM values are
  mandatory.
* ``build_attract_obj_colorizer`` deliberately routes both title paths
  (D880 $00/$01) around the gameplay BG sweep, so the WRAM tile->palette LUT
  at ``0xC600`` is never consulted on the title.  Filling that LUT is a
  no-op; a title-specific attribute writer is required.
* ``COLORIZE`` (bank13:$6E00) contains a one-shot two-map neutral cleaner
  that blanks 2048 attribute bytes with the LCD off whenever ``DF08`` is not
  ``$5A``.  The transition service rearms it on every scene change, so any
  title attribute write must happen *after* colorize in the same VBlank.

What this prototype installs
----------------------------
1. ``bank21`` (previously all-$FF) receives a 576-byte static attribute
   image for map rows 1..18, a 48-byte CRAM block for BG1..BG6, and a small
   routine at the DX bank entry vector ``$6C80``.  The routine writes the six
   palettes through ``FF68/FF69`` and then publishes the attribute image into
   both physical maps with two 36-block general-purpose DMAs.
2. ``bank13:$6EC4`` (48 free bytes between the demo pickup scanner and the
   level-select ROM tail) receives two small helpers:
   * ``paint`` runs the bank-21 service from *inside* colorize's own
     two-map cleaner, in the window where that routine has already switched
     to VBK=1 and turned the LCD off.  CRAM and a 1152-byte GDMA are
     therefore issued with the display disabled, exactly like the clear that
     precedes them, and no per-frame VBlank budget is consumed at all.
   * ``leave`` rearms that cleaner (``DF08``) whenever the *previous* scene
     was the title, so the title attribute map is blanked on the way out and
     the opening story / level selector / attract reel see the same neutral
     plane they see today.
3. Two three-byte retargets: the ``XOR A; LDH [FF4F],A`` that ends colorize's
   cleaner, and ``scene_detect``'s call to the title transition service.

Nothing outside the D880==$01 title menu is reachable, and no gameplay VBlank
gains a single cycle: both helpers sit on scene-change paths only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BANK_SIZE = 0x4000
LIVE_BANK = 13
CODE_BANK = 21

# --- stock addresses in the qualified candidate -------------------------- #
TITLE_LIST_ADDR = 0x4EA5           # bank 1, absolute ROM offset
CLEANER_TAIL_ADDR = 0x6E4E         # bank13: "XOR A; LDH [FF4F],A" in COLORIZE
TRANSITION_CALL_ADDR = 0x6F98      # bank13: scene_detect "CALL $7CFC"
TITLE_TRANSITION_SERVICE = 0x7CFC
SCENE_CACHE_ADDR = 0xDF0D
CLEANER_REARM_ADDR = 0xDF08
BANK_SWITCH_CALL_TRAMPOLINE = 0x0847  # CALL $0061; CALL $6C80; JP $0061
BANK_ENTRY_VECTOR = 0x6C80

# --- free space this prototype claims ------------------------------------ #
HELPER_ADDR = 0x6EC4               # bank13, 48 stock-zero bytes
HELPER_LIMIT = 0x6EF4
ATTR_IMAGE_ADDR = 0x6000           # bank21, 16-byte aligned for GDMA
PAL_DATA_ADDR = 0x6240             # bank21
SERVICE_ADDR = 0x6C83              # bank21

# --- title geometry ------------------------------------------------------ #
# The stock title engine renders the command list one cell down and one cell
# right of the listed coordinates, and the screen is scrolled to SCX=SCY=8,
# so map row/col = list row/col + 1 and map rows 1..18 are the visible ones.
MAP_BASE = 0x9800
MAP_STRIDE = 32
IMAGE_FIRST_ROW = 1
IMAGE_ROWS = 18
LIST_TERMINATOR = 0x9A
CURSOR_TILE = 0x73
CURSOR_CELLS = ((9, 4), (11, 4))   # OPENING START / GAME START selector slots

# --- palette slots ------------------------------------------------------- #
PAPER, LOGO, TEXT, CREDIT, CURSOR, ACCENT = 1, 2, 3, 4, 5, 6

PALETTE_YAML = Path("palettes/penta_palettes_v097.yaml")


def load_title_schemes(
    path: Path,
) -> tuple[dict[str, dict[int, list[int]]], dict[int, str], str]:
    """Read ``title_palettes`` from the tuneable palette YAML.

    The YAML is the single source of truth for these colours, exactly as it is
    for the sprite, boss and hazard rows, so a scheme can be retuned live and
    rebuilt without touching Python.  ``slot`` is authoritative and the role
    names are documentation; every scheme must cover BG1..BG6 with four
    BGR555 entries each.

    Returns ``({scheme: {slot: [4 colours]}}, {slot: role}, active_scheme)``.
    """
    try:
        import yaml
    except ImportError:  # pragma: no cover - environment problem, not logic
        raise SystemExit("PyYAML is required (uv run python ...)")

    if not path.is_file():
        raise SystemExit(f"{path}: palette YAML not found")
    block = (yaml.safe_load(path.read_text()) or {}).get("title_palettes")
    if not isinstance(block, dict) or not block.get("schemes"):
        raise SystemExit(f"{path}: title_palettes.schemes is missing")

    schemes: dict[str, dict[int, list[int]]] = {}
    roles: dict[int, str] = {}
    for name, entries in block["schemes"].items():
        slots: dict[int, list[int]] = {}
        for role, entry in (entries or {}).items():
            slot = entry.get("slot")
            colours = entry.get("colors")
            if not isinstance(slot, int) or not 1 <= slot <= 7:
                raise SystemExit(
                    f"{path}: {name}.{role} slot must be an integer BG1..BG7"
                )
            if not isinstance(colours, list) or len(colours) != 4:
                raise SystemExit(
                    f"{path}: {name}.{role} needs exactly 4 colors"
                )
            if slot in slots:
                raise SystemExit(f"{path}: {name} assigns BG{slot} twice")
            try:
                slots[slot] = [int(str(value), 16) for value in colours]
            except ValueError:
                raise SystemExit(
                    f"{path}: {name}.{role} has a non-hex colour entry"
                )
            if any(value > 0x7FFF for value in slots[slot]):
                raise SystemExit(
                    f"{path}: {name}.{role} colour exceeds 15-bit BGR555"
                )
            roles.setdefault(slot, role)
        missing = [slot for slot in range(1, 7) if slot not in slots]
        if missing:
            raise SystemExit(
                f"{path}: {name} is missing BG slots {missing}"
            )
        schemes[name] = slots

    active = block.get("active_scheme") or sorted(schemes)[0]
    if active not in schemes:
        raise SystemExit(
            f"{path}: active_scheme {active!r} is not one of {sorted(schemes)}"
        )
    return schemes, roles, active


SCHEMES, SLOT_ROLES, ACTIVE_SCHEME = load_title_schemes(PALETTE_YAML)
SLOT_ORDER = tuple(SLOT_ROLES[slot] for slot in range(1, 7))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bank_offset(bank: int, addr: int) -> int:
    if bank == 0:
        return addr
    return bank * BANK_SIZE + (addr - 0x4000)


def header_checksum(rom: bytearray) -> int:
    value = 0
    for index in range(0x134, 0x14D):
        value = (value - rom[index] - 1) & 0xFF
    return value


def global_checksum(rom: bytearray) -> int:
    return (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF


def parse_title_list(rom: bytes) -> list[tuple[int, int, list[int]]]:
    """Return [(map_row, map_col, tiles)] straight from the shipped list."""
    records: list[tuple[int, int, list[int]]] = []
    pointer = TITLE_LIST_ADDR
    while rom[pointer] != LIST_TERMINATOR:
        col, row = rom[pointer], rom[pointer + 1]
        pointer += 2
        tiles: list[int] = []
        while rom[pointer] != LIST_TERMINATOR:
            tiles.append(rom[pointer])
            pointer += 1
        pointer += 1
        records.append((row + 1, col + 1, tiles))
        if pointer >= TITLE_LIST_ADDR + 125:
            raise SystemExit("title command list is not terminated")
    return records


def classify(map_row: int, map_col: int, tile: int) -> int:
    """Pick the CGB BG palette for one occupied title cell."""
    if tile == CURSOR_TILE:
        return CURSOR
    if 4 <= map_row <= 6:
        return LOGO                     # the three JAM emblem rows
    if map_row == 7:
        return ACCENT                   # PENTA DRAGON DX
    if map_row in (15, 16):
        return CREDIT                   # (C) and 1992 JAPAN ART MEDIA
    if map_row == 18 and 1 <= map_col <= 8:
        return ACCENT                   # DX V3.01 identity badge
    return TEXT


def build_attribute_image(
    records: list[tuple[int, int, list[int]]],
) -> tuple[bytearray, dict[str, list[str]]]:
    image = bytearray([PAPER]) * (IMAGE_ROWS * MAP_STRIDE)
    coverage: dict[int, list[tuple[int, int]]] = {}

    def put(map_row: int, map_col: int, palette: int) -> None:
        if not IMAGE_FIRST_ROW <= map_row < IMAGE_FIRST_ROW + IMAGE_ROWS:
            raise SystemExit(f"title cell row {map_row} outside the image")
        image[(map_row - IMAGE_FIRST_ROW) * MAP_STRIDE + map_col] = palette
        coverage.setdefault(palette, []).append((map_row, map_col))

    for map_row, map_col, tiles in records:
        for index, tile in enumerate(tiles):
            if tile == 0x00:
                continue                # embedded spaces stay on the field
            put(map_row, map_col + index, classify(map_row, map_col + index, tile))
    for map_row, map_col in CURSOR_CELLS:
        put(map_row, map_col, CURSOR)

    summary = {
        SLOT_ORDER[palette - 1]: [f"r{r:02d}c{c:02d}" for r, c in cells]
        for palette, cells in sorted(coverage.items())
    }
    return image, summary


def build_palette_block(slots: dict[int, list[int]]) -> bytes:
    """Six BG rows in slot order, four BGR555 entries each, little-endian.

    The YAML convention is that index 0 of every slot carries the shared field
    colour, so a stale attribute on a blank cell (the vacated menu-cursor slot
    is the only moving cell on this screen) renders as field rather than a
    bright square.  Indices 1..3 normally repeat the role ink, but all four are
    emitted verbatim so a role can carry a real ramp if one is tuned in.
    """
    block = bytearray()
    for slot in range(1, 7):
        for value in slots[slot]:
            block += bytes([value & 0xFF, (value >> 8) & 0xFF])
    assert len(block) == 48
    return bytes(block)


def build_bank21_service(both_maps: bool = True) -> bytes:
    """Load BG1..BG6, then publish the attribute image into both maps.

    Entered with the LCD already disabled and VBK already 1 by colorize's
    two-map cleaner, so no display-timing window has to be found.
    """
    blocks = (IMAGE_ROWS * MAP_STRIDE) // 16
    code = bytearray()
    code += bytes([0x3E, 0x88, 0xE0, 0x68])          # BCPS index 8, auto-inc
    code += bytes([0x21, PAL_DATA_ADDR & 0xFF, PAL_DATA_ADDR >> 8])
    code += bytes([0x06, 48])
    code += bytes([0x2A, 0xE0, 0x69, 0x05, 0x20, 0xFA])
    code += bytes([0x3E, 0x01, 0xE0, 0x4F])          # VBK = 1 (already set)
    destinations = [MAP_BASE + IMAGE_FIRST_ROW * MAP_STRIDE]
    if both_maps:
        destinations.append(MAP_BASE + 0x400 + IMAGE_FIRST_ROW * MAP_STRIDE)
    for destination in destinations:
        for register, value in (
            (0x51, (ATTR_IMAGE_ADDR >> 8) & 0xFF),
            (0x52, ATTR_IMAGE_ADDR & 0xF0),
            (0x53, ((destination - 0x8000) >> 8) & 0x1F),
            (0x54, destination & 0xF0),
            (0x55, blocks - 1),                      # bit 7 clear = GDMA
        ):
            code += bytes([0x3E, value, 0xE0, register])
    code += bytes([0x3E, LIVE_BANK, 0xC9])           # trampoline restores 13
    return bytes(code)


def build_paint_helper() -> bytes:
    """Replaces colorize's ``XOR A; LDH [FF4F],A`` cleaner tail."""
    code = bytearray()
    code += bytes([0xFA, 0x80, 0xD8])                # LD A,[D880]
    code += bytes([0x3D])                            # DEC A -> Z only on $01
    site = len(code) + 1
    code += bytes([0x20, 0x00])                      # JR NZ, restore
    code += bytes([0x3E, CODE_BANK])
    code += bytes([
        0xCD,
        BANK_SWITCH_CALL_TRAMPOLINE & 0xFF,
        BANK_SWITCH_CALL_TRAMPOLINE >> 8,
    ])
    restore = len(code)
    code[site] = (restore - site - 1) & 0xFF
    code += bytes([0xAF, 0xE0, 0x4F, 0xC9])          # the displaced VBK reset
    return bytes(code)


def build_leave_helper() -> bytes:
    """Rearm the two-map cleaner when the previous scene was the title.

    Entered where ``scene_detect`` called the title transition service: A is
    the new D880 and HL still addresses the old scene cache.  Both are
    preserved for the stock service, which is tail-called.
    """
    code = bytearray()
    code += bytes([0xF5, 0x7E, 0x3D])                # PUSH AF; LD A,[HL]; DEC A
    site = len(code) + 1
    code += bytes([0x20, 0x00])                      # JR NZ, done
    code += bytes([0xAF])
    code += bytes([0xEA, CLEANER_REARM_ADDR & 0xFF, CLEANER_REARM_ADDR >> 8])
    done = len(code)
    code[site] = (done - site - 1) & 0xFF
    code += bytes([0xF1])                            # POP AF
    code += bytes([
        0xC3, TITLE_TRANSITION_SERVICE & 0xFF, TITLE_TRANSITION_SERVICE >> 8,
    ])
    return bytes(code)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path,
        default=Path("rom/working/penta_dragon_dx_FIXED.gb"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("tmp/title-color/candidate.gb"),
    )
    parser.add_argument("--receipt", type=Path, default=None)
    parser.add_argument(
        "--scheme", choices=sorted(SCHEMES), default=ACTIVE_SCHEME,
        help=(
            "override the YAML's active_scheme "
            f"(currently {ACTIVE_SCHEME!r}); colours themselves live in "
            f"{PALETTE_YAML}"
        ),
    )
    parser.add_argument(
        "--single-map", action="store_true",
        help="publish the attribute image only to $9800 (halves the GDMA cost)",
    )
    parser.add_argument(
        "--no-leave-clear", action="store_true",
        help=(
            "omit the scene_detect hook that rearms the two-map cleaner when "
            "the title is left; the following scene then inherits the title "
            "attribute plane"
        ),
    )
    args = parser.parse_args()

    source = args.input.read_bytes()
    if len(source) != 32 * BANK_SIZE:
        raise SystemExit(f"unexpected ROM size {len(source)}")
    rom = bytearray(source)
    changes: list[dict[str, object]] = []

    def write(bank: int, addr: int, data: bytes, expect: bytes, label: str) -> None:
        offset = bank_offset(bank, addr)
        actual = bytes(rom[offset:offset + len(expect)])
        if actual != expect:
            raise SystemExit(
                f"{label}: preimage mismatch at bank{bank}:${addr:04X}; "
                f"expected {expect.hex()} found {actual.hex()}"
            )
        rom[offset:offset + len(data)] = data
        changes.append({
            "label": label,
            "bank": bank,
            "address": f"0x{addr:04X}",
            "rom_offset": f"0x{offset:06X}",
            "length": len(data),
            "preimage_sha256": sha256(actual),
            "image_sha256": sha256(data),
        })

    # 0. The code bank must still be virgin filler.
    code_bank_slice = bytes(
        rom[CODE_BANK * BANK_SIZE:(CODE_BANK + 1) * BANK_SIZE]
    )
    if set(code_bank_slice) != {0xFF}:
        raise SystemExit(f"bank {CODE_BANK} is not free filler")

    # 1. Attribute image + palettes, derived from the shipped title list.
    records = parse_title_list(source)
    image, coverage = build_attribute_image(records)
    palettes = build_palette_block(SCHEMES[args.scheme])
    print(f"scheme {args.scheme} from {PALETTE_YAML} "
          f"(yaml active_scheme={ACTIVE_SCHEME})")
    write(
        CODE_BANK, ATTR_IMAGE_ADDR, bytes(image),
        b"\xff" * len(image), "bank21 attribute image",
    )
    write(
        CODE_BANK, PAL_DATA_ADDR, palettes,
        b"\xff" * len(palettes), "bank21 title palettes",
    )

    # 2. Bank-21 service plus the DX bank entry vector it is reached through.
    service = build_bank21_service(both_maps=not args.single_map)
    write(
        CODE_BANK, SERVICE_ADDR, service,
        b"\xff" * len(service), "bank21 title service",
    )
    vector = bytes([0xC3, SERVICE_ADDR & 0xFF, SERVICE_ADDR >> 8])
    write(
        CODE_BANK, BANK_ENTRY_VECTOR, vector,
        b"\xff" * len(vector), "bank21 $6C80 entry vector",
    )

    # 3. Bank-13 helpers in the stock-zero gap.
    paint = build_paint_helper()
    leave = b"" if args.no_leave_clear else build_leave_helper()
    if len(paint) + len(leave) > HELPER_LIMIT - HELPER_ADDR:
        raise SystemExit("title helpers overrun the bank-13 gap")
    leave_addr = HELPER_ADDR + len(paint)
    write(
        LIVE_BANK, HELPER_ADDR, paint,
        bytes(len(paint)), "bank13 title paint helper",
    )
    if leave:
        write(
            LIVE_BANK, leave_addr, leave,
            bytes(len(leave)), "bank13 title leave helper",
        )

    # 4. Retarget the two call sites.
    write(
        LIVE_BANK, CLEANER_TAIL_ADDR,
        bytes([0xCD, HELPER_ADDR & 0xFF, HELPER_ADDR >> 8]),
        bytes([0xAF, 0xE0, 0x4F]),
        "colorize cleaner tail -> title paint helper",
    )
    if leave:
        write(
            LIVE_BANK, TRANSITION_CALL_ADDR,
            bytes([0xCD, leave_addr & 0xFF, leave_addr >> 8]),
            bytes([
                0xCD,
                TITLE_TRANSITION_SERVICE & 0xFF,
                TITLE_TRANSITION_SERVICE >> 8,
            ]),
            "scene_detect transition call -> title leave helper",
        )

    rom[0x14D] = header_checksum(rom)
    checksum = global_checksum(rom)
    rom[0x14E] = (checksum >> 8) & 0xFF
    rom[0x14F] = checksum & 0xFF

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(bytes(rom))

    # Exhaustive proof of blast radius: every differing byte, grouped.
    differing = [i for i in range(len(source)) if source[i] != rom[i]]
    runs: list[tuple[int, int]] = []
    for offset in differing:
        if runs and offset == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], offset)
        else:
            runs.append((offset, offset))
    byte_runs = []
    for start, end in runs:
        bank = start // BANK_SIZE
        addr = start if bank == 0 else 0x4000 + (start % BANK_SIZE)
        byte_runs.append({
            "rom_offset": f"0x{start:06X}",
            "bank": bank,
            "address": f"bank{bank}:0x{addr:04X}",
            "length": end - start + 1,
        })

    receipt = {
        "tool": "build_title_color_prototype",
        "scheme": args.scheme,
        "leave_clear": not args.no_leave_clear,
        "input": str(args.input),
        "input_sha256": sha256(source),
        "output": str(args.output),
        "output_sha256": sha256(bytes(rom)),
        "changes": changes,
        "byte_runs": byte_runs,
        "differing_bytes": len(differing),
        "palette_source": str(PALETTE_YAML),
        "palette_source_sha256": sha256(PALETTE_YAML.read_bytes()),
        "yaml_active_scheme": ACTIVE_SCHEME,
        "palette_slots": {
            SLOT_ROLES[slot]: {
                "bg_slot": slot,
                "colors": [
                    f"0x{value:04X}" for value in SCHEMES[args.scheme][slot]
                ],
            }
            for slot in range(1, 7)
        },
        "attribute_cells": coverage,
        "gdma": {
            "source": f"bank{CODE_BANK}:0x{ATTR_IMAGE_ADDR:04X}",
            "destinations": (
                [f"0x{MAP_BASE + IMAGE_FIRST_ROW * MAP_STRIDE:04X}"]
                if args.single_map else [
                    f"0x{MAP_BASE + IMAGE_FIRST_ROW * MAP_STRIDE:04X}",
                    f"0x{MAP_BASE + 0x400 + IMAGE_FIRST_ROW * MAP_STRIDE:04X}",
                ]
            ),
            "bytes_each": IMAGE_ROWS * MAP_STRIDE,
        },
    }
    receipt_path = args.receipt or args.output.with_suffix(".receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    print(f"input  {args.input} sha256={receipt['input_sha256'][:16]}")
    print(f"output {args.output} sha256={receipt['output_sha256'][:16]}")
    for change in changes:
        print(
            f"  {change['label']}: bank{change['bank']}"
            f":{change['address']} +{change['length']}"
        )
    print(
        f"  total differing bytes: {len(differing)} in {len(byte_runs)} runs"
    )
    print(f"receipt {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
