#!/usr/bin/env python3
"""Build the r296 room-wall and locked-room visual repair on exact r292.

r292's Stage-1 attribute compiler uses a tile-ID-only C600 lookup.  Room 01
reuses four ordinary BG0 IDs as the companion half of its BG6 wall bands, so
the immutable table cannot describe both room 01 and the patterned room-05
floor.  Before a dirty attribute compile, this candidate maps an explicitly
unused expansion-bank helper.  The helper changes the four live C600 bytes
only for reachable Stage-1 scenes: room 01 receives full attribute $06 and
every other Stage-1 room receives full attribute $00.  Other scenes leave the
active LUT untouched.

The same candidate admits the stock locked-room publisher D880=$0B through
all five Stage-1 visual gates.  FFB7=$02 is checked at globally reachable
sites, so the Stage-2 scene and the Stage-card splash cannot alias Stage 1.

This is a static diagnostic candidate.  It is not promotable until the
independent room-01 north replay and both operator scene-$0B menu replays pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-exact-background-r292/candidate.gb"
BASE_RECEIPT = TMP / "stage1-exact-background-r292/build-receipt.json"
DEFAULT_OUTPUT = TMP / "stage1-room01-wall-scene0b-r296/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-room01-wall-scene0b-r296/build-receipt.json"
BASE_SHA256 = "924173f3cd82ea0ee2aeb9d520746d60d97ae6b224a965e3f15a150d047d1cb1"
BASE_RECEIPT_SHA256 = "fa5f837e0b5809d05dc1acafaa799613ff472720c0e8fda7e5b9406597125bd0"

BANK_SIZE = 0x4000
ROM_SIZE = 32 * BANK_SIZE
EXPANSION_BANK = 21
WALL_HELPER_ADDR = 0x6C80
PRECOMPILE_SITE = 0x4309
TARGET_TILES = (0x24, 0x27, 0x30, 0x33)
ROOM01_CAPTURE = TMP / "stage1-report-hook/r290-natural-north/candidate/c1a0.bin"
ROOM01_TARGET_CELLS = (
    (0, 5), (0, 18),
    (1, 5), (1, 18),
    (2, 21),
    *((row, column) for row in range(4, 18) for column in (3, 20)),
    (19, 7), (19, 16),
)
ROOM_ORACLE_FIXTURE = (
    ROOT / "scripts/diagnostics/fixtures/stage1_room01_wall_oracle.json"
)

# Exact r292 gates.  Banks 13 and 16 contain the mirrored always-mapped
# sources used by production and the private Ted payload respectively.
MIRROR_BANKS = (13, 16)
SCENE_COMPONENTS = frozenset({"attr", "art", "bg7", "row", "transition"})
ATTR_GATEWAY_ADDR = 0x7C96
ART_LOADER_GATE_ADDR = 0x6A16
BG7_SELECTOR_GATE_ADDR = 0x71B6
PREDICATE_BY_BANK = {13: 0x5D4C, 16: 0x6180}
BANK16_PREDICATE_TAIL_ADDR = 0x6268
ROW_HELPER_BANK = 19
ROW_HELPER_START = 0x6BA7
ROW_HELPER_END = 0x6BEB  # exclusive; exact active r292 helper
TRANSITION_GATE_ADDR = 0x55C3

OLD_PRECOMPILE = bytes.fromhex("3E 03 E0 70 06 C6")
NEW_PRECOMPILE = bytes.fromhex("3E 15 CD 47 08 00")
OLD_ATTR_GATEWAY = bytes.fromhex("FA 80 D8 E6 F7 FE 02 C2 B9 DA")
OLD_ART_GATE = bytes.fromhex("FA 80 D8 E6 F7 FE 02 C0")
OLD_BG7_GATE = bytes.fromhex("FA 80 D8 E6 F7 FE 02 20 02")
OLD_ROW_GATE = bytes.fromhex("FA 80 D8 47 E6 F7 FE 02 C2 50 6C")
OLD_ROW_MINIBOSS = bytes.fromhex("CB 58 20 0C")
OLD_TRANSITION_GATE = bytes.fromhex("FA 80 D8 E6 F7 FE 02 C0")

# Bank 13's range is explicitly classified safe by the Ted sparse integration
# audit.  Bank 16 uses two separately documented exact-safe eight-byte gaps;
# its tempting $56E1 zero tail is allocated runtime source and is forbidden.
BANK13_PREDICATE = bytes.fromhex(
    "F0 B7 FE 02 C0 FA 80 D8 E6 F6 FE 02 C9"
)
BANK16_PREDICATE_FRONT = bytes.fromhex("F0 B7 FE 02 C0 C3 68 62")
BANK16_PREDICATE_TAIL = bytes.fromhex("FA 80 D8 E6 F6 FE 02 C9")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    require(0 < bank < 32 and 0x4000 <= address < 0x8000,
            "bad bank/address")
    return bank * BANK_SIZE + address - 0x4000


class Asm:
    """Tiny relative-branch emitter used only for the bank-21 leaf."""

    def __init__(self) -> None:
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    def db(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def label(self, name: str) -> None:
        require(name not in self.labels, f"duplicate label {name}")
        self.labels[name] = len(self.code)

    def jr(self, opcode: int, label: str) -> None:
        self.db(opcode, 0)
        self.fixups.append((len(self.code) - 1, label))

    def finish(self) -> bytes:
        for operand, label in self.fixups:
            delta = self.labels[label] - (operand + 1)
            require(-128 <= delta <= 127, f"JR {label} out of range")
            self.code[operand] = delta & 0xFF
        return bytes(self.code)


def build_wall_helper() -> bytes:
    """Build the bank-21 LUT updater and banked-stack migration leaf.

    The fixed mapper enters with SVBK1 and two transient return frames:
    $084D above $430E.  The native compiler must continue in SVBK3, so the
    leaf removes those two frames from bank 1, switches WRAM, recreates them
    in bank 3, and returns through the unchanged fixed mapper.  Deeper caller
    frames stay untouched in bank 1 until the native $4350 restore.
    """
    a = Asm()
    # C is the native D400 compiler's live LUT low byte.  The two mapper
    # return addresses temporarily consume BC/DE during the SVBK migration,
    # so preserve C in FFE0; the unchanged continuation overwrites FFE0 with
    # its $18 row count immediately after return.
    a.db(0x79, 0xE0, 0xE0)                  # LD A,C; LDH [$FFE0],A
    # Reachable-state exact Stage-1 predicate.  Stock publishes $0B when
    # DD06!=0, $0A when FFBF!=0, otherwise FFB7.  Therefore FFB7=$02 plus
    # this fold admits exactly the reachable $02/$0A/$0B states.  Splash $18
    # fails the fold and Stage 2 fails FFB7 before it.
    a.db(0xF0, 0xB7, 0xFE, 0x02)
    a.jr(0x20, "migrate")
    a.db(0xFA, 0x80, 0xD8, 0xE6, 0xF6, 0xFE, 0x02)
    a.jr(0x20, "migrate")

    # LD A,0 preserves DEC's flags: room $01 selects $06; all other
    # Stage-1 rooms select the canonical full byte $00.
    a.db(0xF0, 0xBD, 0x3D, 0x3E, 0x00)
    a.jr(0x20, "value_ready")
    a.db(0x3E, 0x06)
    a.label("value_ready")
    for tile in TARGET_TILES:
        a.db(0xEA, tile, 0xC6)              # LD [$C600+tile],A

    a.label("migrate")
    # $0061 first stores A in switchable $DC09, then updates FF99/MBC.  Write
    # the canonical bank-1 shadow while SVBK1 is still visible; the mapper's
    # later bank-3 mirror is harmless.
    a.db(0x3E, 0x01, 0xEA, 0x09, 0xDC)
    a.db(0xC1, 0xD1)                        # POP BC=$084D; DE=$430E
    a.db(0x3E, 0x03, 0xE0, 0x70)            # select SVBK3
    a.db(0xD5, 0xC5)                        # PUSH $430E; PUSH $084D
    a.db(0x11, 0xA0, 0xC1)                  # restore compiler DE
    a.db(0x06, 0xC6)                        # displaced LD B,$C6
    a.db(0xF0, 0xE0, 0x4F)                  # restore native compiler C
    a.db(0x3E, 0x01, 0xC9)                  # mapper restores ROM bank 1
    code = a.finish()
    require(len(code) <= 0x80, "bank-21 wall helper unexpectedly large")
    return code


def reachable_scene(ffb7: int, *, dd06: int = 0, ffbf: int = 0) -> int:
    """Model the exact stock bank-1 $4F5D publisher."""
    return 0x0B if dd06 else (0x0A if ffbf else ffb7)


def predicate_accepts(scene: int, ffb7: int) -> bool:
    return ffb7 == 0x02 and (scene & 0xF6) == 0x02


def apply_wall_model(
    values: dict[int, int], *, scene: int, ffb7: int, room: int,
) -> dict[int, int]:
    result = dict(values)
    if predicate_accepts(scene, ffb7):
        value = 0x06 if room == 0x01 else 0x00
        for tile in TARGET_TILES:
            result[tile] = value
    return result


def patch_exact(
    rom: bytearray,
    source: bytes,
    offset: int,
    old: bytes,
    new: bytes,
    allowed: set[int],
    label: str,
) -> None:
    require(len(old) == len(new), f"{label} changes width")
    require(source[offset:offset + len(old)] == old,
            f"{label} preimage changed")
    rom[offset:offset + len(new)] = new
    allowed.update(range(offset, offset + len(new)))


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def offline_contract(source: bytes, helper: bytes) -> dict[str, object]:
    # Publisher/predicate truth table: no inaccessible raw-state shortcut may
    # make Stage 2 or the Stage-card splash look like Stage 1.
    reachable = []
    for ffb7 in range(0x20):
        for dd06 in (0, 1, 3):
            for ffbf in (0, 1):
                scene = reachable_scene(ffb7, dd06=dd06, ffbf=ffbf)
                accepted = predicate_accepts(scene, ffb7)
                expected = ffb7 == 0x02
                require(accepted == expected,
                        "reachable scene predicate aliases another stage")
                reachable.append((ffb7, dd06, ffbf, scene, accepted))
    require(predicate_accepts(0x02, 0x02), "normal Stage 1 rejected")
    require(predicate_accepts(0x0A, 0x02), "miniboss Stage 1 rejected")
    require(predicate_accepts(0x0B, 0x02), "locked Stage 1 rejected")
    require(not predicate_accepts(0x18, 0x02), "Stage-card splash admitted")
    require(not predicate_accepts(0x03, 0x03), "Stage 2 admitted")

    initial = {tile: (0x80 | index) for index, tile in enumerate(TARGET_TILES)}
    require(apply_wall_model(initial, scene=0x02, ffb7=0x02, room=1)
            == {tile: 0x06 for tile in TARGET_TILES},
            "room-01 model did not publish full BG6 bytes")
    require(apply_wall_model(initial, scene=0x0B, ffb7=0x02, room=3)
            == {tile: 0x00 for tile in TARGET_TILES},
            "locked non-room01 model did not restore full BG0 bytes")
    require(apply_wall_model(initial, scene=0x18, ffb7=0x02, room=1)
            == initial, "splash model mutated the active LUT")
    require(apply_wall_model(initial, scene=0x03, ffb7=0x03, room=1)
            == initial, "later-stage model mutated the active LUT")

    packed = ROOM01_CAPTURE.read_bytes()
    require(len(packed) == 24 * 24, "room-01 packed capture width changed")
    expected_positions = {
        row * 24 + column for row, column in ROOM01_TARGET_CELLS
    }
    actual_positions = {
        index for index, tile in enumerate(packed) if tile in TARGET_TILES
    }
    require(len(expected_positions) == 35,
            "reviewed room-01 companion-cell set changed")
    require(actual_positions == expected_positions,
            "room-01 target IDs escaped the reviewed wall companions")
    counts = {tile: packed.count(tile) for tile in TARGET_TILES}
    require(all(counts.values()) and sum(counts.values()) == 35,
            f"room-01 target population changed: {counts}")
    table = source[bank_offset(13, 0x7000):bank_offset(13, 0x7000) + 0x100]
    require(all(table[tile] == 0 for tile in TARGET_TILES),
            "immutable Stage-1 LUT no longer reproduces the room-01 defect")

    fixture = json.loads(ROOM_ORACLE_FIXTURE.read_text())
    room05 = fixture["room05_patterned_floor_control"]
    require(int(room05["expected_attr"]) == 0,
            "room-05 independent control is no longer BG0")

    require(helper.endswith(bytes.fromhex(
        "3E 01 EA 09 DC C1 D1 3E 03 E0 70 D5 C5 11 A0 C1 06 C6 "
        "F0 E0 4F 3E 01 C9"
    )), "wall helper stack/SVBK epilogue changed")
    return {
        "reachable_publisher_cases": len(reachable),
        "accepted_reachable_scenes": ["02", "0A", "0B"],
        "splash_18_ffb7_02_rejected": True,
        "stage2_03_ffb7_03_rejected": True,
        "room01_target_counts": {f"{tile:02X}": count for tile, count in counts.items()},
        "room01_target_cells": sum(counts.values()),
        "room01_target_positions_exact": True,
        "room05_independent_patterned_floor_expected_attr": "00",
        "nonstage_LUT_is_untouched": True,
        "canonical_DC09_written_before_SVBK3": True,
        "native_compiler_C_preserved_via_FFE0": True,
        "transient_mapper_frames_migrated": ["084D", "430E"],
    }


def mirror_call(bank: int) -> bytes:
    address = PREDICATE_BY_BANK[bank]
    return bytes((0xCD, address & 0xFF, address >> 8))


def install_scene_gates(
    rom: bytearray,
    source: bytes,
    allowed: set[int],
    *,
    components: frozenset[str] = SCENE_COMPONENTS,
) -> dict[str, object]:
    require(components <= SCENE_COMPONENTS,
            f"unknown scene-gate components: {sorted(components - SCENE_COMPONENTS)}")
    for bank in MIRROR_BANKS:
        predicate = PREDICATE_BY_BANK[bank]
        call = mirror_call(bank)
        gateway = call + bytes.fromhex("C2 B9 DA") + bytes(4)
        art = call + bytes.fromhex("C0") + bytes(4)
        bg7 = call + bytes.fromhex("20 06") + bytes(4)
        if "attr" in components:
            patch_exact(
                rom, source, bank_offset(bank, ATTR_GATEWAY_ADDR),
                OLD_ATTR_GATEWAY, gateway, allowed,
                f"bank{bank} Stage-1 attr gateway",
            )
        if "art" in components:
            patch_exact(
                rom, source, bank_offset(bank, ART_LOADER_GATE_ADDR),
                OLD_ART_GATE, art, allowed,
                f"bank{bank} Stage-1 bank-1 art gate",
            )
        if "bg7" in components:
            patch_exact(
                rom, source, bank_offset(bank, BG7_SELECTOR_GATE_ADDR),
                OLD_BG7_GATE, bg7, allowed,
                f"bank{bank} Stage-1 BG7 selector",
            )
        require(predicate in (0x5D4C, 0x6180), "unexpected predicate site")

    if components & {"attr", "art", "bg7"}:
        pred13_off = bank_offset(13, 0x5D4C)
        require(source[pred13_off:pred13_off + len(BANK13_PREDICATE)]
                == bytes(len(BANK13_PREDICATE)),
                "bank13 audited predicate cave changed")
        rom[pred13_off:pred13_off + len(BANK13_PREDICATE)] = BANK13_PREDICATE
        allowed.update(range(pred13_off, pred13_off + len(BANK13_PREDICATE)))

        for address, code, label in (
            (0x6180, BANK16_PREDICATE_FRONT, "front"),
            (BANK16_PREDICATE_TAIL_ADDR, BANK16_PREDICATE_TAIL, "tail"),
        ):
            offset = bank_offset(16, address)
            require(source[offset:offset + len(code)] == bytes(len(code)),
                    f"bank16 audited predicate {label} gap changed")
            rom[offset:offset + len(code)] = code
            allowed.update(range(offset, offset + len(code)))

    # Rebuild the row prefix at identical width: removing LD B,A pays for the
    # explicit FFBF miniboss test, so every later address remains fixed.
    if "row" in components:
        row_off = bank_offset(ROW_HELPER_BANK, ROW_HELPER_START)
        old_row = source[row_off:row_off + ROW_HELPER_END - ROW_HELPER_START]
        require(old_row[1:1 + len(OLD_ROW_GATE)] == OLD_ROW_GATE,
                "bank19 row scene gate changed")
        bit_offset = 0x6BBA - ROW_HELPER_START
        require(old_row[bit_offset:bit_offset + len(OLD_ROW_MINIBOSS)]
                == OLD_ROW_MINIBOSS, "bank19 row miniboss gate changed")
        new_gate = bytes.fromhex("FA 80 D8 E6 F6 FE 02 C2 50 6C")
        new_miniboss = bytes.fromhex("F0 BF B7 20 0C")
        new_row = (
            old_row[:1]
            + new_gate
            + old_row[1 + len(OLD_ROW_GATE):bit_offset]
            + new_miniboss
            + old_row[bit_offset + len(OLD_ROW_MINIBOSS):]
        )
        require(len(new_row) == len(old_row), "row helper width changed")
        rom[row_off:row_off + len(new_row)] = new_row
        allowed.update(range(row_off, row_off + len(new_row)))

    if "transition" in components:
        transition_off = bank_offset(ROW_HELPER_BANK, TRANSITION_GATE_ADDR)
        require(source[transition_off:transition_off + len(OLD_TRANSITION_GATE)]
                == OLD_TRANSITION_GATE, "bank19 transition scene gate changed")
        new_transition = bytearray(OLD_TRANSITION_GATE)
        new_transition[4] = 0xF6
        rom[transition_off:transition_off + len(new_transition)] = new_transition
        allowed.update(range(transition_off, transition_off + len(new_transition)))
    return {
        "diagnostic_components": sorted(components),
        "global_predicate": "FFB7==02 and reachable D880 in {02,0A,0B}",
        "bank13_predicate": "$5D4C-$5D58 audited safe gap",
        "bank16_predicate": "$6180-$6187 + $6268-$626F audited safe gaps",
        "attr_gateway_mirrors": ["bank13:$7C96", "bank16:$7C96"],
        "art_loader_mirrors": ["bank13:$6A16", "bank16:$6A16"],
        "BG7_selector_mirrors": ["bank13:$71B6", "bank16:$71B6"],
        "row_helper": "bank19:$6BA7-$6BEA; FFBF owns miniboss branch",
        "transition_repair": "bank19:$55C3 gate",
    }


def build(
    source: bytes,
    base_receipt_bytes: bytes,
    *,
    variant: str = "full",
) -> tuple[bytes, dict[str, object]]:
    scene_variants = {
        "scene-only": SCENE_COMPONENTS,
        "scene-attr": frozenset({"attr"}),
        "scene-art": frozenset({"art"}),
        "scene-bg7": frozenset({"bg7"}),
        "scene-row": frozenset({"row"}),
        "scene-transition": frozenset({"transition"}),
        "scene-no-bg7": SCENE_COMPONENTS - {"bg7"},
    }
    require(variant in {"full", "wall-only", *scene_variants},
            f"unknown diagnostic variant {variant!r}")
    require(len(source) == ROM_SIZE, "base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256, "wrong exact r292 base")
    require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
            "r292 receipt identity changed")
    require(json.loads(base_receipt_bytes)["candidate_sha256"] == BASE_SHA256,
            "r292 receipt names another candidate")

    helper = build_wall_helper()
    contract = offline_contract(source, helper)
    rom = bytearray(source)
    allowed: set[int] = {0x014D, 0x014E, 0x014F}

    wall_installed = variant in {"full", "wall-only"}
    scene_components = (
        SCENE_COMPONENTS if variant == "full" else scene_variants.get(variant)
    )
    scene_gates_installed = scene_components is not None
    if wall_installed:
        patch_exact(
            rom, source, PRECOMPILE_SITE, OLD_PRECOMPILE, NEW_PRECOMPILE,
            allowed, "bank1 precompiler mapping setup",
        )
        helper_off = bank_offset(EXPANSION_BANK, WALL_HELPER_ADDR)
        require(source[helper_off:helper_off + len(helper)]
                == bytes([0xFF]) * len(helper),
                "bank21 expansion-private wall helper range changed")
        rom[helper_off:helper_off + len(helper)] = helper
        allowed.update(range(helper_off, helper_off + len(helper)))

    scene_gates = (
        install_scene_gates(
            rom, source, allowed, components=scene_components,
        )
        if scene_gates_installed
        else {"installed": False}
    )

    # The immutable table remains the room-05/default truth.  Context exists
    # only in live C600 immediately before compilation.
    lut_off = bank_offset(13, 0x7000)
    require(rom[lut_off:lut_off + 0x100] == source[lut_off:lut_off + 0x100],
            "immutable Stage-1 LUT changed")
    require(all(rom[lut_off + tile] == 0 for tile in TARGET_TILES),
            "immutable same-ID room-05 controls changed")
    require(rom[14 * BANK_SIZE:15 * BANK_SIZE]
            == source[14 * BANK_SIZE:15 * BANK_SIZE],
            "native bank14 isolation violated")

    update_checksums(rom)
    candidate = bytes(rom)
    changed = [
        index
        for index, (old, new) in enumerate(zip(source, candidate, strict=True))
        if old != new
    ]
    require(set(changed) <= allowed,
            "candidate escaped owned code/checksum ranges")
    functional = [offset for offset in changed if offset >= 0x0150]
    require(functional, "candidate has no functional changes")

    receipt = {
        "schema": "penta-stage1-room01-wall-scene0b-r296-build-v1",
        "diagnostic_variant": variant,
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": digest(candidate),
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "root_causes": {
            "room01_walls": (
                "four dual-use BG0 IDs are structural BG6 wall companions "
                "only in room01; a global immutable tile-only LUT cannot "
                "express that context"
            ),
            "locked_room": (
                "stock DD06 lock publishes D880=0B, which five Stage1 visual "
                "gates incorrectly rejected as non-Stage1"
            ),
        },
        "wall_patch": {
            "installed": wall_installed,
            "bank1_site": "$4309-$430E",
            "expansion_bank": EXPANSION_BANK,
            "helper_range": (
                f"${WALL_HELPER_ADDR:04X}-"
                f"${WALL_HELPER_ADDR + len(helper) - 1:04X}"
            ),
            "helper_bytes": len(helper),
            "target_tiles": [f"${tile:02X}" for tile in TARGET_TILES],
            "room01_value": "$06",
            "other_stage1_value": "$00",
            "nonstage_action": "no C600 writes",
            "native_bank14_byte_exact": True,
            "steady_frame_cost": "zero; dirty attribute compilations only",
        },
        "scene0b_patch": scene_gates,
        "offline_contract": contract,
        "ownership": {
            "functional_changed_bytes": len(functional),
            "changed_offsets": [f"0x{offset:06X}" for offset in changed],
            "immutable_bank13_stage1_LUT_byte_exact": True,
            "native_bank14_byte_exact": True,
            "bank21_preimage": "exact erased expansion bytes",
        },
        "required_gates": [
            "independent room01 north replay: full structural class attr06",
            "independent room05 patterned-floor control remains attr00",
            "duplicate live menu roundtrips from both operator scene0B states",
            "blank-SRAM Stage1 handoff has no cyan/partial frame",
            "hazard trail/gray-spike/menu artifact rendered continuity",
            "release speed matrix: Stage1 >=95%, Stages2-7 strict 99%",
        ],
    }
    return candidate, receipt


def checked_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved != scratch and resolved.is_relative_to(scratch),
            f"{label} must be below repository tmp/")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument(
        "--variant",
        choices=(
            "full", "wall-only", "scene-only", "scene-attr", "scene-art",
            "scene-bg7", "scene-row", "scene-transition", "scene-no-bg7",
        ),
        default="full",
        help="build a full candidate or a non-promotable diagnostic isolation",
    )
    args = parser.parse_args()
    output = checked_output(args.output, "candidate output")
    receipt_path = checked_output(args.receipt, "receipt output")
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes(),
        variant=args.variant,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
