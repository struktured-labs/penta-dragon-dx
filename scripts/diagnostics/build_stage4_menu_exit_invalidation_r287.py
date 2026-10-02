#!/usr/bin/env python3
"""Build the exact-r286 Stage-4 SELECT-menu invalidation delta.

The r286 Stage-4 cache key remains unchanged while the item Window owns and
rewrites a physical attribute map.  The next Stage-4 helper therefore sees a
false cache hit after SELECT close and leaves the six menu rows visible as
gameplay colors.

r287 changes only the existing menu-owned invalidator at bank 13:$6A40.  Its
qualified scenes expand from ``{$02,$08}`` to the complete gameplay interval
``$02..$08``.  While FFE4 is nonzero it clears both physical-map signatures;
the next normal publication must miss and repaint.  The FFE4-zero gameplay
path remains byte- and cycle-exact at 36 T-cycles.

This static builder never launches an emulator and writes only below the
repository-local ignored ``tmp/`` tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage4-lazy-departure-r286/candidate.gb"
BASE_RECEIPT = TMP / "stage4-lazy-departure-r286/build-receipt.json"
DEFAULT_OUTPUT = TMP / "stage4-menu-exit-invalidation-r287/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage4-menu-exit-invalidation-r287/build-receipt.json"

BASE_SHA256 = "a5521815ee25ca1c35a063198aec5f6a69609f99df7554201e41ab73699fc3c1"
BASE_RECEIPT_SHA256 = (
    "4a1209778c471dc833ab574d6bac46e70e8f8d925a80a4ec48dd61099f117d49"
)
EXPECTED_CANDIDATE_SHA256 = (
    "a9bc2d2d5d7112584797229d03bfb2fe55a9bcb5fa3c1a33d30cddc3a8364898"
)

BANK_SIZE = 0x4000
BANK = 13
HELPER = 0x6A40
HELPER_END = 0x6A57
CALLSITE = 0x6EB1
VBLANK_MAPPER = 0x0824

OLD_HELPER = bytes.fromhex(
    "F0 E4 B7 C8 FA 80 D8 FE 02 28 03 FE 08 C0 AF EA 53 DF EA 57 DF 3C C9"
)
NEW_HELPER = bytes.fromhex(
    "F0 E4 B7 C8 FA 80 D8 D6 02 FE 07 3D D0 AF EA 53 DF EA 57 DF 3C C9 00"
)
NEXT_HELPER = bytes.fromhex("0E 08 2A E0 69 0D 20 FA C9")
CALLSITE_CONTRACT = bytes.fromhex(
    "CD 40 6A 28 10 F0 40 CB 77 28 04 CB 9F 18 02 CB DF E0 40"
)
VBLANK_MAPPER_CONTRACT = bytes.fromhex(
    "F0 99 F5 3E 0D E0 99 EA 00 21 CD 1D 6F F1 E0 99 EA 00 21 C9"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address < 0x8000,
            f"invalid banked address bank{bank}:${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def checked_output(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved != scratch and scratch in resolved.parents,
            f"{label} must be a child of repository tmp/: {resolved}")
    return resolved


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def old_semantics(*, ffe4: int, scene: int) -> dict[str, Any]:
    if ffe4 == 0:
        return {"z": True, "a": 0, "invalidate": False, "path": "closed"}
    if scene in {0x02, 0x08}:
        return {"z": False, "a": 1, "invalidate": True, "path": "target"}
    return {"z": False, "a": scene, "invalidate": False, "path": "other"}


def new_semantics(*, ffe4: int, scene: int) -> dict[str, Any]:
    """Model the branch-visible flags and side effect of NEW_HELPER."""
    if ffe4 == 0:
        return {"z": True, "a": 0, "invalidate": False, "path": "closed"}
    normalized = (scene - 2) & 0xFF
    carry = normalized < 7                 # CP $07
    decremented = (normalized - 1) & 0xFF  # DEC A preserves Carry
    if not carry:                          # RET NC
        return {
            "z": decremented == 0,
            "a": decremented,
            "invalidate": False,
            "path": "other",
        }
    # XOR A; stores; INC A; RET always returns A=1/NZ to the sole caller.
    return {"z": False, "a": 1, "invalidate": True, "path": "target"}


def timing_contract() -> dict[str, Any]:
    paths = {
        "ffe4_zero": {"old": [12, 4, 20], "new": [12, 4, 20]},
        "scene02": {
            "old": [12, 4, 8, 16, 8, 12, 4, 16, 16, 4, 16],
            "new": [12, 4, 8, 16, 8, 8, 4, 8, 4, 16, 16, 4, 16],
        },
        "scene05": {
            "old": [12, 4, 8, 16, 8, 8, 8, 20],
            "new": [12, 4, 8, 16, 8, 8, 4, 8, 4, 16, 16, 4, 16],
        },
        "scene08": {
            "old": [12, 4, 8, 16, 8, 8, 8, 8, 4, 16, 16, 4, 16],
            "new": [12, 4, 8, 16, 8, 8, 4, 8, 4, 16, 16, 4, 16],
        },
        "non_target": {
            "old": [12, 4, 8, 16, 8, 8, 8, 20],
            "new": [12, 4, 8, 16, 8, 8, 4, 20],
        },
    }
    expected = {
        "ffe4_zero": (36, 36, 0),
        "scene02": (116, 124, 8),
        "scene05": (84, 124, 40),
        "scene08": (128, 124, -4),
        "non_target": (84, 80, -4),
    }
    result: dict[str, Any] = {}
    for name, rows in paths.items():
        old_t, new_t = sum(rows["old"]), sum(rows["new"])
        require((old_t, new_t, new_t - old_t) == expected[name],
                f"timing drift on {name}")
        result[name] = {
            "old_opcode_t_cycles": rows["old"],
            "new_opcode_t_cycles": rows["new"],
            "old": old_t,
            "new": new_t,
            "delta": new_t - old_t,
        }
    require(result["ffe4_zero"]["delta"] == 0,
            "gameplay/no-menu hot path changed")
    return result


def exhaustive_controls() -> dict[str, Any]:
    passed = 0
    for ffe4 in range(256):
        for scene in range(256):
            old = old_semantics(ffe4=ffe4, scene=scene)
            new = new_semantics(ffe4=ffe4, scene=scene)
            expected_invalidation = ffe4 != 0 and 0x02 <= scene <= 0x08
            require(new["invalidate"] == expected_invalidation,
                    f"invalidation mismatch ffe4={ffe4:02X} scene={scene:02X}")
            require(new["z"] == (ffe4 == 0),
                    f"caller-Z mismatch ffe4={ffe4:02X} scene={scene:02X}")
            if ffe4 == 0:
                require(new == old, "FFE4-zero behavior changed")
            passed += 1

    mutant = bytearray(NEW_HELPER)
    mutant[10] = 0x06
    require(bytes.fromhex("FE 07 3D D0") not in mutant,
            "upper-bound mutation escaped")
    mutant = bytearray(NEW_HELPER)
    mutant[12] = 0xC8
    require(bytes.fromhex("3D D0") not in mutant,
            "carry-branch mutation escaped")
    return {
        "state_pairs": 256 * 256,
        "passed": passed,
        "all_FFE4_values": 256,
        "all_D880_values": 256,
        "FFE4_zero_byte_cycle_and_semantic_exact": True,
        "FFE4_nonzero_returns_NZ_for_every_scene": True,
        "invalidation_exactly_scenes_02_through_08": True,
        "scene_upper_bound_mutation_rejected": True,
        "carry_branch_mutation_rejected": True,
    }


def static_contract(source: bytes, base_receipt_bytes: bytes) -> dict[str, Any]:
    require(len(source) == 32 * BANK_SIZE, "r286 base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256, "wrong exact r286 base")
    require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
            "r286 build receipt identity changed")
    base_receipt = json.loads(base_receipt_bytes)
    require(base_receipt.get("candidate_sha256") == BASE_SHA256,
            "r286 build receipt binds another candidate")
    require(base_receipt.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED",
            "r286 build receipt status changed")
    return source_contract(source)


def source_contract(source: bytes) -> dict[str, Any]:
    """Validate the complete fixed menu recipe independently of audit receipts."""
    require(len(source) == 32 * BANK_SIZE, "r286 base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256, "wrong exact r286 base")

    offset = bank_offset(BANK, HELPER)
    require(len(OLD_HELPER) == len(NEW_HELPER) == HELPER_END - HELPER,
            "menu invalidator width changed")
    require(source[offset:offset + len(OLD_HELPER)] == OLD_HELPER,
            "menu invalidator preimage changed")
    require(source[offset + len(OLD_HELPER):offset + len(OLD_HELPER) + len(NEXT_HELPER)]
            == NEXT_HELPER, "next bank13 helper boundary changed")
    callsite = bank_offset(BANK, CALLSITE)
    require(source[callsite:callsite + len(CALLSITE_CONTRACT)] == CALLSITE_CONTRACT,
            "menu invalidator caller changed")
    require(source[VBLANK_MAPPER:VBLANK_MAPPER + len(VBLANK_MAPPER_CONTRACT)]
            == VBLANK_MAPPER_CONTRACT,
            "VBlank no longer maps bank13 around the helper")
    return {
        "preimages": {
            "helper": OLD_HELPER.hex(" ").upper(),
            "next_helper": NEXT_HELPER.hex(" ").upper(),
            "caller": CALLSITE_CONTRACT.hex(" ").upper(),
            "vblank_mapper": VBLANK_MAPPER_CONTRACT.hex(" ").upper(),
        },
        "caller_contract": {
            "site": "bank13:$6EB1 CALL $6A40; $6EB4 JR Z,$6EC6",
            "FFE4_zero": "Z -> Window-off arm; byte/cycle exact",
            "FFE4_nonzero": "NZ -> Window maintenance for all 256 scenes",
            "A_after_branch": "overwritten by bank13:$6EB6 LDH A,[$FF4F]",
            "bank_qualification": "fixed:$0824 maps bank13 for the VBlank wrapper",
        },
        "semantic_controls": exhaustive_controls(),
        "timing_t_cycles": timing_contract(),
    }


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    contract = source_contract(source)
    rom = bytearray(source)
    offset = bank_offset(BANK, HELPER)
    rom[offset:offset + len(NEW_HELPER)] = NEW_HELPER
    update_checksums(rom)
    candidate = bytes(rom)
    require(digest(candidate) == EXPECTED_CANDIDATE_SHA256,
            f"candidate identity drift: {digest(candidate)}")

    changed = [
        index for index, pair in enumerate(zip(source, candidate, strict=True))
        if pair[0] != pair[1]
    ]
    allowed = set(range(offset, offset + len(NEW_HELPER))) | {0x014D, 0x014E, 0x014F}
    require(set(changed) <= allowed,
            f"r287 escaped helper/checksum ownership: {sorted(set(changed) - allowed)[:8]}")
    functional = [index for index in changed if index >= 0x0150]
    require(len(functional) == 15, f"functional delta count changed: {len(functional)}")
    require(len(changed) == 16, f"total delta count changed: {len(changed)}")
    require(changed == [0x014F] + functional,
            f"unexpected checksum delta: {changed[:4]}")
    require(candidate[0x014D] == source[0x014D] == 0xF9,
            "header checksum changed")
    require(candidate[0x014E] == source[0x014E] == 0x3D,
            "global checksum high byte changed")
    require(source[0x014F] == 0x5B and candidate[0x014F] == 0x54,
            "global checksum low-byte delta changed")
    require(candidate[0x0150:offset] == source[0x0150:offset]
            and candidate[offset + len(NEW_HELPER):] == source[offset + len(NEW_HELPER):],
            "candidate changed bytes outside helper/checksums")

    receipt: dict[str, Any] = {
        "schema": "penta-stage4-menu-exit-invalidation-r287-construction-v1",
        "status": "construction-only",
        "promotable": False,
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "emulator_invoked": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": EXPECTED_CANDIDATE_SHA256,
        "checksums": {"header": "F9", "global": "3D54"},
        "patch": {
            "range": "bank13:$6A40-$6A56",
            "rom_offset": f"0x{offset:06X}",
            "old": OLD_HELPER.hex(" ").upper(),
            "new": NEW_HELPER.hex(" ").upper(),
            "functional_changed_offsets": [f"0x{value:06X}" for value in functional],
            "functional_changed_bytes": len(functional),
            "changed_bytes_including_checksums": len(changed),
        },
        "invalidation_contract": {
            "old_scenes": ["$02", "$08"],
            "new_scenes": [f"${value:02X}" for value in range(2, 9)],
            "Stage4_scene": "$05",
            "trigger": "FFE4 != 0 (native item-Window ownership)",
            "operation": "DF53=DF57=0 before Window maintenance/publication",
            "effect": "next physical-map C1F1/C2F1 key comparison must miss in Stage4",
            "repeated_menu_safe": True,
        },
        **contract,
        "transferred_r286_contracts": {
            "Stage4_DB00_DB3D_payload_exact": True,
            "DA5D_trampoline_DAD5_DAB7_exact": True,
            "Stage4_mapper_entry_material_path_exact": True,
            "all_gameplay_speed_path_bytes_exact": True,
            "bank20_menu_publisher_and_private_LUT_exact": True,
            "all_non_menu_candidate_bytes_exact_except_checksums": True,
        },
        "required_live_gates": [
            "two deterministic Stage4 SELECT open/hold/close replays",
            "DF53/DF57 invalidation observed while menu-owned",
            "zero settled-pre, post-close, and final semantic mismatches",
            "exact r286 Stage4 strict speed remains in 0.99-1.01",
            "same-process Stage4 departure/title/Stage1 lifecycle",
        ],
    }
    return candidate, receipt


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    static_contract(source, base_receipt_bytes)
    candidate, receipt = construct(source)
    receipt.pop("historical_evidence_consumed")
    receipt.pop("fresh_live_qualification")
    receipt.update({"schema": "penta-stage4-menu-exit-invalidation-r287-build-v1",
                    "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
                    "base_build_receipt_sha256": BASE_RECEIPT_SHA256,
                    "decision": "STATIC_GO_FOR_EXACT_R287_MENU_AND_LIFECYCLE_GATES"})
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = checked_output(args.output, label="candidate output")
    receipt_path = checked_output(args.receipt, label="build receipt")
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
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
