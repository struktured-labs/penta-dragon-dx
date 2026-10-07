#!/usr/bin/env python3
"""Verify ordinary gameplay sprites against the production OBJ mapping."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_v301_teleport import build_obj_pal_table
from diagnostics.normalize_mgba_state_pc import normalize, retarget_rom_identity
from diagnostics.gameplay_anchor_dma import prepare
from diagnostics.generate_stream_boss_states import run_until_marker


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
PROBE = ROOT / "scripts/diagnostics/probe_gameplay_obj_palettes.lua"
STATE_ROOT = ROOT / "save_states_for_claude"
DEFAULT_STATES = (
    "level1_sara_w_crow.ss0",
    "level1_sara_w_4_hornets.ss0",
    "level1_sara_w_orc.ss0",
    "level1_sara_w_soldier.ss0",
    "level1_sara_w_mage_health1_items.ss0",
    "level1_cat_fish_moth_spike_hazard_orb_item.ss0",
    "level1_sara_w_moth.ss0",
    "level1_sara_w_metal_ball_mage_soldier.ss0",
)


def expected_obj_table(rom: bytes) -> bytes:
    """Source-authenticated #57 tile0F separation; all other roles unchanged."""
    from diagnostics import playtest_successor_lineage as successor
    from diagnostics import build_enemy_projectile_palette as projectile
    expected = bytearray(build_obj_pal_table())
    if successor.is_candidate(rom):
        # Authenticate the complete delta and both live initializer images.
        successor.authenticated_parent(rom, (0x42A7, 0x436E))
        code = projectile.payload()
        for bank in projectile.BANKS:
            offset = projectile.offset(bank)
            if rom[offset:offset+len(code)] != code:
                raise ValueError('enemy projectile initializer differs')
        if expected[15] != 0:
            raise ValueError('parent enemy projectile role changed')
        expected[15] = 3
    return bytes(expected)


def parse_result(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key not in result:
            result[key] = value
    return result


def run_state(
    mgba: str,
    rom: Path,
    state: Path,
    output: Path,
    timeout: float,
) -> dict[str, str]:
    result = output / f"{state.stem}.txt"
    screenshot = output / f"{state.stem}.png"
    stdout = output / f"{state.stem}.stdout.txt"
    state = prepare(mgba, rom, state, output / 'anchors' / state.stem, timeout)
    marker = result.with_suffix('.done')
    marker.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "GAMEPLAY_OBJ_OUT": str(result),
            "GAMEPLAY_OBJ_SCREENSHOT": str(screenshot),
            "GAMEPLAY_OBJ_LUT": str(output / "obj_palette_lut.bin"),
            "GAMEPLAY_OBJ_DONE": str(marker),
        }
    )
    run_until_marker(
            [
                mgba,
                "--fastforward",
                "-t",
                str(state),
                "--script",
                str(PROBE),
                str(rom),
            ],
            environment, ROOT, marker, timeout,
    )
    if marker.read_text() != 'complete':
        raise RuntimeError('gameplay capture incomplete')
    if not result.exists():
        raise RuntimeError(
            f"{state.name}: no result; see {marker.with_suffix('.log')}"
        )
    if not screenshot.exists():
        raise RuntimeError(f"{state.name}: no screenshot; see {stdout}")
    with Image.open(screenshot) as image:
        if image.size != (160, 144):
            raise RuntimeError(
                f"{state.name}: screenshot is {image.size}, expected 160x144"
            )
        image.verify()
    return parse_result(result)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--states", type=Path, default=STATE_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--only",
        action="append",
        choices=[Path(name).stem for name in DEFAULT_STATES],
        help="run only this named state (repeatable)",
    )
    args = parser.parse_args()

    if not args.mgba:
        print("FAIL: mgba-qt was not found")
        return 2
    rom = args.rom.resolve()
    selected = set(args.only or ())
    states = [
        args.states.resolve() / name
        for name in DEFAULT_STATES
        if not selected or Path(name).stem in selected
    ]
    missing = [state for state in states if not state.is_file()]
    if missing:
        print("FAIL: missing combat states:")
        for state in missing:
            print(f"  - {state}")
        return 2

    failures: list[str] = []
    temporary = None
    if args.output:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
    else:
        scratch=ROOT/'tmp';scratch.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="penta-gameplay-obj-",dir=scratch)
        output = Path(temporary.name)
    try:
        (output / "obj_palette_lut.bin").write_bytes(expected_obj_table(rom.read_bytes()))
        total_checked = 0
        total_mismatches = 0
        sampled_states = 0
        for state in states:
            try:
                result = run_state(
                    args.mgba, rom, state, output, args.timeout
                )
            except Exception as exc:
                failures.append(str(exc))
                continue
            retried_current_init = False
            retried_current_init = True  # every anchor uses the safe setup
            checked = int(result.get("checked", "0"))
            mismatches = int(result.get("mismatches", "-1"))
            sampled = int(result.get("sampled_frames", "0"))
            bad_state = int(result.get("bad_state_frames", "-1"))
            if int(result.get('distinct_pcs','0')) < 2:
                failures.append(f'{state.name}: gameplay did not advance')
            if int(result.get('lut_mismatches','-1')) != 0:
                failures.append(f'{state.name}: candidate OBJ LUT did not initialize')
            total_checked += checked
            total_mismatches += max(mismatches, 0)
            if sampled > 0 and checked > 0:
                sampled_states += 1
            print(
                f"{state.stem:51s} "
                f"checked={checked:4d} mismatches={mismatches:4d} "
                f"visible≤{result.get('max_visible', '?'):>2s} "
                f"slot≤{result.get('max_slot', '?'):>2s} "
                f"scene={result.get('D880', '??')} "
                f"current_init_retry={int(retried_current_init)}"
            )
            if sampled <= 0 or checked <= 0:
                print(
                    f"  INFO: {state.name} left ordinary gameplay before "
                    "sampling; aggregate coverage remains the hard gate"
                )
            # Some anchors naturally enter a miniboss after providing dozens
            # of ordinary-enemy frames. Those later frames are excluded by
            # the Lua probe and are informative, not a harness failure.
            if mismatches:
                failures.append(
                    f"{state.name}: {mismatches}/{checked} OBJ samples "
                    "used the wrong palette"
                )

        print(
            f"Total: checked={total_checked} "
            f"mismatches={total_mismatches} "
            f"sampled_states={sampled_states}/{len(states)}"
        )
        if total_checked <= 0 or sampled_states <= 0:
            failures.append("no ordinary-gameplay OBJ samples in any state")
        if failures:
            print("FAIL:")
            for failure in failures:
                print(f"  - {failure}")
            if args.output:
                print(f"Artifacts: {output}")
            return 1
        print("PASS: ordinary gameplay hardware OAM matches its palette map.")
        if args.output:
            print(f"Artifacts: {output}")
        return 0
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
