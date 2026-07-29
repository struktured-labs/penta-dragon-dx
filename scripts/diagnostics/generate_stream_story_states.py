#!/usr/bin/env python3
"""Generate ROM-matched story and ending states for the live scene deck.

OPENING is reached through the untouched default first title option; DOWN is
never sent because it selects GAME START. Pre/post-final states are captured
by the emulator-only final-story probe, then loaded in fresh mGBA processes
against the untouched release ROM. Only states that retain the expected stock
art/ending discriminator and ROM-native production attributes are promoted
to the stream cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_OUTPUT = ROOT / "tmp/palette_session/story_states"
OPENING_PROBE = Path(__file__).with_name("probe_generate_opening_state.lua")
FINAL_PROBE = Path(__file__).with_name("probe_final_cutscene_mgba.lua")
FINAL_INTEGRITY_PROBE = Path(__file__).with_name(
    "probe_final_story_state_integrity.lua"
)
ENDING_TAIL_PROBE = Path(__file__).with_name(
    "probe_generate_ending_tail_state.lua"
)
ENDING_TAIL_INTEGRITY_PROBE = Path(__file__).with_name(
    "probe_ending_tail_state_integrity.lua"
)
OPENING_STATES = (
    ("opening", None),
    ("opening_book", 1),
    ("opening_sara", 2),
    ("opening_dragon_eye", 3),
)
FINAL_STATES = (
    ("pre-final", "pre_final", 4),
    ("pre-final", "pre_final_sara", 7),
    ("post-final", "post_final", 5),
    ("post-final", "post_final_lisa", 6),
    ("post-final", "post_final_sara", 7),
)
ENDING_TAIL_STATES = (
    ("ending_credits", "credits", 1),
    ("ending_end", "end_page", 2),
    ("ending_epilogue", "epilogue_text", 3),
)
ENDING_TAIL_GUARDS = {
    "credits": (0x16, 0x01, 0x00, 0x00, 240),
    "end_page": (0x16, 0x01, 0x00, 0x01, 60),
    "epilogue_text": (0x00, 0x0C, 0x01, 0x01, 180),
}
STORY_STATES = tuple(
    [stem for stem, _art in OPENING_STATES]
    + [stem for _entry, stem, _art in FINAL_STATES]
    + [stem for stem, _target, _palette in ENDING_TAIL_STATES]
)


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cached(output: Path, rom_md5: str) -> bool:
    manifest = output / "manifest.json"
    if not manifest.is_file() or not all(
        (output / f"{name}.ss0").is_file()
        and (output / f"{name}.ss0").stat().st_size >= 1024
        for name in STORY_STATES
    ):
        return False
    try:
        data = json.loads(manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return (
        data.get("rom_md5") == rom_md5
        and data.get("states") == list(STORY_STATES)
    )


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_until_marker(
    command: list[str],
    env: dict[str, str],
    cwd: Path,
    marker: Path,
    timeout: float,
) -> None:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker.is_file():
                # Lua opens the marker before writing its status. Waiting for
                # non-empty content avoids terminating mGBA in that tiny race.
                try:
                    if marker.read_text().strip():
                        return
                except OSError:
                    pass
            if process.poll() is not None:
                raise RuntimeError(
                    f"mGBA exited {process.returncode} before {marker.name}"
                )
            time.sleep(0.05)
        raise TimeoutError(f"timed out waiting for {marker.name}")
    finally:
        terminate(process)


def generate_opening(
    mgba: str,
    rom: Path,
    output: Path,
    tmpdir: Path,
    stem: str,
    art_target: int | None,
    timeout: float,
) -> str:
    prefix = tmpdir / stem
    runtime_dir = tmpdir / f"{stem}.runtime"
    runtime_dir.mkdir()
    state = prefix.with_suffix(".ss0")
    report = prefix.with_suffix(".report")
    done = prefix.with_suffix(".done")
    screenshot = prefix.with_suffix(".png")
    env = os.environ.copy()
    env.update(
        OPENING_STATE_OUT=str(state),
        OPENING_OUT=str(prefix),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    if art_target is not None:
        env["OPENING_ART_ID"] = str(art_target)
    run_until_marker(
        [
            mgba,
            "--fastforward",
            "-C",
            f"savegamePath={runtime_dir}",
            "-C",
            f"savestatePath={runtime_dir}",
            str(rom.resolve()),
            "--script",
            str(OPENING_PROBE),
        ],
        env,
        tmpdir,
        done,
        timeout,
    )
    detail = report.read_text().strip() if report.is_file() else "no report"
    if done.read_text().strip() != "ok":
        raise RuntimeError(f"{stem} state generation failed: {detail}")
    if not state.is_file() or state.stat().st_size < 1024:
        raise RuntimeError(f"{stem} state was not created")
    if not screenshot.is_file() or screenshot.stat().st_size < 100:
        raise RuntimeError(f"{stem} screenshot was not rendered")
    required = [
        "status=ok",
        "d880=15",
        "ffc1=0",
        "stable=240",
        "visible_attr_wrong=0",
        "visible_attr_unsafe=0",
        "message=saved",
    ]
    if art_target is None:
        required.extend((
            "art_target=nil",
            "visible_attr_target=0",
            "visible_attr_neutral=360",
        ))
    else:
        required.extend(
            (
                f"art_target={art_target}",
                "dce8=02",
                "dcea=01",
                f"dcf0={art_target:02X}",
                f"dd07={art_target - 1:02X}",
                "visible_attr_target=160",
                "visible_attr_neutral=200",
            )
        )
    missing = [token for token in required if token not in detail]
    if missing:
        raise RuntimeError(
            f"{stem} state report is invalid: {', '.join(missing)}"
        )
    shutil.move(state, output / f"{stem}.ss0")
    shutil.move(report, output / f"{stem}.report")
    shutil.move(screenshot, output / f"{stem}.png")
    return detail


def generate_final_story(
    mgba: str,
    rom: Path,
    output: Path,
    tmpdir: Path,
    entry: str,
    stem: str,
    art_target: int,
    timeout: float,
) -> str:
    capture_runtime = tmpdir / f"{stem}.capture.runtime"
    capture_runtime.mkdir()
    state = tmpdir / f"{stem}.ss0"
    capture_report = tmpdir / f"{stem}.capture.report"
    capture_done = Path(str(capture_report) + ".done")
    capture_screenshot = tmpdir / f"{stem}.capture.png"
    env = os.environ.copy()
    env.update(
        FINAL_SCENE_ENTRY=entry,
        FINAL_SCENE_OUT=str(capture_report),
        FINAL_SCENE_SCREENSHOT=str(capture_screenshot),
        FINAL_SCENE_MAX_FRAMES=(
            "16000" if entry == "pre-final" else "12000"
        ),
        FINAL_SCENE_STATE_OUT=str(state),
        FINAL_SCENE_CAPTURE_STABLE="240",
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    env["FINAL_SCENE_ART_ID"] = str(art_target)
    run_until_marker(
        [
            mgba,
            "--fastforward",
            "-C",
            f"savegamePath={capture_runtime}",
            "-C",
            f"savestatePath={capture_runtime}",
            str(rom.resolve()),
            "--script",
            str(FINAL_PROBE),
        ],
        env,
        tmpdir,
        capture_done,
        timeout,
    )
    capture_detail = (
        capture_report.read_text().strip()
        if capture_report.is_file()
        else "no capture report"
    )
    expected = "19" if entry == "pre-final" else "1A"
    expected_sequence = 4 if entry == "pre-final" else 5
    required_capture = (
        "status=ok",
        f"expected_scene={expected}",
        "layout_mismatch_total=0",
        "table_bad_samples=0",
        "stable_scene_frames=240",
        "state_saved=true",
        f"art_target={art_target}",
        f"dce8={expected_sequence:02X}",
        "dcea=01",
        f"dcf0={art_target:02X}",
        f"dd07={art_target - 1:02X}",
    )
    missing = [token for token in required_capture if token not in capture_detail]
    if (
        capture_done.read_text().strip() != "ok"
        or missing
        or not state.is_file()
        or state.stat().st_size < 1024
    ):
        raise RuntimeError(
            f"{entry} capture failed: {', '.join(missing) or capture_detail}"
        )

    # This second process does no entry injection. It proves that the state
    # resumes on the untouched release ROM and remains in the expected scene.
    clean_prefix = tmpdir / f"{stem}.clean"
    clean_report = Path(str(clean_prefix) + ".report")
    clean_done = Path(str(clean_prefix) + ".done")
    clean_screenshot = Path(str(clean_prefix) + ".png")
    clean_runtime = tmpdir / f"{stem}.clean.runtime"
    clean_runtime.mkdir()
    clean_env = os.environ.copy()
    clean_env.update(
        FINAL_STORY_ENTRY=entry,
        FINAL_STORY_OUT=str(clean_prefix),
        FINAL_STORY_ART_ID=str(art_target),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    run_until_marker(
        [
            mgba,
            "--fastforward",
            "-t",
            str(state),
            "-C",
            f"savegamePath={clean_runtime}",
            "-C",
            f"savestatePath={clean_runtime}",
            str(rom.resolve()),
            "--script",
            str(FINAL_INTEGRITY_PROBE),
        ],
        clean_env,
        tmpdir,
        clean_done,
        timeout,
    )
    clean_detail = (
        clean_report.read_text().strip()
        if clean_report.is_file()
        else "no clean-load report"
    )
    required_clean = (
        "status=ok",
        f"entry={entry}",
        f"d880={expected}",
        "ffc1=0",
        "stable=60",
        "visible_attr_target=160",
        "visible_attr_neutral=200",
        "visible_attr_wrong=0",
        "table_neutral=true",
        f"art_target={art_target}",
        f"dce8={expected_sequence:02X}",
        "dcea=01",
        f"dcf0={art_target:02X}",
        f"dd07={art_target - 1:02X}",
        "message=colored-release-rom-resume",
    )
    missing = [token for token in required_clean if token not in clean_detail]
    if (
        clean_done.read_text().strip() != "ok"
        or missing
        or not clean_screenshot.is_file()
        or clean_screenshot.stat().st_size < 100
    ):
        raise RuntimeError(
            f"{entry} clean-load validation failed: "
            f"{', '.join(missing) or clean_detail}"
        )

    shutil.move(state, output / f"{stem}.ss0")
    shutil.move(clean_report, output / f"{stem}.report")
    shutil.move(clean_screenshot, output / f"{stem}.png")
    shutil.move(capture_report, output / f"{stem}.capture.report")
    return clean_detail


def generate_ending_tail(
    mgba: str,
    rom: Path,
    output: Path,
    tmpdir: Path,
    stem: str,
    target: str,
    timeout: float,
) -> str:
    capture_runtime = tmpdir / f"{stem}.capture.runtime"
    capture_runtime.mkdir()
    state = tmpdir / f"{stem}.ss0"
    capture_prefix = tmpdir / f"{stem}.capture"
    capture_report = Path(str(capture_prefix) + ".report")
    capture_done = Path(str(capture_prefix) + ".done")
    capture_screenshot = Path(str(capture_prefix) + ".png")
    expected, d889, dce2, fff9, capture_stable = ENDING_TAIL_GUARDS[
        target
    ]
    capture_env = os.environ.copy()
    capture_env.update(
        ENDING_TAIL_STATE_OUT=str(state),
        ENDING_TAIL_OUT=str(capture_prefix),
        ENDING_TAIL_TARGET=target,
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    run_until_marker(
        [
            mgba,
            "--fastforward",
            "-C",
            f"savegamePath={capture_runtime}",
            "-C",
            f"savestatePath={capture_runtime}",
            str(rom.resolve()),
            "--script",
            str(ENDING_TAIL_PROBE),
        ],
        capture_env,
        tmpdir,
        capture_done,
        timeout,
    )
    capture_detail = (
        capture_report.read_text().strip()
        if capture_report.is_file()
        else "no capture report"
    )
    required_capture = (
        "status=ok",
        f"target={target}",
        f"d880={expected:02X}",
        "ffc1=0",
        "ffba=08",
        "ffe4=1",
        f"d889={d889:02X}",
        f"dce2={dce2:02X}",
        f"fff9={fff9:02X}",
        f"stable={capture_stable}",
        "visible_attr_target=360",
        "visible_attr_wrong=0",
        "table_neutral=true",
        "state_saved=true",
        "message=saved-colored-release-rom-tail",
    )
    missing = [
        token for token in required_capture if token not in capture_detail
    ]
    if (
        capture_done.read_text().strip() != "ok"
        or missing
        or not state.is_file()
        or state.stat().st_size < 1024
        or not capture_screenshot.is_file()
        or capture_screenshot.stat().st_size < 100
    ):
        raise RuntimeError(
            f"{target} capture failed: "
            f"{', '.join(missing) or capture_detail}"
        )

    # Prove that the saved direct-written tail resumes in a fresh mGBA
    # process on the untouched release ROM without any entry injection.
    clean_prefix = tmpdir / f"{stem}.clean"
    clean_report = Path(str(clean_prefix) + ".report")
    clean_done = Path(str(clean_prefix) + ".done")
    clean_screenshot = Path(str(clean_prefix) + ".png")
    clean_runtime = tmpdir / f"{stem}.clean.runtime"
    clean_runtime.mkdir()
    clean_env = os.environ.copy()
    clean_env.update(
        ENDING_TAIL_INTEGRITY_OUT=str(clean_prefix),
        ENDING_TAIL_TARGET=target,
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    run_until_marker(
        [
            mgba,
            "--fastforward",
            "-t",
            str(state),
            "-C",
            f"savegamePath={clean_runtime}",
            "-C",
            f"savestatePath={clean_runtime}",
            str(rom.resolve()),
            "--script",
            str(ENDING_TAIL_INTEGRITY_PROBE),
        ],
        clean_env,
        tmpdir,
        clean_done,
        timeout,
    )
    clean_detail = (
        clean_report.read_text().strip()
        if clean_report.is_file()
        else "no clean-load report"
    )
    required_clean = (
        "status=ok",
        f"target={target}",
        f"d880={expected:02X}",
        "ffc1=0",
        "ffba=08",
        "ffe4=1",
        f"d889={d889:02X}",
        f"dce2={dce2:02X}",
        f"fff9={fff9:02X}",
        "stable=60",
        "visible_attr_target=360",
        "visible_attr_wrong=0",
        "table_neutral=true",
        "message=colored-release-rom-resume",
    )
    missing = [token for token in required_clean if token not in clean_detail]
    if (
        clean_done.read_text().strip() != "ok"
        or missing
        or not clean_screenshot.is_file()
        or clean_screenshot.stat().st_size < 100
    ):
        raise RuntimeError(
            f"{target} clean-load validation failed: "
            f"{', '.join(missing) or clean_detail}"
        )

    shutil.move(state, output / f"{stem}.ss0")
    shutil.move(clean_report, output / f"{stem}.report")
    shutil.move(clean_screenshot, output / f"{stem}.png")
    shutil.move(capture_report, output / f"{stem}.capture.report")
    return clean_detail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--target",
        action="append",
        choices=STORY_STATES,
        help="generate only this named state (repeatable; default: all)",
    )
    args = parser.parse_args()

    if not args.rom.is_file():
        parser.error(f"ROM not found: {args.rom}")
    if not args.mgba:
        parser.error("mgba-qt was not found")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rom_md5 = md5(args.rom)
    if not args.target and not args.force and cached(output, rom_md5):
        print(f"Stream story states are current for {rom_md5}.")
        return 0

    selected = set(args.target or STORY_STATES)
    with tempfile.TemporaryDirectory(prefix="penta-story-") as tmp:
        tmpdir = Path(tmp)
        opening_details = {
            stem: generate_opening(
                args.mgba,
                args.rom,
                output,
                tmpdir,
                stem,
                art_target,
                args.timeout,
            )
            for stem, art_target in OPENING_STATES
            if stem in selected
        }
        final_details = {
            stem: generate_final_story(
                args.mgba,
                args.rom,
                output,
                tmpdir,
                entry,
                stem,
                art_target,
                args.timeout,
            )
            for entry, stem, art_target in FINAL_STATES
            if stem in selected
        }
        tail_details = {
            stem: generate_ending_tail(
                args.mgba,
                args.rom,
                output,
                tmpdir,
                stem,
                target,
                args.timeout,
            )
            for stem, target, _palette in ENDING_TAIL_STATES
            if stem in selected
        }

    for stem, detail in opening_details.items():
        print(f"{stem}: PASS | {detail}")
    for stem, detail in final_details.items():
        print(f"{stem}: PASS | {detail}")
    for stem, detail in tail_details.items():
        print(f"{stem}: PASS | {detail}")

    missing_states = [
        stem for stem in STORY_STATES
        if not (output / f"{stem}.ss0").is_file()
    ]
    if missing_states:
        print(
            f"Generated {len(selected)} selected story state(s) in {output}; "
            f"cache still needs: {', '.join(missing_states)}."
        )
        return 0

    manifest = {
        "rom": str(args.rom.resolve()),
        "rom_md5": rom_md5,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "opening_route": "default OPENING START option; no DOWN input",
        "final_route": (
            "diagnostic dialogue entry; ending tail advances from a clean "
            "release-ROM dialogue state; every saved state is then resumed "
            "in a fresh process"
        ),
        "art_palettes": {
            stem: art_target
            for stem, art_target in OPENING_STATES
            if art_target is not None
        }
        | {
            stem: art_target
            for _entry, stem, art_target in FINAL_STATES
        },
        "ending_tail_palettes": {
            stem: palette
            for stem, _target, palette in ENDING_TAIL_STATES
        },
        "ending_tail_guards": {
            stem: {
                "d880": ENDING_TAIL_GUARDS[target][0],
                "ffc1": 0,
                "ffe4": 1,
                "d889": ENDING_TAIL_GUARDS[target][1],
                "dce2": ENDING_TAIL_GUARDS[target][2],
                "fff9": ENDING_TAIL_GUARDS[target][3],
            }
            for stem, target, _palette in ENDING_TAIL_STATES
        },
        "states": list(STORY_STATES),
    }
    temporary = output / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.replace(output / "manifest.json")
    print(
        f"Generated {len(STORY_STATES)} ROM-matched stream story states "
        f"in {output}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
