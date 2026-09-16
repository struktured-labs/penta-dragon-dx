#!/usr/bin/env python3
"""Require every visible Window tile and VBK1 attribute to match."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from menu_icon_colorization import build_menu_lut  # noqa: E402
from menu_commit_protocol import authenticate as authenticate_commit_protocol


PROBE = Path(__file__).with_name("probe_menu_window_order.lua")
MGBA = ROOT / "scripts/mgba-qt-singleflight"
CONTENT_FIXTURE = (
    Path(__file__).with_name("fixtures")
    / "stage1_menu_window_content.json"
)
CONTENT_FIXTURE_SHA256 = (
    "036abc39b74c1804a87fa41ae6fdd3d66656fef75242a87f7e2745618d937a6b"
)
CONTENT_FIXTURE_SCHEMA = "penta-stage1-menu-window-content-v1"
BANK_SIZE = 0x4000
BANK13_LUT = 13 * BANK_SIZE + (0x7000 - 0x4000)
MENU_FIRST_ENTRY = 0x1B48
MENU_WRAPPER_PREFIX = bytes.fromhex(
    "F0 99 F5 3E 14 CD 61 00 CD 00 40"
)
BANK31_OFFSET = 31 * BANK_SIZE - 0x4000
MENU_EXIT_OFFSET = BANK31_OFFSET + 0x6CE2
MENU_WRAPPER_TAIL_OFFSET = BANK31_OFFSET + 0x6EE5
MENU_ATOMIC_EXIT_OFFSET = BANK31_OFFSET + 0x6EF0
MENU_EXIT_EARLY_EI = bytes.fromhex("E1 F1 AF E0 E4 C3 9A 09")
MENU_WRAPPER_TAIL_EARLY_EI = bytes.fromhex(
    "F1 CB AF E0 40 FB C3 E2 6C"
)
MENU_EXIT_ATOMIC_JUMP = bytes.fromhex("E1 F1 C3 F0 6E 00 00 00")
MENU_WRAPPER_TAIL_ATOMIC = bytes.fromhex(
    "F1 CB AF E0 40 00 C3 E2 6C"
)
MENU_ATOMIC_EXIT = bytes.fromhex(
    "AF E0 E4 F0 40 CB AF E0 40 AF FB C3 9A 09"
)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_content_fixture(
    path: Path = CONTENT_FIXTURE,
) -> tuple[dict, bytes, bytes]:
    """Load the reviewed native HUD oracle independently of live WRAM."""
    payload = path.read_bytes()
    if sha256_bytes(payload) != CONTENT_FIXTURE_SHA256:
        raise ValueError("menu content fixture identity changed")
    fixture = json.loads(payload)
    if set(fixture) != {
        "schema", "route", "tile_rows", "raster", "reviewed_evidence"
    }:
        raise ValueError("menu content fixture schema changed")
    if fixture["schema"] != CONTENT_FIXTURE_SCHEMA:
        raise ValueError("menu content fixture has the wrong schema")
    rows = fixture["tile_rows"]
    if not isinstance(rows, list) or len(rows) != 6:
        raise ValueError("menu content fixture must contain six tile rows")
    expected = bytearray()
    mask = bytearray()
    for row in rows:
        cells = row.split() if isinstance(row, str) else []
        if len(cells) != 20:
            raise ValueError("menu content fixture rows must be 20 cells wide")
        for cell in cells:
            if cell == "??":
                expected.append(0)
                mask.append(0)
            elif re.fullmatch(r"[0-9A-F]{2}", cell):
                expected.append(int(cell, 16))
                mask.append(1)
            else:
                raise ValueError("menu content fixture has an invalid tile")
    if sum(mask) < 80:
        raise ValueError("menu content fixture has insufficient fixed coverage")
    raster = fixture["raster"]
    if set(raster) != {
        "native_size", "sample_visible_ages", "regions",
        "expected_rgb_sha256",
    }:
        raise ValueError("menu raster fixture schema changed")
    if raster["native_size"] != [160, 144]:
        raise ValueError("menu raster fixture has a non-native frame size")
    ages = raster["sample_visible_ages"]
    if ages != [1, 8, 32, 64, 96, 128, 160]:
        raise ValueError("menu raster fixture sampling schedule changed")
    regions = raster["regions"]
    if not isinstance(regions, list) or not regions:
        raise ValueError("menu raster fixture has no invariant regions")
    for region in regions:
        if (
            not isinstance(region, list) or len(region) != 4
            or not all(isinstance(value, int) for value in region)
            or not (0 <= region[0] < region[2] <= 160)
            or not (0 <= region[1] < region[3] <= 144)
        ):
            raise ValueError("menu raster fixture has an invalid region")
    if re.fullmatch(r"[0-9a-f]{64}", raster["expected_rgb_sha256"]) is None:
        raise ValueError("menu raster fixture hash is malformed")
    return fixture, bytes(expected), bytes(mask)


def content_raster_receipt(trace: str, fixture: dict) -> dict[str, object]:
    """Check sampled rendered HUD regions, not merely tilemap agreement."""
    raster = fixture["raster"]
    expected_ages = raster["sample_visible_ages"]
    expected_hash = raster["expected_rgb_sha256"]
    expected_size = tuple(raster["native_size"])
    entries: list[tuple[int, int, Path]] = []
    malformed = False
    for item in filter(None, trace.split(";")):
        match = re.fullmatch(r"f(\d+):a(\d+):p(.+)", item)
        if match is None:
            malformed = True
            continue
        entries.append((int(match.group(1)), int(match.group(2)), Path(match.group(3))))
    failures = []
    observed_ages = [age for _, age, _ in entries]
    if malformed or observed_ages != expected_ages:
        failures.append({
            "reason": "raster sample schedule mismatch",
            "observed_ages": observed_ages,
        })
    for frame, age, path in entries:
        if not path.is_file():
            failures.append({
                "frame": frame, "age": age, "path": str(path),
                "reason": "missing raster sample",
            })
            continue
        with Image.open(path) as source:
            image = source.convert("RGB")
            if image.size != expected_size:
                failures.append({
                    "frame": frame, "age": age, "path": str(path),
                    "reason": "non-native raster sample",
                })
                continue
            payload = b"".join(
                image.crop(tuple(region)).tobytes()
                for region in raster["regions"]
            )
        actual_hash = sha256_bytes(payload)
        if actual_hash != expected_hash:
            failures.append({
                "frame": frame, "age": age, "path": str(path),
                "reason": "rendered fixed HUD pixels differ",
                "actual_rgb_sha256": actual_hash,
            })
    return {
        "checked_frames": len(entries),
        "bad_frames": len(failures),
        "expected_rgb_sha256": expected_hash,
        "first_bad": failures[0] if failures else None,
        "passed": not failures,
    }


def expected_window_lut(rom: bytes) -> tuple[bytes, str]:
    """Return the independent per-tile Window attribute oracle."""
    canonical = rom[BANK13_LUT:BANK13_LUT + 0x100]
    if len(canonical) != 0x100:
        raise ValueError("candidate ROM is missing the canonical BG LUT")
    publisher_present = rom[
        MENU_FIRST_ENTRY:MENU_FIRST_ENTRY + len(MENU_WRAPPER_PREFIX)
    ] == MENU_WRAPPER_PREFIX
    if not publisher_present:
        return bytes(0x100), "neutral"
    return build_menu_lut(canonical), "canonical"


def menu_close_atomicity(rom: bytes) -> str:
    """Classify the reviewed Scene-$0B menu-close interrupt boundary."""
    wrapper = rom[
        MENU_WRAPPER_TAIL_OFFSET:
        MENU_WRAPPER_TAIL_OFFSET + len(MENU_WRAPPER_TAIL_EARLY_EI)
    ]
    exit_code = rom[
        MENU_EXIT_OFFSET:MENU_EXIT_OFFSET + len(MENU_EXIT_EARLY_EI)
    ]
    helper = rom[
        MENU_ATOMIC_EXIT_OFFSET:MENU_ATOMIC_EXIT_OFFSET + len(MENU_ATOMIC_EXIT)
    ]
    if (wrapper == MENU_WRAPPER_TAIL_ATOMIC
            and exit_code == MENU_EXIT_ATOMIC_JUMP
            and helper == MENU_ATOMIC_EXIT):
        return "atomic-owner-clear-window-hide-before-ei"
    if (wrapper == MENU_WRAPPER_TAIL_EARLY_EI
            and exit_code == MENU_EXIT_EARLY_EI):
        return "unsafe-ei-before-owner-clear"
    return "unclassified-legacy"


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=1280)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--key", choices=("select", "start", "combo"), default="select"
    )
    parser.add_argument("--open-frame", type=int, default=1200)
    parser.add_argument("--close-frame", type=int, default=-1)
    parser.add_argument("--save-fixture", type=Path)
    parser.add_argument(
        "--move",
        choices=("none", "right", "left", "up", "down"),
        default="none",
    )
    parser.add_argument("--fire-every", type=int, default=0)
    parser.add_argument("--inject-stale-frame", type=int, default=-1)
    parser.add_argument("--force-map-alias-frame", type=int, default=-1)
    parser.add_argument("--force-map-commit-frame", type=int, default=-1)
    parser.add_argument(
        "--inject-stale-scene",
        type=lambda value: int(value, 0),
        help="scene byte to use for a stale-Window boundary fixture",
    )
    args = parser.parse_args()
    if args.inject_stale_scene is not None and not 0 <= args.inject_stale_scene <= 0xFF:
        parser.error("--inject-stale-scene must fit in one byte")
    if args.inject_stale_scene is not None and args.inject_stale_frame < 0:
        parser.error("--inject-stale-scene requires --inject-stale-frame")

    rom = args.rom.resolve()
    if not rom.is_file():
        parser.error(f"ROM not found: {rom}")
    rom_bytes = rom.read_bytes()
    rom_sha256 = sha256_bytes(rom_bytes)
    close_atomicity = menu_close_atomicity(rom_bytes)
    if close_atomicity == "unsafe-ei-before-owner-clear":
        print(
            "FAIL: native menu close enables interrupts before FFE4 "
            "relinquishes Window ownership"
        )
        return 1
    try:
        commit_protocol = (
            authenticate_commit_protocol(rom_bytes)
            if args.force_map_commit_frame >= 0 else None
        )
        menu_lut, menu_mode = expected_window_lut(rom_bytes)
        content_fixture, content_expected, content_mask = (
            load_content_fixture()
        )
    except (AssertionError, ValueError) as error:
        parser.error(str(error))

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    screenshot = output.with_suffix(".first_visible.png")
    for stale in (
        screenshot,
        Path(str(output) + ".first_attr_bad.png"),
        Path(str(output) + ".window_attrs.bin"),
        Path(str(output) + ".expected_attrs.bin"),
        Path(str(output) + ".first_post_close_alias.png"),
    ):
        stale.unlink(missing_ok=True)
    for stale in output.parent.glob(f"{output.name}.content-f*.png"):
        stale.unlink(missing_ok=True)

    runtime = output.parent / f"{output.stem}.runtime"
    runtime.mkdir(exist_ok=True)
    runtime_rom = runtime / "candidate.gb"
    (runtime / "candidate.sav").unlink(missing_ok=True)
    (runtime / "candidate.gb.ram").unlink(missing_ok=True)
    shutil.copy2(rom, runtime_rom)
    if sha256_bytes(runtime_rom.read_bytes()) != rom_sha256:
        raise RuntimeError("isolated runtime ROM does not match the candidate")
    menu_lut_path = runtime / "menu-window-lut.bin"
    menu_lut_path.write_bytes(menu_lut)
    content_expected_path = runtime / "menu-window-content-expected.bin"
    content_mask_path = runtime / "menu-window-content-mask.bin"
    content_expected_path.write_bytes(content_expected)
    content_mask_path.write_bytes(content_mask)
    if args.save_fixture:
        shutil.copy2(args.save_fixture.resolve(), runtime / "candidate.sav")
    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "MENU_WINDOW_ORDER_OUT": str(output),
            "MENU_WINDOW_ORDER_SCREENSHOT": str(screenshot),
            "MENU_WINDOW_ORDER_FRAMES": str(args.frames),
            "MENU_WINDOW_ORDER_KEY": args.key,
            "MENU_WINDOW_ORDER_OPEN_FRAME": str(args.open_frame),
            "MENU_WINDOW_ORDER_CLOSE_FRAME": str(args.close_frame),
            "MENU_WINDOW_ORDER_MOVE": args.move,
            "MENU_WINDOW_ORDER_FIRE_EVERY": str(args.fire_every),
            "MENU_WINDOW_ORDER_STALE_FRAME": str(args.inject_stale_frame),
            "MENU_WINDOW_ORDER_STALE_SCENE": (
                "" if args.inject_stale_scene is None
                else str(args.inject_stale_scene)
            ),
            "MENU_WINDOW_ORDER_FORCE_ALIAS_FRAME": str(
                args.force_map_alias_frame
            ),
            "MENU_WINDOW_ORDER_FORCE_COMMIT_FRAME": str(
                args.force_map_commit_frame
            ),
            "MENU_WINDOW_ORDER_COMMIT_PROTOCOL": (
                commit_protocol['name'] if commit_protocol else ''
            ),
            "MENU_WINDOW_ORDER_COMMIT_POST_PC": str(
                commit_protocol['post_pc'] if commit_protocol else 0
            ),
            "MENU_WINDOW_ORDER_ATTR_LUT": str(menu_lut_path),
            "MENU_WINDOW_ORDER_ATTR_LUT_SHA256": sha256_bytes(menu_lut),
            "MENU_WINDOW_ORDER_ATTR_MODE": menu_mode,
            "MENU_WINDOW_ORDER_CONTENT_EXPECTED": str(
                content_expected_path
            ),
            "MENU_WINDOW_ORDER_CONTENT_MASK": str(content_mask_path),
            "MENU_WINDOW_ORDER_CONTENT_FIXTURE_SHA256": (
                CONTENT_FIXTURE_SHA256
            ),
            "MENU_WINDOW_ORDER_CONTENT_SCREENSHOT_PREFIX": (
                str(output) + ".content"
            ),
            "MENU_WINDOW_ORDER_CONTENT_SAMPLE_AGES": ",".join(
                str(age)
                for age in content_fixture["raster"][
                    "sample_visible_ages"
                ]
            ),
            "MENU_WINDOW_ORDER_ROM": str(rom),
            "MENU_WINDOW_ORDER_ROM_SHA256": rom_sha256,
        }
    )
    command = [
        str(MGBA),
        "--fastforward",
        str(runtime_rom),
        "--script",
        str(PROBE),
        "-C",
        f"savegamePath={runtime}",
    ]
    completed: subprocess.CompletedProcess[bytes] | None = None
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pass
    if not output.is_file():
        print(f"FAIL: no report within {args.timeout:.1f}s")
        if completed is not None:
            print(f"emulator_exit_status={completed.returncode}")
            if completed.stdout:
                print("emulator_stdout=" + completed.stdout.decode(
                    errors="replace").strip())
            if completed.stderr:
                print("emulator_stderr=" + completed.stderr.decode(
                    errors="replace").strip())
        return 1

    report = parse_report(output)
    if args.inject_stale_frame < 0:
        raster_receipt = content_raster_receipt(
            report.get("content_raster_trace", ""), content_fixture
        )
    else:
        raster_receipt = {
            "checked_frames": 0,
            "bad_frames": 0,
            "expected_rgb_sha256": content_fixture["raster"][
                "expected_rgb_sha256"
            ],
            "first_bad": None,
            "passed": True,
        }
    with output.open("a") as handle:
        handle.write(
            "content_raster_checked_frames="
            f"{raster_receipt['checked_frames']}\n"
        )
        handle.write(
            "content_raster_bad_frames="
            f"{raster_receipt['bad_frames']}\n"
        )
        handle.write(
            "content_raster_invariant_sha256="
            f"{raster_receipt['expected_rgb_sha256']}\n"
        )
        first_raster_bad = raster_receipt["first_bad"]
        handle.write(
            "first_content_raster_bad="
            + (
                "none" if first_raster_bad is None
                else json.dumps(first_raster_bad, sort_keys=True)
            )
            + "\n"
        )
    report = parse_report(output)
    print(f"ROM: {rom}")
    print(f"menu_close_atomicity={close_atomicity}")
    for key, value in report.items():
        print(f"{key}={value}")
    if int(report.get("window_frames", "0")) == 0:
        print("FAIL: SELECT route never exposed the hardware Window")
        return 1
    if report.get("rom") != str(rom):
        print("FAIL: Window receipt is not bound to the candidate ROM path")
        return 1
    if report.get("rom_sha256") != rom_sha256:
        print("FAIL: Window receipt is not bound to the candidate ROM hash")
        return 1
    expected_route = {
        "route_frame_limit": args.frames,
        "route_open_frame": args.open_frame,
        "route_close_frame": args.close_frame,
        "route_force_alias_frame": args.force_map_alias_frame,
        "route_force_commit_frame": args.force_map_commit_frame,
        "route_stale_frame": args.inject_stale_frame,
    }
    if any(
        report.get(field) != str(expected)
        for field, expected in expected_route.items()
    ):
        print("FAIL: Window receipt route does not match the requested route")
        return 1
    if report.get("attr_lut_sha256") != sha256_bytes(menu_lut):
        print("FAIL: Window receipt used the wrong attribute oracle")
        return 1
    if report.get("attr_mode") != menu_mode:
        print("FAIL: Window receipt used the wrong menu-color mode")
        return 1
    window_frames = int(report.get("window_frames", "0"))
    if report.get("content_fixture_sha256") != CONTENT_FIXTURE_SHA256:
        print("FAIL: Window receipt used the wrong native HUD content fixture")
        return 1
    expected_content_mode = (
        "native-fixture" if args.inject_stale_frame < 0
        else "disabled-stale-injection"
    )
    if report.get("content_mode") != expected_content_mode:
        print("FAIL: Window receipt used the wrong HUD content mode")
        return 1
    if args.inject_stale_frame < 0:
        if int(report.get("content_checked_frames", "-1")) != window_frames:
            print("FAIL: native HUD tile fixture did not cover every Window frame")
            return 1
        if (
            int(report.get("content_bad_frames", "-1")) != 0
            or int(report.get("content_source_mismatch_cells", "-1")) != 0
            or int(report.get("content_window_mismatch_cells", "-1")) != 0
        ):
            print(
                "FAIL: visible menu is blank or differs from the independent "
                "native HUD tile fixture"
            )
            return 1
        if not raster_receipt["passed"]:
            print(
                "FAIL: visible menu raster is blank/white or differs in its "
                "fixed labels, borders, or palette"
            )
            return 1
    attr_checked_frames = int(report.get("attr_checked_frames", "-1"))
    if attr_checked_frames != window_frames:
        print(
            "FAIL: visible Window VBK1 coverage is incomplete "
            f"({attr_checked_frames}/{window_frames} frames)"
        )
        return 1
    allowed_attr_bad_frames = 1 if args.inject_stale_frame >= 0 else 0
    if int(report.get("attr_bad_frames", "0")) > allowed_attr_bad_frames:
        print(
            "FAIL: visible Window used stale, unsafe, or noncanonical "
            "palette attributes"
        )
        return 1
    if args.inject_stale_frame < 0:
        if int(report.get("attr_entry_frames", "0")) == 0:
            print("FAIL: no Window-entry attribute frame was checked")
            return 1
        if int(report.get("attr_settled_frames", "0")) == 0:
            print("FAIL: no settled Window attribute frame was checked")
            return 1
        if args.close_frame >= 0 and (
            int(report.get("attr_exit_frames", "0")) == 0
            and int(report.get("window_hidden_at_close_frames", "0")) == 0
        ):
            print("FAIL: menu-exit Window attribute boundary was not observed")
            return 1
    allowed_bad_frames = 1 if args.inject_stale_frame >= 0 else 0
    if int(report.get("bad_frames", "0")) > allowed_bad_frames:
        print(
            "FAIL: visible hardware Window did not match the native "
            "C4E0 HUD buffer"
        )
        return 1
    # The stale-Window mutation deliberately exposes one aliased frame. Its
    # contract is that the next VBlank hides it, so count that injected frame
    # here and let the recovery checks below fail closed on persistence.
    allowed_alias_frames = 1 if (
        args.force_map_alias_frame >= 0 or args.inject_stale_frame >= 0
    ) else 0
    if int(report.get("map_alias_frames", "0")) > allowed_alias_frames:
        print(
            "FAIL: item Window aliases the displayed gameplay BG map; "
            "menu rows can overwrite the level"
        )
        return 1
    if (
        args.close_frame >= 0
        and int(report.get("window_frames_after_close", "0")) != 0
    ):
        print("FAIL: hardware Window remained visible after closing the menu")
        return 1
    if args.close_frame >= 0:
        if int(report.get("post_close_selector_checked_frames", "0")) == 0:
            print("FAIL: no stationary post-close selector frame was checked")
            return 1
        if int(report.get("post_close_selector_alias_frames", "0")) != 0:
            print(
                "FAIL: post-close gameplay BG aliases the former Window map; "
                "red/green menu rows can remain visible until movement"
            )
            return 1
        if int(report.get("post_close_hud_leak_frames", "0")) != 0:
            print("FAIL: native item HUD rows leaked into post-close gameplay")
            return 1
    if args.force_map_commit_frame >= 0:
        if report.get("forced_commit_protocol") != commit_protocol['name']:
            print("FAIL: completed-map fixture used an unauthenticated protocol")
            return 1
        if report.get("forced_commit") != "1":
            print("FAIL: completed-map close-edge fixture was not injected")
            return 1
        if report.get("forced_commit_consumed") != "1":
            print("FAIL: ROM never consumed the close-edge map transaction")
            return 1
    if args.inject_stale_frame >= 0:
        if report.get("stale_injected") != "1":
            print("FAIL: stale-Window fixture was not injected")
            return 1
        expected_scene = (
            "native" if args.inject_stale_scene is None
            else f"{args.inject_stale_scene:02X}"
        )
        if report.get("stale_scene") != expected_scene:
            print("FAIL: stale-Window fixture used the wrong scene")
            return 1
        if int(report.get("stale_window_frames_after_grace", "-1")) != 0:
            print("FAIL: stale gameplay Window survived the next VBlank")
            return 1
    if args.inject_stale_frame >= 0:
        print("PASS: stale gameplay Window was hidden by the next VBlank.")
    else:
        print(
            "PASS: every visible Window frame matched the native 6x20 HUD "
            "tile fixture, rendered-pixel fixture, and candidate palette LUT."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
