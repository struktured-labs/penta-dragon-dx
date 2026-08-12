#!/usr/bin/env python3
"""Shared deterministic-suite source and receipt contract."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "penta-dragon-dx-deterministic-suite-v1"
DEFAULT_RECEIPT = ROOT / "docs/release/verification/latest.json"

GUARDED_ENTRYPOINTS = (
    "mgba-qt.sh",
    "scripts/launch_mgba.sh",
    "scripts/launch_mgba_record.sh",
    "scripts/inventory_probe.sh",
    "scripts/palette_session.sh",
    "scripts/play_record.sh",
    "scripts/play_record_curriculum.sh",
    "scripts/probes/verify_boss_arena_palettes.py",
    "scripts/probes/verify_gameplay_palette.py",
    "scripts/probes/verify_menu_hud_and_combo.py",
    "scripts/probes/verify_miniboss_color.py",
    "scripts/probes/verify_phantom_d887.py",
    "scripts/probes/verify_scroll_tearing.py",
    "scripts/probes/verify_stage_intro_timing.py",
    "scripts/probes/verify_title_color.py",
    "scripts/diagnostics/generate_stream_boss_states.py",
    "scripts/diagnostics/generate_stream_stage_states.py",
    "scripts/diagnostics/generate_stream_story_states.py",
    "scripts/diagnostics/inventory_attract_reel.py",
    "scripts/diagnostics/inventory_savestate_scenes.py",
    "scripts/diagnostics/verify_attract_pickup_palettes.py",
    "scripts/diagnostics/verify_bonus_stage_live.py",
    "scripts/diagnostics/verify_boss_publication_cadence.py",
    "scripts/diagnostics/verify_boss_semantic_cadence.py",
    "scripts/diagnostics/verify_crystal_dragon_ghost.py",
    "scripts/diagnostics/verify_death_gameover.py",
    "scripts/diagnostics/verify_final_cutscene_mgba.py",
    "scripts/diagnostics/verify_frame_flicker.py",
    "scripts/diagnostics/verify_game_start_routes.py",
    "scripts/diagnostics/verify_gameplay_obj_palettes.py",
    "scripts/diagnostics/verify_later_stage_integrity.py",
    "scripts/diagnostics/verify_later_stage_soak.py",
    "scripts/diagnostics/verify_levelselect_screen.py",
    "scripts/diagnostics/verify_live_palette_session.py",
    "scripts/diagnostics/verify_low_health_flicker.py",
    "scripts/diagnostics/verify_palette_build_roundtrip.py",
    "scripts/diagnostics/verify_pickup_live_palettes.py",
    "scripts/diagnostics/verify_stage1_no_bleed.py",
    "scripts/diagnostics/verify_stage1_pickup_art.py",
    "scripts/diagnostics/verify_stage_speed_matrix.py",
    "scripts/diagnostics/verify_story_attr_production.py",
    "scripts/diagnostics/verify_stale_window_state.py",
    "scripts/diagnostics/verify_title_showcase_mgba.py",
)

FIXED_INPUTS = (
    "AGENTS.md",
    ".claude/settings.json",
    ".claude/skills/launch-game.md",
    ".githooks/pre-commit",
    ".gitignore",
    "CLAUDE.md",
    "pyproject.toml",
    "uv.lock",
    "scripts/arena_position.py",
    "scripts/bg_experiment.py",
    "scripts/build_release_bundle.py",
    "scripts/build_v296_phantomsafe.py",
    "scripts/build_v301_gdma.py",
    "scripts/build_v301_teleport.py",
    "scripts/build_v302_title_fix.py",
    "scripts/check_emulator_processes.sh",
    "scripts/cutscene_region_palettes.py",
    "scripts/create_vblank_colorizer_v288.py",
    "scripts/install_git_hooks.sh",
    "scripts/live_palette_editor.py",
    "scripts/lua/live_palettes.lua",
    "scripts/mister.py",
    "scripts/mgba-headless-singleflight",
    "scripts/mgba-qt-singleflight",
    "scripts/mgba_singleflight.py",
    "scripts/record_palette_approval.py",
    "scripts/stage1_hazard_art.py",
    "scripts/hooks/guard_mgba_launch.py",
    *GUARDED_ENTRYPOINTS,
)

INPUT_TREES = (
    ("palettes", {".yaml", ".yml"}),
    ("scripts/diagnostics", {".py", ".lua", ".sh"}),
    ("scripts/probes", {".py", ".lua", ".sh"}),
    ("src/penta_dragon_dx", {".py"}),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_paths() -> list[Path]:
    paths = {ROOT / relative for relative in FIXED_INPUTS}
    for relative, suffixes in INPUT_TREES:
        base = ROOT / relative
        paths.update(
            path
            for path in base.rglob("*")
            if path.is_file()
            and path.suffix in suffixes
            and "__pycache__" not in path.parts
        )
    missing = [path for path in paths if not path.is_file()]
    if missing:
        rendered = ", ".join(
            str(path.relative_to(ROOT)) for path in sorted(missing)
        )
        raise FileNotFoundError(f"suite input(s) missing: {rendered}")
    return sorted(paths, key=lambda path: str(path.relative_to(ROOT)))


def source_snapshot() -> tuple[str, list[dict[str, str | int]]]:
    aggregate = hashlib.sha256()
    entries: list[dict[str, str | int]] = []
    for path in source_paths():
        relative = path.relative_to(ROOT).as_posix()
        digest = sha256_file(path)
        size = path.stat().st_size
        aggregate.update(relative.encode())
        aggregate.update(b"\0")
        aggregate.update(digest.encode())
        aggregate.update(b"\0")
        aggregate.update(str(size).encode())
        aggregate.update(b"\n")
        entries.append(
            {"path": relative, "sha256": digest, "size": size}
        )
    return aggregate.hexdigest(), entries
