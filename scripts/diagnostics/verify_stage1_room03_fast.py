#!/usr/bin/env python3
"""Fail-closed static gate for the production Stage-1 room-$03 fast path."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from stage1_room03_fast import (  # noqa: E402
    EXPANDED_RETURN_TRAMPOLINE,
    GATE,
    GATE_ADDR,
    LIVE_HAZARD_MAPPER_CALL,
    LIVE_HAZARD_MAPPER_CALL_ADDR,
    PRIVATE_BANK,
    ROOM_GATE,
    ROOM_GATE_ADDR,
    SCANNER_ADDR,
    bank_offset,
    inspect,
)
from stage_card_palette_handoff import (  # noqa: E402
    inspect_stage_card_palette_handoff,
)


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def route(scene: int, room: int) -> str:
    if scene & 0x08:
        return "full-scanner"
    if room != 0x03:
        return "full-scanner"
    return "balanced-fast-exit"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    rom = args.rom.resolve().read_bytes()
    installed = inspect(rom)
    handoff = inspect_stage_card_palette_handoff(rom)
    controls = {
        "ordinary_scene02_room03": route(0x02, 0x03),
        "ordinary_scene02_room01": route(0x02, 0x01),
        "room12_repair": route(0x02, 0x12),
        "miniboss_scene0A_room03": route(0x0A, 0x03),
        "miniboss_scene0A_room12": route(0x0A, 0x12),
    }
    expected_controls = {
        "ordinary_scene02_room03": "balanced-fast-exit",
        "ordinary_scene02_room01": "full-scanner",
        "room12_repair": "full-scanner",
        "miniboss_scene0A_room03": "full-scanner",
        "miniboss_scene0A_room12": "full-scanner",
    }

    # CALL leaves its continuation above the row helper's saved HL. The fast
    # leaf must reproduce the original scanner+$55C0 unwind exactly.
    stack = ["return-$6BEA", "saved-HL", "outer"]
    bc = stack.pop(0)
    de = stack.pop(0)
    stack.insert(0, bc)
    landed = stack.pop(0)
    stack_ok = (
        landed == "return-$6BEA"
        and de == "saved-HL"
        and stack == ["outer"]
    )

    # Bind the exact production code, not just a high-level Python model.
    call = bank_offset(installed["call_address"])
    call_target = bytes([
        0xCD, GATE_ADDR & 0xFF, GATE_ADDR >> 8,
    ])
    scanner = bank_offset(SCANNER_ADDR)
    checks = {
        "512 KiB expanded ROM": len(rom) == 32 * 0x4000,
        "room03 fast path is installed": installed["installed"] is True,
        "scanner call targets guarded dispatcher": (
            rom[call:call + 3] == call_target
        ),
        "guard bytes are exact": (
            rom[bank_offset(GATE_ADDR):bank_offset(GATE_ADDR) + len(GATE)]
            == GATE
        ),
        "guard JR lands at the first room-gate opcode": (
            GATE_ADDR + 4 + int.from_bytes(
                GATE[3:4], byteorder="little", signed=True
            ) == ROOM_GATE_ADDR
        ),
        "room gate bytes are exact": (
            rom[
                bank_offset(ROOM_GATE_ADDR):
                bank_offset(ROOM_GATE_ADDR) + len(ROOM_GATE)
            ] == ROOM_GATE
        ),
        "live start-4 CALL $0061 operand is not overwritten": (
            rom[
                bank_offset(LIVE_HAZARD_MAPPER_CALL_ADDR):
                bank_offset(LIVE_HAZARD_MAPPER_CALL_ADDR) + 3
            ] == LIVE_HAZARD_MAPPER_CALL
            and installed["live_hazard_mapper_call_preserved"] is True
        ),
        "bank-20 $6B70 semantic trampoline is byte-exact": (
            rom[
                20 * 0x4000 + GATE_ADDR - 0x4000:
                20 * 0x4000 + GATE_ADDR - 0x4000 + 3
            ] == EXPANDED_RETURN_TRAMPOLINE
            and installed["expanded_return_trampoline_preserved"] is True
        ),
        "full scanner remains populated": rom[scanner:scanner + 8] != bytes(8),
        "scene and repair controls fail closed": controls == expected_controls,
        "fast leaf preserves mapper stack ABI": stack_ok,
        "exact Stage-card handoff remains installed": handoff["installed"],
        "tagged exact-destination copier is present": (
            rom[0x42A7:0x42B1] == bytes.fromhex(
                "2E 00 7C E0 A5 16 FF CD 85 34"
            )
            and rom[0x42A7:0x4368].count(
                bytes.fromhex("F0 A5 1F 38")
            ) == 1
            and rom[bank_offset(0x6CCE):bank_offset(0x6CD6)]
            == bytes.fromhex("F0 A5 E6 FE 67 C3 A7 6B")
        ),
        "tagged pure path always enters the scene-aware owner": (
            rom[0x42A7:0x436E].count(bytes.fromhex(
                "F0 A5 1F 38 0A CD F1 DB "
                "00 00 00 00 00 FB C9"
            )) == 1
        ),
    }
    receipt = {
        "schema": "penta-stage1-room03-fast-production-v1",
        "status": "pass" if all(checks.values()) else "fail",
        "rom": str(args.rom.resolve()),
        "rom_sha256": digest(rom),
        "private_bank": PRIVATE_BANK,
        "installed": installed,
        "controls": controls,
        "stack_balance": {
            "saved_hl_consumed": de == "saved-HL",
            "return_lands_at": landed,
            "outer_stack_exact": stack == ["outer"],
        },
        "stage_card_hook": f"${handoff['hook_address']:04X}",
        "checks": checks,
        "passed": all(checks.values()),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
