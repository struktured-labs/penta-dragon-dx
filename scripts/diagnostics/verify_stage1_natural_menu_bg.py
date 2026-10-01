#!/usr/bin/env python3
"""Reject menu colors in the displayed Stage-1 BG on a natural SRAM route."""

# PENTA_CHECKED_SINGLEFLIGHT_DELEGATION: MGBA is the checked-in fail-closed
# wrapper. This verifier never accepts a caller-supplied emulator executable.

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
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from stage1_hazard_art import (  # noqa: E402
    decode_tile,
    encode_tile,
    load_stage1_hazard_config,
)
from diagnostics.verify_stage1_north_integrity import (  # noqa: E402
    detect_publication_boundary,
)


MGBA = ROOT / "scripts/mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_stage1_natural_menu_bg.lua")
BANK13_LUT = 13 * 0x4000 + (0x7000 - 0x4000)
HAZARD = load_stage1_hazard_config()
RASTER_BASELINE_FRAMES = 600
NATIVE_WIDTH = 160
NATIVE_HEIGHT = 144
TIMER_BASELINE_FRAMES = 120
TIMER_CADENCE_FLOOR = 0.99


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def state_field(state: str, name: str) -> str | None:
    match = re.search(rf":{re.escape(name)}([0-9A-F]+)(?=:|$)", state)
    return match.group(1) if match else None


def timer_cadence_receipt(
    report: dict[str, str], frames: int, open_frame: int, close_frame: int,
) -> dict[str, object]:
    """Prove SELECT does not merely keep Timer alive, but keeps its cadence."""
    hits = {
        "total": int(report.get("timer_isr_hits", "-1")),
        "baseline": int(report.get("timer_baseline_hits", "-1")),
        "menu": int(report.get("timer_menu_hits", "-1")),
        "post_close": int(report.get("timer_post_close_hits", "-1")),
        "max_frame_gap": int(report.get("timer_max_frame_gap", "999")),
    }
    spans = {
        "baseline": TIMER_BASELINE_FRAMES,
        "menu": close_frame - open_frame,
        "post_close": frames - close_frame,
    }
    rates = {
        phase: hits[phase] / span if span > 0 else 0.0
        for phase, span in spans.items()
    }
    baseline_rate = rates["baseline"]
    ratios = {
        phase: rate / baseline_rate if baseline_rate > 0 else 0.0
        for phase, rate in rates.items()
        if phase != "baseline"
    }
    accounting = (
        hits["total"]
        == hits["baseline"] + hits["menu"] + hits["post_close"]
    )
    passed = (
        accounting
        and all(span > 0 for span in spans.values())
        and all(hits[phase] > 0 for phase in spans)
        and hits["max_frame_gap"] <= 1
        and all(ratio >= TIMER_CADENCE_FLOOR for ratio in ratios.values())
    )
    return {
        "passed": passed,
        "accounting_exact": accounting,
        "cadence_floor": TIMER_CADENCE_FLOOR,
        "spans": spans,
        "hits": hits,
        "rates_per_frame": rates,
        "ratios_to_baseline": ratios,
    }


def projectile_observation_is_safe(raster: dict[str, object]) -> bool:
    """A clean route need not spawn one historical projectile in slot 34.

Absence is not classification. Permit it only with actual baseline/post-close
coverage and no unknown visible OAM or full-frame raster mismatch. A block
that appears only after SELECT still fails, irrespective of its slot.
An observed moving projectile that departed before SELECT may also pass;
it need not reappear after the menu to establish a clean roundtrip.
"""
    observed = raster["operator_projectile_classification"]
    clean = (
        raster["enabled"] is True
        and raster["baseline_frames"] >= RASTER_BASELINE_FRAMES
        and raster["checked_frames"] > 0
        and raster["visible_unknown_oam_frames"] == 0
        and raster["unmatched_phase_frames"] == 0
        and raster["full_frame_mismatch_frames"] == 0
        and raster["mismatch_frames"] == 0
    )
    absent = (
        observed["baseline_frames"] == 0
        and observed["post_close_frames"] == 0
        and observed["unique_screen_positions"] == 0
        and observed["palette_indices"] == []
    )
    departed = (
        observed.get("departed_before_select") is True
        and observed["predates_select"] is True
        and observed["post_close_frames"] == 0
        and observed["moves"] is True
        and observed["palette_indices"] == [0]
    )
    return bool(clean and (
        observed["classified_as_moving_projectile"] is True or absent or departed
    ))


def native_stage1_enemy_quads(rom: bytes) -> frozenset[tuple]:
    """Reviewed native bank-1 enemy records, not observed OAM slots.

    Only used with independently authenticated OBJ CHR/CRAM/OAM snapshots.
    Keep every source flag and the assembler's exact TL/TR/BL/BR geometry.
    """
    reviewed_sources = (
        (0x650B, bytes.fromhex(
            '5000510052005300 5400550056005700 5240534050405140 5640574054405540 '
            '580059005A005B00 5C005D005E005F00 592058205B205A20 5D205C205F205E20 '
            '6000610062006300 6400650066006700 6240634060406140 6640674064406540 '
            '680069006A006B00 6C006D006E006F00 692068206B206A20 6D206C206F206E20'
        )),
        (0x664B, bytes.fromhex(
            '5000510052005300 5120502053205220 5520542057205620 5400550056005700 '
            '580059005A005B00 5C005D005E005F00 5D205C205F205E20 592058205B205A20 '
            '6000610062006300 6120602063206220 6520642067206620 6400650066006700 '
            '680069006A006B00 6C006D006E006F00 6D206C206F206E20 692068206B206A20'
        )),
    )
    for offset, records in reviewed_sources:
        if rom[offset:offset + len(records)] != records:
            raise ValueError(
                f'native Stage-1 enemy animation records changed at ${offset:04X}'
            )
    from verify_stage1_obj_visual_contract import candidate_contract, expected_oam_palette
    contract = candidate_contract(rom)
    result = set()
    for _offset, records in reviewed_sources:
        for start in range(0, len(records), 8):
            quad = []
            for n,(dx,dy) in enumerate(((0,0),(8,0),(0,8),(8,8))):
                tile,flags = records[start+2*n:start+2*n+2]
                palette = expected_oam_palette(
                    contract, slot=4+n, tile=tile, ffbe=0, ffbf=0,
                )
                quad.append((
                    dx, dy, f'{tile:02X}',
                    f'{(flags & 0xF8) | palette:02X}',
                ))
            result.add(tuple(quad))
    return frozenset(result)


def enemy_quad_signatures(item: dict) -> dict[int, tuple]:
    """Recognize complete 16x16 enemy assemblies, never Sara/projectiles.

    OAM allocation is transient. Retain relative geometry, every tile and all
    flags, rather than treating an allocation slot as an entity identity.
    """
    if item["height"] != 8:
        return {}
    objects = {int(obj["slot"]): obj for obj in item["oam_objects"]}
    result = {}
    for base in range(4, 32, 4):
        if not all(base + n in objects for n in range(4)):
            continue
        quad = [objects[base + n] for n in range(4)]
        x, y = quad[0]["x"], quad[0]["y"]
        # Native OAM coordinates are bytes. An enemy crossing the left/top
        # boundary can therefore span $FF->$07 even though its geometry is
        # still an exact +8-pixel quad.
        physical_positions = tuple(
            ((obj["x"] - x) & 0xFF, (obj["y"] - y) & 0xFF)
            for obj in quad
        )
        # The native assembler writes the top and bottom Y pairs
        # sequentially. A frame-boundary observer may therefore see the two
        # complete rows one pixel apart in update phase (7 or 9 rather than
        # 8), while X pairing and the Y within each row remain exact.
        bottom_y = physical_positions[2][1]
        if not (
            physical_positions[:2] == ((0, 0), (8, 0))
            and physical_positions[2][0] == 0
            and physical_positions[3] == (8, bottom_y)
            and bottom_y in (7, 8, 9)
        ):
            continue
        positions = ((0, 0), (8, 0), (0, 8), (8, 8))
        if not all(0x40 <= int(obj["tile"], 16) < 0x80 for obj in quad):
            continue
        result[base] = tuple((dx, dy, obj["tile"], obj["flags"])
                             for (dx, dy), obj in zip(positions, quad))
    return result


def temporal_raster_receipt(
    report: dict[str, str], open_frame: int, close_frame: int,
    *, obj_atlas_authenticated: bool = False,
    native_animation_quads: frozenset[tuple] = frozenset(),
    authenticated_enemy_oam: dict[
        int, dict[int, tuple[str, str]]
    ] | None = None,
) -> dict[str, object]:
    frames: list[dict[str, object]] = []
    for entry in filter(None, report.get("temporal_raster_trace", "").split(";")):
        match = re.fullmatch(
            r"f(\d+):h(8|16):s([0-9A-F]+):o([^:]*):p(.+)", entry
        )
        if not match:
            continue
        oam = []
        oam_identities = []
        oam_objects = []
        height = int(match.group(2))
        oam_rows = re.findall(
            r"(\d+)/(\d+)/(\d+)/([0-9A-F]{2})/([0-9A-F]{2})",
            match.group(4),
        )
        canonical_oam = ",".join("/".join(row) for row in oam_rows)
        if canonical_oam != match.group(4):
            continue
        for slot, x, y, tile, flags in oam_rows:
            oam.append((int(x) - 8, int(y) - 16, 8, height))
            oam_identities.append((int(slot), tile, flags))
            oam_objects.append({
                "slot": int(slot),
                "x": int(x) - 8,
                "y": int(y) - 16,
                "tile": tile,
                "flags": flags,
            })
        frames.append({
            "frame": int(match.group(1)),
            "height": height,
            "signature": match.group(3),
            "oam_signature": canonical_oam,
            "oam": oam,
            "oam_identities": oam_identities,
            "oam_objects": oam_objects,
            "path": Path(match.group(5)),
        })

    def saturated(color: tuple[int, int, int]) -> bool:
        return max(color) >= 200 and max(color) - min(color) >= 150

    def covered(item: dict[str, object], index: int) -> bool:
        x, y = index % 160, index // 160
        return any(
            left <= x < left + width and top <= y < top + height
            for left, top, width, height in item["oam"]
        )

    baseline_frames = int(report.get("raster_baseline_frames", "0"))
    baseline = [
        item for item in frames
        if open_frame - baseline_frames <= item["frame"] < open_frame
    ]
    checked = [
        item for item in frames
        if close_frame + 2 <= item["frame"] <= close_frame + 100
    ]
    raster_cache: dict[Path, list[tuple[int, int, int]] | None] = {}

    def native_pixels(path: Path) -> list[tuple[int, int, int]] | None:
        if path not in raster_cache:
            if not path.is_file():
                raster_cache[path] = None
            else:
                with Image.open(path) as source:
                    image = source.convert("RGB")
                    raster_cache[path] = (
                        list(image.getdata())
                        if image.size == (NATIVE_WIDTH, NATIVE_HEIGHT)
                        else None
                    )
        return raster_cache[path]

    allowed: dict[str, dict[int, set[tuple[int, int, int]]]] = {}
    background_allowed: dict[
        str, dict[int, set[tuple[int, int, int]]]
    ] = {}
    known_oam_identities: dict[int, set[tuple[str, str]]] = {}
    known_enemy_quads: set[tuple] = set(native_animation_quads if obj_atlas_authenticated else ())

    def oam_identity(slot: int, tile: str, flags: str) -> tuple[str, str]:
        """Return the raster-relevant identity for an authenticated Sara tile.

        OAM attribute bit 4 selects DMG OBP1 and is ignored in CGB mode.  The
        native game can toggle that bit across SELECT while leaving the CGB
        sprite byte-identical on screen.  Normalize only that non-rendering
        bit, only for Sara's fixed slots/tile range, and only when the
        independent ROM atlas/CHR/CRAM/OAM snapshot oracle authenticated the
        route.  Palette, VRAM-bank, flips, priority, tile, and slot remain
        exact identity inputs.
        """
        value = int(flags, 16)
        if (
            obj_atlas_authenticated
            and slot < 4
            and 0x10 <= int(tile, 16) <= 0x2F
        ):
            value &= ~0x10
        return tile, f"{value:02X}"

    for item in baseline:
        path = item["path"]
        pixels = native_pixels(path)
        if pixels is None:
            continue
        phase = allowed.setdefault(item["signature"], {})
        for index, color in enumerate(pixels):
            if saturated(color) and not covered(item, index):
                phase.setdefault(index, set()).add(color)

        background_phase = background_allowed.setdefault(
            item["signature"], {}
        )
        for index, color in enumerate(pixels):
            if not covered(item, index):
                background_phase.setdefault(index, set()).add(color)
        for slot, tile, flags in item["oam_identities"]:
            known_oam_identities.setdefault(slot, set()).add(
                oam_identity(slot, tile, flags)
            )
        known_enemy_quads.update(enemy_quad_signatures(item).values())

    mismatches = []
    full_frame_mismatches = []
    unmatched = 0
    unmatched_oam = 0
    visible_unknown_oam_frames = 0
    authenticated_quad_reallocation_frames = 0

    def projectile_observations(items: list[dict[str, object]]) -> list[dict]:
        return [
            obj
            for item in items
            for obj in item["oam_objects"]
            if obj["slot"] == 34 and obj["tile"] == "0F"
        ]

    baseline_projectile = projectile_observations(baseline)
    post_close_projectile = projectile_observations(checked)
    projectile = baseline_projectile + post_close_projectile
    projectile_positions = sorted({
        (int(obj["x"]), int(obj["y"])) for obj in projectile
    })
    projectile_palettes = sorted({
        int(str(obj["flags"]), 16) & 0x07 for obj in projectile
    })
    baseline_projectile_frames = [
        int(item["frame"]) for item in baseline
        if any(obj["slot"] == 34 and obj["tile"] == "0F"
               for obj in item["oam_objects"])
    ]
    baseline_coverage_complete = {int(item["frame"]) for item in baseline} == set(
        range(open_frame - baseline_frames, open_frame)
    )
    projectile_classification = {
        "identity": "hardware OAM slot 34 / tile $0F",
        "baseline_frames": len(baseline_projectile),
        "post_close_frames": len(post_close_projectile),
        "unique_screen_positions": len(projectile_positions),
        "palette_indices": projectile_palettes,
        "predates_select": bool(baseline_projectile),
        "survives_roundtrip": bool(post_close_projectile),
        "moves": len(projectile_positions) >= 2,
        "last_baseline_frame": max(baseline_projectile_frames, default=None),
        "departed_before_select": bool(
            baseline_coverage_complete and baseline_projectile_frames
            and max(baseline_projectile_frames) < open_frame - 1
            and not post_close_projectile
        ),
        "classified_as_moving_projectile": (
            bool(baseline_projectile)
            and bool(post_close_projectile)
            and len(projectile_positions) >= 2
            and projectile_palettes == [0]
        ),
    }
    audited_oam_frames = baseline + checked
    sarah_priority = [
        {
            "frame": item["frame"],
            "slot": obj["slot"],
            "tile": obj["tile"],
            "flags": obj["flags"],
            "x": obj["x"],
            "y": obj["y"],
        }
        for item in audited_oam_frames
        for obj in item["oam_objects"]
        if int(obj["slot"]) < 4
        and 0x10 <= int(str(obj["tile"]), 16) <= 0x2F
        and int(str(obj["flags"]), 16) & 0x80
    ]
    sarah_oam_entries = sum(
        1
        for item in audited_oam_frames
        for obj in item["oam_objects"]
        if int(obj["slot"]) < 4
        and 0x10 <= int(str(obj["tile"]), 16) <= 0x2F
    )
    for item in checked:
        path = item["path"]
        phase = allowed.get(item["signature"])
        if phase is None or not path.is_file():
            unmatched += 1
            mismatches.append({
                "frame": item["frame"],
                "pixels": -1,
                "first_xy": None,
                "path": str(path),
                "reason": "missing same-phase baseline" if phase is None
                else "missing raster screenshot",
            })
            continue
        pixels = native_pixels(path)
        if pixels is None:
            mismatches.append({
                "frame": item["frame"],
                "pixels": -1,
                "first_xy": None,
                "path": str(path),
                "reason": "missing or non-native raster screenshot",
            })
            continue
        unexpected = [
            index for index, color in enumerate(pixels)
            if saturated(color) and not covered(item, index)
            and color not in phase.get(index, set())
        ]
        if unexpected:
            mismatches.append({
                "frame": item["frame"],
                "pixels": len(unexpected),
                "first_xy": [unexpected[0] % 160, unexpected[0] // 160],
                "path": str(path),
            })

        relocated_slots = set()
        if obj_atlas_authenticated:
            for base, signature in enemy_quad_signatures(item).items():
                if signature in known_enemy_quads:
                    relocated_slots.update(range(base, base + 4))
            frame_oam = (authenticated_enemy_oam or {}).get(
                int(item["frame"]), {}
            )
            relocated_slots.update(
                int(obj["slot"])
                for obj in item["oam_objects"]
                if frame_oam.get(int(obj["slot"]))
                == (str(obj["tile"]), str(obj["flags"]))
            )
        if any(slot in relocated_slots and oam_identity(slot, tile, flags)
               not in known_oam_identities.get(slot, set())
               for slot, tile, flags in item["oam_identities"]):
            authenticated_quad_reallocation_frames += 1
        unknown_oam = [
            (slot, tile, flags)
            for slot, tile, flags in item["oam_identities"]
            if oam_identity(slot, tile, flags)
            not in known_oam_identities.get(slot, set())
            and slot not in relocated_slots
        ]
        visible_unknown_oam = [
            (obj["slot"], obj["tile"], obj["flags"], obj["x"], obj["y"])
            for obj in item["oam_objects"]
            if oam_identity(obj["slot"], obj["tile"], obj["flags"])
            not in known_oam_identities.get(obj["slot"], set())
            and obj["slot"] not in relocated_slots
            and int(obj["x"]) < NATIVE_WIDTH
            and int(obj["x"]) + 8 > 0
            and int(obj["y"]) < NATIVE_HEIGHT
            and int(obj["y"]) + int(item["height"]) > 0
        ]
        frame_failures = []
        if unknown_oam:
            unmatched_oam += 1
        if visible_unknown_oam:
            visible_unknown_oam_frames += 1
            frame_failures.append("new visible OAM identity after SELECT")

        background_phase = background_allowed.get(item["signature"])
        if background_phase is None:
            frame_failures.append("missing same-phase full-screen BG baseline")
            full_unexpected = []
        else:
            full_unexpected = [
                index for index, color in enumerate(pixels)
                if not covered(item, index)
                and index in background_phase
                and color not in background_phase[index]
            ]
            if full_unexpected:
                frame_failures.append(
                    "full-screen BG differs from pre-menu phase"
                )
        if frame_failures:
            full_frame_mismatches.append({
                "frame": item["frame"],
                "pixels": len(full_unexpected) if full_unexpected else -1,
                "first_xy": (
                    [
                        full_unexpected[0] % NATIVE_WIDTH,
                        full_unexpected[0] // NATIVE_WIDTH,
                    ]
                    if full_unexpected else None
                ),
                "path": str(path),
                "reason": "; ".join(frame_failures),
                "unknown_oam_identities": unknown_oam,
                "visible_unknown_oam": visible_unknown_oam,
            })
    return {
        "enabled": (
            baseline_frames == RASTER_BASELINE_FRAMES
            and len(baseline) >= RASTER_BASELINE_FRAMES - 1
            and len(checked) >= 60
        ),
        "raster_height": NATIVE_HEIGHT,
        "baseline_frames_requested": baseline_frames,
        "baseline_frames": len(baseline),
        "baseline_signatures": len(allowed),
        "baseline_oam_identities": sum(
            len(identities) for identities in known_oam_identities.values()
        ),
        "checked_frames": len(checked),
        "unmatched_phase_frames": unmatched,
        "unmatched_oam_phase_frames": unmatched_oam,
        "visible_unknown_oam_frames": visible_unknown_oam_frames,
        "obj_atlas_authenticated": obj_atlas_authenticated,
        "native_animation_quad_count": len(native_animation_quads) if obj_atlas_authenticated else 0,
        "authenticated_quad_reallocation_frames": authenticated_quad_reallocation_frames,
        "operator_projectile_classification": projectile_classification,
        "sarah_priority_contract": {
            "oam_entries": sarah_oam_entries,
            "priority_entries": len(sarah_priority),
            "priority_frames": len({item["frame"] for item in sarah_priority}),
            "first_priority_entry": sarah_priority[0] if sarah_priority else None,
            "passed": sarah_oam_entries > 0 and not sarah_priority,
        },
        "palette_mismatch_frames": len(mismatches),
        "full_frame_mismatch_frames": len(full_frame_mismatches),
        "mismatch_frames": len(mismatches) + len(full_frame_mismatches),
        "first_mismatch": (
            mismatches[0] if mismatches
            else full_frame_mismatches[0] if full_frame_mismatches
            else None
        ),
        "first_full_frame_mismatch": (
            full_frame_mismatches[0] if full_frame_mismatches else None
        ),
    }


def expected_bank1_art(rom: bytes) -> bytes:
    payload = bytearray()
    for tile in (
        0x01, 0x02, 0x03, 0x04,
        0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
        0x74, 0x75, 0x76, 0x77, 0x78, 0x79,
    ):
        source = rom[0x1D000 + tile * 16:0x1D000 + (tile + 1) * 16]
        if len(source) != 16:
            raise ValueError("candidate hazard art source is truncated")
        if tile <= 0x04:
            payload.extend(encode_tile([
                HAZARD.environment_remap[pixel]
                for pixel in decode_tile(source)
            ]))
        else:
            payload.extend(source)
    return bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--save-fixture", type=Path)
    parser.add_argument("--blank-sram", action="store_true")
    parser.add_argument("--export-state", action="store_true",
                        help="export the final boot-derived state with ROM provenance")
    parser.add_argument("--no-menu-control", action="store_true",
                        help="diagnostic: omit SELECT pulses; cannot qualify a menu roundtrip")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=1500)
    parser.add_argument("--open-frame", type=int, default=1200)
    parser.add_argument("--close-frame", type=int, default=1380)
    parser.add_argument("--menu-key", choices=("select", "start"), default="select",
                        help="physical menu-opening button; START is a separate regression route")
    parser.add_argument("--close-key", choices=("select", "start", "b"),
                        help="physical close button (default: menu-key); START inside the menu uses an item")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--move", choices=("none", "right", "left", "up", "down"),
        default="none",
    )
    parser.add_argument("--move-start", type=int, default=-1)
    parser.add_argument("--move-end", type=int, default=-1)
    parser.add_argument(
        "--expected-room", type=lambda value: int(value, 16), default=0x05,
        help="expected final Stage-1 room byte (hex; default: 05)",
    )
    args = parser.parse_args()
    close_key = args.close_key or args.menu_key

    rom = args.rom.resolve()
    save = args.save_fixture.resolve() if args.save_fixture else None
    output = args.output.resolve()
    if not rom.is_file():
        parser.error("ROM must exist")
    if args.blank_sram == (save is not None):
        parser.error("choose exactly one of --save-fixture or --blank-sram")
    if save is not None and not save.is_file():
        parser.error("save fixture must exist")
    if not (0 < args.open_frame < args.close_frame < args.frames):
        parser.error("require 0 < open-frame < close-frame < frames")
    if not (0 <= args.expected_room <= 0xFF):
        parser.error("--expected-room must be one byte")

    rom_bytes = rom.read_bytes()
    rom_sha256 = digest(rom_bytes)
    publication = detect_publication_boundary(rom_bytes)
    gameplay_lut = rom_bytes[BANK13_LUT:BANK13_LUT + 0x100]
    hazard_art = expected_bank1_art(rom_bytes)
    if len(gameplay_lut) != 0x100 or any(value > 0x0F for value in gameplay_lut):
        parser.error("candidate has no valid canonical Stage-1 attribute LUT")

    output.parent.mkdir(parents=True, exist_ok=True)
    for stale in output.parent.glob(output.name + "*"):
        if stale.is_file():
            stale.unlink()
    runtime = output.parent / f"{output.stem}.runtime"
    runtime.mkdir(exist_ok=True)
    runtime_rom = runtime / "candidate.gb"
    shutil.copy2(rom, runtime_rom)
    for stale_save in (runtime / "candidate.sav", runtime / "candidate.gb.ram"):
        stale_save.unlink(missing_ok=True)
    if save is not None:
        shutil.copy2(save, runtime / "candidate.sav")
    lut_path = runtime / "stage1-gameplay-lut.bin"
    lut_path.write_bytes(gameplay_lut)
    art_path = runtime / "stage1-hazard-bank1-art.bin"
    art_path.write_bytes(hazard_art)
    if digest(runtime_rom.read_bytes()) != rom_sha256:
        raise RuntimeError("isolated runtime ROM identity changed")

    env = os.environ.copy()
    env.update({
        "STAGE1_NATURAL_EXPORT_STATE": "1" if args.export_state else "0",
        "STAGE1_NATURAL_NO_MENU_CONTROL": "1" if args.no_menu_control else "0",
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "TMPDIR": str((ROOT / "tmp").resolve()),
        "STAGE1_NATURAL_MENU_BG_OUT": str(output),
        "STAGE1_NATURAL_MENU_BG_ROM": str(rom),
        "STAGE1_NATURAL_MENU_BG_ROM_SHA256": rom_sha256,
        "STAGE1_NATURAL_MENU_BG_LUT": str(lut_path),
        "STAGE1_NATURAL_MENU_BG_LUT_SHA256": digest(gameplay_lut),
        "STAGE1_NATURAL_MENU_BG_ART": str(art_path),
        "STAGE1_NATURAL_MENU_BG_ART_SHA256": digest(hazard_art),
        "STAGE1_NATURAL_MENU_BG_FRAMES": str(args.frames),
        "STAGE1_NATURAL_MENU_BG_OPEN": str(args.open_frame),
        "STAGE1_NATURAL_MENU_BG_CLOSE": str(args.close_frame),
        "STAGE1_NATURAL_MENU_BG_KEY": args.menu_key,
        "STAGE1_NATURAL_MENU_BG_CLOSE_KEY": close_key,
        "STAGE1_NATURAL_MENU_BG_RASTER_BASELINE_FRAMES": str(
            RASTER_BASELINE_FRAMES
        ),
        "STAGE1_NATURAL_MENU_BG_MOVE": args.move,
        "STAGE1_NATURAL_MENU_BG_MOVE_START": str(args.move_start),
        "STAGE1_NATURAL_MENU_BG_MOVE_END": str(args.move_end),
        "STAGE1_NATURAL_MENU_BG_EXPECTED_ROOM": f"{args.expected_room:02X}",
        "STAGE1_NATURAL_MENU_BG_PUBLICATION_PC": (
            str(publication["publication_pc_hex"])
        ),
        "STAGE1_NATURAL_MENU_BG_PUBLICATION_SEGMENT": (
            str(publication["publication_segment_hex"])
        ),
    })
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    command = [
        str(MGBA), "--fastforward", str(runtime_rom),
        "--script", str(PROBE), "-C", f"savegamePath={runtime}",
    ]
    completed: subprocess.CompletedProcess[bytes] | None = None
    try:
        completed = subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True,
            timeout=args.timeout, check=False,
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
    if args.export_state:
        state = Path(str(output) + ".final.ss0")
        if not state.is_file() or state.stat().st_size == 0:
            raise RuntimeError("requested final machine state was not exported")
        Path(str(state) + ".json").write_text(json.dumps({
            "schema": "penta-boot-derived-state-v1",
            "rom_path": str(rom), "rom_sha256": rom_sha256,
            "state_path": str(state), "state_sha256": digest(state.read_bytes()),
            "probe_sha256": digest(PROBE.read_bytes()),
            "report_path": str(output), "report_sha256": digest(output.read_bytes()),
            "blank_sram": args.blank_sram,
            "final_state": report.get("final_state"),
            "fixture_writes": "physical bank1 DCBB=FF each active frame (#37/#41); native inventory/cursor DCDC/DCDD untouched",
            "qualification": "export provenance only; not a scene0B or readiness pass",
        }, indent=2) + "\n")
    obj_evidence = None
    from verify_natural_stage1_obj import bind as bind_natural_obj
    try:
        obj_evidence = bind_natural_obj(
            rom, output, args.open_frame, args.close_frame,
            expected_room=args.expected_room,
        )
    except (ValueError, OSError, KeyError) as error:
        print(f"OBJ evidence failed: {error}")
    authenticated_enemy_oam = {
        int(snapshot["frame"]): {
            int(entry.split("/", 1)[0]): tuple(entry.split("/")[1:])
            for entry in snapshot.get("native_enemy_oam", [])
        }
        for snapshot in (obj_evidence or {}).get("snapshots", [])
    }
    raster = temporal_raster_receipt(
        report, args.open_frame, args.close_frame,
        obj_atlas_authenticated=bool(obj_evidence and obj_evidence["status"] == "pass"),
        native_animation_quads=(
            native_stage1_enemy_quads(rom_bytes)
            if obj_evidence else frozenset()
        ),
        authenticated_enemy_oam=authenticated_enemy_oam,
    )
    timer_cadence = timer_cadence_receipt(
        report, args.frames, args.open_frame, args.close_frame
    )
    preopen_bg = state_field(report.get("last_preopen", ""), "bg")
    menu_bg = state_field(report.get("first_window", ""), "bg")
    menu_window = state_field(report.get("first_window", ""), "win")
    selector_lcdc = int(report.get("first_selector_lcdc", "-1"), 16)
    selector_bg = "9C00" if selector_lcdc & 0x08 else "9800"
    checks = {
        "menu button matches the requested physical input": (
            report.get("menu_key") == args.menu_key
            and report.get("close_key") == close_key
        ),
        "real menu roundtrip, not a no-menu diagnostic control": (
            not args.no_menu_control and report.get("no_menu_control", "0") == "0"
        ),
        "natural sprite atlas, palettes and Sara priority match independent ROM sources": (
            obj_evidence is not None
        ),
        "receipt is bound to the exact ROM": (
            report.get("rom") == str(rom)
            and report.get("rom_sha256") == rom_sha256
            and report.get("lut_sha256") == digest(gameplay_lut)
            and report.get("art_sha256") == digest(hazard_art)
        ),
        f"natural route reached Stage 1 room {args.expected_room:02X}": (
            f"scene02:room{args.expected_room:02X}" in report.get(
                "last_preopen", ""
            )
            and f"scene02:room{args.expected_room:02X}" in report.get(
                "final_state", ""
            )
        ),
        "pre-menu gameplay is canonical": (
            int(report.get("baseline_frames", "0")) >= 60
            and int(report.get("baseline_bad_frames", "-1")) == 0
        ),
        "natural Stage-1 entry loaded every bank-1 hazard-art byte": (
            "scene02:room05" in report.get("first_gameplay", "")
            and int(report.get("settled_art_mismatch_bytes", "-1")) == 0
            and (int(report.get("settled_df5b", "-1"), 16) & 0x03) == 0x03
        ),
        "visible menu leaves displayed gameplay BG canonical": (
            int(report.get("menu_frames", "0")) >= 60
            and int(report.get("menu_bad_frames", "-1")) == 0
        ),
        "menu never migrates gameplay onto the preparation peer": (
            preopen_bg is not None
            and selector_lcdc >= 0
            and menu_bg == selector_bg
            and menu_window is not None
            and menu_window != menu_bg
        ),
        "menu close leaves displayed gameplay BG canonical": (
            int(report.get("post_close_frames", "0")) >= 60
            and int(report.get("post_close_bad_frames", "-1")) == 0
        ),
        "music Timer ISR cadence remains within one percent across SELECT": (
            timer_cadence["passed"]
        ),
        "post-menu temporal raster contains no transient palette garbage": (
            raster["enabled"]
            and raster["raster_height"] == NATIVE_HEIGHT
            and raster["baseline_frames_requested"]
            == RASTER_BASELINE_FRAMES
            and raster["unmatched_phase_frames"] == 0
            and raster["visible_unknown_oam_frames"] == 0
            and raster["full_frame_mismatch_frames"] == 0
            and raster["mismatch_frames"] == 0
        ),
        "Sarah-adjacent projectile is classified or absent on a clean route": (
            args.expected_room != 0x05
            or projectile_observation_is_safe(raster)
        ),
        "Sarah never exposes the floor through OBJ priority": (
            raster["sarah_priority_contract"]["passed"]
        ),
    }
    print(f"ROM: {rom}")
    for key in (
        "last_preopen", "first_window", "first_closed", "first_baseline_bad",
        "first_menu_bad",
        "first_post_close_bad", "baseline_bad_frames", "menu_bad_frames",
        "post_close_bad_frames", "settled_art_mismatch_bytes",
        "settled_df5b", "settled_art_state", "first_selector_frame",
        "first_selector_lcdc", "first_selector_dc0b",
        "timer_isr_hits", "timer_baseline_hits", "timer_menu_hits",
        "timer_post_close_hits", "timer_max_frame_gap",
    ):
        print(f"{key}={report.get(key, 'missing')}")
    print("temporal_raster=" + repr(raster))
    print("timer_cadence=" + repr(timer_cadence))
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    if not all(checks.values()):
        return 1
    print(f"PASS: natural Stage-1 {args.menu_key.upper()} roundtrip never colors the gameplay BG.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
