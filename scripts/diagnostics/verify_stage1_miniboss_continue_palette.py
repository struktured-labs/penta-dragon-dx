#!/usr/bin/env python3
"""Stage-1 Continue restores BG palettes, with and without a live miniboss.

Two cold-boot runs go through the fail-closed single-flight launcher:

* ``miniboss``: the native Gargoyle spawns (FFBF=01, scene $0A). Sara dies
  with one credit and Continue is accepted with native A. The game must resume
  in scene $0A with the miniboss alive. All 64 BG CRAM bytes at resume+30,
  +60 and +300 frames must equal the pre-death fight CRAM. Regression: the
  792319cb release lock kept the death/white-fade palettes (flat pink room and
  HUD) until the miniboss died.
* ``control``: the same route without a miniboss resumes in scene $02 with
  the same CRAM equality (unchanged behaviour).

Both runs also require that no CRAM data write (FF69/FF6B) from the death
through resume+300 lands in PPU mode 3, where hardware drops it (the stale
pal4 colour-3 / #28 "4A29" byte).

Assistance is memory-only and declared in the probe header (spawn pulses,
keepalive, one credit, lethal HP). Emulator evidence only, never hardware
qualification.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
PROBE = SELF.parent / "probe_stage1_miniboss_continue_palette.lua"
LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"
SCHEMA = "penta-stage1-miniboss-continue-palette-v1"
CASES = {"miniboss": dict(scene=0x0A, boss=True), "control": dict(scene=0x02, boss=False)}
SAMPLES = ("resume+30", "resume+60", "resume+300")


class GateError(RuntimeError):
    pass


def evaluate(case: str, events: list[dict]) -> dict:
    """Pure acceptance logic over the probe's event stream."""
    expect = CASES[case]
    kinds = [e["kind"] for e in events]
    for required in ("gameplay", "stimulus", "death", "resume", "done"):
        if required not in kinds:
            raise GateError(f"{case}: probe never reached {required!r} (events {kinds})")
    crams = {e["tag"]: e for e in events if e["kind"] == "cram"}
    if "pre-death" not in crams or any(tag not in crams for tag in SAMPLES):
        raise GateError(f"{case}: missing CRAM samples {sorted(crams)}")
    pre = crams["pre-death"]
    if expect["boss"]:
        spawn = [e for e in events if e["kind"] == "miniboss"]
        if not spawn or spawn[0]["ffbf"] == 0 or pre["scene"] != 0x0A or pre["ffbf"] == 0:
            raise GateError(f"{case}: native miniboss fight (scene $0A) not reached before the death")
    elif pre["scene"] != 0x02 or pre["ffbf"] != 0:
        raise GateError(f"{case}: control was not in plain scene $02 before the death")
    resume = next(e for e in events if e["kind"] == "resume")
    if resume["scene"] != expect["scene"] or bool(resume["ffbf"]) != expect["boss"]:
        raise GateError(f"{case}: resumed scene {resume['scene']:#04x} ffbf {resume['ffbf']:#04x}")
    reference = crams["pre-death"]["bg"]
    if len(reference) != 128 or reference.upper().count("FF") == 64:
        raise GateError(f"{case}: implausible pre-death BG CRAM")
    mismatches = {}
    for tag in SAMPLES:
        observed = crams[tag]["bg"]
        if observed != reference:
            mismatches[tag] = [i for i in range(64) if observed[2 * i:2 * i + 2] != reference[2 * i:2 * i + 2]]
    if mismatches:
        raise GateError(f"{case}: BG CRAM after Continue differs from pre-death at {mismatches}")
    mode3 = [e for e in events if e["kind"] == "mode3_write"]
    if mode3:
        raise GateError(f"{case}: {len(mode3)} CRAM write(s) in PPU mode 3, first {mode3[0]}")
    done = next(e for e in events if e["kind"] == "done")
    return dict(case=case, resume_scene=resume["scene"], resume_ffbf=resume["ffbf"],
                death_frame=next(e for e in events if e["kind"] == "death")["frame"],
                resume_frame=resume["frame"], bg_cram=reference,
                cram_writes_checked=done["cram_writes"], status="pass")


def run_case(rom: Path, case: str, output: Path, timeout: float) -> list[dict]:
    work = output / case
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copyfile(rom, work / "rom.gb")
    shutil.copyfile(PROBE, work / "probe.lua")
    environment = dict(os.environ)
    for name in ("PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN"):
        environment.pop(name, None)
    environment.update(PMC_OUT=str(work), PMC_CASE=case,
                       QT_QPA_PLATFORM=environment.get("QT_QPA_PLATFORM", "offscreen"),
                       SDL_AUDIODRIVER="dummy")
    command = [str(LAUNCHER), "--fastforward", "--script", str(work / "probe.lua"), str(work / "rom.gb")]
    with (work / "emulator.log").open("w") as log:
        try:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            raise GateError(f"{case}: emulator timed out") from error
    if result.returncode == 75:
        raise GateError("single-flight emulator lock is busy")
    events_path = work / "events.jsonl"
    if not events_path.is_file():
        raise GateError(f"{case}: probe produced no events (exit {result.returncode})")
    return [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = dict(schema=SCHEMA, rom=str(args.rom.resolve()), cases=[], status="fail")
    try:
        for case in CASES:
            report["cases"].append(evaluate(case, run_case(args.rom.resolve(), case,
                                                           args.output, args.timeout)))
        report["status"] = "pass"
    except GateError as error:
        report["error"] = str(error)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if report["status"] != "pass":
        print(f"FAIL: {report['error']}")
        return 1
    print("PASS: Continue restores pre-death BG CRAM with and without a miniboss; "
          "no CRAM write in mode 3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
