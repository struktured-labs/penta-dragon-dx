#!/usr/bin/env python3
"""Build the exact Stage-7 menu-signature invalidation experiment.

The frozen e048 Stage-7 transport candidate leaves the established Window
maintenance helper Stage-1-only.  While the SELECT menu owns physical map
$9800, its native attribute-row passes deliberately replace gameplay attrs.
On close, a clean DF53/DF57 signature can let the next stock tile publication
flip that map before the Stage-7 attribute plane is rebuilt.  This bounded
candidate admits exact scene $08 to the existing dual-signature invalidation.

Static-only builder: no emulator is launched and the frozen input is never
modified.  The emitted ROM remains non-promotable until the exact r264 control,
duplicate menu roundtrip, Stage-7 visual/ABI, and speed gates pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "tmp/stage7-dual-plane-hdma-r264/candidate.gb"
BASE_RECEIPT = ROOT / "tmp/stage7-dual-plane-hdma-r264/static-receipt.json"
DEFAULT_OUTPUT = ROOT / "tmp/stage7-menu-signature-invalidation-r265/candidate.gb"
DEFAULT_RECEIPT = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/static-receipt.json"
)

BASE_SHA256 = "e04801c8b8b0c1eb5ddaddce31a9581ad5c1fc83e3f1b043c581afa33df216a0"
BASE_RECEIPT_SHA256 = (
    "b724cfae07e8e72cda8629778bef9d4f85a9ad7c3f1413eb691a06e6e1ef7272"
)
# Canonical exact-r264 ROM.  The similarly named Stage-7 scene08 router
# directory contains a *derived* 0866... experiment whose build receipt names
# aa4c... as its base; it is therefore not a valid native control input.
R264_CONTROL = ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb"
R264_CONTROL_SHA256 = (
    "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
)

BANK = 13
HELPER = 0x6A40
HELPER_END = 0x6A57
CALLSITE = 0x6EB1
VBLANK_MAPPER = 0x0824

OLD_HELPER = bytes.fromhex(
    "F0 E4 B7 C8 FA 80 D8 D6 02 C0 AF EA 53 DF EA 57 DF 3C C9 "
    "00 00 00 00"
)
NEW_HELPER = bytes.fromhex(
    "F0 E4 B7 C8 FA 80 D8 FE 02 28 03 FE 08 C0 AF EA 53 DF "
    "EA 57 DF 3C C9"
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
    require(bank > 0 and 0x4000 <= address <= 0x7FFF,
            "invalid switchable-bank address")
    return bank * 0x4000 + address - 0x4000


def checked_scratch(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(any(resolved != root and resolved.is_relative_to(root)
                for root in roots),
            f"{label} must be a child of repo tmp/ or /mnt/data/tmp/")
    return resolved


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def helper_semantics(*, ffe4: int, scene: int) -> dict[str, Any]:
    """Model the exact branch-visible contract of NEW_HELPER."""

    if ffe4 == 0:
        return {"z": True, "a": 0, "invalidate": False}
    if scene in {2, 8}:
        return {"z": False, "a": 1, "invalidate": True}
    return {"z": False, "a": scene, "invalidate": False}


def timing_contract() -> dict[str, Any]:
    """Bind every executed opcode cost for the four distinct helper paths."""

    paths = {
        "FFE4_zero_all_scenes": {
            "old_ops": [12, 4, 20],
            "new_ops": [12, 4, 20],
        },
        "FFE4_nonzero_scene02": {
            "old_ops": [12, 4, 8, 16, 8, 8, 4, 16, 16, 4, 16],
            "new_ops": [
                12, 4, 8, 16, 8, 12, 4, 16, 16, 4, 16,
            ],
        },
        "FFE4_nonzero_scene08": {
            "old_ops": [12, 4, 8, 16, 8, 20],
            "new_ops": [
                12, 4, 8, 16, 8, 8, 8, 8, 4, 16, 16, 4, 16,
            ],
        },
        "FFE4_nonzero_other_scene": {
            "old_ops": [12, 4, 8, 16, 8, 20],
            "new_ops": [12, 4, 8, 16, 8, 8, 8, 20],
        },
    }
    expected = {
        "FFE4_zero_all_scenes": (36, 36, 0),
        "FFE4_nonzero_scene02": (112, 116, 4),
        "FFE4_nonzero_scene08": (68, 128, 60),
        "FFE4_nonzero_other_scene": (68, 84, 16),
    }
    result: dict[str, Any] = {}
    for name, path in paths.items():
        old = sum(path["old_ops"])
        new = sum(path["new_ops"])
        require((old, new, new - old) == expected[name],
                f"exact opcode timing changed for {name}")
        result[name] = {
            "old_opcode_t_cycles": path["old_ops"],
            "new_opcode_t_cycles": path["new_ops"],
            "old": old,
            "new": new,
            "delta": new - old,
        }
    return result


def static_contract(source: bytes, *, base_receipt: bytes | None = None,
                    control: bytes | None = None) -> dict[str, Any]:
    require(digest(source) == BASE_SHA256, "wrong frozen Stage-7 candidate")
    receipt_bytes = BASE_RECEIPT.read_bytes() if base_receipt is None else base_receipt
    require(digest(receipt_bytes) == BASE_RECEIPT_SHA256,
            "frozen Stage-7 static receipt changed")
    control_identity = (
        digest(control) if control is not None else
        (digest(R264_CONTROL.read_bytes()) if R264_CONTROL.is_file() else None)
    )
    require(control_identity == R264_CONTROL_SHA256,
            "exact r264 control is missing or changed")
    contract = source_contract(source)
    return {"base_sha256": BASE_SHA256,
            "base_static_receipt_sha256": BASE_RECEIPT_SHA256,
            "r264_control_sha256": R264_CONTROL_SHA256,
            **{key: value for key, value in contract.items() if key != "base_sha256"}}


def source_contract(source: bytes) -> dict[str, Any]:
    """Check the fixed recipe without a historical receipt or control ROM."""
    require(digest(source) == BASE_SHA256, "wrong frozen Stage-7 candidate")

    helper_offset = bank_offset(BANK, HELPER)
    require(len(OLD_HELPER) == len(NEW_HELPER) == HELPER_END - HELPER,
            "helper width is not exactly 23 bytes")
    require(source[helper_offset:helper_offset + len(OLD_HELPER)] == OLD_HELPER,
            "bank13 stale-Window helper/cave preimage changed")
    require(source[helper_offset + len(OLD_HELPER):
                   helper_offset + len(OLD_HELPER) + len(NEXT_HELPER)]
            == NEXT_HELPER, "live bank13:$6A57 helper boundary changed")
    callsite_offset = bank_offset(BANK, CALLSITE)
    require(source[callsite_offset:callsite_offset + len(CALLSITE_CONTRACT)]
            == CALLSITE_CONTRACT, "Window-maintenance caller changed")
    require(source[VBLANK_MAPPER:VBLANK_MAPPER + len(VBLANK_MAPPER_CONTRACT)]
            == VBLANK_MAPPER_CONTRACT,
            "VBlank no longer maps bank13 around Window maintenance")

    # Every nonzero FFE4 route remains NZ at the sole caller branch.  The
    # following instruction reloads A from FF4F, so changing the unobserved A
    # value on non-target scenes cannot escape the helper.
    controls: dict[str, bool] = {}
    for scene in range(256):
        closed = helper_semantics(ffe4=0, scene=scene)
        opened = helper_semantics(ffe4=1, scene=scene)
        controls[f"scene_{scene:02x}_closed_returns_Z"] = (
            closed == {"z": True, "a": 0, "invalidate": False}
        )
        controls[f"scene_{scene:02x}_open_returns_NZ"] = not opened["z"]
        controls[f"scene_{scene:02x}_invalidation_exact"] = (
            opened["invalidate"] == (scene in {2, 8})
        )
    require(all(controls.values()), "helper semantic negative control escaped")

    timing = timing_contract()
    require(timing["FFE4_zero_all_scenes"]["delta"] == 0,
            "gameplay/no-Window hot path changed")
    return {
        "base_sha256": BASE_SHA256,
        "preimages": {
            "helper_and_zero_cave": OLD_HELPER.hex(" ").upper(),
            "next_live_helper": NEXT_HELPER.hex(" ").upper(),
            "window_caller": CALLSITE_CONTRACT.hex(" ").upper(),
            "vblank_bank13_mapper": VBLANK_MAPPER_CONTRACT.hex(" ").upper(),
        },
        "caller_contract": {
            "site": "bank13:$6EB1 CALL $6A40; $6EB4 JR Z,$6EC6",
            "FFE4_zero": "Z -> Window-off arm; byte/cycle exact",
            "FFE4_nonzero": "NZ -> Window maintenance for every scene",
            "A_after_branch": "overwritten by bank13:$6EB6 LDH A,[$FF4F]",
            "bank_qualification": (
                "fixed:$0824-$0837 maps bank13 for the entire VBlank wrapper"
            ),
        },
        "signature_contract": {
            "scene02": "DF53=DF57=0 while FFE4!=0 (preserved)",
            "scene08": "DF53=DF57=0 while FFE4!=0 (new)",
            "all_other_scenes": "no DF53/DF57 mutation",
            "next_close_publication": (
                "dirty signature forces hidden-map attribute publication before "
                "the stock caller's LCDC map flip"
            ),
        },
        "timing_t_cycles": timing,
        "semantic_controls": {
            "count": len(controls),
            "passed": sum(controls.values()),
            "all_256_scenes_and_both_FFE4_classes": all(controls.values()),
        },
    }


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    """Construct the menu repair with source checks, not historical approval."""
    contract = source_contract(source)
    rom = bytearray(source)
    helper_offset = bank_offset(BANK, HELPER)
    rom[helper_offset:helper_offset + len(NEW_HELPER)] = NEW_HELPER
    update_checksums(rom)
    candidate = bytes(rom)

    changed = [index for index, pair in enumerate(zip(source, candidate))
               if pair[0] != pair[1]]
    allowed = {0x014D, 0x014E, 0x014F}
    allowed.update(range(helper_offset, helper_offset + len(NEW_HELPER)))
    unexpected = [index for index in changed if index not in allowed]
    require(not unexpected, f"unexpected ROM changes: {unexpected[:16]}")
    payload_changes = [index for index in changed if index >= 0x0150]
    require(payload_changes, "menu signature patch changed no payload bytes")
    require(candidate[helper_offset:helper_offset + len(NEW_HELPER)]
            == NEW_HELPER, "emitted helper differs from construction")
    require(candidate[helper_offset + len(NEW_HELPER):
                      helper_offset + len(NEW_HELPER) + len(NEXT_HELPER)]
            == NEXT_HELPER, "emitted helper overlaps bank13:$6A57")
    require(candidate[VBLANK_MAPPER:VBLANK_MAPPER + len(VBLANK_MAPPER_CONTRACT)]
            == VBLANK_MAPPER_CONTRACT, "emitted candidate changed mapper")
    require(candidate[bank_offset(BANK, CALLSITE):
                      bank_offset(BANK, CALLSITE) + len(CALLSITE_CONTRACT)]
            == CALLSITE_CONTRACT, "emitted candidate changed caller")
    require(candidate[0x014D] == source[0x014D],
            "payload-only patch changed the header checksum")
    require(int.from_bytes(candidate[0x014E:0x0150], "big")
            == (sum(candidate[:0x014E]) + sum(candidate[0x0150:])) & 0xFFFF,
            "emitted global checksum is invalid")

    return candidate, {
        "schema": "penta-stage7-menu-signature-r265-construction-v1",
        "status": "construction-only",
        "promotable": False,
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "emulator_run": False,
        "candidate_sha256": digest(candidate),
        "patch": {
            "range": "bank13:$6A40-$6A56",
            "old": OLD_HELPER.hex(" ").upper(),
            "new": NEW_HELPER.hex(" ").upper(),
            "payload_changed_offsets": [f"0x{index:05X}"
                                        for index in payload_changes],
            "changed_byte_count_including_checksums": len(changed),
        },
        **contract,
    }


def build(source: bytes, *, base_receipt: bytes | None = None,
          control: bytes | None = None) -> tuple[bytes, dict[str, Any]]:
    contract = static_contract(source, base_receipt=base_receipt, control=control)
    candidate, construction = construct(source)
    receipt = {
        "schema": "penta-stage7-menu-signature-invalidation-r265-static-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_run": False,
        "candidate_sha256": digest(candidate),
        "patch": construction["patch"],
        **contract,
        "exact_control_plan": {
            "r264_rom": str(R264_CONTROL.relative_to(ROOT)),
            "r264_sha256": R264_CONTROL_SHA256,
            "fixture_derivation": (
                "normalize the exact r4a publication state with "
                "normalize_mgba_state_pc.py preserve_machine=True and only the "
                "ROM CRC rebound; bind both source and normalized gbAs SHAs"
            ),
            "control_probe_scope": (
                "same SELECT input, FFE4/Window nonvacuity, dual-map per-frame "
                "tile/attr vs immutable LUT semantics; no candidate-helper "
                "coverage assertion on r264"
            ),
            "classification": (
                "r264 drift => inherited menu/signature lineage; r264 clean and "
                "e048 drift => Stage7 transport interaction"
            ),
        },
        "required_live_gates": [
            "exact r264 normalized control receipt",
            "two sequential candidate menu roundtrips with zero semantic trails",
            "optimized helper before/after menu and zero helper/DMA while owned",
            "Stage7 visual/ABI recheck against frozen e048 receipts",
            "Stage7 speed ratio remains >=0.95",
        ],
        "decision": "STATIC_GO_FOR_BOUND_CONTROL_THEN_MENU_R2",
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    require(args.base.resolve() == BASE.resolve(),
            "this experiment accepts only the frozen e048 base path")
    output = checked_scratch(args.output, label="candidate output")
    receipt_path = checked_scratch(args.receipt, label="static receipt")
    require(output != receipt_path, "candidate and receipt paths alias")

    candidate, receipt = build(args.base.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt["candidate_path"] = str(output.relative_to(ROOT))
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    receipt_path.write_text(payload)
    print(json.dumps({
        "status": receipt["status"],
        "candidate": receipt["candidate_path"],
        "candidate_sha256": receipt["candidate_sha256"],
        "receipt": str(receipt_path.relative_to(ROOT)),
        "receipt_sha256": digest(payload.encode()),
        "decision": receipt["decision"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
