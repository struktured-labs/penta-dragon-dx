#!/usr/bin/env python3
"""Hide an orphaned Stage-1 hardware Window without changing hot-path phase.

r194 can leave an FFE4=0 hardware Window visible for two rendered frames when
its faster semantic-key path shifts the native cleanup phase.  Redirect only
the existing stale-window Z branch to a helper that clears DF0F and LCDC.5,
then rejoins the unchanged semantic tail.  Normal prelude fallthrough jumps
over the helper and is cycle-balanced to the original 48 NOP bytes without
changing any architectural state, even transiently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import update_checksums


BASE_SHA256 = "c6bd39a4eac5bcce00bd621a19af13c0a54f87f51ea89aec5fde8a3b42593272"
BANK = 13
BANK_SIZE = 0x4000
STALE_BRANCH_ADDR = 0x6EB4
CAVE_ADDR = 0x6EC4
CAVE_END = 0x6EF4
FINISH_ADDR = 0x6EF4
HELPER_ADDR = CAVE_ADDR + 2


def offset(address: int) -> int:
    return BANK * BANK_SIZE + address - 0x4000


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    if sha256(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r194 base: {sha256(source)}")
    rom = bytearray(source)
    branch_off = offset(STALE_BRANCH_ADDR)
    cave_off = offset(CAVE_ADDR)
    if rom[branch_off:branch_off + 2] != bytes.fromhex("28 F6"):
        raise SystemExit("stale-Window branch preimage moved")
    if rom[cave_off:offset(CAVE_END)] != bytes(CAVE_END - CAVE_ADDR):
        raise SystemExit("prelude padding cave is not empty")
    if rom[cave_off - 2:cave_off] != bytes.fromhex("E0 40"):
        raise SystemExit("normal prelude fallthrough moved")
    if rom[offset(FINISH_ADDR):offset(FINISH_ADDR) + 5] != bytes.fromhex(
        "23 2B C3 2C 57"
    ):
        raise SystemExit("semantic finish tail moved")

    helper = bytes.fromhex(
        "AF EA 0F DF "      # DF0F = 0
        "F0 40 CB AF E0 40 "# clear LCDC.5 (Window enable)
        "C3 F4 6E"          # rejoin semantic finish
    )
    assert len(helper) == 13
    landing = HELPER_ADDR + len(helper)
    skip = bytes([0x18, len(helper)])
    # Twelve JR +0 instructions add 48T over the 24 NOP bytes they replace.
    # They exactly compensate for the 13-byte helper skipped by the leading
    # JR without changing registers, flags, stack, or memory at any interrupt
    # boundary. Earlier diagnostics used balanced stack/HL operations and
    # proved visually correct but allowed low-health replay phase drift.
    phase_balance = bytes.fromhex("18 00 " * 12)
    cave = bytearray(CAVE_END - CAVE_ADDR)
    cave[0:2] = skip
    cave[2:2 + len(helper)] = helper
    cave[landing - CAVE_ADDR:landing - CAVE_ADDR + len(phase_balance)] = (
        phase_balance
    )
    rom[cave_off:offset(CAVE_END)] = cave

    branch_after = STALE_BRANCH_ADDR + 2
    delta = HELPER_ADDR - branch_after
    assert -128 <= delta <= 127
    rom[branch_off + 1] = delta & 0xFF
    update_checksums(rom)
    candidate = bytes(rom)

    original_cycles = (CAVE_END - CAVE_ADDR) * 4
    balanced_cycles = 12 + 12 * 12
    balanced_cycles += (CAVE_END - landing - len(phase_balance)) * 4
    assert balanced_cycles == original_cycles == 192

    changed = [i for i, (old, new) in enumerate(zip(source, candidate)) if old != new]
    allowed = set(range(cave_off, offset(CAVE_END))) | {branch_off + 1, 0x14E, 0x14F}
    if not set(changed) <= allowed:
        raise SystemExit("candidate changed bytes outside confined regions")
    report = {
        "schema": "penta-stage1-stale-window-hide-r199-v1",
        "status": "STATIC_PASS_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": sha256(source),
        "candidate_sha256": sha256(candidate),
        "stale_branch": f"0x{STALE_BRANCH_ADDR:04X}",
        "helper": f"0x{HELPER_ADDR:04X}",
        "normal_fallthrough_cycles_before": original_cycles,
        "normal_fallthrough_cycles_after": balanced_cycles,
        "normal_registers_flags_and_memory_preserved": True,
        "required_first_gate": "stale_gameplay_window r120-pass/r194-fail control",
    }
    return candidate, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    candidate, report = build(args.base.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
