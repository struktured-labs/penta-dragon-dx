#!/usr/bin/env python3
"""Capture all 16 native miniboss descriptors under guarded mGBA.

Each run copies the candidate into repository-local scratch and transplants one
complete native five-entity descriptor into Stage 1's first miniboss section at
file offset 0x3402F.  Patching only DC04 creates a deterministic Frankenstein:
the selected miniboss's first entity plus Gargoyle entities 2-5.  The complete
descriptor keeps DC04:DC08 semantically valid while the source ROM remains
unchanged.  Two full passes must match exactly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any

from PIL import Image, ImageDraw
import yaml


ROOT = Path(__file__).resolve().parents[2]
MGBA = ROOT / "scripts/mgba-qt-singleflight"
PROBE = ROOT / "scripts/diagnostics/probe_all_minibosses_visual.lua"
PALETTE_YAML = ROOT / "palettes/penta_palettes_v097.yaml"
OWNER = ".penta-miniboss-audit-owned"
SPAWN_SELECTOR_OFFSET = 0x3402F
SPAWN_DESCRIPTOR_ORIGINAL = bytes(range(0x30, 0x35))
# First native occurrence of every complete descriptor.  These offsets come
# from the eight stock bank-13 level tables, not from a fabricated selector
# sequence.  Level/section metadata is retained in the receipt for review.
NATIVE_CONTEXTS = (
    (1, 2, 0x3402F), (1, 5, 0x3403E),
    (2, 2, 0x343F7), (2, 5, 0x34406),
    (3, 2, 0x3466E), (3, 5, 0x3467D),
    (4, 12, 0x34CA3), (4, 13, 0x34CA8),
    (5, 4, 0x34D2B), (5, 5, 0x34D30),
    (6, 4, 0x34E36), (6, 7, 0x34E45),
    (7, 4, 0x35049), (7, 5, 0x3504E),
    (8, 2, 0x3511E), (8, 5, 0x3512D),
)
BOSS_YAML_KEYS = (
    "Gargoyle", "Spider", "Boss3_Crimson", "Boss4_Ice", "Boss5_Void",
    "Boss6_Poison", "Boss7_Knight", "Angela",
)
BOSS_NAMES = (
    "Gargoyle", "Spider", "Crimson", "Ice", "Void", "Poison", "Knight",
    "Angela", "Boss 9 (unnamed)", "Boss 10 (unnamed)",
    "Boss 11 (unnamed)", "Boss 12 (unnamed)", "Boss 13 (unnamed)",
    "Boss 14 (unnamed)", "Boss 15 (unnamed)",
    "Boss 16 (unfinished / unnamed)",
)


def palette_source_index(boss_index: int) -> int:
    """Return the 1-based YAML row selected by the ROM's O(1) alias rule."""
    return ((boss_index - 1) & 0x07) + 1


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_report(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def bgr555_to_rgb(value: str) -> str:
    packed = int(value, 16)
    channels = (packed & 0x1F, (packed >> 5) & 0x1F, (packed >> 10) & 0x1F)
    return "#" + "".join(f"{round(channel * 255 / 31):02X}" for channel in channels)


def parse_oam(raw: str) -> list[dict[str, int]]:
    rows = []
    for record in raw.split(","):
        if not record:
            continue
        slot, x, y, tile, attr = record.split(":")
        rows.append({
            "slot": int(slot), "x": int(x), "y": int(y),
            "tile": int(tile, 16), "attr": int(attr, 16),
            "palette": int(attr, 16) & 7,
        })
    return rows


def capture_one(
    source_rom: bytes,
    boss_index: int,
    output: Path,
    replay: int,
    palette_document: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    dc04 = 0x30 + (boss_index - 1) * 5
    source_index = palette_source_index(boss_index)
    palette_key = BOSS_YAML_KEYS[source_index - 1]
    palette_source = palette_document["boss_palettes"][palette_key]
    level, section, descriptor_offset = NATIVE_CONTEXTS[boss_index - 1]
    descriptor = source_rom[descriptor_offset:descriptor_offset + 5]
    expected_descriptor = bytes(range(dc04, dc04 + 5))
    if descriptor != expected_descriptor:
        raise RuntimeError(
            f"FFBF={boss_index} native descriptor drift at "
            f"0x{descriptor_offset:X}: {descriptor.hex(' ')} != "
            f"{expected_descriptor.hex(' ')}"
        )
    patched = bytearray(source_rom)
    patched[SPAWN_SELECTOR_OFFSET:SPAWN_SELECTOR_OFFSET + 5] = descriptor
    stem = f"miniboss-{boss_index:02d}.r{replay}"
    screenshot = output / f"{stem}.png"
    report = output / f"{stem}.txt"
    stdout = output / f"{stem}.stdout.txt"
    with tempfile.NamedTemporaryFile(suffix=".gb", dir=ROOT / "tmp") as rom_file:
        rom_file.write(patched)
        rom_file.flush()
        environment = os.environ.copy()
        environment.update({
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "PENTA_MINIBOSS_INDEX": str(boss_index),
            "PENTA_MINIBOSS_PALETTE_SLOT": str(
                int(palette_source["slot"])
            ),
            "PENTA_MINIBOSS_REPORT": str(report),
            "PENTA_MINIBOSS_SCREENSHOT": str(screenshot),
        })
        with stdout.open("w") as stream:
            process = subprocess.Popen(
                [
                    str(MGBA), "--fastforward", "--script", str(PROBE),
                    rom_file.name,
                ],
                cwd=ROOT,
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
            deadline = time.monotonic() + timeout
            completed_report = False
            while time.monotonic() < deadline:
                returncode = process.poll()
                if report.is_file():
                    completed_report = True
                    break
                if returncode is not None:
                    if returncode == 75:
                        raise SystemExit(75)
                    break
                time.sleep(0.02)

            # The Lua shutdown APIs in this mGBA build either hang or
            # intermittently segfault.  Once the probe closes its report, stop
            # only the exact single-flight child owned by this verifier.  The
            # wrapper execs mGBA, so this PID remains the owned emulator PID.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            returncode = process.returncode
            if not completed_report:
                raise RuntimeError(
                    f"FFBF={boss_index} ended without a report (status "
                    f"{returncode}); see {stdout}"
                )
    if not report.is_file() or not screenshot.is_file():
        detail = parse_report(report) if report.is_file() else {}
        raise RuntimeError(
            f"FFBF={boss_index} replay {replay} incomplete: {detail}; "
            f"see {stdout}"
        )
    result = parse_report(report)
    if result.get("status") != "pass" or int(result.get("FFBF", "0"), 16) != boss_index:
        raise RuntimeError(f"FFBF={boss_index} invalid report: {result}")
    observed_descriptor = bytes.fromhex(result.get("descriptor", ""))
    if observed_descriptor != descriptor:
        raise RuntimeError(
            f"FFBF={boss_index} loaded DC04:DC08 "
            f"{observed_descriptor.hex(' ')} instead of native "
            f"{descriptor.hex(' ')}"
        )
    words = [str(value) for value in palette_source["colors"]]
    expected = {
        "yaml_key": palette_key,
        "source_selector": source_index,
        "aliased": boss_index != source_index,
        "slot": int(palette_source["slot"]),
        "colors_bgr555": words,
        "colors_rgb888": [bgr555_to_rgb(value) for value in words],
    }
    with Image.open(screenshot) as image:
        if image.size != (160, 144):
            raise RuntimeError(f"FFBF={boss_index} screenshot size is {image.size}")
        image.verify()
    oam = parse_oam(result.get("boss_oam", ""))
    return {
        "ffbf": boss_index,
        "dc04": dc04,
        "name": BOSS_NAMES[boss_index - 1],
        "native_context": {
            "level": level,
            "section": section,
            "descriptor_offset": descriptor_offset,
            "descriptor": descriptor.hex(" ").upper(),
        },
        "gameplay_frame": int(result["gameplay_at"]),
        "spawn_frame": int(result["spawn_at"]),
        "capture_frame": int(result.get("screenshot_at", result["frame"])),
        "exit_frame": int(result["frame"]),
        "scene": int(result["D880"], 16),
        "screenshot": str(screenshot),
        "screenshot_sha256": digest(screenshot),
        "visible_boss_oam": oam,
        "hardware_palette_slots": sorted({row["palette"] for row in oam}),
        "selected_expected_palette_sprite_count": int(
            result.get("selected_expected_count", "0")
        ),
        "selected_center_distance": int(
            result.get("selected_center_distance", "0")
        ),
        "expected_palette": expected,
        "palette_status": "aliased" if expected["aliased"] else "defined",
    }


def stable(row: dict[str, Any]) -> dict[str, Any]:
    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: clean(item) for key, item in value.items()
                if key not in ("screenshot",)
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    return clean(row)


def create_contact_sheet(entries: list[dict[str, Any]], output: Path) -> None:
    columns, label_height = 4, 30
    sheet = Image.new("RGB", (640, 4 * (144 + label_height)), "black")
    draw = ImageDraw.Draw(sheet)
    for position, entry in enumerate(entries):
        x = position % columns * 160
        y = position // columns * (144 + label_height)
        with Image.open(str(entry["screenshot"])) as source:
            sheet.paste(source.convert("RGB"), (x, y + label_height))
        palette = entry["expected_palette"]
        expected = (
            f"OBJ{palette['slot']} {palette['yaml_key']}"
            + (
                f" (alias {palette['source_selector']:02d})"
                if palette["aliased"] else ""
            )
        )
        draw.text((x + 2, y + 2), f"{entry['ffbf']:02d} {entry['name']}", fill="white")
        draw.text(
            (x + 2, y + 16), expected,
            fill="#77edaa",
        )
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/visual-audit-evidence/minibosses",
    )
    parser.add_argument("--determinism-replays", type=int, choices=(1, 2), default=2)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--indices",
        default="1-16",
        help="selector range for targeted diagnosis (default: 1-16)",
    )
    args = parser.parse_args()
    if args.indices == "1-16":
        indices = list(range(1, 17))
    else:
        try:
            indices = sorted({int(value) for value in args.indices.split(",")})
        except ValueError as exc:
            raise SystemExit("--indices must be 1-16 or comma-separated integers") from exc
        if not indices or any(index < 1 or index > 16 for index in indices):
            raise SystemExit("--indices values must be between 1 and 16")
    rom = args.rom.resolve()
    output = args.output.resolve()
    allowed = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    if not any(output.is_relative_to(root) for root in allowed):
        raise SystemExit("output must be under repo tmp/ or /mnt/data/tmp/")
    output.mkdir(parents=True, exist_ok=True)
    marker = output / OWNER
    if any(output.iterdir()) and not marker.is_file():
        raise SystemExit(f"refusing to replace unowned output: {output}")
    marker.write_text("penta-miniboss-visual-audit-v1\n")
    for path in output.iterdir():
        if path != marker and path.is_file():
            path.unlink()

    source_rom = rom.read_bytes()
    if source_rom[SPAWN_SELECTOR_OFFSET:SPAWN_SELECTOR_OFFSET + 5] != SPAWN_DESCRIPTOR_ORIGINAL:
        raise SystemExit(
            f"unexpected Stage 1 descriptor at 0x{SPAWN_SELECTOR_OFFSET:X}: "
            f"{source_rom[SPAWN_SELECTOR_OFFSET:SPAWN_SELECTOR_OFFSET + 5].hex(' ')}"
        )
    palettes = yaml.safe_load(PALETTE_YAML.read_text())
    passes: list[list[dict[str, Any]]] = []
    try:
        for replay in range(1, args.determinism_replays + 1):
            rows = []
            for index in indices:
                row = capture_one(source_rom, index, output, replay, palettes, args.timeout)
                rows.append(row)
                print(
                    f"replay {replay}: FFBF={index:02d} frame "
                    f"{row['capture_frame']} sprites={len(row['visible_boss_oam'])}",
                    flush=True,
                )
            passes.append(rows)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    exact = len(passes) == 1 or all(
        stable(first) == stable(second)
        for first, second in zip(passes[0], passes[1], strict=True)
    )
    failures = []
    if not exact:
        failures.append("two complete 16-index capture passes differ")
    for row in passes[0]:
        expected = row["expected_palette"]
        if not row["visible_boss_oam"]:
            failures.append(f"FFBF={row['ffbf']} has no visible boss OAM")
        if expected["slot"] not in row["hardware_palette_slots"]:
            failures.append(
                f"FFBF={row['ffbf']} expected OBJ{expected['slot']}, "
                f"saw {row['hardware_palette_slots']}"
            )
        if row["selected_expected_palette_sprite_count"] < 4:
            failures.append(
                f"FFBF={row['ffbf']} has only "
                f"{row['selected_expected_palette_sprite_count']} visible "
                f"sprites in expected OBJ{expected['slot']}"
            )
    # Stable public names omit replay suffix; the replay-1 images are the
    # canonical, hash-verified human evidence.
    for row in passes[0]:
        canonical = output / f"miniboss-{row['ffbf']:02d}.png"
        canonical.write_bytes(Path(str(row["screenshot"])).read_bytes())
        row["screenshot"] = str(canonical)
        row["screenshot_sha256"] = digest(canonical)
    contact_sheet = output / "miniboss-contact-sheet.png"
    create_contact_sheet(passes[0], contact_sheet)
    receipt = {
        "schema": "penta-dragon-dx-miniboss-visual-audit-v1",
        "status": "failed" if failures else "ok",
        "rom": str(rom),
        "rom_sha256": digest(rom),
        "palette_yaml_sha256": digest(PALETTE_YAML),
        "determinism_replays": args.determinism_replays,
        "deterministic_replay_exact": exact,
        "replay_screenshot_sha256": [
            row["screenshot_sha256"] for row in passes[-1]
        ],
        "capture_method": {
            "emulator": "guarded-mgba-qt-offscreen",
            "temporary_descriptor_patch_offset": SPAWN_SELECTOR_OFFSET,
            "source_descriptor": SPAWN_DESCRIPTOR_ORIGINAL.hex(" ").upper(),
            "native_descriptor_offsets": [row[2] for row in NATIVE_CONTEXTS],
            "source_rom_modified": False,
        },
        "captured": len(passes[0]),
        "expected": len(indices),
        "indices": indices,
        "defined_palette_source_rows": 8,
        "direct_palette_selectors": list(range(1, 9)),
        "aliased_palette_selectors": {
            str(index): palette_source_index(index) for index in range(9, 17)
        },
        "undefined_palette_selectors": [],
        "contact_sheet": str(contact_sheet),
        "contact_sheet_sha256": digest(contact_sheet),
        "entries": passes[0],
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "status": receipt["status"], "captured": receipt["captured"],
        "deterministic_replay_exact": exact, "failures": failures,
        "receipt": str(receipt_path),
    }, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
