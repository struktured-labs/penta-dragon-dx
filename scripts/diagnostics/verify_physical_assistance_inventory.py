#!/usr/bin/env python3
"""#37/#41 static guard: harness assistance must not use mapped/banked writes.

Native health/setup bytes (DCBB health, DCFD level-select unlock, DCB8/DCBA
section counters) live in physical WRAM bank1. ``emu:write8(0xDCxx, ...)``
writes whichever bank SVBK currently selects, so a frame callback that lands
while a graphics routine parks SVBK=2/3 corrupts scratch planes instead.
DCDC/DCDD are native inventory/ten-slot-cursor state, not health; the legacy
``DCDD=0x17`` / ``DCDC=0xFF`` "godmode" writes forced an out-of-range cursor.

This scans every checked-in Lua probe (and Lua embedded in Python probes) and
fails on any remaining mapped write to those addresses or any fake-health
cursor write, except for the explicitly listed pending files below.
Run with ``--self-test`` to prove the scanner rejects both defect shapes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ("scripts/diagnostics", "scripts/probes")
NATIVE = ("DCBB", "DCFD", "DCB8", "DCBA", "DCDC", "DCDD")
MAPPED = re.compile(
    r"emu:write8\(\s*0x(" + "|".join(NATIVE) + r")\b", re.IGNORECASE)
# Any writer (mapped, physical offset, or helper) that stores the legacy
# fake-health values into the native inventory/cursor bytes.
FAKE_HEALTH = re.compile(
    r"(?:write8|write|game_write)\(\s*0x(?:1CD[CD]|DCD[CD])\s*,\s*"
    r"(?:0x17|0xFF|23|255)\s*\)", re.IGNORECASE)
# Probes whose source text is pinned by tests/ assertions; converting them is
# a production-path change batched with its test updates (#37/#41 follow-up).
PENDING = {
    "scripts/diagnostics/probe_generate_boss_state.lua":
        "pinned by tests/test_star_boss_profile.py source assertion",
    "scripts/diagnostics/probe_low_health_flicker.lua":
        "pinned by tests/test_low_health_scene0b_gate.py source assertion",
    "scripts/diagnostics/probe_stage1_death_continue_chr_reload.lua":
        "pinned by tests/test_stage1_death_continue_chr_reload.py and "
        "verify_stage1_death_continue_chr_reload.py source assertions",
    "scripts/diagnostics/verify_stage1_death_continue_chr_reload.py":
        "source-snippet check for the pending death/continue probe above",
}
SELF = Path(__file__).resolve()


def scan_text(text: str) -> list[dict]:
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("--") or stripped.startswith("#"):
            continue
        for match in MAPPED.finditer(line):
            findings.append({"line": number, "kind": "mapped-bank-write",
                             "address": match.group(1).upper()})
        for match in FAKE_HEALTH.finditer(line):
            findings.append({"line": number, "kind": "fake-health-cursor-write",
                             "text": match.group(0)})
    return findings


def scan(root: Path = ROOT) -> dict:
    files, failures, pending = 0, {}, {}
    for directory in SCAN_DIRS:
        for path in sorted((root / directory).glob("*")):
            if path.suffix not in {".lua", ".py"} or path.resolve() == SELF:
                continue
            files += 1
            rel = str(path.relative_to(root))
            findings = scan_text(path.read_text(errors="ignore"))
            if not findings:
                continue
            (pending if rel in PENDING else failures)[rel] = findings
    stale = sorted(rel for rel in PENDING if rel not in pending)
    return {
        "schema": "penta-physical-assistance-inventory-v1",
        "files_scanned": files,
        "failures": failures,
        "pending": {rel: {"reason": PENDING[rel], "findings": pending[rel]}
                    for rel in sorted(pending)},
        "stale_pending_entries": stale,
        "status": "pass" if not failures and not stale else "fail",
    }


def self_test() -> None:
    assert scan_text("  emu:write8(0xDCBB, 0xFF)\n")[0]["kind"] == "mapped-bank-write"
    assert scan_text("emu:write8(0xdcfd,1)")[0]["address"] == "DCFD"
    kinds = {f["kind"] for f in scan_text(
        "native_assistance.write(0xDCDD, 0x17)\nwram:write8(0x1CDC,255)")}
    assert kinds == {"fake-health-cursor-write"}, kinds
    assert not scan_text("native_assistance.write(0xDCBB, 0xFF)")
    assert not scan_text("native_assistance.write(0xDCDD, 0)")  # declared setup
    assert not scan_text("emu:write8(0xFF70, 1)")
    assert not scan_text("-- emu:write8(0xDCDD, 0x17) historical note")
    print("PASS: physical-assistance scanner rejects mapped and fake-health writes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    self_test()
    if args.self_test:
        return 0
    result = scan()
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.json:
        args.json.write_text(text + "\n")
    print(text if result["status"] != "pass" else
          f"PASS: {result['files_scanned']} probe sources; no mapped native "
          f"assistance writes; {len(result['pending'])} pending test-pinned files")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
