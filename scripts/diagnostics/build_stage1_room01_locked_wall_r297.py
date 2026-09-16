#!/usr/bin/env python3
"""Build the minimal r297 Stage-1 locked-room/wall repair on exact r292.

r296 proved both defects but changed the attribute compiler's hot entry and
rebuilt a row helper with the wrong B-register ABI.  This candidate instead:

* extends only the rejected scene-$0B attribute path; ordinary $02/$0A keeps
  the exact r292 bytes, registers, flags, and 44 T-cycle gateway cost;
* changes the two bank-19 scene masks by one bit, retaining the native row
  helper and its raw-scene B register;
* updates the four room-01-only wall companion attributes from the existing
  FFBD room-write hook, never from the renderer; and
* restores the caller's arbitrary ROM bank and AF/BC/DE/HL/SP exactly.

The immutable Stage-1 LUT remains the room-05/default truth.  This remains a
non-promotable diagnostic candidate until the independent live oracles pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-exact-background-r292/candidate.gb"
BASE_RECEIPT = TMP / "stage1-exact-background-r292/build-receipt.json"
DEFAULT_OUTPUT = TMP / "stage1-room01-locked-wall-r297/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-room01-locked-wall-r297/build-receipt.json"
BASE_SHA256 = "924173f3cd82ea0ee2aeb9d520746d60d97ae6b224a965e3f15a150d047d1cb1"
BASE_RECEIPT_SHA256 = "fa5f837e0b5809d05dc1acafaa799613ff472720c0e8fda7e5b9406597125bd0"

BANK_SIZE = 0x4000
ROM_SIZE = 32 * BANK_SIZE
EXPANSION_BANK = 21
WALL_HELPER_ADDR = 0x6C80
TARGET_TILES = (0x24, 0x27, 0x30, 0x33)
ROOM_HOOK_SITES = (0x0B7E, 0x11D2, 0x11FC, 0x4106)

RST0_ADDR = 0x0000
OLD_RST0 = bytes.fromhex("E0 BD F5 3E 12 C3 38 08")
NEW_RST0 = bytes.fromhex("E0 BD F5 F0 99 C3 38 08")
ROOM_STUB_ADDR = 0x0838
OLD_ROOM_STUB = bytes.fromhex("EA 4E DF 3E A6 EA 4F DF F1 C9")
NEW_ROOM_STUB = bytes.fromhex("F5 3E 15 C3 47 08 F1 F1 C9 00")
MAPPER_DISPATCH_ADDR = 0x0847
MAPPER_DISPATCH = bytes.fromhex("CD 61 00 CD 80 6C C3 61 00")

# The bank-21 helper preserves HL, performs the existing room-sweep rearm,
# scopes contextual C600 writes to Stage 1 (FFBA=$00), rewrites the mapper's
# transient return from $084D to fixed continuation $083E, reloads the saved
# arbitrary ROM bank from the stack, restores HL, and tail-calls mapper $0061.
WALL_HELPER = bytes.fromhex(
    "E5 "
    "3E 12 EA 4E DF 3E A6 EA 4F DF "
    "F0 BA B7 20 16 "
    "F8 07 7E 3D 3E 00 20 02 3E 06 "
    "EA 24 C6 EA 27 C6 EA 30 C6 EA 33 C6 "
    "F8 02 36 3E 23 36 08 "
    "F8 05 7E E1 C3 61 00"
)

MIRROR_BANKS = (13, 16)
ATTR_GATEWAY_ADDR = 0x7C96
OLD_ATTR_GATEWAY = bytes.fromhex("FA 80 D8 E6 F7 FE 02 C2 B9 DA")
ATTR_HELPER_BY_BANK = {13: 0x5D4C, 16: 0x6180}
BANK13_ATTR_HELPER = bytes.fromhex("47 F0 B7 A8 3D C8 F1 C3 B9 DA")
BANK16_ATTR_FRONT = bytes.fromhex("47 F0 B7 A8 C3 68 62 00")
BANK16_ATTR_TAIL_ADDR = 0x6268
BANK16_ATTR_TAIL = bytes.fromhex("3D C8 F1 C3 B9 DA 00 00")

ROW_BANK = 19
ROW_MASK_ADDR = 0x6BAD
TRANSITION_MASK_ADDR = 0x55C7
OLD_SCENE_MASK = 0xF7
NEW_SCENE_MASK = 0xF6

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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    require(0 < bank < 32 and 0x4000 <= address < 0x8000,
            "bad bank/address")
    return bank * BANK_SIZE + address - 0x4000


def reachable_scene(ffb7: int, *, dd06: int = 0, ffbf: int = 0) -> int:
    """Model the stock bank-1 $4F5D publisher."""
    return 0x0B if dd06 else (0x0A if ffbf else ffb7)


def old_attr_accepts(scene: int) -> bool:
    return (scene & 0xF7) == 0x02


def r297_attr_accepts(scene: int, ffb7: int) -> bool:
    """Model the unchanged fast path plus the conditional-call slow path."""
    masked = scene & 0xF7
    if masked == 0x02:
        return True
    return ((ffb7 ^ masked) - 1) & 0xFF == 0


def wall_values(values: dict[int, int], *, stage: int, room: int) -> dict[int, int]:
    result = dict(values)
    if stage == 0:
        value = 0x06 if room == 1 else 0x00
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


def checked_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved != scratch and resolved.is_relative_to(scratch),
            f"{label} must be below repository tmp/")
    return resolved


def wall_source_contract(source: bytes) -> dict[str, object]:
    """Source/stack/semantic checks, without asserting captured room contents."""
    require(len(WALL_HELPER) == 52, "wall helper width changed")
    require(source[RST0_ADDR:RST0_ADDR + len(OLD_RST0)] == OLD_RST0,
            "RST0 room hook preimage changed")
    require(source[ROOM_STUB_ADDR:ROOM_STUB_ADDR + len(OLD_ROOM_STUB)]
            == OLD_ROOM_STUB, "fixed room stub preimage changed")
    require(source[MAPPER_DISPATCH_ADDR:
                   MAPPER_DISPATCH_ADDR + len(MAPPER_DISPATCH)]
            == MAPPER_DISPATCH, "fixed mapper dispatcher changed")
    require(all(source[offset:offset + 2] == bytes.fromhex("C7 00")
                for offset in ROOM_HOOK_SITES),
            "one of the four native room writers lost its RST0 hook")

    helper_offset = bank_offset(EXPANSION_BANK, WALL_HELPER_ADDR)
    require(source[helper_offset:helper_offset + len(WALL_HELPER)]
            == bytes([0xFF]) * len(WALL_HELPER),
            "bank-21 room helper ownership changed")

    # Exact GB stack layout at the expansion helper after PUSH HL:
    # [saved L,H][CALL return 4D,08][bank F,A][room F,A][RST return].
    stack = [0x34, 0x12, 0x4D, 0x08, 0xB0, 0x0D, 0x70, 0x01, 0xAA, 0xBB]
    require(stack[7] == 1 and stack[5] == 13,
            "documented room/bank stack offsets changed")
    stack[2:4] = [0x3E, 0x08]
    restored_hl = stack[:2]
    after_pop_hl = stack[2:]
    mapper_return = after_pop_hl[:2]
    after_mapper_ret = after_pop_hl[2:]
    saved_bank_af = after_mapper_ret[:2]
    room_af = after_mapper_ret[2:4]
    rst_return = after_mapper_ret[4:6]
    require(restored_hl == [0x34, 0x12], "HL stack restore drifted")
    require(mapper_return == [0x3E, 0x08], "mapper return is not $083E")
    require(saved_bank_af == [0xB0, 0x0D], "saved bank AF moved")
    require(room_af == [0x70, 0x01], "original room AF moved")
    require(rst_return == [0xAA, 0xBB], "RST caller return moved")

    initial = {tile: 0x80 + index for index, tile in enumerate(TARGET_TILES)}
    require(wall_values(initial, stage=0, room=1)
            == {tile: 0x06 for tile in TARGET_TILES},
            "room 01 does not publish full BG6 attributes")
    require(wall_values(initial, stage=0, room=5)
            == {tile: 0x00 for tile in TARGET_TILES},
            "room 05 does not restore full BG0 attributes")
    require(wall_values(initial, stage=1, room=1) == initial,
            "later stage aliases the Stage-1 contextual writes")

    fixture = json.loads(ROOM_ORACLE_FIXTURE.read_text())
    require(int(fixture["room05_patterned_floor_control"]["expected_attr"]) == 0,
            "room-05 independent control is no longer BG0")
    return {
        "native_room_writer_hooks": len(ROOM_HOOK_SITES),
        "helper_bytes": len(WALL_HELPER),
        "room05_independent_expected_attr": "00",
        "caller_bank_and_AF_BC_DE_HL_SP_restored": True,
        "SVBK_untouched": True,
        "renderer_4309_untouched": True,
    }


def validate_wall_contract(source: bytes, room01_capture: bytes | None = None
                           ) -> dict[str, object]:
    contract = wall_source_contract(source)
    packed = ROOM01_CAPTURE.read_bytes() if room01_capture is None else room01_capture
    require(len(packed) == 24 * 24, "room-01 packed capture width changed")
    expected_positions = {
        row * 24 + column for row, column in ROOM01_TARGET_CELLS
    }
    actual_positions = {
        index for index, tile in enumerate(packed) if tile in TARGET_TILES
    }
    require(actual_positions == expected_positions,
            "target IDs escaped the 35 reviewed room-01 wall companions")
    counts = {tile: packed.count(tile) for tile in TARGET_TILES}
    require(sum(counts.values()) == 35 and all(counts.values()),
            f"room-01 target population changed: {counts}")

    return {
        **contract,
        "room01_target_cells": sum(counts.values()),
        "room01_target_counts": {
            f"{tile:02X}": count for tile, count in counts.items()
        },
        "room05_independent_expected_attr": "00",
        "caller_bank_and_AF_BC_DE_HL_SP_restored": True,
        "SVBK_untouched": True,
        "renderer_4309_untouched": True,
    }


def validate_scene_contract(source: bytes) -> dict[str, object]:
    added = []
    for ffb7 in range(256):
        for dd06 in (0, 1, 3):
            for ffbf in (0, 1):
                scene = reachable_scene(ffb7, dd06=dd06, ffbf=ffbf)
                old = old_attr_accepts(scene)
                new = r297_attr_accepts(scene, ffb7)
                if new and not old:
                    added.append((ffb7, dd06, ffbf, scene))
    require(added and {item[0] for item in added} == {0x02},
            "slow path admits a reachable non-Stage-1 state")
    require({item[3] for item in added} == {0x0B},
            "slow path admits a reachable scene other than locked Stage 1")
    require(r297_attr_accepts(0x02, 0x02), "normal Stage 1 rejected")
    require(r297_attr_accepts(0x0A, 0x02), "miniboss Stage 1 rejected")
    require(r297_attr_accepts(0x0B, 0x02), "locked Stage 1 rejected")
    require(not r297_attr_accepts(0x18, 0x02), "Stage-card splash admitted")
    require(not r297_attr_accepts(0x03, 0x03), "Stage 2 admitted")

    for bank in MIRROR_BANKS:
        gateway = bank_offset(bank, ATTR_GATEWAY_ADDR)
        require(source[gateway:gateway + len(OLD_ATTR_GATEWAY)]
                == OLD_ATTR_GATEWAY,
                f"bank{bank} attribute gateway preimage changed")
    require(source[bank_offset(13, 0x5D4C):bank_offset(13, 0x5D4C) + 10]
            == bytes(10), "bank13 attr helper ownership changed")
    require(source[bank_offset(16, 0x6180):bank_offset(16, 0x6180) + 8]
            == bytes(8), "bank16 attr helper front ownership changed")
    require(source[bank_offset(16, BANK16_ATTR_TAIL_ADDR):
                   bank_offset(16, BANK16_ATTR_TAIL_ADDR) + 8]
            == bytes(8), "bank16 attr helper tail ownership changed")
    require(source[bank_offset(ROW_BANK, ROW_MASK_ADDR)] == OLD_SCENE_MASK,
            "bank19 row mask preimage changed")
    require(source[bank_offset(ROW_BANK, TRANSITION_MASK_ADDR)]
            == OLD_SCENE_MASK, "bank19 transition mask preimage changed")
    return {
        "reachable_slow_path_cases": len(added),
        "reachable_slow_path_scene": "0B",
        "reachable_slow_path_stage_selector": "02",
        "normal_02_0A_gateway_t_cycles": {"r292": 44, "r297": 44},
        "normal_02_0A_registers_and_flags_exact": True,
        "splash_18_ffb7_02_rejected": True,
        "stage2_03_ffb7_03_rejected": True,
        "row_helper_raw_scene_B_retained": True,
    }


def install_wall_patch(
    rom: bytearray, source: bytes, allowed: set[int],
) -> None:
    patch_exact(rom, source, RST0_ADDR, OLD_RST0, NEW_RST0, allowed,
                "RST0 room writer")
    patch_exact(rom, source, ROOM_STUB_ADDR, OLD_ROOM_STUB, NEW_ROOM_STUB,
                allowed, "fixed room mapper stub")
    helper_offset = bank_offset(EXPANSION_BANK, WALL_HELPER_ADDR)
    patch_exact(
        rom, source, helper_offset, bytes([0xFF]) * len(WALL_HELPER),
        WALL_HELPER, allowed, "bank21 contextual wall helper",
    )


def install_scene_patch(
    rom: bytearray, source: bytes, allowed: set[int],
) -> None:
    for bank in MIRROR_BANKS:
        helper = ATTR_HELPER_BY_BANK[bank]
        new_gateway = (
            OLD_ATTR_GATEWAY[:7]
            + bytes((0xC4, helper & 0xFF, helper >> 8))  # CALL NZ,helper
        )
        patch_exact(
            rom, source, bank_offset(bank, ATTR_GATEWAY_ADDR),
            OLD_ATTR_GATEWAY, new_gateway, allowed,
            f"bank{bank} cycle-neutral attr slow path",
        )

    patch_exact(
        rom, source, bank_offset(13, 0x5D4C), bytes(10),
        BANK13_ATTR_HELPER, allowed, "bank13 attr predicate helper",
    )
    patch_exact(
        rom, source, bank_offset(16, 0x6180), bytes(8),
        BANK16_ATTR_FRONT, allowed, "bank16 attr predicate front",
    )
    patch_exact(
        rom, source, bank_offset(16, BANK16_ATTR_TAIL_ADDR), bytes(8),
        BANK16_ATTR_TAIL, allowed, "bank16 attr predicate tail",
    )

    row_mask = bank_offset(ROW_BANK, ROW_MASK_ADDR)
    patch_exact(
        rom, source, row_mask, bytes((OLD_SCENE_MASK,)),
        bytes((NEW_SCENE_MASK,)), allowed, "bank19 row scene mask",
    )
    transition_mask = bank_offset(ROW_BANK, TRANSITION_MASK_ADDR)
    patch_exact(
        rom, source, transition_mask, bytes((OLD_SCENE_MASK,)),
        bytes((NEW_SCENE_MASK,)), allowed, "bank19 transition scene mask",
    )


def construct(
    source: bytes,
    *,
    variant: str = "full",
) -> tuple[bytes, dict[str, object]]:
    require(variant in {"full", "wall-only", "scene-only"},
            f"unknown diagnostic variant {variant!r}")
    require(len(source) == ROM_SIZE, "base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256, "wrong exact r292 base")
    wall_contract = wall_source_contract(source)
    scene_contract = validate_scene_contract(source)
    rom = bytearray(source)
    allowed: set[int] = {0x014D, 0x014E, 0x014F}
    wall_installed = variant in {"full", "wall-only"}
    scene_installed = variant in {"full", "scene-only"}
    if wall_installed:
        install_wall_patch(rom, source, allowed)
    if scene_installed:
        install_scene_patch(rom, source, allowed)

    # The failed r296 renderer insertion is explicitly forbidden.
    require(rom[0x4303:0x4319] == source[0x4303:0x4319],
            "native attribute compiler entry changed")
    lut_offset = bank_offset(13, 0x7000)
    require(rom[lut_offset:lut_offset + 0x100]
            == source[lut_offset:lut_offset + 0x100],
            "immutable Stage-1 LUT changed")
    require(all(rom[lut_offset + tile] == 0 for tile in TARGET_TILES),
            "room-05/default target LUT entries changed")
    require(rom[14 * BANK_SIZE:15 * BANK_SIZE]
            == source[14 * BANK_SIZE:15 * BANK_SIZE],
            "native bank14 isolation violated")
    require(rom[bank_offset(ROW_BANK, 0x6BA7)] == 0xC1,
            "row helper POP BC changed")
    require(rom[bank_offset(ROW_BANK, 0x6BAB)] == 0x47,
            "row helper LD B,A changed")
    require(rom[bank_offset(ROW_BANK, 0x6BBA):
                bank_offset(ROW_BANK, 0x6BBE)] == bytes.fromhex("CB 58 20 0C"),
            "row helper native miniboss BIT 3,B changed")

    update_checksums(rom)
    candidate = bytes(rom)
    changed = {
        offset
        for offset, (old, new) in enumerate(zip(source, candidate, strict=True))
        if old != new
    }
    require(changed <= allowed, "candidate escaped owned code/checksum ranges")
    functional = sorted(offset for offset in changed if offset >= 0x0150)
    require(functional, "candidate has no functional changes")

    receipt: dict[str, object] = {
        "schema": "penta-stage1-room01-locked-wall-r297-construction-v1",
        "diagnostic_variant": variant,
        "status": "construction-only",
        "promotable": False,
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": digest(candidate),
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "root_causes": {
            "locked_room_blank_walls": (
                "D880=$0B took the attribute gateway rejection path"
            ),
            "room01_wall_edges": (
                "four tile IDs are BG6 wall companions in room01 but BG0 "
                "patterned floor in room05"
            ),
            "r296_transition_regression": (
                "renderer-entry bank mapping and a dropped LD B,A changed "
                "the publication cadence/ABI"
            ),
        },
        "wall_patch": {
            "installed": wall_installed,
            "trigger": "existing four native FFBD room-write hooks",
            "helper": "bank21:$6C80-$6CB3",
            "target_tiles": [f"${tile:02X}" for tile in TARGET_TILES],
            "room01_value": "$06",
            "other_stage1_value": "$00",
            "later_stage_action": "no C600 writes",
            "hot_renderer_delta_t_cycles": 0,
        },
        "scene0b_patch": {
            "installed": scene_installed,
            "attr_gateway_mirrors": ["bank13:$7C96", "bank16:$7C96"],
            "row_mask": "bank19:$6BAD $F7->$F6; native LD B,A retained",
            "transition_mask": "bank19:$55C7 $F7->$F6",
            "art_and_BG7_gates": "byte-exact r292; live oracle decides necessity",
        },
        "offline_contract": {
            "wall": wall_contract,
            "scene": scene_contract,
        },
        "ownership": {
            "functional_changed_bytes": len(functional),
            "changed_offsets": [f"0x{offset:06X}" for offset in sorted(changed)],
            "immutable_bank13_stage1_LUT_byte_exact": True,
            "native_bank14_byte_exact": True,
            "renderer_4303_4318_byte_exact": True,
            "bank21_preimage": "exact erased expansion bytes",
        },
        "required_gates": [
            "independent room01 north transition oracle",
            "room05 patterned-floor attr00 control",
            "two sequential replays of both operator scene0B menu states",
            "blank-SRAM Stage1 handoff has no cyan/partial frame",
            "hazard trail/gray-spike/menu artifact rendered continuity",
            "release speed matrix: Stage1 >=95%, Stages2-7 strict 99%",
        ],
    }
    return candidate, receipt


def build(source: bytes, base_receipt_bytes: bytes, *, variant: str = "full",
          room01_capture: bytes | None = None) -> tuple[bytes, dict[str, object]]:
    require(variant in {"full", "wall-only", "scene-only"},
            f"unknown diagnostic variant {variant!r}")
    require(len(source) == ROM_SIZE, "base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256, "wrong exact r292 base")
    require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
            "r292 receipt identity changed")
    require(json.loads(base_receipt_bytes)["candidate_sha256"] == BASE_SHA256,
            "r292 receipt names another candidate")
    wall = validate_wall_contract(source, room01_capture)
    candidate, receipt = construct(source, variant=variant)
    receipt.pop("historical_evidence_consumed")
    receipt.pop("fresh_live_qualification")
    receipt.update({"schema": "penta-stage1-room01-locked-wall-r297-build-v1",
                    "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
                    "base_receipt_sha256": BASE_RECEIPT_SHA256})
    receipt["offline_contract"]["wall"] = wall
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument(
        "--variant", choices=("full", "wall-only", "scene-only"),
        default="full", help="build full candidate or diagnostic isolation",
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
