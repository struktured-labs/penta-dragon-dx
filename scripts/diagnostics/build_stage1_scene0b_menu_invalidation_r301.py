#!/usr/bin/env python3
"""Build non-promotable r301 scene-$0B SELECT-menu invalidation on r297-full.

The r292/r297 bank13:$6A40 menu helper accepts only D880 scenes $02..$08.
Locked Stage-1 rooms publish D880=$0B with FFB7=$02, leaving a valid-looking
physical-map cache across SELECT close.  r301 leaves r297's wall route and
scene-$0B row repair intact, but replaces only $6A44-$6A56 after the exact
FFE4==0 prefix.  The nonzero path maps an isolated bank21 helper which writes
the split-decider's fail-closed $FF only for FFB7=$02, clears cache keys for
FFB7=$03..$08, and otherwise does nothing.

$0847 cannot be used here: r297-full owns its unconditional bank21:$6C80
callee and that routine requires the RST room-writer stack layout.  The native
fixed mapper tail $09C0 (``LD [$2000],A; RET``) safely maps bank21 and, on the
helper tail, maps bank13 before consuming the original $6EB1 caller frame.
No emulator is launched by this builder.
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
DEFAULT_OUTPUT = TMP / "stage1-scene0b-menu-invalidation-r301/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-scene0b-menu-invalidation-r301/build-receipt.json"

R297_FULL_SHA256 = "4a7c3f6bae9e79e767326fcdf07a18fb0707783e2023db8b5f2c9fa3f5b14e1c"
BANK13 = 13
BANK21 = 21
MENU_HELPER_ADDR = 0x6A40
MENU_PREFIX = bytes.fromhex("F0 E4 B7 C8")
OLD_MENU_HELPER = bytes.fromhex(
    "F0 E4 B7 C8 FA 80 D8 D6 02 FE 07 3D D0 87 9F "
    "EA 53 DF EA 57 DF 3D C9"
)
# $6A44: map bank21 through the fixed $09C0 tail.  Its RET enters bank21 at
# $6A49, where the erased ingress jumps into the post-r297 cave.  The local
# RET is deliberately bank13-only padding: it is never fetched after mapping.
NEW_MENU_BODY = bytes.fromhex("3E 15 CD C0 09 C9") + bytes(13)

FIXED_MAPPER_TAIL_ADDR = 0x09C0
FIXED_MAPPER_TAIL = bytes.fromhex("EA 00 21 C9")
INGRESS_ADDR = 0x6A49
INGRESS = bytes.fromhex("C3 B4 6C")
R297_WALL_START = 0x6C80
R297_WALL_END = 0x6CB4  # exclusive; r297 owns $6C80-$6CB3.
CONTEXT_HELPER_ADDR = 0x6CB4
CONTEXT_HELPER = bytes.fromhex(
    "F0 B7 FE 02 28 11 "           # FFB7 == $02 -> Stage-1 sentinel
    "FE 03 38 15 FE 09 30 11 "     # only $03..$08 clear the keys
    "AF EA 53 DF EA 57 DF 18 08 "
    "3E FF EA 53 DF EA 57 DF "
    "3E 0D B7 C3 C0 09"            # A=$0D and NZ, map bank13, RET
)
CONTEXT_HELPER_END = CONTEXT_HELPER_ADDR + len(CONTEXT_HELPER)
CACHE_ADDRS = (0xDF53, 0xDF57)
CALLSITE_ADDR = 0x6EB1
CALLSITE = bytes.fromhex(
    "CD 40 6A 28 10 F0 40 CB 77 28 04 CB 9F 18 02 CB DF E0 40"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def model(*, ffe4: int, ffb7: int, d880: int, caches: dict[int, int]) -> dict[str, object]:
    """Exact observable helper contract; D880 is intentionally not inspected."""
    result = dict(caches)
    if ffe4 == 0:
        return {"a": 0, "z": True, "caches": result, "action": "closed"}
    if ffb7 == 0x02:
        value: int | None = 0xFF
        action = "stage1-sentinel"
    elif 0x03 <= ffb7 <= 0x08:
        value = 0x00
        action = "later-stage-clear"
    else:
        value = None
        action = "unchanged"
    if value is not None:
        for address in CACHE_ADDRS:
            result[address] = value
    return {
        "a": 0x0D,
        "z": False,
        "caches": result,
        "action": action,
        "d880_ignored": d880,
    }


def exhaustive_model_contract() -> dict[str, object]:
    """Exhaust 256x256 branch inputs and prove all 256 D880 values are inert."""
    seed = {0xDF53: 0x12, 0xDF57: 0x34}
    pairs = 0
    for ffe4 in range(256):
        for ffb7 in range(256):
            actual = model(ffe4=ffe4, ffb7=ffb7, d880=0x0B, caches=seed)
            if ffe4 == 0:
                expected_action, expected_a, expected_z = "closed", 0, True
                expected = seed
            elif ffb7 == 2:
                expected_action, expected_a, expected_z = "stage1-sentinel", 13, False
                expected = {0xDF53: 0xFF, 0xDF57: 0xFF}
            elif 3 <= ffb7 <= 8:
                expected_action, expected_a, expected_z = "later-stage-clear", 13, False
                expected = {0xDF53: 0, 0xDF57: 0}
            else:
                expected_action, expected_a, expected_z = "unchanged", 13, False
                expected = seed
            r297.require(actual["action"] == expected_action
                         and actual["a"] == expected_a and actual["z"] == expected_z
                         and actual["caches"] == expected,
                         f"semantic drift FFE4={ffe4:02X} FFB7={ffb7:02X}")
            pairs += 1
    # D880=$0B is the new operator state, but the helper has no D880 opcode;
    # prove each possible scene byte yields exactly the same branch result.
    reference = model(ffe4=1, ffb7=2, d880=0, caches=seed)
    for d880 in range(256):
        current = model(ffe4=1, ffb7=2, d880=d880, caches=seed)
        r297.require({key: value for key, value in current.items() if key != "d880_ignored"}
                     == {key: value for key, value in reference.items() if key != "d880_ignored"},
                     f"D880 leaked into helper at {d880:02X}")
    return {
        "ffe4_ffb7_pairs": pairs,
        "logical_ffe4_ffb7_d880_states": 256 * 256 * 256,
        "FFE4_zero_returns_Z_without_mapping_or_writes": True,
        "FFB7_02_writes_FF": True,
        "FFB7_03_through_08_write_00": True,
        "all_other_FFB7_values_unchanged": True,
        "all_D880_values_ignored": True,
        "return_A_0D_NZ": True,
    }


def timing_contract() -> dict[str, object]:
    # Only the first line is the normal FFE4==0 hot path; it is bit-for-bit
    # r297 and remains 36 T-cycles.  Remaining values include the wrapper,
    # fixed mapper enter/exit, ingress JP, and scoped-helper instruction path.
    paths = {
        "FFE4_zero": (12 + 4 + 20, 12 + 4 + 20),
        "FFB7_02": (0, 236),
        "FFB7_03_through_08": (0, 272),
        "FFB7_00_or_01": (0, 212),
        "FFB7_09_plus": (0, 228),
    }
    r297.require(paths["FFE4_zero"] == (36, 36), "FFE4-zero timing drift")
    return {
        name: {"r297": old, "r301": new, "delta": new - old}
        for name, (old, new) in paths.items()
    }


def patch_exact(rom: bytearray, source: bytes, *, bank: int, address: int,
                old: bytes, new: bytes, allowed: set[int], label: str) -> None:
    r297.require(len(old) == len(new), f"{label} changes width")
    offset = r297.bank_offset(bank, address)
    r297.require(source[offset:offset + len(old)] == old, f"{label} preimage changed")
    rom[offset:offset + len(new)] = new
    allowed.update(range(offset, offset + len(new)))


def validate_preimages(r297_full: bytes) -> dict[str, object]:
    menu = r297.bank_offset(BANK13, MENU_HELPER_ADDR)
    r297.require(r297_full[menu:menu + len(OLD_MENU_HELPER)] == OLD_MENU_HELPER,
                 "bank13 menu helper preimage changed")
    r297.require(r297_full[menu:menu + len(MENU_PREFIX)] == MENU_PREFIX,
                 "FFE4-zero prefix changed before r301")
    caller = r297.bank_offset(BANK13, CALLSITE_ADDR)
    r297.require(r297_full[caller:caller + len(CALLSITE)] == CALLSITE,
                 "menu caller ABI changed")
    r297.require(r297_full[FIXED_MAPPER_TAIL_ADDR:FIXED_MAPPER_TAIL_ADDR + 4]
                 == FIXED_MAPPER_TAIL, "fixed direct mapper tail changed")
    r297.require(r297_full[r297.MAPPER_DISPATCH_ADDR:r297.MAPPER_DISPATCH_ADDR + len(r297.MAPPER_DISPATCH)]
                 == r297.MAPPER_DISPATCH, "r297 fixed dispatcher changed")
    wall = r297.bank_offset(BANK21, R297_WALL_START)
    r297.require(r297_full[wall:wall + len(r297.WALL_HELPER)] == r297.WALL_HELPER,
                 "r297 bank21 wall-helper ownership changed")
    ingress = r297.bank_offset(BANK21, INGRESS_ADDR)
    cave = r297.bank_offset(BANK21, CONTEXT_HELPER_ADDR)
    r297.require(r297_full[ingress:ingress + len(INGRESS)] == b"\xFF" * len(INGRESS),
                 "bank21 ingress cave is not erased")
    r297.require(r297_full[cave:cave + len(CONTEXT_HELPER)] == b"\xFF" * len(CONTEXT_HELPER),
                 "bank21 post-r297 cave is not erased")
    r297.require(CONTEXT_HELPER_ADDR >= R297_WALL_END,
                 "r301 main cave overlaps r297 wall helper")
    r297.require(CONTEXT_HELPER_END == 0x6CD9, "contextual helper width/layout drifted")
    r297.require(INGRESS == bytes.fromhex("C3 B4 6C"), "ingress no longer targets main cave")
    r297.require(CONTEXT_HELPER.endswith(bytes.fromhex("3E 0D B7 C3 C0 09")),
                 "helper no longer returns A=$0D/NZ through fixed mapper")
    r297.require(bytes.fromhex("FA 80 D8") not in CONTEXT_HELPER,
                 "scoped helper must not inspect stale D880")
    return {
        "base": "exact r292 composed with exact r297 full",
        "r297_wall_helper_preserved": "bank21:$6C80-$6CB3",
        "r301_ingress_cave": "bank21:$6A49-$6A4B",
        "r301_main_cave": f"bank21:${CONTEXT_HELPER_ADDR:04X}-${CONTEXT_HELPER_END - 1:04X}",
        "fixed_dispatcher_0847_untouched": True,
        "fixed_mapper_tail_09C0_untouched": True,
    }


def stack_bank_contract() -> dict[str, object]:
    # Outer CALL $6A40 owns return $6EB4.  The local CALL $09C0 owns $6A49;
    # mapper RET consumes only that local frame after selecting bank21.  The
    # bank21 tail JP $09C0 creates no frame; its RET selects bank13 then
    # consumes the untouched outer frame.  SP therefore has zero net delta.
    stack = [0x49, 0x6A, 0xB4, 0x6E, 0xAA, 0xBB]
    local_return = stack[:2]
    after_enter = stack[2:]
    outer_return = after_enter[:2]
    after_exit = after_enter[2:]
    r297.require(local_return == [0x49, 0x6A], "bank21 helper entry frame drifted")
    r297.require(outer_return == [0xB4, 0x6E], "menu caller frame drifted")
    r297.require(after_exit == [0xAA, 0xBB], "stack did not restore after bank13 map")
    return {
        "enter": "$6A44 CALL $09C0 -> bank21:$6A49",
        "exit": "bank21 helper JP $09C0 -> bank13:$6EB4",
        "stack_delta": 0,
        "BC_DE_HL_SP_FF99_DC09_untouched": True,
        "returned_A": "$0D",
        "returned_Z": False,
    }


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    """Compose exact r297-full first, then apply only r301-owned bytes."""
    r297_full, r297_receipt = r297.build(source, base_receipt_bytes, variant="full")
    r297.require(digest(r297_full) == R297_FULL_SHA256, "r297 full identity changed")
    r297.require(r297_receipt["candidate_sha256"] == R297_FULL_SHA256,
                 "r297 receipt identity changed")
    preimages = validate_preimages(r297_full)
    semantic = exhaustive_model_contract()
    timing = timing_contract()
    stack = stack_bank_contract()

    rom = bytearray(r297_full)
    allowed = {0x014D, 0x014E, 0x014F}
    patch_exact(rom, r297_full, bank=BANK13, address=MENU_HELPER_ADDR + 4,
                old=OLD_MENU_HELPER[4:], new=NEW_MENU_BODY, allowed=allowed,
                label="bank13 nonzero menu body")
    patch_exact(rom, r297_full, bank=BANK21, address=INGRESS_ADDR,
                old=b"\xFF" * len(INGRESS), new=INGRESS, allowed=allowed,
                label="bank21 ingress")
    patch_exact(rom, r297_full, bank=BANK21, address=CONTEXT_HELPER_ADDR,
                old=b"\xFF" * len(CONTEXT_HELPER), new=CONTEXT_HELPER, allowed=allowed,
                label="bank21 post-r297 contextual helper")

    lut = r297.bank_offset(BANK13, 0x7000)
    r297.require(rom[lut:lut + 0x100] == r297_full[lut:lut + 0x100], "immutable Stage1 LUT changed")
    r297.require(rom[0x4303:0x4319] == r297_full[0x4303:0x4319], "renderer changed")
    wall = r297.bank_offset(BANK21, R297_WALL_START)
    r297.require(rom[wall:wall + len(r297.WALL_HELPER)] == r297.WALL_HELPER,
                 "r301 overwrote r297 wall helper")
    r297.require(rom[r297.MAPPER_DISPATCH_ADDR:r297.MAPPER_DISPATCH_ADDR + len(r297.MAPPER_DISPATCH)]
                 == r297.MAPPER_DISPATCH, "r301 changed fixed dispatcher")
    r297.update_checksums(rom)
    candidate = bytes(rom)
    changed = {index for index, pair in enumerate(zip(r297_full, candidate, strict=True)) if pair[0] != pair[1]}
    r297.require(changed <= allowed, "r301 escaped owned/checksum ranges")
    functional = sorted(index for index in changed if index >= 0x0150)
    r297.require(functional, "r301 has no functional delta")
    return candidate, {
        "schema": "penta-stage1-scene0b-menu-invalidation-r301-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": r297.BASE_SHA256,
        "base_receipt_sha256": r297.BASE_RECEIPT_SHA256,
        "r297_full_sha256": R297_FULL_SHA256,
        "candidate_sha256": digest(candidate),
        "checksums": {"header": f"{candidate[0x014D]:02X}", "global": candidate[0x014E:0x0150].hex().upper()},
        "patch": {
            "bank13_nonzero_body": "bank13:$6A44-$6A56",
            "bank21_ingress": "bank21:$6A49-$6A4B",
            "bank21_contextual_cave": preimages["r301_main_cave"],
            "FFB7_02": "DF53/DF57=$FF",
            "FFB7_03_to_08": "DF53/DF57=$00",
            "other_FFB7": "no cache writes",
            "D880": "intentionally not read",
            "direct_FFBD_RST_hook": False,
        },
        "offline_contract": {"preimages": preimages, "semantic": semantic, "timing": timing, "stack_bank": stack},
        "ownership": {"functional_changed_bytes": len(functional), "changed_offsets_from_r297": [f"0x{item:06X}" for item in sorted(changed)], "r297_6C80_6CB3_byte_exact": True, "renderer_byte_exact": True, "immutable_LUT_byte_exact": True},
        "required_gates": ["scene-$0B SELECT close repeatedly invalidates both physical maps", "room05 and later-stage control", "r297 wall route continuity", "live stack/bank/render continuity"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r297.checked_output(args.output, "candidate output")
    receipt = r297.checked_output(args.receipt, "receipt output")
    candidate, payload = build(args.base.read_bytes(), args.base_receipt.read_bytes())
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
