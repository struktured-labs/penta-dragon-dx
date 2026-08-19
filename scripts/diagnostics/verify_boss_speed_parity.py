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
    r"last_main_loop_frame=(?P<last>-?\d+) "
    r"parked_frames=(?P<parked>\d+) scene=(?P<scene>[0-9A-F]{2})"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accepted_slow_boss(value: str) -> tuple[str, float]:
    try:
        name, raw_floor = value.rsplit("=", 1)
        floor = float(raw_floor)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "accepted slow boss must be NAME=MINIMUM_RATIO"
        ) from error
    if not name or not 0 < floor < 1:
        raise argparse.ArgumentTypeError(
            "accepted slow boss floor must be between zero and one"
        )
    return name, floor


def classify_throughput(
    boss: str,
    ratio: float,
    target_tolerance: float,
    accepted_slow_bosses: dict[str, float],
    bounded_speedup_ceiling: float | None,
) -> dict[str, object]:
    """Keep the parity target visible while applying one-sided policy."""

    target_met = abs(1.0 - ratio) <= target_tolerance + 1e-9
    slow_floor = accepted_slow_bosses.get(boss)
    accepted_slowdown = (
        not target_met
        and ratio < 1.0
        and slow_floor is not None
        and ratio >= slow_floor - 1e-9
    )
    accepted_speedup = (
        not target_met
        and ratio > 1.0
        and bounded_speedup_ceiling is not None
        and ratio <= bounded_speedup_ceiling + 1e-9
    )
    policy = (
        "within_target" if target_met
        else "accepted_operator_slowdown" if accepted_slowdown
        else "accepted_bounded_speedup" if accepted_speedup
        else "rejected"
    )
    return {
        "target_met": target_met,
        "accepted_slowdown_deviation": accepted_slowdown,
        "accepted_slowdown_floor": slow_floor,
        "accepted_bounded_speedup": accepted_speedup,
        "acceptance_policy": policy,
        "throughput_accepted": (
            target_met or accepted_slowdown or accepted_speedup
        ),
    }


def throughput_policy_controls() -> dict[str, bool]:
    accepted_slow = {"crystal_dragon": 0.95}
    classify = lambda boss, ratio: classify_throughput(
        boss, ratio, 0.02, accepted_slow, 1.20
    )
    return {
        "target_center_passes": classify("ted", 1.0)["throughput_accepted"],
        "ted_one_percent_slow_meets_target": classify("ted", 0.99)[
            "target_met"
        ],
        "unlisted_boss_three_percent_slow_rejected": not classify(
            "ted", 0.97
        )["throughput_accepted"],
        "crystal_three_percent_slow_accepted": classify(
            "crystal_dragon", 0.97
        )["accepted_slowdown_deviation"],
        "crystal_below_floor_rejected": not classify(
            "crystal_dragon", 0.949
        )["throughput_accepted"],
        "bounded_speedup_accepted": classify("cameo", 1.16)[
            "accepted_bounded_speedup"
        ],
        "excessive_speedup_rejected": not classify("cameo", 1.201)[
            "throughput_accepted"
        ],
    }


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
    # Sticky scene accounting (the probe) keeps SVBK-parked mid-scene frames
    # in the denominator; parked_frames records how many there were. Without
    # it, the parked share silently deflated scene_frames on banked-writer
    # candidates and inflated this rate by 1/(1-share) -- the "+22.46%
    # faster" Ted artifact was exactly that (share ~20.1%).
    return {
        "status": status,
        "scene_frames": scene_frames,
        "main_loop_hits": hits,
        "raw_anchor_hits": raw_hits,
        "hits_per_scene_frame": hits / scene_frames,
        "max_main_loop_gap": int(match.group("max_gap")),
        "last_main_loop_frame": int(match.group("last")),
        "parked_frames": int(match.group("parked")),
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
    parser.add_argument(
        "--accepted-slow-boss",
        action="append",
        type=accepted_slow_boss,
        default=[],
        metavar="NAME=MINIMUM_RATIO",
        help=(
            "operator-approved boss-specific slowdown floor; the parity "
            "target miss remains visible"
        ),
    )
    parser.add_argument(
        "--bounded-speedup-ceiling",
        "--phase-mismatch-speedup-ceiling",
        dest="bounded_speedup_ceiling",
        type=float,
        default=None,
        help=(
            "one-sided operator-policy ceiling for faster arena-loop "
            "throughput; does not excuse any slowdown"
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.max_slowdown < 0 or args.max_slowdown >= 1:
        parser.error("max slowdown must be in [0, 1)")
    accepted_slow_bosses = dict(args.accepted_slow_boss)
    if len(accepted_slow_bosses) != len(args.accepted_slow_boss):
        parser.error("accepted slow boss names must be unique")
    known_bosses = {boss.name for boss in BOSSES}
    unknown_bosses = set(accepted_slow_bosses) - known_bosses
    if unknown_bosses:
        parser.error(
            "unknown accepted slow boss: " + ", ".join(sorted(unknown_bosses))
        )
    if any(
        floor > 1.0 - args.max_slowdown
        for floor in accepted_slow_bosses.values()
    ):
        parser.error(
            "accepted slow boss floors must not overlap the parity target"
        )
    if (
        args.bounded_speedup_ceiling is not None
        and args.bounded_speedup_ceiling < 1.0 + args.max_slowdown
    ):
        parser.error(
            "bounded speedup ceiling must be at or above the target "
            "envelope"
        )

    dx_rom = args.dx_rom.resolve()
    original = args.original.resolve()
    targets = args.target or list(range(9))
    rows: list[dict[str, object]] = []
    failures: list[str] = []
    policy_controls = throughput_policy_controls()
    if not all(policy_controls.values()):
        failures.append("internal throughput policy controls failed")

    for target in targets:
        name = BOSSES[target].name
        pair: dict[str, object] = {"boss": name, "scene": f"{BOSSES[target].scene:02X}"}
        try:
            for side, rom, states in (
                ("og", original, args.og_states.resolve()),
                ("dx", dx_rom, args.dx_states.resolve()),
            ):
                state = state_for(states, target)
                replays = [
                    capture(
                        rom,
                        state,
                        args.output.parent / "boss-speed" / name
                            / f"{side}-{replay}",
                        target,
                        args.warmup,
                        args.frames,
                        args.timeout,
                    )
                    for replay in ("a", "b")
                ]
                deterministic_keys = (
                    "status", "scene_frames", "main_loop_hits",
                    "raw_anchor_hits", "hits_per_scene_frame",
                    "max_main_loop_gap", "parked_frames", "state_sha256",
                )
                # A restored-state run can enter the first host frame callback
                # one frame earlier or later.  Cameo exposed this only in the
                # terminal label (2398 vs 2397): counts, scene denominator,
                # maximum gap, parked frames, and the entire measured rate
                # were identical. Treat a <=1 terminal-boundary shift as the
                # host callback phase it is, while every gameplay quantity
                # remains exact and continuity is still gated below.
                terminal_frame_delta = abs(
                    replays[0]["last_main_loop_frame"]
                    - replays[1]["last_main_loop_frame"]
                )
                deterministic = terminal_frame_delta <= 1 and all(
                    replays[0][key] == replays[1][key]
                    for key in deterministic_keys
                )
                if not deterministic:
                    raise RuntimeError(
                        f"non-deterministic {side} replay for {name}"
                    )
                pair[side] = dict(replays[0])
                pair[side]["deterministic_replay"] = True
                pair[side]["replay_trace_sha256"] = [
                    replay["trace_sha256"] for replay in replays
                ]
                pair[side]["replay_last_main_loop_frame"] = [
                    replay["last_main_loop_frame"] for replay in replays
                ]
                pair[side]["terminal_frame_delta"] = terminal_frame_delta
        except Exception as error:  # noqa: BLE001 - reported per boss
            pair["status"] = "error"
            pair["error"] = str(error)
            failures.append(f"{name}: {error}")
            rows.append(pair)
            continue

        og_rate = pair["og"]["hits_per_scene_frame"]
        dx_rate = pair["dx"]["hits_per_scene_frame"]
        ratio = dx_rate / og_rate
        throughput = classify_throughput(
            name,
            ratio,
            args.max_slowdown,
            accepted_slow_bosses,
            args.bounded_speedup_ceiling,
        )
        maximum_continuity_gap = 30
        continuity = {
            side: (
                pair[side]["max_main_loop_gap"] <= maximum_continuity_gap
                and pair[side]["last_main_loop_frame"]
                    >= pair[side]["scene_frames"] - maximum_continuity_gap
            )
            for side in ("og", "dx")
        }
        within = throughput["throughput_accepted"] and all(continuity.values())
        pair["speed_ratio"] = ratio
        pair.update(throughput)
        pair["slowdown_percent"] = (1.0 - ratio) * 100.0
        # Deficit framing (above) is the gate's historical convention; the
        # trajectory instrument reports frames-per-iteration framing. They
        # diverge with magnitude (27.68% deficit == 38.3% fpi), so publish
        # both to keep cross-instrument comparisons in one convention.
        pair["slowdown_percent_fpi"] = (1.0 / ratio - 1.0) * 100.0
        pair["maximum_slowdown_percent"] = args.max_slowdown * 100.0
        pair["maximum_continuity_gap"] = maximum_continuity_gap
        pair["continuity"] = continuity
        pair["status"] = "pass" if within else "fail"
        if not within:
            reason = (
                f"DX/OG main-loop throughput {ratio:.4f}, "
                f"slowdown {(1 - ratio) * 100:.2f}% "
                f"(absolute limit {args.max_slowdown * 100:.2f}%)"
            )
            if not all(continuity.values()):
                reason += f", continuity={continuity}"
            failures.append(f"{name}: {reason}")
        rows.append(pair)
        print(
            f"{name:16s} og={og_rate:7.3f} dx={dx_rate:7.3f} "
            f"ratio={ratio:.3f} slowdown={(1 - ratio) * 100:+6.2f}% "
            f"target={'PASS' if throughput['target_met'] else 'MISS'} "
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
        "accepted_slow_bosses": accepted_slow_bosses,
        "bounded_speedup_ceiling": args.bounded_speedup_ceiling,
        "policy_controls": policy_controls,
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
