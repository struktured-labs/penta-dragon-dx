#!/usr/bin/env python3
"""End-to-end gate for the release-safe browser → Lua → mGBA palette bridge."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
EDITOR = ROOT / "scripts/live_palette_editor.py"
LUA = ROOT / "scripts/lua/live_palettes.lua"
STAGE_GENERATOR = Path(__file__).with_name("generate_stream_stage_states.py")
BOSS_GENERATOR = Path(__file__).with_name("generate_stream_boss_states.py")
STORY_GENERATOR = Path(__file__).with_name("generate_stream_story_states.py")


def reserve_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(url: str, path: str, payload: dict | None = None) -> str:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        url + path,
        data=data,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=2) as response:
        return response.read().decode()


def wait_for_server(url: str, process: subprocess.Popen, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    last_error = "not started"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"editor exited early with status {process.returncode}")
        try:
            return request(url, "/")
        except (OSError, urllib.error.URLError) as error:
            last_error = str(error)
            time.sleep(0.05)
    raise RuntimeError(f"editor did not bind: {last_error}")


def terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def parse_fields(text: str) -> dict[str, str]:
    return dict(field.split("=", 1) for field in text.split() if "=" in field)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--stage-states",
        type=Path,
        help="reuse an exact-ROM Stage 2-7 state cache",
    )
    parser.add_argument(
        "--boss-states",
        type=Path,
        help="reuse an exact-ROM nine-boss state cache",
    )
    parser.add_argument(
        "--story-states",
        type=Path,
        help="reuse an exact-ROM story/ending state cache",
    )
    parser.add_argument(
        "--keep-story-states",
        type=Path,
        help="copy the verified ROM-matched story state cache here on success",
    )
    args = parser.parse_args()

    if not args.rom.is_file():
        parser.error(f"ROM not found: {args.rom}")
    if not args.mgba:
        parser.error("mgba-qt was not found")

    with tempfile.TemporaryDirectory(prefix="penta-live-palette-") as tmp:
        tmpdir = Path(tmp)
        live_file = tmpdir / "live.txt"
        palette_yaml = tmpdir / "palettes.yaml"
        palette_backup_dir = tmpdir / "palette-backups"
        stage_state_dir = (
            args.stage_states.resolve()
            if args.stage_states
            else tmpdir / "stage-states"
        )
        boss_state_dir = (
            args.boss_states.resolve()
            if args.boss_states
            else tmpdir / "boss-states"
        )
        story_state_dir = (
            args.story_states.resolve()
            if args.story_states
            else tmpdir / "story-states"
        )
        lua_log = tmpdir / "lua.log"
        smoke_out = tmpdir / "smoke.txt"
        source_yaml = ROOT / "palettes/penta_palettes_v097.yaml"
        shutil.copy2(source_yaml, palette_yaml)
        original_yaml = palette_yaml.read_text()
        original_palette_data = yaml.safe_load(original_yaml)
        expected_bg3 = [
            str(color).upper().zfill(4)
            for color in original_palette_data["bg_palettes"]["BG3"]["colors"]
        ]
        expected_bg3[1] = "001F"
        expected_bg3_quoted = ", ".join(
            f'"{color}"' for color in expected_bg3
        )
        expected_bg3_yaml = f"colors: [{expected_bg3_quoted}]"
        expected_bg3_protocol = "BG3:" + ",".join(
            f"{index}={color}" for index, color in enumerate(expected_bg3)
        )
        expected_bg3_cram = ",".join(expected_bg3)
        conversion_env = os.environ.copy()
        conversion_env.update(
            PENTA_LIVE_PALETTE_FILE=str(live_file),
            PENTA_PALETTE_YAML=str(palette_yaml),
            PENTA_PALETTE_BACKUP_DIR=str(palette_backup_dir),
        )
        conversion_check = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from scripts.live_palette_editor import "
                    "bgr555_to_rgb888, rgb888_to_bgr555; "
                    "bad = [value for value in range(0x8000) "
                    "if rgb888_to_bgr555(bgr555_to_rgb888(value)) != value]; "
                    "assert not bad, f'{len(bad)} failed CGB words'"
                ),
            ],
            cwd=ROOT,
            env=conversion_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
            check=False,
        )
        generated = None if args.stage_states else subprocess.run(
            [
                sys.executable,
                str(STAGE_GENERATOR),
                str(args.rom),
                "--output",
                str(stage_state_dir),
                "--force",
                "--timeout",
                str(args.timeout),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=args.timeout * 2,
            check=False,
        )
        if generated is not None and generated.returncode != 0:
            print(
                "FAIL: Stage 2-7 stream-state generation exited "
                f"{generated.returncode}\n{generated.stdout.rstrip()}"
            )
            return 1
        generated_bosses = None if args.boss_states else subprocess.run(
            [
                sys.executable,
                str(BOSS_GENERATOR),
                str(args.rom),
                "--output",
                str(boss_state_dir),
                "--force",
                "--timeout",
                str(args.timeout),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=args.timeout * 2,
            check=False,
        )
        if generated_bosses is not None and generated_bosses.returncode != 0:
            print(
                "FAIL: boss stream-state generation exited "
                f"{generated_bosses.returncode}\n"
                f"{generated_bosses.stdout.rstrip()}"
            )
            return 1
        generated_story = None if args.story_states else subprocess.run(
            [
                sys.executable,
                str(STORY_GENERATOR),
                str(args.rom),
                "--output",
                str(story_state_dir),
                "--force",
                "--timeout",
                str(args.timeout),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            # The generator serially captures twelve opening/final/ending
            # states, each with its own ``--timeout`` budget. Three multiples
            # left no scheduler margin and killed otherwise healthy runs at
            # exactly 180 seconds. Keep this bounded below the release gate's
            # 600-second outer limit while allowing the complete deck to
            # finish on a loaded workstation.
            timeout=max(args.timeout * 5, 120),
            check=False,
        )
        if generated_story is not None and generated_story.returncode != 0:
            print(
                "FAIL: story-panel stream-state generation exited "
                f"{generated_story.returncode}\n"
                f"{generated_story.stdout.rstrip()}"
            )
            return 1
        port = reserve_port()
        url = f"http://127.0.0.1:{port}"

        server_env = os.environ.copy()
        server_env.update(
            PENTA_LIVE_PALETTE_FILE=str(live_file),
            PENTA_PALETTE_YAML=str(palette_yaml),
            PENTA_PALETTE_BACKUP_DIR=str(palette_backup_dir),
            PYTHONUNBUFFERED="1",
        )
        server = subprocess.Popen(
            [
                sys.executable,
                str(EDITOR),
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=server_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        emulator: subprocess.Popen | None = None
        try:
            html = wait_for_server(url, server, 5)
            ui_checks = {
                "release-safe scene deck is present": "Stream Scene Deck" in html,
                "retired DX teleport is absent": "DX Teleport" not in html,
                "raw state-byte hold is absent": "State-byte Hold" not in html,
                "title choices are labeled correctly": (
                    "first title option is the story intro" in html
                    and "DOWN selects" in html
                    and "GAME START" in html
                ),
                "story preview preserves dialogue": (
                    "dialogue border" in html
                    and "neutral BG0" in html
                ),
                "ending tail controls are present": all(
                    label in html
                    for label in (
                        "Ending — credits (BG1)",
                        "Ending — END page (BG2)",
                        "Ending — epilogue text (BG3)",
                        "ending-phase guards",
                    )
                ),
                "builder boss overrides are directly tunable": (
                    "Miniboss / Boss Override Palettes" in html
                    and "FFBF 1: Gargoyle" in html
                    and "FFBF 2: Spider" in html
                    and "FFBF 8: Angela" in html
                ),
                "builder jet and powerup palettes are directly tunable": (
                    "Jet Form Palettes" in html
                    and "SaraDragonJet" in html
                    and "SaraWitchJet" in html
                    and "Powerup Projectile Palettes" in html
                    and "SpiralProjectile" in html
                    and "ShieldProjectile" in html
                    and "TurboProjectile" in html
                    and "Spiral projectile (FFC0=1)" in html
                    and "Shield projectile (FFC0=2)" in html
                ),
                "all CGB colors round-trip exactly through the editor": (
                    conversion_check.returncode == 0
                    and "Math.round(r * 31 / 255)" in html
                    and "Math.round(g * 31 / 255)" in html
                    and "Math.round(b * 31 / 255)" in html
                ),
            }

            # Change base and guarded special palettes. The bridge must emit
            # only those complete palettes, leaving unrelated CRAM alone.
            request(
                url,
                "/update",
                {"kind": "BG", "pal": 3, "color": 1, "bgr": "001F"},
            )
            request(
                url,
                "/update",
                {"kind": "OBJ", "pal": 4, "color": 2, "bgr": "7C00"},
            )
            request(
                url,
                "/update",
                {"kind": "BOSS", "pal": 1, "color": 2, "bgr": "03E0"},
            )
            request(
                url,
                "/update",
                {"kind": "JET", "pal": 2, "color": 1, "bgr": "1234"},
            )
            request(
                url,
                "/update",
                {"kind": "POWER", "pal": 1, "color": 1, "bgr": "2345"},
            )
            request(
                url,
                "/update",
                {"kind": "POWER", "pal": 2, "color": 1, "bgr": "3456"},
            )
            request(
                url,
                "/update",
                {"kind": "POWER", "pal": 3, "color": 1, "bgr": "4567"},
            )
            concurrent_payloads = [
                {"kind": "BG", "pal": 3, "color": 1, "bgr": "001F"}
                if index % 2 == 0
                else {"kind": "OBJ", "pal": 4, "color": 2, "bgr": "7C00"}
                for index in range(64)
            ]
            concurrent_errors = []
            with ThreadPoolExecutor(max_workers=16) as pool:
                futures = [
                    pool.submit(request, url, "/update", payload)
                    for payload in concurrent_payloads
                ]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as error:
                        concurrent_errors.append(str(error))
            first_save_response = request(url, "/save", {})
            saved_yaml = palette_yaml.read_text()
            palette_backups = sorted(palette_backup_dir.glob("*.backup.yaml"))
            second_save_response = request(url, "/save", {})
            palette_backups_after_noop = sorted(
                palette_backup_dir.glob("*.backup.yaml")
            )
            changed_lines = sum(
                before != after
                for before, after in zip(
                    original_yaml.splitlines(),
                    saved_yaml.splitlines(),
                )
            )
            persistence_checks = {
                "YAML comments and structure are preserved": (
                    saved_yaml.startswith("# Penta Dragon DX Palettes\n")
                    and len(saved_yaml.splitlines()) == len(original_yaml.splitlines())
                    and changed_lines == 7
                ),
                "BG edit persisted to YAML": (
                    expected_bg3_yaml in saved_yaml
                ),
                "OBJ edit persisted to YAML": (
                    'colors: ["0000", "03FF", "7C00", "0000"]'
                    in saved_yaml
                ),
                "Gargoyle override persisted to its builder YAML entry": (
                    'colors: ["0000", "601F", "03E0", "0000"]'
                    in saved_yaml
                ),
                "Jet override persisted to its builder YAML entry": (
                    'colors: ["0000", "1234", "5817", "3010"]'
                    in saved_yaml
                ),
                "all powerup overrides persisted to builder YAML entries": all(
                    colors in saved_yaml
                    for colors in (
                        'colors: ["0000", "2345", "5EC0", "3E80"]',
                        'colors: ["0000", "3456", "02BF", "019F"]',
                        'colors: ["0000", "4567", "00BF", "005F"]',
                    )
                ),
                "changed save preserves exact pre-save YAML": (
                    len(palette_backups) == 1
                    and palette_backups[0].read_text() == original_yaml
                    and "Backup:" in first_save_response
                    and str(palette_backups[0]) in first_save_response
                ),
                "unchanged save creates no redundant backup": (
                    palette_backups_after_noop == palette_backups
                    and second_save_response.startswith("No palette changes;")
                ),
            }
            request(url, "/load_scene", {"scene": "gargoyle"})
            first_scene_protocol = live_file.read_text()
            request(url, "/load_scene", {"scene": "gargoyle"})
            protocol = live_file.read_text()
            protocol_checks = {
                "rapid concurrent edits are serialized": not concurrent_errors,
                "only edited BG palette is emitted": (
                    expected_bg3_protocol in protocol
                    and all(f"BG{index}:" not in protocol for index in range(8) if index != 3)
                ),
                "only edited OBJ palette is emitted": (
                    "OBJ4:0=0000,1=03FF,2=7C00,3=0000" in protocol
                    and all(f"OBJ{index}:" not in protocol for index in range(8) if index != 4)
                ),
                "guarded boss override is emitted": (
                    "BOSS1@6:0=0000,1=601F,2=03E0,3=0000" in protocol
                ),
                "guarded jet override is emitted": (
                    "JET2:0=0000,1=1234,2=5817,3=3010" in protocol
                ),
                "all guarded powerup overrides are emitted": all(
                    line in protocol
                    for line in (
                        "POWER1:0=0000,1=2345,2=5EC0,3=3E80",
                        "POWER2:0=0000,1=3456,2=02BF,3=019F",
                        "POWER3:0=0000,1=4567,2=00BF,3=005F",
                    )
                ),
                "curated scene request is emitted": "SCENE:gargoyle" in protocol,
                "repeated scene requests remain observable": (
                    first_scene_protocol != protocol
                    and "# SCENE_REQUEST:1" in first_scene_protocol
                    and "# SCENE_REQUEST:2" in protocol
                ),
                "no ROM-state directive is emitted": not any(
                    marker in protocol
                    for marker in ("DX:", "FFBA:", "D880:", "FFB7:", "DF0A:")
                ),
            }

            emulator_env = os.environ.copy()
            emulator_env.update(
                LIVE_PALETTE_FILE=str(live_file),
                LIVE_PALETTE_LOG=str(lua_log),
                LIVE_PALETTE_SMOKE_OUT=str(smoke_out),
                LIVE_PALETTE_STAGE_STATE_DIR=str(stage_state_dir),
                LIVE_PALETTE_BOSS_STATE_DIR=str(boss_state_dir),
                LIVE_PALETTE_STORY_STATE_DIR=str(story_state_dir),
                QT_QPA_PLATFORM="offscreen",
                SDL_AUDIODRIVER="dummy",
            )
            emulator = subprocess.Popen(
                [
                    args.mgba,
                    "--fastforward",
                    str(args.rom.resolve()),
                    "--script",
                    str(LUA),
                ],
                cwd=ROOT,
                env=emulator_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline and not smoke_out.exists():
                if emulator.poll() is not None:
                    break
                time.sleep(0.05)

            if not smoke_out.exists():
                log = lua_log.read_text() if lua_log.exists() else "(no Lua log)"
                print(f"FAIL: mGBA bridge did not report\n{log}")
                return 1

            report = smoke_out.read_text().strip()
            fields = parse_fields(report)
            smoke_screenshot = smoke_out.with_suffix(".txt.png")
            screenshot_deadline = time.monotonic() + 2
            while time.monotonic() < screenshot_deadline:
                if (
                    smoke_screenshot.is_file()
                    and smoke_screenshot.stat().st_size > 100
                ):
                    break
                if emulator.poll() is not None:
                    break
                time.sleep(0.02)
            runtime_checks = {
                "curated Gargoyle state loaded": (
                    fields.get("scene") == "gargoyle"
                    and fields.get("ffbf") == "01"
                ),
                "loaded state is active gameplay": fields.get("ffc1") == "1",
                "edited BG3 reached CGB CRAM": (
                    fields.get("bg3") == expected_bg3_cram
                ),
                "edited OBJ4 reached CGB CRAM": (
                    fields.get("obj4") == "0000,03FF,7C00,0000"
                ),
                "edited Gargoyle override reached OBJ6 CRAM": (
                    fields.get("obj6") == "0000,601F,03E0,0000"
                ),
                "rendered frame was captured": (
                    smoke_screenshot.is_file()
                    and smoke_screenshot.stat().st_size > 100
                ),
            }

            # A second mGBA run proves every special palette is guarded by the
            # exact production state byte and reaches its builder-owned CRAM
            # slot. Turbo uses a diagnostic-only forced FFC0=3 because no
            # natural checked-in state carries that value.
            terminate(emulator)
            emulator = None
            special_audit = tmpdir / "special-audit.txt"
            special_env = os.environ.copy()
            special_env.update(
                LIVE_PALETTE_FILE=str(live_file),
                LIVE_PALETTE_LOG=str(lua_log),
                LIVE_PALETTE_SPECIAL_AUDIT_OUT=str(special_audit),
                LIVE_PALETTE_STAGE_STATE_DIR=str(stage_state_dir),
                LIVE_PALETTE_BOSS_STATE_DIR=str(boss_state_dir),
                LIVE_PALETTE_STORY_STATE_DIR=str(story_state_dir),
                QT_QPA_PLATFORM="offscreen",
                SDL_AUDIODRIVER="dummy",
            )
            emulator = subprocess.Popen(
                [
                    args.mgba,
                    "--fastforward",
                    str(args.rom.resolve()),
                    "--script",
                    str(LUA),
                ],
                cwd=ROOT,
                env=special_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            special_audit_done = Path(str(special_audit) + ".done")
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                if special_audit_done.is_file():
                    break
                if emulator.poll() is not None:
                    break
                time.sleep(0.05)
            special_lines = (
                special_audit.read_text().splitlines()[1:]
                if special_audit.exists()
                else []
            )
            specials = {
                item["scene"]: item
                for item in (parse_fields(line) for line in special_lines)
                if "scene" in item
            }
            special_checks = {
                "guarded boss palette reaches its exact OBJ slot": (
                    specials.get("gargoyle", {}).get("ok") == "true"
                    and specials.get("gargoyle", {}).get("ffbf") == "01"
                    and specials.get("gargoyle", {}).get("obj6")
                    == "0000,601F,03E0,0000"
                ),
                "guarded jet palette reaches its exact OBJ slot": (
                    specials.get("jet", {}).get("ok") == "true"
                    and specials.get("jet", {}).get("ffd0") == "01"
                    and specials.get("jet", {}).get("obj2")
                    == "0000,1234,5817,3010"
                ),
                "Spiral and Shield palettes follow exact FFC0 guards": (
                    specials.get("spiral", {}).get("ffc0") == "01"
                    and specials.get("spiral", {}).get("obj0")
                    == "0000,2345,5EC0,3E80"
                    and specials.get("shield", {}).get("ffc0") == "02"
                    and specials.get("shield", {}).get("obj0")
                    == "0000,3456,02BF,019F"
                ),
                "Turbo palette follows diagnostic FFC0=3 guard": (
                    specials.get("turbo_guard", {}).get("ffc0") == "03"
                    and specials.get("turbo_guard", {}).get("obj0")
                    == "0000,4567,00BF,005F"
                ),
                "all guarded-special frames rendered": (
                    special_audit_done.is_file()
                    and special_audit_done.read_text().strip() == "ok"
                    and all(
                        Path(f"{special_audit}.{scene}.png").is_file()
                        and Path(f"{special_audit}.{scene}.png").stat().st_size
                        > 100
                        for scene in (
                            "gargoyle",
                            "jet",
                            "spiral",
                            "shield",
                            "turbo_guard",
                        )
                    )
                ),
            }

            # A third mGBA run loads every button in the scene deck through
            # the same Lua bridge. This catches stale/incompatible state files
            # before a stream, not after the host clicks one.
            terminate(emulator)
            emulator = None
            scene_audit = tmpdir / "scene-audit.txt"
            audit_env = os.environ.copy()
            audit_env.update(
                LIVE_PALETTE_FILE=str(live_file),
                LIVE_PALETTE_LOG=str(lua_log),
                LIVE_PALETTE_SCENE_AUDIT_OUT=str(scene_audit),
                LIVE_PALETTE_STAGE_STATE_DIR=str(stage_state_dir),
                LIVE_PALETTE_BOSS_STATE_DIR=str(boss_state_dir),
                LIVE_PALETTE_STORY_STATE_DIR=str(story_state_dir),
                QT_QPA_PLATFORM="offscreen",
                SDL_AUDIODRIVER="dummy",
            )
            emulator = subprocess.Popen(
                [
                    args.mgba,
                    "--fastforward",
                    str(args.rom.resolve()),
                    "--script",
                    str(LUA),
                ],
                cwd=ROOT,
                env=audit_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            scene_audit_done = Path(str(scene_audit) + ".done")
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                if scene_audit_done.is_file():
                    break
                if emulator.poll() is not None:
                    break
                time.sleep(0.05)

            audit_lines = (
                scene_audit.read_text().splitlines()[1:]
                if scene_audit.exists()
                else []
            )
            audited = {
                fields["scene"]: fields
                for fields in (parse_fields(line) for line in audit_lines)
                if "scene" in fields
            }
            expected_scenes = {
                "title", "opening", "opening_book", "opening_sara",
                "opening_dragon_eye", "pre_final_story", "pre_final_sara",
                "post_final_story", "post_final_lisa", "post_final_sara",
                "ending_credits", "ending_end", "ending_epilogue",
                "stage2", "stage3", "stage4", "stage5", "stage6", "stage7",
                "witch", "dragon", "crow", "hornets", "orc", "soldier",
                "mage", "mixed", "gargoyle", "spider", "spiral", "shield",
                "jet", "menu",
                "boss_shalamar", "boss_riff", "boss_crystal_dragon",
                "boss_cameo", "boss_ted", "boss_troop", "boss_faze",
                "boss_angela", "boss_penta_dragon",
            }
            story_scenes = {
                "opening": ("15", "00", "0"),
                "opening_book": ("15", "00", "0"),
                "opening_sara": ("15", "00", "0"),
                "opening_dragon_eye": ("15", "00", "0"),
                "pre_final_story": ("19", "06", "0"),
                "pre_final_sara": ("19", "06", "0"),
                "post_final_story": ("1A", "08", "1"),
                "post_final_lisa": ("1A", "08", "1"),
                "post_final_sara": ("1A", "08", "1"),
            }
            story_art_scenes = {
                "opening_book": ("02", "01"),
                "opening_sara": ("02", "02"),
                "opening_dragon_eye": ("02", "03"),
                "pre_final_story": ("04", "04"),
                "pre_final_sara": ("04", "07"),
                "post_final_story": ("05", "05"),
                "post_final_lisa": ("05", "06"),
                "post_final_sara": ("05", "07"),
            }
            ending_tail_scenes = {
                "ending_credits": ("16", "01", "00", "00", "1"),
                "ending_end": ("16", "01", "00", "01", "2"),
                "ending_epilogue": ("00", "0C", "01", "01", "3"),
            }
            boss_scenes = {
                "boss_shalamar": (0x0C, 0),
                "boss_riff": (0x0D, 1),
                "boss_crystal_dragon": (0x0E, 2),
                "boss_cameo": (0x0F, 3),
                "boss_ted": (0x10, 4),
                "boss_troop": (0x11, 5),
                "boss_faze": (0x12, 6),
                "boss_angela": (0x13, 7),
                "boss_penta_dragon": (0x14, 8),
            }
            scene_checks = {
                "all 42 curated/generated states loaded": (
                    scene_audit_done.is_file()
                    and scene_audit_done.read_text().strip() == "ok"
                    and set(audited) == expected_scenes
                    and all(fields.get("ok") == "true" for fields in audited.values())
                ),
                "scene deck has expected game-state domains": (
                    audited.get("title", {}).get("ffc1") == "0"
                    and all(
                        audited.get(scene, {}).get("ffc1") == "0"
                        and audited.get(scene, {}).get("d880") == d880
                        and audited.get(scene, {}).get("ffba") == ffba
                        and audited.get(scene, {}).get("ffe4") == ffe4
                        for scene, (d880, ffba, ffe4) in story_scenes.items()
                    )
                    and all(
                        audited.get(scene, {}).get("dce8") == sequence
                        and audited.get(scene, {}).get("dcea") == "01"
                        and audited.get(scene, {}).get("dcf0") == art
                        and audited.get(scene, {}).get("dd07")
                        == f"{int(art, 16) - 1:02X}"
                        and audited.get(scene, {}).get("story_preview")
                        == "true"
                        and audited.get(scene, {}).get("story_top") == "160"
                        and audited.get(scene, {}).get("story_dialogue") == "200"
                        for scene, (sequence, art) in story_art_scenes.items()
                    )
                    and all(
                        audited.get(scene, {}).get("ffc1") == "0"
                        and audited.get(scene, {}).get("d880") == d880
                        and audited.get(scene, {}).get("ffe4") == "1"
                        and audited.get(scene, {}).get("d889") == d889
                        and audited.get(scene, {}).get("dce2") == dce2
                        and audited.get(scene, {}).get("fff9") == fff9
                        and audited.get(scene, {}).get("tail_preview")
                        == "true"
                        and audited.get(scene, {}).get("tail_cells") == "360"
                        and audited.get(scene, {}).get("tail_palette")
                        == palette
                        for scene, (
                            d880,
                            d889,
                            dce2,
                            fff9,
                            palette,
                        ) in ending_tail_scenes.items()
                    )
                    and all(
                        audited.get(scene, {}).get("ffc1") == "1"
                        for scene in expected_scenes
                        - {
                            "title",
                            *story_scenes.keys(),
                            *ending_tail_scenes.keys(),
                        }
                    )
                    and audited.get("gargoyle", {}).get("ffbf") == "01"
                    and audited.get("spider", {}).get("ffbf") == "02"
                    and audited.get("spiral", {}).get("ffc0") == "01"
                    and audited.get("shield", {}).get("ffc0") == "02"
                    and audited.get("jet", {}).get("ffd0") == "01"
                    and all(
                        audited.get(f"stage{stage}", {}).get("d880")
                        == f"{stage + 1:02X}"
                        for stage in range(2, 8)
                    )
                    and all(
                        audited.get(scene, {}).get("d880") == f"{d880:02X}"
                        # FFBA is consumed by the stock $1A2B dispatcher and
                        # becomes runtime scratch. D880 is the persistent boss
                        # identity used by the production colorizer.
                        for scene, (d880, _ffba) in boss_scenes.items()
                    )
                ),
                "every scene deck frame rendered": all(
                    Path(f"{scene_audit}.{scene}.png").is_file()
                    and Path(f"{scene_audit}.{scene}.png").stat().st_size > 100
                    for scene in expected_scenes
                ),
            }

            if not scene_checks["scene deck has expected game-state domains"]:
                print("Scene-domain audit (exact Lua receipt fields):")
                for scene in sorted(audited):
                    print(
                        f"  {scene}: "
                        + json.dumps(audited[scene], sort_keys=True)
                    )

            print(report)
            all_checks = {
                **ui_checks,
                **protocol_checks,
                **persistence_checks,
                **runtime_checks,
                **special_checks,
                **scene_checks,
            }
            for name, passed in all_checks.items():
                print(f"{'PASS' if passed else 'FAIL'}: {name}")
            if all(all_checks.values()):
                if args.keep_story_states:
                    destination = args.keep_story_states.resolve()
                    destination.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(
                        story_state_dir,
                        destination,
                        dirs_exist_ok=True,
                    )
                    print(f"Verified story states: {destination}")
                print("PASS: browser edits and scene deck reach FIXED.gb in mGBA.")
                return 0
            return 1
        finally:
            if emulator is not None:
                terminate(emulator)
            terminate(server)


if __name__ == "__main__":
    raise SystemExit(main())
