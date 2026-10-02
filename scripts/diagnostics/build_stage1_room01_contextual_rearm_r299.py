#!/usr/bin/env python3
"""Build non-promotable r299: post-scene contextual wall rearm on exact r292.

r297's scene-$0B admission repair remains byte-for-byte intact.  Its direct
FFBD/RST room hook does not: menu and scene refreshes may bulk-copy C600 after
that hook ran.  r299 instead invalidates the two physical-map keys while the
Stage-1 scene detector publishes its fresh LUT, then rearms the four
room-context entries from the already post-detect lava marker path.

This is a diagnostic candidate only.  Static success is not a live verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_room01_locked_wall_r297 as r297


ROOT = r297.ROOT
TMP = r297.TMP
BASE = r297.BASE
BASE_RECEIPT = r297.BASE_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-room01-contextual-rearm-r299/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-room01-contextual-rearm-r299/build-receipt.json"

BANK13 = 13
BANK21 = 21
TARGET_TILES = r297.TARGET_TILES
CACHE_ADDRS = (0xDF53, 0xDF57)

SCENE_DISPATCH_ADDR = 0x6FE1
OLD_SCENE_DISPATCH = bytes.fromhex("F0 BA B7 28 03 C3 E7 7F AF EA 53 DF EA 57 DF")
NEW_SCENE_DISPATCH = bytes.fromhex("F0 BA B7 C2 E7 7F 3E A6 EA 4F DF C3 60 6E 00")
SCENE_REARM_ADDR = 0x6E60
SCENE_REARM_PREIMAGE = bytes(11)
SCENE_REARM = bytes.fromhex("AF EA 53 DF EA 57 DF C3 F0 6F")

LAVA_MARKER_ADDR = 0x7E0E
# The CALL's bank-21 trampoline returns directly to the original lava caller;
# its continuation bytes therefore remain native and are deliberately not
# owned by r299.
OLD_LAVA_MARKER = bytes.fromhex("20 01 34 F0 BA FE")
NEW_LAVA_MARKER = bytes.fromhex("20 04 34 CD 80 61")
MAPPER_ENTRY_ADDR = 0x6180
MAPPER_ENTRY_PREIMAGE = bytes(5)
MAPPER_ENTRY = bytes.fromhex("3E 15 EA 00 21")
CONTEXT_HELPER_ADDR = 0x6185
CONTEXT_HELPER = bytes.fromhex(
    "F0 B7 FE 02 20 1E "
    "FA 80 D8 E6 F6 FE 02 20 15 "
    "F0 BD 3D 3E 00 20 02 3E 06 "
    "EA 24 C6 EA 27 C6 EA 30 C6 EA 33 C6 "
    "C3 E2 6B"
)
RETURN_BANK13_ADDR = 0x6BE2
RETURN_BANK13 = bytes.fromhex("3E 0D EA 00 21")


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def contextual_values(
    values: dict[int, int], *, ffb7: int, scene: int, room: int,
) -> dict[int, int]:
    """Model the bank-21 helper; rejected contexts make no C600 writes."""
    result = dict(values)
    if ffb7 != 0x02 or (scene & 0xF6) != 0x02:
        return result
    value = 0x06 if room == 1 else 0x00
    for tile in TARGET_TILES:
        result[tile] = value
    return result


def scene_rearm_caches(caches: dict[int, int], *, stage: int) -> dict[int, int]:
    result = dict(caches)
    if stage == 0:
        for address in CACHE_ADDRS:
            result[address] = 0
    return result


def validate_contextual_contract(source: bytes) -> dict[str, object]:
    """Pin every byte, ownership region, bank handoff, and call ABI."""
    r297.require(
        source[r297.RST0_ADDR:r297.RST0_ADDR + len(r297.OLD_RST0)]
        == r297.OLD_RST0, "r299 requires the untouched r292 RST0 preimage",
    )
    r297.require(
        source[r297.ROOM_STUB_ADDR:r297.ROOM_STUB_ADDR + len(r297.OLD_ROOM_STUB)]
        == r297.OLD_ROOM_STUB, "r299 requires the untouched r292 room stub",
    )
    r297.require(
        source[r297.MAPPER_DISPATCH_ADDR:r297.MAPPER_DISPATCH_ADDR + len(r297.MAPPER_DISPATCH)]
        == r297.MAPPER_DISPATCH, "r299 requires the native mapper dispatcher",
    )
    for address, old, label in (
        (SCENE_DISPATCH_ADDR, OLD_SCENE_DISPATCH, "scene dispatch"),
        (SCENE_REARM_ADDR, SCENE_REARM_PREIMAGE, "scene rearm ownership"),
        (LAVA_MARKER_ADDR, OLD_LAVA_MARKER, "lava marker/control suffix"),
        (MAPPER_ENTRY_ADDR, MAPPER_ENTRY_PREIMAGE, "bank13 mapper entry"),
    ):
        offset = r297.bank_offset(BANK13, address)
        r297.require(source[offset:offset + len(old)] == old,
                     f"{label} preimage changed")
    helper = r297.bank_offset(BANK21, CONTEXT_HELPER_ADDR)
    trailer = r297.bank_offset(BANK21, RETURN_BANK13_ADDR)
    r297.require(source[helper:helper + len(CONTEXT_HELPER)] == bytes([0xFF]) * len(CONTEXT_HELPER),
                 "bank21 contextual helper ownership changed")
    r297.require(source[trailer:trailer + len(RETURN_BANK13)] == bytes([0xFF]) * len(RETURN_BANK13),
                 "bank21 return trampoline ownership changed")
    r297.require(len(CONTEXT_HELPER) == 39, "contextual helper width changed")
    r297.require(source[r297.bank_offset(BANK13, 0x6BE7)] == 0xC9,
                 "bank13 post-map return is no longer RET")

    # CALL $6180 maps bank21 and falls through to $6185; its JP $6BE2 maps
    # bank13 before falling into the pre-existing RET at $6BE7.  No stack
    # adjustment occurs between CALL and RET, and BC/DE/HL/SVBK/FF99/DC09 are
    # not addressed by either trampoline or helper.
    r297.require(MAPPER_ENTRY + CONTEXT_HELPER[:1] == bytes.fromhex("3E 15 EA 00 21 F0"),
                 "bank13-to-bank21 fallthrough drifted")
    r297.require(CONTEXT_HELPER.endswith(bytes.fromhex("C3 E2 6B")),
                 "helper must tail-map its caller bank")
    r297.require(RETURN_BANK13 == bytes.fromhex("3E 0D EA 00 21"),
                 "return trampoline must restore bank13")
    r297.require(not any(opcode in CONTEXT_HELPER for opcode in (0xC5, 0xD5, 0xE5, 0xF5, 0xC1, 0xD1, 0xE1, 0xF1)),
                 "contextual helper changed stack ABI")
    r297.require(bytes.fromhex("E0 99") not in CONTEXT_HELPER
                 and bytes.fromhex("EA 09 DC") not in CONTEXT_HELPER
                 and bytes.fromhex("E0 70") not in CONTEXT_HELPER,
                 "helper touched FF99/DC09/SVBK")

    initial = {tile: 0x80 + index for index, tile in enumerate(TARGET_TILES)}
    r297.require(contextual_values(initial, ffb7=2, scene=0x0B, room=1)
                 == {tile: 6 for tile in TARGET_TILES}, "room01 rearm is not BG6")
    r297.require(contextual_values(initial, ffb7=2, scene=0x02, room=5)
                 == {tile: 0 for tile in TARGET_TILES}, "room05 does not restore BG0")
    r297.require(contextual_values(initial, ffb7=3, scene=0x03, room=1) == initial,
                 "later-stage context wrote C600")
    r297.require(scene_rearm_caches({0xDF53: 0x11, 0xDF57: 0x22}, stage=0)
                 == {0xDF53: 0, 0xDF57: 0}, "Stage1 scene rearm missed a cache")

    return {
        "contextual_helper_bytes": len(CONTEXT_HELPER),
        "scene_rearm_invalidates": ["DF53", "DF57"],
        "r297_direct_ffbd_rst_hook_absent": True,
        "call_ret_stack_delta": 0,
        "BC_DE_HL_SP_SVBK_FF99_DC09_preserved": True,
        "A_and_flags_dead_before_native_lava_caller": True,
        "bank21_to_bank13_return_exact": True,
        "scene0b_normal_gateway_t_cycles": {"r292": 44, "r297": 44, "r299": 44},
    }


def install_contextual_patch(rom: bytearray, source: bytes, allowed: set[int]) -> None:
    r297.patch_exact(rom, source, r297.bank_offset(BANK13, SCENE_DISPATCH_ADDR),
                     OLD_SCENE_DISPATCH, NEW_SCENE_DISPATCH, allowed, "post-scene dispatcher")
    r297.patch_exact(rom, source, r297.bank_offset(BANK13, SCENE_REARM_ADDR),
                     bytes(10), SCENE_REARM, allowed, "Stage1 scene cache rearm")
    r297.patch_exact(rom, source, r297.bank_offset(BANK13, LAVA_MARKER_ADDR),
                     OLD_LAVA_MARKER, NEW_LAVA_MARKER, allowed, "post-detect lava marker")
    r297.patch_exact(rom, source, r297.bank_offset(BANK13, MAPPER_ENTRY_ADDR),
                     MAPPER_ENTRY_PREIMAGE, MAPPER_ENTRY, allowed, "bank21 map entry")
    r297.patch_exact(rom, source, r297.bank_offset(BANK21, CONTEXT_HELPER_ADDR),
                     bytes([0xFF]) * len(CONTEXT_HELPER), CONTEXT_HELPER, allowed,
                     "bank21 contextual helper")
    r297.patch_exact(rom, source, r297.bank_offset(BANK21, RETURN_BANK13_ADDR),
                     bytes([0xFF]) * len(RETURN_BANK13), RETURN_BANK13, allowed,
                     "bank13 return mapper")


def build(source: bytes, base_receipt_bytes: bytes, *, variant: str = "full") -> tuple[bytes, dict[str, object]]:
    r297.require(variant in {"full", "wall-only", "scene-only"}, f"unknown variant {variant!r}")
    r297.require(len(source) == r297.ROM_SIZE, "base is not exactly 512 KiB")
    r297.require(digest(source) == r297.BASE_SHA256, "wrong exact r292 base")
    r297.require(digest(base_receipt_bytes) == r297.BASE_RECEIPT_SHA256, "r292 receipt identity changed")
    r297.require(json.loads(base_receipt_bytes)["candidate_sha256"] == r297.BASE_SHA256,
                 "r292 receipt names another candidate")
    wall_contract = validate_contextual_contract(source)
    scene_contract = r297.validate_scene_contract(source)
    rom = bytearray(source)
    allowed: set[int] = {0x014D, 0x014E, 0x014F}
    wall_installed = variant in {"full", "wall-only"}
    scene_installed = variant in {"full", "scene-only"}
    if wall_installed:
        install_contextual_patch(rom, source, allowed)
    if scene_installed:
        r297.install_scene_patch(rom, source, allowed)

    # Immutable r292 controls, including the rejected r296 renderer mutation.
    r297.require(rom[0x4303:0x4319] == source[0x4303:0x4319], "renderer entry changed")
    lut = r297.bank_offset(BANK13, 0x7000)
    r297.require(rom[lut:lut + 0x100] == source[lut:lut + 0x100], "Stage1 LUT changed")
    r297.require(all(rom[lut + tile] == 0 for tile in TARGET_TILES), "room05 LUT control changed")
    r297.require(rom[14 * r297.BANK_SIZE:15 * r297.BANK_SIZE] == source[14 * r297.BANK_SIZE:15 * r297.BANK_SIZE],
                 "native bank14 isolation violated")
    r297.require(rom[r297.bank_offset(r297.ROW_BANK, 0x6BAB)] == 0x47, "row-helper B ABI changed")
    r297.update_checksums(rom)
    candidate = bytes(rom)
    changed = {offset for offset, pair in enumerate(zip(source, candidate, strict=True)) if pair[0] != pair[1]}
    r297.require(changed <= allowed, "candidate escaped owned ranges")
    functional = sorted(offset for offset in changed if offset >= 0x0150)
    r297.require(functional, "candidate has no functional changes")
    return candidate, {
        "schema": "penta-stage1-room01-contextual-rearm-r299-build-v1",
        "diagnostic_variant": variant,
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": r297.BASE_SHA256,
        "base_receipt_sha256": r297.BASE_RECEIPT_SHA256,
        "candidate_sha256": digest(candidate),
        "checksums": {"header": f"{candidate[0x014D]:02X}", "global": candidate[0x014E:0x0150].hex().upper()},
        "wall_patch": {"installed": wall_installed, "trigger": "post-scene-detect lava marker", "helper": "bank21:$6185-$61AB", "return_mapper": "bank21:$6BE2-$6BE6", "direct_ffbd_rst_hook": False},
        "scene0b_patch": {"installed": scene_installed, "retained_from": "r297", "normal_gateway_t_cycles": {"r292": 44, "r297": 44, "r299": 44}},
        "offline_contract": {"wall": wall_contract, "scene": scene_contract},
        "ownership": {"functional_changed_bytes": len(functional), "changed_offsets": [f"0x{offset:06X}" for offset in sorted(changed)], "immutable_bank13_stage1_LUT_byte_exact": True, "renderer_4303_4318_byte_exact": True, "native_bank14_byte_exact": True},
        "r297_live_rejection": {"cause": "menu/scene refresh bulk-copies global C600 after FFBD hook", "room01_target_attrs": "24/27/30/33 attr06 -> attr00", "post_close_frames": 371},
        "required_gates": ["repeated refresh/menu reapply has zero target mismatches", "room05 BG0 restoration", "later-stage no-op", "live ABI/render continuity"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--variant", choices=("full", "wall-only", "scene-only"), default="full")
    args = parser.parse_args()
    output = r297.checked_output(args.output, "candidate output")
    receipt = r297.checked_output(args.receipt, "receipt output")
    candidate, payload = build(args.base.read_bytes(), args.base_receipt.read_bytes(), variant=args.variant)
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
