#!/usr/bin/env python3
"""Verify Crystal Dragon's scene-local frost/ghost OBJ palette contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import yaml

from normalize_mgba_state_pc import normalize


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
PROBE = ROOT / "scripts/diagnostics/probe_crystal_flicker.lua"
BANK13 = 13 * 0x4000


def rom_offset(address: int) -> int:
    return BANK13 + address - 0x4000


def parse_trace(path: Path) -> list[tuple[int, bytes, bytes]]:
    rows: list[tuple[int, bytes, bytes]] = []
    for line in path.read_text().splitlines():
        if not line.startswith("frame="):
            continue
        frame_match = re.search(r"frame=(\d+)", line)
        oam_match = re.search(r" oam=([0-9A-F]+)", line)
        obj_match = re.search(r" obj=([0-9A-F]+)", line)
        if frame_match and oam_match and obj_match:
            rows.append((
                int(frame_match.group(1)),
                bytes.fromhex(oam_match.group(1)),
                bytes.fromhex(obj_match.group(1)),
            ))
    return rows


def run_probe(
    mgba: Path,
    rom: Path,
    state: Path,
    output: Path,
    scene: int,
    frames: int,
    timeout: float,
) -> list[tuple[int, bytes, bytes]]:
    env = os.environ.copy()
    env.update({
        "CRYSTAL_FLICKER_OUT": str(output),
        "CRYSTAL_FLICKER_FRAMES": str(frames),
        "CRYSTAL_FLICKER_EXPECTED_SCENE": str(scene),
        "CRYSTAL_FLICKER_RELOAD_MATERIAL": "1",
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
    })
    marker = output.with_suffix(".done")
    process = subprocess.Popen(
        [
            str(mgba), "--fastforward", "-t", str(state),
            "-C", f"savegamePath={output.parent}",
            "-C", f"savestatePath={output.parent}",
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
                raise RuntimeError(
                    f"mGBA exited {process.returncode} before {marker.name}"
                )
            time.sleep(0.05)
        else:
            raise TimeoutError(f"timed out waiting for {marker.name}")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    assert marker.read_text().strip() == "ok", marker.read_text().strip()
    rows = parse_trace(output.with_suffix(".trace"))
    assert len(rows) == frames, f"expected {frames} trace rows, got {len(rows)}"
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument(
        "--stage3-state",
        type=Path,
        default=ROOT / "tmp/palette_session/states/stage3.ss0",
        help="ordinary Stage 3 fixture used as the same-index isolation control",
    )
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--frames", type=int, default=720)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    rom = args.rom.resolve().read_bytes()
    palette_path = ROOT / "palettes/penta_palettes_v097.yaml"
    document = yaml.safe_load(palette_path.read_text())

    from scripts.build_v302_title_fix import (
        CRYSTAL_PALETTE_REARM_ADDR,
        PALETTE_LOADER_ADDR,
        TITLE_TRANSITION_SERVICE_ADDR,
        build_crystal_palette_rearm,
        build_phased_palette_loader,
        build_title_transition_service,
        load_crystal_obj_palette_override,
        load_palettes_from_yaml,
    )

    scene, slots, source_addr, source_name = load_crystal_obj_palette_override(
        palette_path
    )
    source_colors = document["boss_palettes"][source_name]["colors"]
    source_bytes = b"".join(
        (int(color, 16) & 0x7FFF).to_bytes(2, "little")
        for color in source_colors
    )
    assert rom[rom_offset(source_addr):rom_offset(source_addr) + 8] == source_bytes

    tuned = load_palettes_from_yaml(palette_path)
    base_rows = {
        slot: tuned["obj_data"][slot * 8:(slot + 1) * 8]
        for slot in slots
    }
    assert all(row != source_bytes for row in base_rows.values()), (
        "override must remain distinguishable"
    )
    for slot, base_row in base_rows.items():
        assert rom[
            rom_offset(0x6840 + slot * 8):
            rom_offset(0x6840 + slot * 8) + 8
        ] == base_row

    loader = build_phased_palette_loader(
        crystal_obj_slots=slots,
        crystal_obj_source_addr=source_addr,
        crystal_scene=scene,
    )[0]
    assert rom[rom_offset(PALETTE_LOADER_ADDR):rom_offset(PALETTE_LOADER_ADDR) + len(loader)] == loader
    rearm = build_crystal_palette_rearm()
    assert rom[
        rom_offset(CRYSTAL_PALETTE_REARM_ADDR):
        rom_offset(CRYSTAL_PALETTE_REARM_ADDR) + len(rearm)
    ] == rearm
    transition = build_title_transition_service()
    assert rom[
        rom_offset(TITLE_TRANSITION_SERVICE_ADDR):
        rom_offset(TITLE_TRANSITION_SERVICE_ADDR) + len(transition)
    ] == transition

    crystal_state = args.states / "boss2_crystal_dragon.ss0"
    shalamar_state = args.states / "boss0_shalamar.ss0"
    assert (
        crystal_state.is_file()
        and shalamar_state.is_file()
        and args.stage3_state.is_file()
    )
    with tempfile.TemporaryDirectory(prefix="penta-crystal-ghost-") as temp:
        temp_path = Path(temp)
        crystal_candidate_state = temp_path / "crystal.ss0"
        shalamar_candidate_state = temp_path / "shalamar.ss0"
        stage3_candidate_state = temp_path / "stage3.ss0"
        normalize(
            crystal_state,
            crystal_candidate_state,
            pc=0,
            writes=[],
            rom=args.rom.resolve(),
            preserve_machine=True,
            arena_table=2,
        )
        normalize(
            shalamar_state,
            shalamar_candidate_state,
            pc=0,
            writes=[],
            rom=args.rom.resolve(),
            preserve_machine=True,
            arena_table=0,
        )
        normalize(
            args.stage3_state,
            stage3_candidate_state,
            pc=0,
            writes=[],
            rom=args.rom.resolve(),
            preserve_machine=True,
        )
        crystal_rows = run_probe(
            args.mgba.resolve(), args.rom.resolve(), crystal_candidate_state,
            temp_path / "crystal", scene, args.frames, args.timeout,
        )
        shalamar_rows = run_probe(
            args.mgba.resolve(), args.rom.resolve(), shalamar_candidate_state,
            temp_path / "shalamar", 0x0C, 24, args.timeout,
        )
        stage3_rows = run_probe(
            args.mgba.resolve(), args.rom.resolve(), stage3_candidate_state,
            temp_path / "stage3", 0x04, 24, args.timeout,
        )

    for slot in slots:
        crystal_rows_for_slot = {
            obj[slot * 8:(slot + 1) * 8]
            for frame, _, obj in crystal_rows if frame >= 12
        }
        shalamar_rows_for_slot = {
            obj[slot * 8:(slot + 1) * 8]
            for frame, _, obj in shalamar_rows if frame >= 12
        }
        stage3_rows_for_slot = {
            obj[slot * 8:(slot + 1) * 8]
            for frame, _, obj in stage3_rows if frame >= 12
        }
        assert crystal_rows_for_slot == {source_bytes}, (
            slot, crystal_rows_for_slot
        )
        assert shalamar_rows_for_slot == {base_rows[slot]}, (
            slot, shalamar_rows_for_slot
        )
        assert stage3_rows_for_slot == {base_rows[slot]}, (
            slot, stage3_rows_for_slot
        )

    visibility: list[int] = []
    for _, oam, _ in crystal_rows:
        body_sprites = sum(
            1 for index in range(4, 20)
            if 16 <= oam[index * 4] < 160
            and 8 <= oam[index * 4 + 1] < 168
            and 0x40 <= oam[index * 4 + 2] <= 0x66
        )
        visibility.append(body_sprites)
    assert 0 in visibility and max(visibility) >= 12, (
        "native visible/ghost phase cadence was not exercised"
    )
    settled_visibility = visibility[59:]
    longest_blank_run = 0
    blank_run = 0
    for body_sprites in settled_visibility:
        if body_sprites == 0:
            blank_run += 1
            longest_blank_run = max(longest_blank_run, blank_run)
        else:
            blank_run = 0
    assert longest_blank_run <= 1, (
        "Crystal Dragon body disappeared for "
        f"{longest_blank_run} consecutive settled frames; OG permits one"
    )

    print("PASS: Crystal Dragon ghost palette")
    print(
        f"  scene ${scene:02X}: OBJ{slots[0]}-{slots[-1]} <- "
        f"boss_palettes.{source_name}"
    )
    print(
        f"  Crystal runtime: {args.frames - 11} settled frames held "
        f"{source_bytes.hex().upper()} across all four material slots"
    )
    print(
        f"  native ghost cadence: body sprites {min(visibility)}.."
        f"{max(visibility)}, longest settled blank={longest_blank_run} frame"
    )
    print("  Shalamar isolation: 13 settled frames retained all four base rows")
    print(
        "  Stage 3 isolation: shared FFBA index retained all four base rows "
        "under scene $04"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
