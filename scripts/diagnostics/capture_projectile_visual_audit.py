#!/usr/bin/env python3
"""Capture eight deterministic projectile/effect fixtures under mGBA."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

import yaml
from PIL import Image

from normalize_mgba_state_pc import normalize


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_projectile_visual_audit.lua"
MGBA = ROOT / "scripts/mgba-qt-singleflight"
STATES = ROOT / "save_states_for_claude"
PALETTES = ROOT / "palettes/penta_palettes_v097.yaml"
OWNER = ".penta-projectile-audit-owned"
SPAWN_SELECTOR_OFFSET = 0x3402F
SPAWN_DESCRIPTOR_ORIGINAL = bytes(range(0x30, 0x35))
# Complete native five-entity descriptors.  A one-byte DC04 selector patch is
# invalid: it creates the requested first entity followed by four entities
# from Stage 1's Gargoyle descriptor.
NATIVE_DESCRIPTOR_OFFSETS = {
    2: 0x3403E,
}

SCENARIOS = (
    {
        "id": "sara_w", "label": "Sara W shot",
        "state": "level1_sara_w_alone.ss0", "tiles": (0x01, 0x01),
        "boss": 0, "powerup": 0, "input_mask": 0x01,
        "state_mode": "retarget",
        "normalize_instances": 1,
        "expected_slot": 0,
        "palette_row": "obj_palettes.EnemyProjectile",
    },
    {
        "id": "sara_d", "label": "Sara D breath / attack",
        "state": "level1_sara_d_alone.ss0", "tiles": (0x2C, 0x2F),
        "boss": 0, "powerup": 0, "input_mask": 0x01,
        "state_mode": "current",
        "min_matches": 4,
        "expected_slot": 1,
        "palette_row": "obj_palettes.SaraDragon",
    },
    {
        "id": "enemy", "label": "Enemy projectile",
        "state": "level1_sara_w_4_hornets.ss0", "tiles": (0x0F, 0x0F),
        "boss": 0, "powerup": 0, "input_mask": 0x00,
        "state_mode": "current",
        "normalize_instances": 1,
        "expected_slot": 0,
        "palette_row": "obj_palettes.EnemyProjectile",
    },
    {
        "id": "spider", "label": "Spider orbiting attack",
        "selector": 2, "tiles": (0x00, 0xFF), "oam_slots": (32, 39),
        "boss": 2, "powerup": 0, "input_mask": 0x00,
        "min_matches": 8,
        "expected_slot": 7,
        "palette_row": "boss_palettes.Spider",
    },
    {
        "id": "effects", "label": "Sara W weapon / hit effect",
        "state": "level1_sara_w_4_hornets.ss0", "tiles": (0x12, 0x15),
        "boss": 0, "powerup": 0, "input_mask": 0x01,
        "state_mode": "current",
        "min_matches": 4,
        "expected_slot": 2,
        "palette_row": "obj_palettes.SaraWitch",
    },
    {
        "id": "spiral", "label": "Spiral weapon",
        "state": "level1_sara_w_alone.ss0", "tiles": (0x02, 0x02),
        "boss": 0, "powerup": 1, "input_mask": 0x01,
        "state_mode": "retarget",
        "min_matches": 3,
        "normalize_instances": 1,
        "expected_slot": 0,
        "palette_row": "powerup_palettes.SpiralProjectile",
    },
    {
        "id": "shield", "label": "Shield weapon",
        "state": "level1_sara_w_alone.ss0", "tiles": (0x03, 0x03),
        "boss": 0, "powerup": 2, "input_mask": 0x01,
        "state_mode": "retarget",
        "min_matches": 4,
        "max_oam_span": 16,
        "expected_slot": 0,
        "palette_row": "powerup_palettes.ShieldProjectile",
    },
    {
        "id": "turbo", "label": "Turbo palette guard (no natural active fixture)",
        "state": "level1_sara_d_turbo_powerup_health1_item.ss0",
        "tiles": (0x00, 0x00),
        "boss": 0, "powerup": 3, "input_mask": 0x01,
        "state_mode": "retarget",
        "settle": 30,
        "palette_only_slot": 0,
        "expected_slot": 0,
        "palette_row": "powerup_palettes.TurboProjectile",
    },
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_report(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def palette_bytes(document: dict[str, Any], dotted: str) -> str:
    value: Any = document
    for part in dotted.split("."):
        value = value[part]
    return "".join(
        int(str(word), 16).to_bytes(2, "little").hex().upper()
        for word in value["colors"]
    )


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


def isolate_target(
    context: Path, output: Path, oam: list[dict[str, int]], sprite_height: int,
    *, palette_rgb: set[tuple[int, int, int]] | None = None,
    normalize_instances: int = 0,
) -> None:
    """Keep only target OAM rectangles so ambient actors cannot taint proof."""
    with Image.open(context) as source:
        frame = source.convert("RGB")
    isolated = Image.new("RGB", frame.size, "black")
    entries = sorted(oam, key=lambda row: row["slot"])
    if normalize_instances:
        entries = entries[:normalize_instances]
    for index, entry in enumerate(entries):
        left = entry["x"] - 8
        top = entry["y"] - 16
        box = (
            max(0, left), max(0, top),
            min(frame.width, left + 8), min(frame.height, top + sprite_height),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        crop = frame.crop(box)
        if palette_rgb is not None:
            masked = Image.new("RGB", crop.size, "black")
            for y in range(crop.height):
                for x in range(crop.width):
                    pixel = crop.getpixel((x, y))
                    if pixel in palette_rgb:
                        masked.putpixel((x, y), pixel)
            crop = masked
        destination = (
            (76 + index * 10, 64)
            if normalize_instances else box[:2]
        )
        isolated.paste(crop, destination)
    bounds = isolated.getbbox()
    if bounds:
        crop = isolated.crop(bounds)
        scale = max(1, min(16, 96 // max(crop.width, crop.height)))
        if scale > 1:
            crop = crop.resize(
                (crop.width * scale, crop.height * scale),
                Image.Resampling.NEAREST,
            )
        presentation = Image.new("RGB", frame.size, "black")
        presentation.paste(
            crop,
            ((frame.width - crop.width) // 2, (frame.height - crop.height) // 2),
        )
        isolated = presentation
    isolated.save(output)


def cram_rgb(raw: str) -> set[tuple[int, int, int]]:
    payload = bytes.fromhex(raw)
    words = [int.from_bytes(payload[index:index + 2], "little") for index in range(0, 8, 2)]
    colors = []
    for word in words[1:]:
        colors.append(tuple(
            round(channel * 255 / 31)
            for channel in (word & 31, (word >> 5) & 31, (word >> 10) & 31)
        ))
    return set(colors)


def run_one(
    rom: Path,
    scenario: dict[str, Any],
    output: Path,
    replay: int,
    timeout: float,
    launch_attempts: int,
) -> dict[str, Any]:
    stem = f"{scenario['id']}.r{replay}"
    report = output / f"{stem}.txt"
    screenshot = output / f"{stem}.png"
    context_screenshot = output / f"{stem}.context.png"
    source_state = STATES / str(scenario.get("state", ""))
    selector = int(scenario.get("selector", 0))
    if not selector and not source_state.is_file():
        raise RuntimeError(f"missing fixture: {source_state}")
    with tempfile.TemporaryDirectory(
        prefix=f"penta-projectile-{scenario['id']}-", dir=ROOT / "tmp"
    ) as state_dir:
        state_root = Path(state_dir)
        normalized = state_root / "current.ss0"
        run_rom = rom
        state_args: list[str] = []
        native_context: dict[str, Any] | None = None
        if selector:
            patched = bytearray(rom.read_bytes())
            original = bytes(
                patched[SPAWN_SELECTOR_OFFSET:SPAWN_SELECTOR_OFFSET + 5]
            )
            if original != SPAWN_DESCRIPTOR_ORIGINAL:
                raise RuntimeError(
                    f"unexpected Stage 1 descriptor at "
                    f"0x{SPAWN_SELECTOR_OFFSET:X}: {original.hex(' ')}"
                )
            descriptor_offset = NATIVE_DESCRIPTOR_OFFSETS.get(selector)
            if descriptor_offset is None:
                raise RuntimeError(
                    f"no complete native descriptor context for selector {selector}"
                )
            descriptor = bytes(patched[descriptor_offset:descriptor_offset + 5])
            expected_descriptor = bytes(
                range(0x30 + (selector - 1) * 5, 0x35 + (selector - 1) * 5)
            )
            if descriptor != expected_descriptor:
                raise RuntimeError(
                    f"selector {selector} native descriptor drift at "
                    f"0x{descriptor_offset:X}: {descriptor.hex(' ')} != "
                    f"{expected_descriptor.hex(' ')}"
                )
            patched[SPAWN_SELECTOR_OFFSET:SPAWN_SELECTOR_OFFSET + 5] = descriptor
            native_context = {
                "level": 1,
                "section": 5,
                "descriptor_offset": descriptor_offset,
                "descriptor": descriptor.hex(" ").upper(),
            }
            run_rom = state_root / "selector.gb"
            run_rom.write_bytes(patched)
        else:
            mode = str(scenario.get("state_mode", "retarget"))
            normalize(
                source_state,
                normalized,
                0x016C,
                [] if mode == "retarget" else [(0xDF51, 0x00)],
                rom,
                bank=None if mode == "retarget" else 1,
                retarget_only=mode == "retarget",
            )
            state_args = ["-t", str(normalized)]
        environment = os.environ.copy()
        environment.update({
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "PENTA_PROJECTILE_REPORT": str(report),
            "PENTA_PROJECTILE_SCREENSHOT": str(context_screenshot),
            "PENTA_PROJECTILE_TILE_MIN": str(scenario["tiles"][0]),
            "PENTA_PROJECTILE_TILE_MAX": str(scenario["tiles"][1]),
            "PENTA_PROJECTILE_OAM_MIN": str(scenario.get("oam_slots", (0, 39))[0]),
            "PENTA_PROJECTILE_OAM_MAX": str(scenario.get("oam_slots", (0, 39))[1]),
            "PENTA_PROJECTILE_BOSS": str(scenario["boss"]),
            "PENTA_PROJECTILE_POWERUP": str(scenario["powerup"]),
            "PENTA_PROJECTILE_FORCE_FORM": str(
                scenario.get("force_form", -1)
            ),
            "PENTA_PROJECTILE_INPUT_MASK": str(scenario["input_mask"]),
            "PENTA_PROJECTILE_COLD_TARGET": str(selector),
            "PENTA_PROJECTILE_SETTLE": str(scenario.get("settle", 180)),
            "PENTA_PROJECTILE_MIN_MATCHES": str(
                scenario.get("min_matches", 1)
            ),
            "PENTA_PROJECTILE_MAX_OAM_SPAN": str(
                scenario.get("max_oam_span", -1)
            ),
            "PENTA_PROJECTILE_PALETTE_ONLY_SLOT": str(
                scenario.get("palette_only_slot", -1)
            ),
        })
        attempt_records = []
        for attempt in range(1, launch_attempts + 1):
            report.unlink(missing_ok=True)
            screenshot.unlink(missing_ok=True)
            context_screenshot.unlink(missing_ok=True)
            stdout = output / f"{stem}.attempt-{attempt:02d}.stdout.txt"
            with stdout.open("w") as stream:
                try:
                    completed = subprocess.run(
                        [
                            str(MGBA), "--fastforward", *state_args,
                            "--script", str(PROBE), str(run_rom),
                        ],
                        cwd=ROOT,
                        env=environment,
                        stdout=stream,
                        stderr=subprocess.STDOUT,
                        timeout=timeout,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError(
                        f"{scenario['id']} timed out; check the exact owned "
                        "emulator process before any retry"
                    ) from exc
            # This mGBA build can fault in Lua shutdown after the probe has
            # atomically closed both artifacts.  Evidence completeness and
            # the parsed semantic status are authoritative; an already-exited
            # post-report transport fault is retained in the attempt log.
            complete = report.is_file() and context_screenshot.is_file()
            attempt_records.append({
                "attempt": attempt,
                "returncode": completed.returncode,
                "complete": complete,
                "log": str(stdout),
            })
            if completed.returncode == 75:
                raise SystemExit(75)
            if complete:
                break
            print(
                f"retrying {scenario['id']} replay {replay} after exited "
                f"transport status {completed.returncode}",
                flush=True,
            )
    if not complete:
        raise RuntimeError(
            f"{scenario['id']} replay {replay} failed with status "
            f"{completed.returncode}; see {attempt_records[-1]['log']}"
        )
    parsed = parse_report(report)
    if parsed.get("status") != "pass":
        raise RuntimeError(f"{scenario['id']} produced no target; see {report}")
    if native_context:
        observed_descriptor = bytes.fromhex(parsed.get("descriptor", ""))
        expected_descriptor = bytes.fromhex(str(native_context["descriptor"]))
        if observed_descriptor != expected_descriptor:
            raise RuntimeError(
                f"{scenario['id']} loaded DC04:DC08 "
                f"{observed_descriptor.hex(' ')} instead of native "
                f"{expected_descriptor.hex(' ')}"
            )
    slots = [int(value, 16) for value in parsed["palette_slots"].split(",") if value]
    tiles = [int(value, 16) for value in parsed["observed_tiles"].split(",") if value]
    target_oam = parse_oam(parsed.get("target_oam", ""))
    if not target_oam and int(parsed.get("matches", "0")):
        raise RuntimeError(f"{scenario['id']} reported matches without target OAM")
    sprite_height = 16 if int(parsed.get("LCDC", "0"), 16) & 0x04 else 8
    if target_oam:
        normalize_instances = int(scenario.get("normalize_instances", 0))
        expected_slot = int(scenario["expected_slot"])
        # OAM rectangles contain the already-rendered background underneath
        # transparent OBJ pixels. That background can legitimately animate or
        # scroll between otherwise identical semantic target frames. Retain
        # only colors from the target OBJ palette for every isolated proof;
        # exact geometry remains enforced separately by target_oam.
        palette_colors = cram_rgb(parsed[f"obj{expected_slot}_cram"])
        isolate_target(
            context_screenshot, screenshot, target_oam, sprite_height,
            palette_rgb=palette_colors,
            normalize_instances=normalize_instances,
        )
    else:
        with Image.open(context_screenshot) as source:
            source.save(screenshot)
    return {
        "id": scenario["id"],
        "label": scenario["label"],
        "fixture": scenario.get("state") or "cold-boot-native-descriptor-2",
        "fixture_sha256": digest(source_state) if not selector else None,
        "native_context": native_context,
        "state_mode": scenario.get("state_mode", "cold-boot"),
        "emulator_control": {
            "forced_powerup_ffc0": scenario["powerup"],
            "forced_form_ffbe": scenario.get("force_form"),
            "input_mask_schedule": int(scenario["input_mask"]),
            "expected_boss_ffbf": scenario["boss"],
        },
        "frame": int(parsed["frame"]),
        "matches": int(parsed["matches"]),
        "observations": int(parsed["observations"]),
        "observed_tiles": tiles,
        "target_oam": target_oam,
        "sprite_height": sprite_height,
        "determinism_mode": (
            "normalized-single-rendered-instance"
            if scenario.get("normalize_instances") else "exact-target-geometry"
        ),
        "palette_slots": slots,
        "registers": {
            key: parsed[key] for key in ("D880", "FFC1", "FFBE", "FFBF", "FFC0")
        },
        "palette_row": scenario["palette_row"],
        "obj_cram": {f"OBJ{slot}": parsed.get(f"obj{slot}_cram", "") for slot in slots},
        "screenshots": [
            {
                "path": str(context_screenshot),
                "sha256": digest(context_screenshot),
                "role": "gameplay-context",
            },
            {
                "path": str(screenshot),
                "sha256": digest(screenshot),
                "role": "isolated-target-proof",
            },
        ],
    }


def stable(record: dict[str, Any]) -> dict[str, Any]:
    excluded = {
        "screenshots", "observations", "frame",
    }
    if record.get("determinism_mode") == "normalized-single-rendered-instance":
        excluded.update({"target_oam", "matches"})
    canonical = {
        key: value for key, value in record.items()
        if key not in excluded
    }
    if record.get("determinism_mode") == "normalized-single-rendered-instance":
        canonical["target_tile_attrs"] = sorted({
            (row["tile"], row["attr"])
            for row in record["target_oam"]
        })
    canonical["target_screenshot_sha256"] = record["screenshots"][1]["sha256"]
    return canonical


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/visual-audit-evidence/projectiles",
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--determinism-replays", type=int, choices=(1, 2), default=2)
    parser.add_argument("--launch-attempts", type=int, default=2)
    args = parser.parse_args()
    if args.launch_attempts < 1:
        parser.error("--launch-attempts must be at least 1")
    rom = args.rom.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    allowed = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    if not any(output.is_relative_to(root) for root in allowed):
        raise SystemExit("output must be under repo tmp/ or /mnt/data/tmp/")
    marker = output / OWNER
    if any(output.iterdir()) and not marker.is_file():
        raise SystemExit(f"refusing to replace unowned output: {output}")
    marker.write_text("penta-projectile-visual-audit-v1\n")
    for path in output.iterdir():
        if path != marker and path.is_file():
            path.unlink()

    document = yaml.safe_load(PALETTES.read_text())
    passes: list[list[dict[str, Any]]] = []
    try:
        for replay in range(1, args.determinism_replays + 1):
            rows = []
            for scenario in SCENARIOS:
                row = run_one(
                    rom, scenario, output, replay, args.timeout,
                    args.launch_attempts,
                )
                rows.append(row)
                print(
                    f"replay {replay}: {scenario['id']} frame {row['frame']} "
                    f"tiles={row['observed_tiles']} slots={row['palette_slots']}",
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
    failures: list[str] = []
    if not exact:
        failures.append("complete replay metadata/PNG hashes differ")
    for scenario, row in zip(SCENARIOS, passes[0], strict=True):
        expected_slot = int(scenario["expected_slot"])
        if row["palette_slots"] != [expected_slot]:
            failures.append(
                f"{row['id']} uses OBJ slots {row['palette_slots']}, "
                f"expected [{expected_slot}]"
            )
        expected = palette_bytes(document, str(scenario["palette_row"]))
        if row["obj_cram"].get(f"OBJ{expected_slot}") != expected:
            failures.append(
                f"{row['id']} OBJ{expected_slot} CRAM "
                f"{row['obj_cram'].get(f'OBJ{expected_slot}')} "
                f"does not match {scenario['palette_row']} {expected}"
            )
    receipt = {
        "schema": "penta-dragon-dx-projectile-visual-audit-v1",
        "status": "pass" if not failures else "failed",
        "rom": str(rom),
        "rom_sha256": digest(rom),
        "palette_yaml_sha256": digest(PALETTES),
        "determinism_replays": args.determinism_replays,
        "deterministic_replay_exact": exact,
        "projectiles": passes[0],
        "replay_screenshot_sha256": [
            row["screenshots"][1]["sha256"] for row in passes[-1]
        ],
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "status": receipt["status"], "captured": len(passes[0]),
        "deterministic_replay_exact": exact, "failures": failures,
        "receipt": str(receipt_path),
    }, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
