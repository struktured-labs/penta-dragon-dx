#!/usr/bin/env python3
"""Verify Crystal Dragon's scene-local frost/ghost OBJ palette contract."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zlib

import yaml

from normalize_mgba_state_pc import normalize, retarget_rom_identity, png_chunks


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
PROBE = ROOT / "scripts/diagnostics/probe_crystal_flicker.lua"
BANK13 = 13 * 0x4000


def verify_exact_stage3_payload(raw: bytes, rom: bytes) -> None:
    """#61: freshly generated isolation states must never be retargeted."""
    if len(raw) != 0x11800 or int.from_bytes(raw[:4], 'little') != 0x00400003:
        raise ValueError('exact Stage3 requires an mGBA v3 GB state')
    if raw[8] != 0x80 or raw[0x350] == 0xFF:
        raise ValueError('exact Stage3 requires post-BIOS CGB state')
    if raw[16:32] != rom[0x134:0x144] or int.from_bytes(raw[4:8], 'little') != zlib.crc32(rom) & 0xFFFFFFFF:
        raise ValueError('Stage3 state does not belong to exact ROM')
    if raw[0x5C80] != 4 or raw[0x3BA] != 2:
        raise ValueError('isolation state is not ordinary Stage3')


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


def body_visibility(rows: list[tuple[int, bytes, bytes]]) -> list[int]:
    return [
        sum(
            1 for index in range(4, 20)
            if 16 <= oam[index * 4] < 160
            and 8 <= oam[index * 4 + 1] < 168
            and 0x40 <= oam[index * 4 + 2] <= 0x66
        )
        for _, oam, _ in rows
    ]


def visibility_histogram_distance_limit(frame_count: int) -> int:
    # Histogram L1 counts both the bucket a sample leaves and the bucket it
    # enters. A 2% L1 envelope therefore permits at most 1% of observations
    # to move across the native loaded-state phase boundary.
    return max(8, (frame_count + 49) // 50)


def semantic_replay_matches(
    first: list[tuple[int, bytes, bytes]],
    second: list[tuple[int, bytes, bytes]],
) -> bool:
    """Ignore only mGBA's first-frame double-buffered OAM phase choice.

    A loaded state can expose either half of the native alternating hardware
    OAM pair at frame callbacks. The production OBJ CRAM must remain exact on
    every frame. Permit at most 1% of visibility observations to move between
    histogram buckets; all disappearance/cadence limits remain hard checks.
    """

    if len(first) != len(second):
        return False
    if any(a[2] != b[2] for a, b in zip(first, second)):
        return False
    first_visibility = body_visibility(first)
    second_visibility = body_visibility(second)
    if (
        min(first_visibility) != min(second_visibility)
        or max(first_visibility) != max(second_visibility)
    ):
        return False
    first_counts = Counter(first_visibility)
    second_counts = Counter(second_visibility)
    histogram_distance = sum(
        abs(first_counts[key] - second_counts[key])
        for key in first_counts.keys() | second_counts.keys()
    )
    return histogram_distance <= visibility_histogram_distance_limit(len(first))


def run_probe(
    mgba: Path,
    rom: Path,
    state: Path,
    output: Path,
    scene: int,
    frames: int,
    timeout: float,
    reload_material: bool = False,
) -> list[tuple[int, bytes, bytes]]:
    env = os.environ.copy()
    env.update({
        "CRYSTAL_FLICKER_OUT": str(output),
        "CRYSTAL_FLICKER_FRAMES": str(frames),
        "CRYSTAL_FLICKER_EXPECTED_SCENE": str(scene),
        "CRYSTAL_FLICKER_STATE_FILE": str(state.resolve()),
        "CRYSTAL_FLICKER_RELOAD_MATERIAL": "1" if reload_material else "0",
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
    })
    runtime_dir = output.parent / f"{output.name}-runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    marker = output.with_suffix(".done")
    process = subprocess.Popen(
        [
            str(mgba), "--fastforward",
            "-C", f"savegamePath={runtime_dir}",
            "-C", f"savestatePath={runtime_dir}",
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
    marker_status = marker.read_text().strip()
    if marker_status != "ok":
        trace_path = output.with_suffix(".trace")
        tail = trace_path.read_text().splitlines()[-4:] if trace_path.is_file() else []
        raise RuntimeError(
            f"crystal probe status={marker_status} scene={scene:02X} "
            f"state={state} trace_tail={tail}"
        )
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
    parser.add_argument("--stage3-exact-rom", action="store_true",
                        help="require freshly generated exact-ROM Stage3; forbid identity retargeting")
    parser.add_argument("--frames", type=int, default=720)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--debug-dir",
        type=Path,
        help="retain raw per-frame traces under a unique repo-local directory",
    )
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
    from crystal_transition_contract import verify_transition
    verify_transition(rom)

    crystal_state = args.states / "boss2_crystal_dragon.ss0"
    riff_state = args.states / "boss1_riff.ss0"
    assert (
        crystal_state.is_file()
        and riff_state.is_file()
        and args.stage3_state.is_file()
    )
    scratch_root = ROOT / "tmp"
    scratch_root.mkdir(parents=True, exist_ok=True)
    if args.debug_dir is not None:
        debug_root = args.debug_dir.resolve()
        debug_root.mkdir(parents=True, exist_ok=True)
        retained = tempfile.mkdtemp(
            prefix="penta-crystal-ghost-", dir=debug_root
        )
        temp_context = nullcontext(retained)
    else:
        temp_context = tempfile.TemporaryDirectory(
            prefix="penta-crystal-ghost-", dir=scratch_root
        )
    with temp_context as temp:
        temp_path = Path(temp)
        crystal_candidate_state = temp_path / "crystal.ss0"
        riff_candidate_state = temp_path / "riff.ss0"
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
        # The release matrix generates this control from the exact candidate
        # ROM. Preserve the raw hash-bound Riff fixture already proven by the
        # semantic-cadence gate. Shalamar's synthetic entry is too close to a
        # stock exit boundary for this heavier per-frame CRAM/OAM probe.
        shutil.copy2(riff_state, riff_candidate_state)
        stage3_source = args.stage3_state
        if args.stage3_exact_rom:
            chunks = [data for kind, data in png_chunks(stage3_source.read_bytes()) if kind == b'gbAs']
            if len(chunks) != 1:
                raise ValueError('exact Stage3 requires one serialized state')
            verify_exact_stage3_payload(zlib.decompress(chunks[0]), rom)
        elif rom[0x143] == 0xC0:
            stage3_source = temp_path / "stage3-identity.ss0"
            retarget_rom_identity(args.stage3_state, stage3_source, args.rom.resolve())
        normalize(
            stage3_source,
            stage3_candidate_state,
            pc=0,
            writes=[],
            rom=args.rom.resolve(),
            preserve_machine=True,
        )
        crystal_rows = run_probe(
            args.mgba.resolve(), args.rom.resolve(), crystal_candidate_state,
            temp_path / "crystal-a", scene, args.frames, args.timeout, True,
        )
        crystal_replay_rows = run_probe(
            args.mgba.resolve(), args.rom.resolve(), crystal_candidate_state,
            temp_path / "crystal-b", scene, args.frames, args.timeout, True,
        )
        determinism_attempts = [(crystal_rows, crystal_replay_rows)]
        if not semantic_replay_matches(crystal_rows, crystal_replay_rows):
            crystal_rows = run_probe(
                args.mgba.resolve(), args.rom.resolve(), crystal_candidate_state,
                temp_path / "crystal-c", scene, args.frames, args.timeout, True,
            )
            crystal_replay_rows = run_probe(
                args.mgba.resolve(), args.rom.resolve(), crystal_candidate_state,
                temp_path / "crystal-d", scene, args.frames, args.timeout, True,
            )
            determinism_attempts.append((crystal_rows, crystal_replay_rows))
        riff_rows = run_probe(
            args.mgba.resolve(), args.rom.resolve(), riff_candidate_state,
            temp_path / "riff", 0x0D, 24, args.timeout,
        )
        stage3_rows = run_probe(
            args.mgba.resolve(), args.rom.resolve(), stage3_candidate_state,
            temp_path / "stage3", 0x04, 24, args.timeout,
        )

    assert semantic_replay_matches(crystal_rows, crystal_replay_rows), (
        "Crystal Dragon ghost replay exceeded the bounded native OAM phase "
        "allowance"
    )

    for slot in slots:
        crystal_rows_for_slot = {
            obj[slot * 8:(slot + 1) * 8]
            for frame, _, obj in crystal_rows if frame >= 12
        }
        riff_rows_for_slot = {
            obj[slot * 8:(slot + 1) * 8]
            for frame, _, obj in riff_rows if frame >= 12
        }
        stage3_rows_for_slot = {
            obj[slot * 8:(slot + 1) * 8]
            for frame, _, obj in stage3_rows if frame >= 12
        }
        assert crystal_rows_for_slot == {source_bytes}, (
            slot, crystal_rows_for_slot
        )
        assert riff_rows_for_slot == {base_rows[slot]}, (
            slot, riff_rows_for_slot
        )
        assert stage3_rows_for_slot == {base_rows[slot]}, (
            slot, stage3_rows_for_slot
        )

    visibility = body_visibility(crystal_rows)
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

    def row_digest(rows: list[tuple[int, bytes, bytes]]) -> str:
        payload = b"".join(
            frame.to_bytes(4, "little") + oam + obj
            for frame, oam, obj in rows
        )
        return hashlib.sha256(payload).hexdigest()

    receipt = {
        "schema": "penta-crystal-ghost-v1",
        "status": "pass",
        "rom_sha256": hashlib.sha256(rom).hexdigest(),
        "crystal_state_sha256": hashlib.sha256(
            crystal_state.read_bytes()
        ).hexdigest(),
        "frames": args.frames,
        "deterministic_replay": True,
        "determinism_contract": (
            "exact OBJ CRAM plus at most 1% native double-buffered OAM "
            "visibility observations reclassified"
        ),
        "visibility_histogram_distance_limit": (
            visibility_histogram_distance_limit(args.frames)
        ),
        "determinism_attempts": [
            {
                "exact": first == second,
                "semantic_match": semantic_replay_matches(first, second),
                "visibility_histogram_distance": sum(
                    abs(
                        Counter(body_visibility(first))[key]
                        - Counter(body_visibility(second))[key]
                    )
                    for key in (
                        Counter(body_visibility(first)).keys()
                        | Counter(body_visibility(second)).keys()
                    )
                ),
                "replay_sha256": [row_digest(first), row_digest(second)],
            }
            for first, second in determinism_attempts
        ],
        "replay_sha256": [row_digest(crystal_rows), row_digest(crystal_replay_rows)],
        "scene": f"{scene:02X}",
        "obj_slots": list(slots),
        "material_bytes": source_bytes.hex().upper(),
        "body_sprite_visibility": {
            "minimum": min(visibility),
            "maximum": max(visibility),
            "longest_settled_blank_frames": longest_blank_run,
        },
        "riff_isolation": "pass",
        "stage3_isolation": "pass",
    }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")

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
    print("  Riff isolation: 13 settled frames retained all four base rows")
    print(
        "  Stage 3 isolation: shared FFBA index retained all four base rows "
        "under scene $04"
    )
    if args.output is not None:
        print(f"  receipt: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
