#!/usr/bin/env python3
"""Compare OG/DX boss-arena main-loop throughput.

WHY THIS EXISTS
---------------
``verify_boss_publication_cadence.py`` is the only boss-side speed check, and
it is not a speed instrument. It measures the frame gap between native 24x24
map publications -- a game-logic *event rate*, not CPU cost. Its receipts in
``tmp/boss-2pct/`` report physically impossible speedups (angela -24.06%,
cameo -22.22%, ted -14.47%) and change with the observation window for one
unchanged ROM (crystal +2.156% at 1800 frames vs +4.432% at 3600).

``verify_stage_speed_matrix.py`` instead counts executions of the main loop.
Fewer iterations across the same emulated frames means the game genuinely got
less work done. That gate is what caught the real regression (Stage 1 0.943,
Stage 5 0.939, Stage 7 0.850). No boss probe had ever used that instrument;
this one does, over the existing boss arena state pairs.

The dungeon anchor ``$016C`` never executes inside arenas (measured: 599
arena frames, zero hits). Arenas park inside ``1A6F: CALL 4000`` with bank 2
mapped and iterate the loop headed at bank2:``$406F`` (``$4083`` increments
the FFCD phase counter once per iteration; ~5.3 frames/iteration, matching
the publication cadence's mean gap). That is the anchor used here, filtered
on the FF99 bank shadow reading $02, with the unfiltered count retained in
the trace so a filter mismatch cannot hide.

Emitted ratio is DX/OG main-loop iterations **per observed scene frame**, so a
run that holds the arena for a different number of frames than its counterpart
cannot bias the comparison.

This tool is additive. It does not modify or replace the cadence gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from boss_geometry_contract import BOSSES

SCHEMA = "penta-boss-speed-parity-v1"
ROOT = Path(__file__).resolve().parents[2]
MGBA = ROOT / "scripts" / "mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_boss_speed_parity.lua")
DEFAULT_ORIGINAL = ROOT / "rom/Penta Dragon (J).gb"
DEFAULT_MAX_SLOWDOWN = 0.02

COMPLETE = re.compile(
    r"complete status=(?P<status>\S+) frames=(?P<frames>\d+) "
    r"scene_frames=(?P<scene_frames>\d+) "
    r"main_loop_hits=(?P<hits>\d+) "
    r"raw_anchor_hits=(?P<raw_hits>\d+) "
    r"max_main_loop_gap=(?P<max_gap>\d+) "
    r"last_main_loop_frame=(?P<last>-?\d+) scene=(?P<scene>[0-9A-F]{2})"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state_for(directory: Path, target: int) -> Path:
    matches = sorted(
        path for path in directory.glob(f"boss{target}_*.ss0")
        if ".failed." not in path.name and ".candidate." not in path.name
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one state for boss {target} in {directory}, "
            f"found {len(matches)}"
        )
    return matches[0]


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def capture(
    rom: Path,
    state: Path,
    prefix: Path,
    target: int,
    warmup: int,
    frames: int,
    timeout: float,
) -> dict[str, object]:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    marker = Path(str(prefix) + ".done")
    trace = Path(str(prefix) + ".trace")
    marker.unlink(missing_ok=True)
    trace.unlink(missing_ok=True)
    rom_bytes = rom.read_bytes()
    env = os.environ.copy()
    env.update(
        BOSS_SPEED_OUT=str(prefix),
        BOSS_SPEED_SCENE=str(BOSSES[target].scene),
        BOSS_SPEED_WARMUP=str(warmup),
        BOSS_SPEED_FRAMES=str(frames),
        # Same banked-writer sniff as verify_boss_publication_cadence.py: only
        # those candidates park SVBK on 2/3 across frame boundaries. The stock
        # DMG ROM reads FF70=$FF, so the guard must stay off there.
        BOSS_SPEED_BANKED_WRITER=(
            "1" if (
                rom_bytes[0x3136:0x3139] == bytes.fromhex("C3 38 08")
                or rom_bytes[0x028A:0x028D] == bytes.fromhex("CD 80 DB")
                or rom_bytes[0x028A:0x028D] == bytes.fromhex("CD E4 6F")
                or rom_bytes[0x028A:0x028D] == bytes.fromhex("CD 87 DB")
            )
            else "0"
        ),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    process = subprocess.Popen(
        [
            str(MGBA), "--fastforward", "-t", str(state),
            "-C", f"savegamePath={prefix.parent}",
            "-C", f"savestatePath={prefix.parent}",
            str(rom), "--script", str(PROBE),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker.is_file() and marker.read_text().strip():
                break
            if process.poll() is not None:
                raise RuntimeError(f"mGBA exited {process.returncode}")
            time.sleep(0.05)
        else:
            raise TimeoutError(f"boss speed probe timed out: {prefix.name}")
    finally:
        terminate(process)

    match = None
    for line in trace.read_text().splitlines():
        found = COMPLETE.fullmatch(line.strip())
        if found:
            match = found
    if match is None:
        raise RuntimeError(f"no completion record for {prefix.name}")
    status = match.group("status")
    if status not in {"ok", "scene-exit"}:
        raise RuntimeError(f"boss speed probe rejected {prefix.name}: {status}")
    scene_frames = int(match.group("scene_frames"))
    hits = int(match.group("hits"))
    if scene_frames <= 0:
        raise RuntimeError(f"no arena frames observed for {prefix.name}")
    # A main loop that never ran is a broken capture, not a 100% slowdown.
    if hits <= 0:
        raise RuntimeError(f"no main-loop iterations observed for {prefix.name}")
    raw_hits = int(match.group("raw_hits"))
    if raw_hits != hits:
        raise RuntimeError(
            f"anchor bank filter dropped hits for {prefix.name}: "
            f"raw {raw_hits} vs filtered {hits} -- foreign-bank code executes "
            "at the anchor address, the count cannot be trusted"
        )
    return {
        "status": status,
        "scene_frames": scene_frames,
        "main_loop_hits": hits,
        "raw_anchor_hits": raw_hits,
        "hits_per_scene_frame": hits / scene_frames,
        "max_main_loop_gap": int(match.group("max_gap")),
        "state_sha256": sha256(state),
        "trace_sha256": sha256(trace),
        "trace": str(trace.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dx_rom", type=Path)
    parser.add_argument("--original", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--dx-states", type=Path, required=True)
    parser.add_argument("--og-states", type=Path, required=True)
    parser.add_argument("--target", action="append", type=int, choices=range(9))
    parser.add_argument("--warmup", type=int, default=60)
    parser.add_argument("--frames", type=int, default=1800)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--max-slowdown",
        type=float,
        default=DEFAULT_MAX_SLOWDOWN,
        help=(
            "maximum absolute DX/OG throughput deviation (default: 0.02). A "
            "speedup fails too: it means the runs diverged."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dx_rom = args.dx_rom.resolve()
    original = args.original.resolve()
    targets = args.target or list(range(9))
    rows: list[dict[str, object]] = []
    failures: list[str] = []

    for target in targets:
        name = BOSSES[target].name
        pair: dict[str, object] = {"boss": name, "scene": f"{BOSSES[target].scene:02X}"}
        try:
            for side, rom, states in (
                ("og", original, args.og_states.resolve()),
                ("dx", dx_rom, args.dx_states.resolve()),
            ):
                pair[side] = capture(
                    rom,
                    state_for(states, target),
                    args.output.parent / "boss-speed" / name / side,
                    target,
                    args.warmup,
                    args.frames,
                    args.timeout,
                )
        except Exception as error:  # noqa: BLE001 - reported per boss
            pair["status"] = "error"
            pair["error"] = str(error)
            failures.append(f"{name}: {error}")
            rows.append(pair)
            continue

        og_rate = pair["og"]["hits_per_scene_frame"]
        dx_rate = pair["dx"]["hits_per_scene_frame"]
        ratio = dx_rate / og_rate
        within = abs(1.0 - ratio) <= args.max_slowdown + 1e-9
        pair["speed_ratio"] = ratio
        pair["slowdown_percent"] = (1.0 - ratio) * 100.0
        pair["maximum_slowdown_percent"] = args.max_slowdown * 100.0
        pair["status"] = "pass" if within else "fail"
        if not within:
            failures.append(
                f"{name}: DX/OG main-loop throughput {ratio:.4f}, "
                f"slowdown {(1 - ratio) * 100:.2f}% "
                f"(absolute limit {args.max_slowdown * 100:.2f}%)"
            )
        rows.append(pair)
        print(
            f"{name:16s} og={og_rate:7.3f} dx={dx_rate:7.3f} "
            f"ratio={ratio:.3f} slowdown={(1 - ratio) * 100:+6.2f}% "
            f"{'PASS' if within else 'FAIL'}"
        )

    receipt = {
        "schema": SCHEMA,
        "status": "pass" if not failures else "fail",
        "instrument": (
            "arena-loop iterations at bank2:$406F (FF99==$02 filtered) "
            "per observed arena frame"
        ),
        "warmup_frames": args.warmup,
        "observation_frames": args.frames,
        "maximum_slowdown_percent": args.max_slowdown * 100.0,
        "original_rom_sha256": sha256(original),
        "dx_rom_sha256": sha256(dx_rom),
        "bosses": rows,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
    print(f"Receipt: {args.output}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
