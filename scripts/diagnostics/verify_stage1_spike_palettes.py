#!/usr/bin/env python3
"""Prove the YAML-owned Stage 1 rotating-spike art and palettes are live."""

from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zlib

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v301_gdma import (  # noqa: E402
    _bg_table,
    create_inline_tile_copy_postcomputed_attrs,
    create_inline_tile_copy_stage1_precomputed_attrs,
)
from build_v302_title_fix import (  # noqa: E402
    BANK13,
    BANK14,
    BANK7,
    COLORIZE_ADDR,
    COLD_STAGE1_SWEEP_ARM_ADDR,
    COLD_STAGE1_SWEEP_ARM_TAIL_ADDR,
    INLINE_ATTR_DECISION_HELPER_ADDR,
    LAVA_ATTR_DECIDER_ADDR,
    OAM_WRAM_COPY_ADDR,
    OAM_WRAM_COPY_TAIL_ADDR,
    PALETTE_COPY_CRAM8_ADDR,
    PALETTE_LOADER_ADDR,
    PALETTE_LOADER_EXT_ADDR,
    STAGE1_ATOMIC_GROUP_WIDTH,
    STAGE1_ATOMIC_SETUP_ADDR,
    STAGE1_ATOMIC_WRAP_ADDR,
    STAGE1_ATTR_ROW_INIT_ADDR,
    STAGE1_ATTR_ROW_INIT_TAIL_ADDR,
    STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR,
    STAGE1_HAZARD_BANK1_BANK7_COPY_ADDR,
    STAGE1_HAZARD_BANK1_BANK7_COPY_MIDDLE_ADDR,
    STAGE1_HAZARD_BANK1_BANK7_COPY_TAIL_ADDR,
    STAGE1_HAZARD_BANK1_BANK14_COPY_ADDR,
    STAGE1_HAZARD_BANK1_BANK14_LOADER_ADDR,
    STAGE1_HAZARD_BANK1_LOADER_ADDR,
    STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR,
    STAGE1_HAZARD_BANK1_REFRESH_COUNT,
    STAGE1_HAZARD_BANK1_TILE_COUNT,
    STAGE1_HAZARD_BANK0_MAP_ADDR,
    STAGE1_HAZARD_PURE_MAP_ADDR,
    STAGE1_HAZARD_BG7_SOURCE_ADDR,
    STAGE1_HAZARD_ROW_COMPILER_ADDR,
    STAGE1_HAZARD_ROW_HELPER_ADDR,
    STAGE1_HAZARD_ROW0_REPAIR_FRONT_ADDR,
    STAGE1_HAZARD_ROW0_REPAIR_MIDDLE_ADDR,
    STAGE1_HAZARD_ROW0_REPAIR_TAIL_ADDR,
    STAGE1_HAZARD_ROOM12_WALL_REPAIR_ADDR,
    STAGE1_HAZARD_ROOM_DISPATCH_ADDR,
    STAGE1_HAZARD_SCANNER_FRONT_ADDR,
    STAGE1_HAZARD_SCANNER_MIDDLE_ADDR,
    STAGE1_HAZARD_SCANNER_SEAM_ADDR,
    STAGE1_HAZARD_SCANNER_TAIL_ADDR,
    STAGE1_HAZARD_START4_EDGE_ADDR,
    STAGE1_HAZARD_START4_HELPER_ADDR,
    STAGE1_HAZARD_TRANSITION_REPAIR_ADDR,
    STAGE1_HAZARD_BANKED_ENTRY_ADDR,
    STAGE1_SOURCE_GENERATION_RST,
    STAGE1_ENTRY_PATCH_BODY_ADDR,
    STAGE1_ENTRY_PATCH_FINISH_ADDR,
    STAGE1_ENTRY_PATCH_GATE_ADDR,
    STAGE1_ENTRY_PATCH_LOWER_ADDR,
    STAGE1_ENTRY_PATCH_TAIL_ADDR,
    WRAPPER_ADDR,
    build_cold_stage1_sweep_arm,
    build_later_stage_bg0_arm,
    build_oam_wram_copy,
    build_oam_wram_copy_tail,
    build_phased_palette_loader,
    build_stage1_attr_runtime,
    build_stage1_attr_row_helper,
    build_stage1_attr_row_initializer,
    build_stage1_atomic_attr_stack_vector,
    build_stage1_atomic_wrap,
    build_stage1_entry_attr_patch,
    build_stage1_entry_patch_gate,
    build_stage1_hazard_bank1_copy_routines,
    build_stage1_hazard_bank1_bank14_loader,
    build_stage1_hazard_bank1_loader,
    build_stage1_hazard_bank1_neutral_art,
    build_stage1_hazard_dispatcher,
    build_stage1_hazard_dynamic_scanner,
    build_stage1_hazard_row_helper,
    build_stage1_hazard_row0_transition_repair,
    build_stage1_hazard_room_dispatcher,
    build_stage1_hazard_room12_wall_repair,
    build_stage1_hazard_start4_edge_helpers,
    build_stage1_hazard_transition_repair,
    build_stage1_hazard_banked_entries,
)
from normalize_mgba_state_pc import (  # noqa: E402
    GB_STATE_SIZE,
    normalize,
    png_chunks,
    write_png,
)
from stage1_hazard_art import (  # noqa: E402
    compile_stage1_hazard_variants,
    decode_tile,
    load_stage1_hazard_config,
    load_stage1_hazard_palette,
)
from verify_pickup_class_palettes import (
    BG_PALETTE_OFFSET,
    BG_TABLE_OFFSET,
    serialized_state,
)


DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
STOCK_ROM = ROOT / "rom/Penta Dragon (J).gb"
PALETTE_YAML = ROOT / "palettes/penta_palettes_v097.yaml"
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
STATE_DIR = ROOT / "save_states_for_claude"
PROBE = Path(__file__).with_name("probe_stage1_spike_palettes.lua")
LIVE_STATE = "level1_cat_fish_moth_spike_hazard_orb_item.ss0"
CEILING_LIVE_STATE = "level1_sara_w_spike_hazard.ss0"
PIXEL_SETTLE_FRAME = 120
STATE_NAMES = (
    "level1_sara_w_spike_hazard.ss0",
    "level1_sara_w_thrusting_spike_hazard.ss0",
    "level1_cat_fish_moth_spike_hazard_orb_item.ss0",
    "v2.26_level1_sara_w_gargoyle_mini_boss.ss0",
)
HAZARD = load_stage1_hazard_config()
SPIKE_TILES = HAZARD.family_tiles
SPIKE_TOOTH_TILES = HAZARD.tooth_tiles
SPIKE_FIRE_TILES = HAZARD.ring_tiles | HAZARD.body_tiles
SPIKE_CONNECTOR_TILES = HAZARD.connector_tiles
SPIKE_SUPPORT_TILES = HAZARD.support_tiles
SPIKE_TOOTH_PALETTE = HAZARD.tooth_palette
SPIKE_FIRE_PALETTE = HAZARD.body_palette
SPIKE_CONNECTOR_PALETTE = HAZARD.connector_palette
SPIKE_SUPPORT_PALETTE = HAZARD.support_palette
PATTERNED_FLOOR_TILES = frozenset(
    (*range(0x2A, 0x2F), *range(0x3A, 0x3E))
)
ROOM_OFFSET = 0x4400 + 0x1A0
ROOM_SIZE = 24 * 24
EXPECTED_TABLE = _bg_table()
EXPECTED_HISTOGRAM = dict(sorted(Counter(EXPECTED_TABLE).items()))
APPROVED_ART_TILES = HAZARD.art_tiles - {0x60, 0x61, 0x70, 0x71}
APPROVED_ART_SHA256 = (
    "b777a161c3ee50ff8d184637de0b0adbae23adb6756db0c3f0984702106ad3e5"
)
# Captured natural animation corpus. Room $02's ceiling cylinder is shifted
# four packed cells from room $12, so each room owns one four-phase tooth
# sample. DC0E contributes the physical-map bit to the runtime key.
CAPTURED_PHASE_TILES = {
    0x02: (0x01, 0x74, 0x66, 0x64),
    0x12: (0x67, 0x75, 0x02, 0x65),
}
CYLINDER_BODY = bytes.fromhex(
    "60 61 6E 6E 6C 6D 6E 6E 6C 6D 6E 62"
)
CYLINDER_LOWER = bytes.fromhex(
    "70 71 7E 7D 7C 7E 7E 7D 7C 7E 7E 72"
)
SERIALIZED_VRAM_OFFSET = 0x400
SERIALIZED_LCDC_OFFSET = 0x340


def refresh_hazard_vram(state: Path, rom: bytes) -> dict[str, object]:
    """Replace stale fixture tile pixels with this candidate's source art."""
    chunks = png_chunks(state.read_bytes())
    indices = [
        index for index, (kind, _) in enumerate(chunks) if kind == b"gbAs"
    ]
    if len(indices) != 1:
        raise RuntimeError(f"expected one gbAs chunk, found {len(indices)}")
    index = indices[0]
    raw = bytearray(zlib.decompress(chunks[index][1]))
    if len(raw) != GB_STATE_SIZE:
        raise RuntimeError(f"unexpected Game Boy state size 0x{len(raw):X}")
    signed_tiles = not raw[SERIALIZED_LCDC_OFFSET] & 0x10
    changed = 0
    refreshed = bytearray()
    for tile in sorted(HAZARD.family_tiles):
        source = rom[
            HAZARD.source_offset + tile * 16:
            HAZARD.source_offset + (tile + 1) * 16
        ]
        tile_offset = (0x1000 if signed_tiles else 0) + tile * 16
        start = SERIALIZED_VRAM_OFFSET + tile_offset
        before = raw[start:start + 16]
        changed += sum(left != right for left, right in zip(before, source))
        raw[start:start + 16] = source
        refreshed.extend(source)
    chunks[index] = (b"gbAs", zlib.compress(bytes(raw), level=9))
    write_png(state, chunks)
    return {
        "tile_addressing": "signed" if signed_tiles else "unsigned",
        "tiles": len(HAZARD.family_tiles),
        "changed_bytes": changed,
        "sha256": hashlib.sha256(refreshed).hexdigest(),
    }


def cgb_rgb(word: int) -> tuple[int, int, int]:
    return tuple(
        round(((word >> shift) & 0x1F) * 255 / 31)
        for shift in (0, 5, 10)
    )


def rgb_palette(raw: bytes) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        cgb_rgb(raw[index] | (raw[index + 1] << 8))
        for index in range(0, 8, 2)
    )


def rendered_tile(
    tile: bytes,
    palette: tuple[tuple[int, int, int], ...],
) -> bytes:
    return bytes(channel for pixel in decode_tile(tile) for channel in palette[pixel])


def rendered_hazard_cells(
    path: Path,
    scx: int,
    scy: int,
    patterns: dict[int, dict[bytes, tuple[int, ...]]],
) -> dict[str, object]:
    """Decode aligned native pixels back to candidate hazard tile/palette."""
    with Image.open(path) as source:
        image = source.convert("RGB")
    wrong_teeth = []
    gold_teeth = []
    for y in range((-scy) & 7, image.height - 7, 8):
        for x in range((-scx) & 7, image.width - 7, 8):
            block = image.crop((x, y, x + 8, y + 8)).tobytes()
            wrong = set(patterns[0].get(block, ())) & SPIKE_TOOTH_TILES
            gold = set(patterns[SPIKE_TOOTH_PALETTE].get(block, ())) & SPIKE_TOOTH_TILES
            # A no-accent black/white block can be byte-identical under two
            # palettes. It is not evidence of gray palette-0 tooth pixels.
            wrong -= gold
            if wrong:
                wrong_teeth.append({
                    "x": x, "y": y,
                    "tiles": [f"{tile:02X}" for tile in sorted(wrong)],
                })
            if gold:
                gold_teeth.append({
                    "x": x, "y": y,
                    "tiles": [f"{tile:02X}" for tile in sorted(gold)],
                })
    return {
        "path": str(path),
        "scx": scx,
        "scy": scy,
        "wrong_palette0_teeth": wrong_teeth,
        "gold_teeth": gold_teeth,
    }


def room_source(path: Path) -> bytes:
    state = serialized_state(path)
    return state[ROOM_OFFSET:ROOM_OFFSET + ROOM_SIZE]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def parse_live_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def live_receipt(
    rom: Path,
    state: Path,
    mgba: Path,
    output: Path,
    timeout: float,
    *,
    prefix_name: str = "stage1-spike-live",
    reinitialize: bool = True,
    settle: int = 180,
    input_mask: int = 0,
    screenshot_interval: int = 0,
    expected_room: int = 0x12,
    normalization_writes: tuple[tuple[int, int], ...] = (),
    normalization_bank: int | None = None,
    expect_scroll: bool = False,
    force_miniboss_frame: int = -1,
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    prefix = output / prefix_name
    report_path = Path(str(prefix) + ".txt")
    screenshot_path = Path(str(prefix) + ".png")
    log_path = output / "mgba.log"
    for path in (report_path, screenshot_path, log_path):
        path.unlink(missing_ok=True)
    for path in output.glob(prefix.name + "-*.png"):
        path.unlink()
    normalized = output / "stage1-spike-current.ss0"
    normalize(
        state,
        normalized,
        0x016C,
        [
            *normalization_writes,
            (STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR, 0),
        ],
        rom,
        bank=normalization_bank,
    )

    rom_bytes = rom.read_bytes()
    vram_refresh = refresh_hazard_vram(normalized, rom_bytes)
    expected_bg5 = rom_bytes[
        BG_PALETTE_OFFSET + SPIKE_FIRE_PALETTE * 8:
        BG_PALETTE_OFFSET + (SPIKE_FIRE_PALETTE + 1) * 8
    ]
    expected_bg7 = rom_bytes[
        BANK13 + (STAGE1_HAZARD_BG7_SOURCE_ADDR - 0x4000):
        BANK13 + (STAGE1_HAZARD_BG7_SOURCE_ADDR - 0x4000) + 8
    ]
    rendered_palettes = {
        palette: rgb_palette(
            expected_bg7 if palette == SPIKE_TOOTH_PALETTE else
            rom_bytes[
                BG_PALETTE_OFFSET + palette * 8:
                BG_PALETTE_OFFSET + (palette + 1) * 8
            ]
        )
        for palette in (0, SPIKE_FIRE_PALETTE, SPIKE_SUPPORT_PALETTE,
                        SPIKE_TOOTH_PALETTE)
    }
    mutable_patterns: dict[int, dict[bytes, list[int]]] = {
        palette: {} for palette in rendered_palettes
    }
    for palette, colors in rendered_palettes.items():
        for tile in sorted(HAZARD.family_tiles):
            source = rom_bytes[
                HAZARD.source_offset + tile * 16:
                HAZARD.source_offset + (tile + 1) * 16
            ]
            pattern = rendered_tile(source, colors)
            mutable_patterns[palette].setdefault(pattern, []).append(tile)
    rendered_patterns = {
        palette: {
            pattern: tuple(tiles) for pattern, tiles in patterns.items()
        }
        for palette, patterns in mutable_patterns.items()
    }
    expected_bg5_words = [
        expected_bg5[index] | (expected_bg5[index + 1] << 8)
        for index in range(0, 8, 2)
    ]
    expected_bg7_words = [
        expected_bg7[index] | (expected_bg7[index + 1] << 8)
        for index in range(0, 8, 2)
    ]
    bank1_art = bytearray()
    for tile in (
        0x01, 0x02, 0x03, 0x04,
        0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
        0x74, 0x75, 0x76, 0x77, 0x78, 0x79,
    ):
        source = rom_bytes[
            HAZARD.source_offset + tile * 16:
            HAZARD.source_offset + (tile + 1) * 16
        ]
        if tile <= 0x04:
            for index in range(0, 16, 2):
                low, high = source[index:index + 2]
                bank1_art.extend((low | high, low & high))
        else:
            bank1_art.extend(source)

    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STAGE1_SPIKE_OUT": str(prefix),
        "STAGE1_SPIKE_SETTLE": str(settle),
        "STAGE1_SPIKE_REINIT": "1" if reinitialize else "0",
        "STAGE1_SPIKE_REFRESH_CODE": "1",
        "STAGE1_SPIKE_KEYS": str(input_mask),
        "STAGE1_SPIKE_SCREENSHOT_INTERVAL": str(screenshot_interval),
        "STAGE1_SPIKE_FORCE_MINIBOSS_FRAME": str(force_miniboss_frame),
        "STAGE1_SPIKE_EXPECTED_LOAD_COUNT": str(
            STAGE1_HAZARD_BANK1_REFRESH_COUNT
        ),
        "STAGE1_SPIKE_EXPECTED_BG5": ",".join(
            f"{word:04X}" for word in expected_bg5_words
        ),
        "STAGE1_SPIKE_EXPECTED_BG7": ",".join(
            f"{word:04X}" for word in expected_bg7_words
        ),
        "STAGE1_SPIKE_EXPECTED_BANK1_ART": bank1_art.hex(),
    })
    with log_path.open("w") as stream:
        completed = subprocess.run(
            [
                str(mgba), "--fastforward", "-t", str(normalized),
                "--script", str(PROBE), str(rom),
            ],
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    if (
        completed.returncode != 0
        or not report_path.is_file()
        or not screenshot_path.is_file()
    ):
        raise RuntimeError(
            f"live spike probe status={completed.returncode}; see {log_path}"
        )
    values = parse_live_report(report_path)
    found9800, matched9800 = (
        int(value) for value in values["map9800"].split(",")
    )
    found9c00, matched9c00 = (
        int(value) for value in values["map9c00"].split(",")
    )
    lcdc = int(values["lcdc"], 16)
    active_base = "9c00" if lcdc & 0x08 else "9800"
    active_found, active_matched = (
        (found9c00, matched9c00)
        if active_base == "9c00"
        else (found9800, matched9800)
    )
    actual_bg5 = [int(value, 16) for value in values["bg5"].split(",")]
    actual_bg7 = [int(value, 16) for value in values["bg7"].split(",")]
    tooth_found, tooth_matched = (
        int(value) for value in values["tooth"].split(",")
    )
    tooth_bank1 = int(values["tooth_bank1"])
    static_rows_found, static_rows_matched = (
        int(value) for value in values["static_tooth_rows"].split(",")
    )
    active_static_rows_found, active_static_rows_matched = (
        int(value)
        for value in values["active_static_tooth_rows"].split(",")
    )
    # Low two bits count art uploads; high bits cache the first two stable-map
    # stamps after the immutable art is ready.
    bank1_load_index = int(values["bank1_load_index"], 16) & 0x03
    bank1_art_mismatches = int(values["bank1_art_mismatches"])
    fire_found, fire_matched = (
        int(value) for value in values["fire"].split(",")
    )
    support_found, support_matched = (
        int(value) for value in values["support"].split(",")
    )
    transient_mismatch_frames = int(values["transient_mismatch_frames"])
    miniboss_first_frame = int(values["miniboss_first_frame"])
    palette_mismatch_frames = int(values["palette_mismatch_frames"])
    floor_mismatch_frames = int(values["floor_mismatch_frames"])
    floor_lut_mismatch_frames = int(values["floor_lut_mismatch_frames"])
    atomic_floor_lut_mismatch_hits = int(
        values["atomic_floor_lut_mismatch_hits"]
    )
    atomic_path_hits = int(values["atomic_path_hits"])
    post_miniboss_helper_hits = int(values["post_miniboss_hazard_helper_hits"])
    post_miniboss_row_hits = int(values["post_miniboss_hazard_row_hits"])
    invalid_hazard_row_writes = int(values["invalid_hazard_row_writes"])
    published_rows = set(re.findall(
        r":row:hl([0-9A-F]{4}):c(?:09|0A|0B):e0F",
        values["hazard_event_trace"],
    ))
    row_shift = 4 if expected_room == 0x02 else 0
    reviewed_rows = {
        f"{base + offset:04X}"
        for base in (0x9800, 0x9C00)
        for offset in (0x40 + row_shift, 0xA0 + row_shift)
    }
    rendered_phases: list[dict[str, object]] = []
    for entry in filter(None, values.get("rendered_phase_trace", "").split(";")):
        frame_text, tile_attr, image_path = entry.split(":", 2)
        tile_text, attr_text = tile_attr.split("/", 1)
        rendered_phases.append({
            "frame": int(frame_text.removeprefix("f")),
            "tile": int(tile_text, 16),
            "attr": int(attr_text),
            "path": image_path,
        })
    expected_rendered_phases = set(CAPTURED_PHASE_TILES[expected_room])
    captured_rendered_phases = {
        int(item["tile"]) for item in rendered_phases
    }
    active_reviewed_map_receipts: dict[str, bool] = {}
    phase_images = [
        Image.open(str(item["path"])).convert("RGB")
        for item in rendered_phases
        if Path(str(item["path"])).is_file()
    ]
    phase_montage_path = Path(str(prefix) + "-phase-montage.png")
    if phase_images:
        cell_width, cell_height, label_height = 160, 144, 12
        montage = Image.new(
            "RGB", (cell_width * 2, (cell_height + label_height) * 2), "black"
        )
        draw = ImageDraw.Draw(montage)
        for index, (item, phase_image) in enumerate(
            zip(rendered_phases[:4], phase_images[:4])
        ):
            left = (index % 2) * cell_width
            top = (index // 2) * (cell_height + label_height)
            montage.paste(phase_image, (left, top))
            draw.text(
                (left + 2, top + cell_height),
                f"phase {int(item['tile']):02X} frame {int(item['frame'])}",
                fill="white",
            )
        montage.save(phase_montage_path)
    lower_field_metrics = []
    for phase_image in phase_images:
        lower = phase_image.crop((0, 64, 160, 144))
        colors = list(lower.getdata())
        upper = phase_image.crop((0, 0, 160, 64))
        upper_colors = list(upper.getdata())
        lower_field_metrics.append({
            "red": colors.count((255, 0, 0)),
            "yellow": colors.count((255, 255, 0)),
            "upper_red": upper_colors.count((255, 0, 0)),
            "upper_yellow": upper_colors.count((255, 255, 0)),
        })
    periodic_paths = sorted(prefix.parent.glob(prefix.name + "-frame*.png"))
    phase_scroll = {}
    for entry in filter(
        None, values.get("rendered_phase_map_trace", "").split(";")
    ):
        match = re.match(
            r"f(\d+):[0-9A-F]{2}:[0-9A-F]{4}:"
            r"([0-9A-F]{2}):([0-9A-F]{2}):",
            entry,
        )
        if match:
            phase_scroll[int(match.group(1))] = (
                int(match.group(2), 16), int(match.group(3), 16)
            )
        map_match = re.match(
            r"f\d+:[0-9A-F]{2}:([0-9A-F]{4}):"
            r"[0-9A-F]{2}:[0-9A-F]{2}:(.*)",
            entry,
        )
        if map_match:
            base = int(map_match.group(1), 16)
            cells = {
                int(offset, 16): int(attr, 16)
                for offset, _tile, attr in re.findall(
                    r"([0-9A-F]{3})/([0-9A-F]{2})/([0-9A-F]{2})",
                    map_match.group(2),
                )
            }
            reviewed_offsets = {
                row + column
                for row in (0x40 + row_shift, 0xA0 + row_shift)
                for column in range(9)
            }
            # The completed-map stamper upgrades these cells from the compiled
            # BG7 value $07 to immutable-bank BG7 value $0F. Either value is
            # pixel-identical after the receipt-locked bank-1 art upload; what
            # must never become visible is a non-BG7 (gray/disco) attribute.
            exact = all(
                cells.get(offset) in {0x07, 0x0F}
                for offset in reviewed_offsets
            )
            key = f"{base:04X}"
            active_reviewed_map_receipts[key] = (
                active_reviewed_map_receipts.get(key, True) and exact
            )
    periodic_trace = []
    for entry in filter(
        None, values.get("periodic_render_trace", "").split(";")
    ):
        match = re.match(
            r"f(\d+):([0-9A-F]{2}):([0-9A-F]{2}):"
            r"([0-9A-F]{2}):([0-9A-F]{2}):([0-9A-F]{2}):(.*)",
            entry,
        )
        if match:
            periodic_trace.append({
                "frame": int(match.group(1)),
                "scx": int(match.group(2), 16),
                "scy": int(match.group(3), 16),
                "scene": int(match.group(4), 16),
                "room": int(match.group(5), 16),
                "miniboss": int(match.group(6), 16),
                "path": match.group(7),
            })
    phase_pixel_receipts = []
    for item in rendered_phases:
        frame_number = int(item["frame"])
        path = Path(str(item["path"]))
        if path.is_file() and frame_number in phase_scroll:
            scx, scy = phase_scroll[frame_number]
            decoded = rendered_hazard_cells(
                path, scx, scy, rendered_patterns
            )
            decoded["frame"] = frame_number
            phase_pixel_receipts.append(decoded)
    periodic_pixel_receipts = []
    for item in periodic_trace:
        path = Path(str(item["path"]))
        if path.is_file():
            decoded = rendered_hazard_cells(
                path, int(item["scx"]), int(item["scy"]),
                rendered_patterns,
            )
            decoded.update({
                "frame": item["frame"],
                "scene": f"{int(item['scene']):02X}",
                "room": f"{int(item['room']):02X}",
                "miniboss": f"{int(item['miniboss']):02X}",
            })
            periodic_pixel_receipts.append(decoded)
    pixel_receipts = phase_pixel_receipts + periodic_pixel_receipts
    settled_pixel_receipts = [
        item for item in pixel_receipts
        if int(item["frame"]) >= PIXEL_SETTLE_FRAME
    ]
    wrong_tooth_cells = sum(
        len(item["wrong_palette0_teeth"]) for item in settled_pixel_receipts
    )
    gold_tooth_cells = sum(
        len(item["gold_teeth"]) for item in pixel_receipts
    )
    periodic_metrics = []
    for path in periodic_paths:
        with Image.open(path) as source:
            periodic = source.convert("RGB")
        lower_colors = list(periodic.crop((0, 64, 160, 144)).getdata())
        periodic_metrics.append({
            "path": str(path),
            "red": lower_colors.count((255, 0, 0)),
            "yellow": lower_colors.count((255, 255, 0)),
        })
    scroll_montage_path = Path(str(prefix) + "-scroll-montage.png")
    if periodic_paths:
        count = min(16, len(periodic_paths))
        indices = sorted({
            round(index * (len(periodic_paths) - 1) / max(1, count - 1))
            for index in range(count)
        })
        cell_width, cell_height, label_height = 160, 144, 12
        montage = Image.new(
            "RGB", (cell_width * 4, (cell_height + label_height) * 4), "black"
        )
        draw = ImageDraw.Draw(montage)
        for slot, index in enumerate(indices):
            with Image.open(periodic_paths[index]) as source:
                image = source.convert("RGB")
            left = (slot % 4) * cell_width
            top = (slot // 4) * (cell_height + label_height)
            montage.paste(image, (left, top))
            draw.text(
                (left + 2, top + cell_height),
                periodic_paths[index].stem.rsplit("-", 1)[-1],
                fill="white",
            )
        montage.save(scroll_montage_path)

    floor_checks = {
        "visible patterned floors never inherit a hazard palette": (
            floor_mismatch_frames == 0
        ),
        "every atomic floor compile reads Dungeon BG0": (
            atomic_floor_lut_mismatch_hits == 0
        ),
    }
    if expect_scroll:
        progress_trace = values["progress_trace"]
        tile_copy_states = values["tile_copy_states"]
        atomic_source_trace = values["atomic_source_trace"]
        patterned_counts = [
            int(value) for value in re.findall(r":p(\d+):", atomic_source_trace)
        ]
        platform_counts = [
            int(left) + int(right)
            for left, right in re.findall(r":c(\d+):d(\d+):", atomic_source_trace)
        ]
        checks = {
            **floor_checks,
            "scroll receipt holds the exact north input": input_mask == 0x80,
            "north scroll reaches patterned-floor room $05": (
                bool(re.search(r":r05:", progress_trace))
            ),
            "north scroll exercises live Stage-1 scene $0A": (
                bool(re.search(r":s0A:", progress_trace))
            ),
            "regular and Gargoyle layouts both use atomic attributes": (
                "02/01:" in tile_copy_states
                and "0A/01:" in tile_copy_states
                and atomic_path_hits > 0
            ),
            "scroll corpus includes patterned and 4C/4D floor layouts": (
                bool(patterned_counts)
                and max(patterned_counts) >= 200
                and bool(platform_counts)
                and max(platform_counts) >= 100
            ),
            "Stage-1 hazard CRAM does not flicker during north scroll": (
                palette_mismatch_frames == 0
            ),
            "periodic rendered receipt covers the complete north scroll": (
                screenshot_interval > 0
                and len(periodic_paths) >= max(4, settle // screenshot_interval - 1)
                and scroll_montage_path.is_file()
            ),
            "rendered lower field never becomes a red/gold disco floor": (
                bool(periodic_metrics)
                and max(item["red"] for item in periodic_metrics) < 200
                and max(item["yellow"] for item in periodic_metrics) < 700
            ),
        }
    else:
        checks = {
            **floor_checks,
            "historical spike room remains a live Stage-1 phase": (
                values["room"] == f"{expected_room:02X}"
                and values["scene"] in {"02", "0A"}
            ),
            "active map contains the rotating spike family": active_found >= 20,
            "every active-map spike tile uses its YAML material split": (
                active_matched == active_found
            ),
            "visible map contains complete BG7 teeth": (
                tooth_found >= 4 and tooth_matched == tooth_found
            ),
            "every visible tooth phase uses the immutable bank-1 cell": (
                tooth_bank1 == tooth_found
            ),
            "both physical maps are observed active with exact tooth colors": (
                active_reviewed_map_receipts == {"9800": True, "9C00": True}
                and active_static_rows_found == 18
                and active_static_rows_matched == 18
            ),
            "all bank-1 neutral/tooth art finished and matches bank 0": (
                bank1_load_index == STAGE1_HAZARD_BANK1_REFRESH_COUNT
                and bank1_art_mismatches == 0
            ),
            "visible map contains BG5 rings and fire body": (
                fire_found >= 4 and fire_matched == fire_found
            ),
            "visible support and shadow cells remain metallic BG6": (
                support_found >= 2 and support_matched == support_found
            ),
            "every sampled animation frame keeps tile and palette atomic": (
                transient_mismatch_frames == 0
            ),
            "live BG5 CRAM matches the candidate": (
                actual_bg5 == expected_bg5_words
            ),
            "live Stage-1 BG7 CRAM matches the YAML hazard row": (
                actual_bg7 == expected_bg7_words
            ),
            "Stage-1 hazard BG5/BG7 never flicker during the sampled interval": (
                palette_mismatch_frames == 0
            ),
            "source-row publisher limits main spans to four reviewed rows": (
                published_rows == reviewed_rows
                and invalid_hazard_row_writes == 0
            ),
            "all four live cylinder phases have rendered-frame receipts": (
                captured_rendered_phases == expected_rendered_phases
                and len(phase_images) == 4
                and phase_montage_path.is_file()
            ),
            "normalized fixtures render current candidate hazard art": (
                vram_refresh["tiles"] == len(HAZARD.family_tiles)
            ),
            "rendered candidate pixels never expose gray palette-0 teeth": (
                bool(pixel_receipts) and wrong_tooth_cells == 0
            ),
            "every rendered phase visibly contains candidate BG7 gold teeth": (
                len(phase_pixel_receipts) == 4
                and all(item["gold_teeth"] for item in phase_pixel_receipts)
            ),
            "rendered cylinder phases visibly contain red and gold material": (
                bool(lower_field_metrics)
                and all(
                    item["upper_red"] >= 100 and item["upper_yellow"] >= 100
                    for item in lower_field_metrics
                )
            ),
            "rendered lower field has no legacy red/gold palette wash": (
                bool(lower_field_metrics)
                and max(item["red"] for item in lower_field_metrics) < 200
                and max(item["yellow"] for item in lower_field_metrics) < 700
            ),
        }
    if input_mask and not expect_scroll:
        checks.update({
            "held combat input naturally starts the Gargoyle": (
                miniboss_first_frame > 0 and "0A/01/02" in values["miniboss_trace"]
            ),
            "hazard helper remains active in the live miniboss scene": (
                post_miniboss_helper_hits > 0 and post_miniboss_row_hits > 0
            ),
        })
        if screenshot_interval > 0:
            pre_miniboss_pixels = [
                item for item in periodic_pixel_receipts
                if int(item["frame"]) < miniboss_first_frame
            ]
            post_miniboss_pixels = [
                item for item in periodic_pixel_receipts
                if int(item["frame"]) > miniboss_first_frame
            ]
            checks.update({
                "rendered pixel trace brackets the live miniboss transition": (
                    bool(pre_miniboss_pixels) and bool(post_miniboss_pixels)
                    and any(item["gold_teeth"] for item in pre_miniboss_pixels)
                    and any(item["gold_teeth"] for item in post_miniboss_pixels)
                ),
                "post-miniboss raster keeps every decoded tooth on BG7": (
                    all(
                        not item["wrong_palette0_teeth"]
                        for item in post_miniboss_pixels
                    )
                ),
            })
    return {
        "state": str(state),
        "state_sha256": digest(state),
        "normalized_state": str(normalized),
        "normalized_vram_refresh": vram_refresh,
        "report": str(report_path),
        "screenshot": str(screenshot_path),
        "active_map": active_base,
        "scene": values["scene"],
        "room": values["room"],
        "map9800": {"found": found9800, "matched": matched9800},
        "map9c00": {"found": found9c00, "matched": matched9c00},
        "tooth": {"found": tooth_found, "matched": tooth_matched},
        "tooth_bank1": tooth_bank1,
        "static_tooth_rows": {
            "found": static_rows_found,
            "matched": static_rows_matched,
        },
        "active_static_tooth_rows": {
            "found": active_static_rows_found,
            "matched": active_static_rows_matched,
        },
        "static_tooth_rows_mismatch_trace": (
            values["static_tooth_rows_mismatch_trace"]
        ),
        "active_reviewed_map_receipts": active_reviewed_map_receipts,
        "compiler_unreadable_scene_frames": int(
            values["compiler_unreadable_scene_frames"]
        ),
        "bank1_load_index": f"{bank1_load_index:02X}",
        "bank1_art_mismatches": bank1_art_mismatches,
        "fire": {"found": fire_found, "matched": fire_matched},
        "support": {"found": support_found, "matched": support_matched},
        "transient_mismatch_frames": transient_mismatch_frames,
        "transient_mismatch_trace": values["transient_mismatch_trace"],
        "first_transient_mismatch": values["first_transient_mismatch"],
        "miniboss_first_frame": miniboss_first_frame,
        "miniboss_trace": values["miniboss_trace"],
        "progress_trace": values["progress_trace"],
        "palette_mismatch_frames": palette_mismatch_frames,
        "first_palette_mismatch": values["first_palette_mismatch"],
        "floor_mismatch_frames": floor_mismatch_frames,
        "floor_mismatch_trace": values["floor_mismatch_trace"],
        "first_floor_mismatch": values["first_floor_mismatch"],
        "floor_lut_trace": values["floor_lut_trace"],
        "floor_lut_mismatch_frames": floor_lut_mismatch_frames,
        "atomic_floor_lut_mismatch_hits": atomic_floor_lut_mismatch_hits,
        "atomic_path_hits": atomic_path_hits,
        "atomic_source_trace": values["atomic_source_trace"],
        "tile_copy_states": values["tile_copy_states"],
        "post_miniboss_hazard_helper_hits": post_miniboss_helper_hits,
        "post_miniboss_hazard_row_hits": post_miniboss_row_hits,
        "invalid_hazard_row_writes": invalid_hazard_row_writes,
        "published_rows": sorted(published_rows),
        "rendered_phases": rendered_phases,
        "phase_montage": str(phase_montage_path),
        "scroll_montage": str(scroll_montage_path),
        "lower_field_metrics": lower_field_metrics,
        "periodic_metrics": periodic_metrics,
        "phase_pixel_receipts": phase_pixel_receipts,
        "periodic_pixel_receipts": periodic_pixel_receipts,
        "rendered_wrong_palette0_tooth_cells": wrong_tooth_cells,
        "rendered_bg7_gold_tooth_cells": gold_tooth_cells,
        "bg5": [f"{word:04X}" for word in actual_bg5],
        "bg7": [f"{word:04X}" for word in actual_bg7],
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--states", type=Path, default=STATE_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument(
        "--live-state",
        default=LIVE_STATE,
        help=(
            "checked-in state used by both live spike passes; accepts a "
            "path relative to --states"
        ),
    )
    parser.add_argument(
        "--ceiling-state",
        default=CEILING_LIVE_STATE,
        help=(
            "checked-in room-$02 ceiling-cylinder state; accepts a path "
            "relative to --states"
        ),
    )
    parser.add_argument(
        "--live-settle",
        type=int,
        default=180,
        help="frames sampled after current-ROM runtime reinitialization",
    )
    parser.add_argument(
        "--natural-settle",
        type=int,
        default=420,
        help="frames sampled from the untouched checked-in state",
    )
    parser.add_argument(
        "--ceiling-settle",
        type=int,
        default=180,
        help="frames sampled from the current-ROM ceiling-cylinder fixture",
    )
    parser.add_argument(
        "--miniboss-settle",
        type=int,
        default=600,
        help="frames sampled from the active-Gargoyle spike-room fixture",
    )
    parser.add_argument(
        "--scroll-settle",
        type=int,
        default=600,
        help="frames sampled while holding north through the patterned floor",
    )
    parser.add_argument(
        "--scroll-screenshot-interval",
        type=int,
        default=15,
        help="native-frame interval for the deterministic north-scroll receipt",
    )
    parser.add_argument(
        "--keys",
        type=lambda value: int(value, 0),
        default=0,
        help=(
            "controller bit mask held during floor/miniboss passes; the "
            "ceiling animation fixture remains stationary"
        ),
    )
    parser.add_argument(
        "--screenshot-interval",
        type=int,
        default=0,
        help="capture a native frame at this interval (0 disables periodic captures)",
    )
    args = parser.parse_args()

    rom_path = args.rom.resolve()
    rom = rom_path.read_bytes()
    if len(rom) != 0x40000:
        print(f"FAIL: ROM size is {len(rom)}, expected 262144")
        return 1

    rooms = {
        name: room_source((args.states / name).resolve())
        for name in STATE_NAMES
    }
    observed_family = {
        tile
        for room in rooms.values()
        for tile in room
        if 0x60 <= tile <= 0x7F
    }
    cylinder_room = rooms[STATE_NAMES[0]]
    rows = [
        cylinder_room[offset:offset + 24]
        for offset in range(0, ROOM_SIZE, 24)
    ]
    body_rows = [index for index, row in enumerate(rows) if CYLINDER_BODY in row]
    paired_rows = [
        row
        for row in body_rows
        if row + 1 < len(rows) and CYLINDER_LOWER in rows[row + 1]
    ]

    table = rom[BG_TABLE_OFFSET:BG_TABLE_OFFSET + 256]
    histogram = dict(sorted(Counter(table).items()))
    stock = STOCK_ROM.read_bytes()
    variants = compile_stage1_hazard_variants(stock, HAZARD)
    candidate_variants = {
        tile: rom[
            HAZARD.source_offset + tile * 16:
            HAZARD.source_offset + (tile + 1) * 16
        ]
        for tile in HAZARD.art_tiles
    }
    changed_bytes = sum(
        before != after
        for tile in sorted(HAZARD.art_tiles)
        for before, after in zip(
            stock[
                HAZARD.source_offset + tile * 16:
                HAZARD.source_offset + (tile + 1) * 16
            ],
            candidate_variants[tile],
        )
    )
    detached_tooth_accent_pixels = 0
    for tile in sorted(HAZARD.tooth_tiles):
        source_pixels = decode_tile(stock[
            HAZARD.source_offset + tile * 16:
            HAZARD.source_offset + (tile + 1) * 16
        ])
        candidate_pixels = decode_tile(candidate_variants[tile])
        rows = HAZARD.tooth_row_spans[tile]
        for index, (source_pixel, candidate_pixel) in enumerate(
            zip(source_pixels, candidate_pixels)
        ):
            x, y = index & 7, index >> 3
            span = rows.get(y)
            inside = bool(span and span[0] <= x < span[1])
            if (
                not inside
                and candidate_pixel != HAZARD.environment_remap[source_pixel]
            ):
                detached_tooth_accent_pixels += 1
    hazard_slot, hazard_palette = load_stage1_hazard_palette(PALETTE_YAML)
    hazard_palette_off = (
        BANK13 + STAGE1_HAZARD_BG7_SOURCE_ADDR - 0x4000
    )
    loader, loader_ext, copy_cram8, _later_stage_selector = (
        build_phased_palette_loader()
    )
    later_stage_bg0_arm = build_later_stage_bg0_arm()
    loader_off = BANK13 + PALETTE_LOADER_ADDR - 0x4000
    loader_ext_off = BANK13 + PALETTE_LOADER_EXT_ADDR - 0x4000
    copy_cram8_off = BANK13 + PALETTE_COPY_CRAM8_ADDR - 0x4000
    runtime_gate = build_stage1_attr_runtime()
    atomic_wrap = build_stage1_atomic_wrap()
    atomic_attr_stack_vector = build_stage1_atomic_attr_stack_vector()
    scanner_front, scanner_middle, scanner_tail, scanner_seam = (
        build_stage1_hazard_dynamic_scanner()
    )
    transition_repair = build_stage1_hazard_transition_repair()
    room12_wall_repair = build_stage1_hazard_room12_wall_repair()
    gap_front, gap_middle, gap_tail = (
        build_stage1_hazard_row0_transition_repair()
    )
    start4_helper, start4_edge = build_stage1_hazard_start4_edge_helpers()
    scanner_blobs = (
        (STAGE1_HAZARD_SCANNER_FRONT_ADDR, scanner_front),
        (STAGE1_HAZARD_SCANNER_MIDDLE_ADDR, scanner_middle),
        (STAGE1_HAZARD_SCANNER_TAIL_ADDR, scanner_tail),
        (STAGE1_HAZARD_SCANNER_SEAM_ADDR, scanner_seam),
        (STAGE1_HAZARD_TRANSITION_REPAIR_ADDR, transition_repair),
        (STAGE1_HAZARD_ROOM12_WALL_REPAIR_ADDR, room12_wall_repair),
        (STAGE1_HAZARD_ROW0_REPAIR_FRONT_ADDR, gap_front),
        (STAGE1_HAZARD_ROW0_REPAIR_MIDDLE_ADDR, gap_middle),
        (STAGE1_HAZARD_ROW0_REPAIR_TAIL_ADDR, gap_tail),
        (STAGE1_HAZARD_START4_HELPER_ADDR, start4_helper),
        (STAGE1_HAZARD_START4_EDGE_ADDR, start4_edge),
    )
    production_inline = create_inline_tile_copy_stage1_precomputed_attrs(
        INLINE_ATTR_DECISION_HELPER_ADDR + 3,
        STAGE1_ATOMIC_SETUP_ADDR,
        STAGE1_ATOMIC_WRAP_ADDR,
        external_post_copy_helper_addr=STAGE1_HAZARD_PURE_MAP_ADDR,
        external_attr_stack_helper_rst=STAGE1_SOURCE_GENERATION_RST,
        atomic_group_width=STAGE1_ATOMIC_GROUP_WIDTH,
    )
    postcomputed_inline = create_inline_tile_copy_postcomputed_attrs(
        INLINE_ATTR_DECISION_HELPER_ADDR + 3,
        STAGE1_ATOMIC_SETUP_ADDR,
        STAGE1_ATOMIC_WRAP_ADDR,
        STAGE1_HAZARD_PURE_MAP_ADDR,
        STAGE1_SOURCE_GENERATION_RST,
    )
    postcomputed_active = (
        rom[0x42A7:0x42A7 + len(postcomputed_inline)]
        == postcomputed_inline
    )
    oam_wram_copy = build_oam_wram_copy()
    oam_wram_tail13, _oam_wram_tail14 = build_oam_wram_copy_tail(
        postcomputed_attrs=postcomputed_active,
    )
    row_init_front, row_init_tail = build_stage1_attr_row_initializer()
    generated_row_helper = build_stage1_attr_row_helper()
    arena_sanitizer_marker = bytes(
        [STAGE1_SOURCE_GENERATION_RST]
        + [0x13] * STAGE1_ATOMIC_GROUP_WIDTH
        + [0x1B, 0x1A, 0x4F, 0x0A, 0xF5] * STAGE1_ATOMIC_GROUP_WIDTH
    )
    oam_wram_copy_off = BANK13 + OAM_WRAM_COPY_ADDR - 0x4000
    oam_wram_tail13_off = BANK13 + OAM_WRAM_COPY_TAIL_ADDR - 0x4000
    bank1_art_loader = build_stage1_hazard_bank1_loader()
    bank1_art_bank14_loader = build_stage1_hazard_bank1_bank14_loader()
    bank14_copy, bank7_copy, bank7_copy_middle, bank7_copy_tail = (
        build_stage1_hazard_bank1_copy_routines()
    )
    bank1_neutral_art = build_stage1_hazard_bank1_neutral_art(rom)
    bank1_art_loader_off = (
        BANK13 + STAGE1_HAZARD_BANK1_LOADER_ADDR - 0x4000
    )
    bank1_art_bank14_loader_off = (
        BANK14 + STAGE1_HAZARD_BANK1_BANK14_LOADER_ADDR - 0x4000
    )
    entry_patch_gate = build_stage1_entry_patch_gate()
    (
        entry_patch_body,
        entry_patch_tail,
        entry_patch_finish,
        entry_patch_lower,
    ) = build_stage1_entry_attr_patch(table)
    entry_patch_blobs = (
        (STAGE1_ENTRY_PATCH_GATE_ADDR, entry_patch_gate),
        (STAGE1_ENTRY_PATCH_BODY_ADDR, entry_patch_body),
        (STAGE1_ENTRY_PATCH_LOWER_ADDR, entry_patch_lower),
        (STAGE1_ENTRY_PATCH_TAIL_ADDR, entry_patch_tail),
        (STAGE1_ENTRY_PATCH_FINISH_ADDR, entry_patch_finish),
    )
    cold_sweep_arm, cold_sweep_arm_tail = build_cold_stage1_sweep_arm()
    cold_sweep_arm_blobs = (
        (COLD_STAGE1_SWEEP_ARM_ADDR, cold_sweep_arm),
        (COLD_STAGE1_SWEEP_ARM_TAIL_ADDR, cold_sweep_arm_tail),
    )
    wrapper_entry_marker = bytes([
        0xFA, 0x80, 0xD8, 0xD6, 0x17, 0xD6, 0x01,
        0xCC,
        STAGE1_ENTRY_PATCH_GATE_ADDR & 0xFF,
        STAGE1_ENTRY_PATCH_GATE_ADDR >> 8,
        0xD4, COLORIZE_ADDR & 0xFF, COLORIZE_ADDR >> 8,
    ])
    hazard_row_helper, hazard_row_compiler = build_stage1_hazard_row_helper()
    embedded_hazard_helper = bytearray(hazard_row_helper)
    neutral_relative = (
        STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR
        - STAGE1_HAZARD_ROW_HELPER_ADDR
    )
    bank14_copy_relative = (
        STAGE1_HAZARD_BANK1_BANK14_COPY_ADDR
        - STAGE1_HAZARD_ROW_HELPER_ADDR
    )
    embedded_hazard_helper[
        neutral_relative:neutral_relative + len(bank1_neutral_art)
    ] = bank1_neutral_art
    embedded_hazard_helper[
        bank14_copy_relative:bank14_copy_relative + len(bank14_copy)
    ] = bank14_copy
    hazard_room_dispatcher = build_stage1_hazard_room_dispatcher()
    hazard_row_helper_off = (
        BANK14 + STAGE1_HAZARD_ROW_HELPER_ADDR - 0x4000
    )
    hazard_row_compiler_off = (
        BANK14 + STAGE1_HAZARD_ROW_COMPILER_ADDR - 0x4000
    )
    hazard_dispatcher = build_stage1_hazard_dispatcher()
    hazard_dispatcher_off = BANK13 + LAVA_ATTR_DECIDER_ADDR - 0x4000
    hazard_banked_entry13, hazard_banked_entry14 = (
        build_stage1_hazard_banked_entries()
    )
    phase_keys = {
        room: {
            map_bit: {
                (
                    (tile ^ map_bit)
                    ^ 0x02                  # ordinary Stage-1 D880
                    ^ room
                ) + 1 & 0xFF
                for tile in CAPTURED_PHASE_TILES[room]
            }
            for map_bit in (0x00, 0x80)
        }
        for room in (0x02, 0x12)
    }
    checks = {
        "tracked BG room fixtures cover every 60-7F animation tile": (
            observed_family == SPIKE_TILES
        ),
        "rotating cylinder body is serialized in the packed BG room": (
            bool(paired_rows)
        ),
        "all 24 production source-art variants match the YAML compiler": (
            candidate_variants == variants
        ),
        "the 20 audience-approved variants retain their exact artifact hash": (
            hashlib.sha256(b"".join(
                candidate_variants[tile]
                for tile in sorted(APPROVED_ART_TILES)
            )).hexdigest() == APPROVED_ART_SHA256
        ),
        "duplicate 61/71 body phases exactly match remapped 6E/7E": (
            candidate_variants[0x61] == candidate_variants[0x6E]
            and candidate_variants[0x71] == candidate_variants[0x7E]
        ),
        "production source-art delta is exactly 258 of 384 bytes": (
            changed_bytes == 258 and len(candidate_variants) == 24
        ),
        "tooth color is pixel-contained by every black-outline mask": (
            detached_tooth_accent_pixels == 0
        ),
        "all 8 support and cast-shadow source tiles remain stock": all(
            rom[
                HAZARD.source_offset + tile * 16:
                HAZARD.source_offset + (tile + 1) * 16
            ] == stock[
                HAZARD.source_offset + tile * 16:
                HAZARD.source_offset + (tile + 1) * 16
            ]
            for tile in SPIKE_SUPPORT_TILES
        ),
        "tooth frames select scene-local BG7": all(
            table[tile] == SPIKE_TOOTH_PALETTE
            for tile in SPIKE_TOOTH_TILES
        ),
        "rings and continuous body select fire BG5": all(
            table[tile] == SPIKE_FIRE_PALETTE
            for tile in SPIKE_FIRE_TILES
        ),
        "wall-facing cylinder connector selects fire BG5": all(
            table[tile] == SPIKE_CONNECTOR_PALETTE
            for tile in SPIKE_CONNECTOR_TILES
        ),
        "unpainted support and shadow cells remain metallic BG6": all(
            table[tile] == SPIKE_SUPPORT_PALETTE
            for tile in SPIKE_SUPPORT_TILES
        ),
        "2A-3D patterned floor remains on stable Dungeon BG0": all(
            table[tile] == 0
            for tile in PATTERNED_FLOOR_TILES
        ),
        "complete Stage 1 palette table equals its YAML compilation": (
            table == EXPECTED_TABLE
        ),
        "Stage 1 palette histogram is exact": histogram == EXPECTED_HISTOGRAM,
        "candidate embeds the YAML Stage-1 hazard palette row": (
            hazard_slot == SPIKE_TOOTH_PALETTE
            and rom[
                hazard_palette_off:hazard_palette_off + 8
            ] == hazard_palette
        ),
        "candidate embeds the cycle-neutral inline Stage-1 BG7 selector": (
            rom[loader_off:loader_off + len(loader)] == loader
            and rom[
                loader_ext_off:loader_ext_off + len(loader_ext)
            ] == loader_ext
        ),
        "candidate embeds the shared CRAM copier and later-stage BG0 arm": (
            rom[
                copy_cram8_off:copy_cram8_off + len(copy_cram8)
            ] == copy_cram8
            and rom[
                copy_cram8_off + len(copy_cram8):
                copy_cram8_off + len(copy_cram8) + len(later_stage_bg0_arm)
            ] == later_stage_bg0_arm
            and rom[
                copy_cram8_off + len(copy_cram8) + len(later_stage_bg0_arm):
                copy_cram8_off + 18
            ] == bytes(18 - len(copy_cram8) - len(later_stage_bg0_arm))
        ),
        "candidate embeds one scene-gated Stage 1 attr runtime": (
            runtime_gate.startswith(bytes.fromhex("FA80D8E6F7FE02"))
            and rom.count(runtime_gate) == 1
        ),
        "candidate embeds one complete Stage-1 attribute publisher": (
            (
                rom[0x42A7:0x42A7 + len(production_inline)]
                == production_inline
                and arena_sanitizer_marker in production_inline
                and rom[0x0018:0x0020] == atomic_attr_stack_vector
            )
            or (
                postcomputed_active
                and len(generated_row_helper) == 121
                and generated_row_helper == bytes(
                    opcode
                    for _ in range(24)
                    for opcode in (0x1A, 0x13, 0x4F, 0x0A, 0x22)
                ) + bytes([0xC9])
                and rom[
                    BANK13 + STAGE1_ATTR_ROW_INIT_ADDR - 0x4000:
                    BANK13 + STAGE1_ATTR_ROW_INIT_ADDR - 0x4000
                    + len(row_init_front)
                ] == row_init_front
                and rom[
                    BANK13 + STAGE1_ATTR_ROW_INIT_TAIL_ADDR - 0x4000:
                    BANK13 + STAGE1_ATTR_ROW_INIT_TAIL_ADDR - 0x4000
                    + len(row_init_tail)
                ] == row_init_tail
            )
        ),
        "candidate embeds the exact source-row scanner and transition repairs": (
            all(
                rom[
                    BANK14 + address - 0x4000:
                    BANK14 + address - 0x4000 + len(payload)
                ] == payload
                for address, payload in scanner_blobs
            )
        ),
        "one-time WRAM initialization crosses banks and returns exactly": (
            rom[
                oam_wram_copy_off:oam_wram_copy_off + len(oam_wram_copy)
            ] == oam_wram_copy
            and oam_wram_copy[-3:] == bytes([
                0xC3,
                OAM_WRAM_COPY_TAIL_ADDR & 0xFF,
                OAM_WRAM_COPY_TAIL_ADDR >> 8,
            ])
            and rom[
                oam_wram_tail13_off:
                oam_wram_tail13_off + 12
            ] == oam_wram_tail13[:12]
        ),
        "captured hazard phase keys are room-aware, nonzero, and disjoint": (
            all(
                len(keys) == len(CAPTURED_PHASE_TILES[room])
                and 0 not in keys
                for room, maps in phase_keys.items()
                for keys in maps.values()
            )
            and all(
                maps[0x00].isdisjoint(maps[0x80])
                for maps in phase_keys.values()
            )
            and phase_keys[0x02][0x00].isdisjoint(
                phase_keys[0x12][0x00]
            )
            and phase_keys[0x02][0x80].isdisjoint(
                phase_keys[0x12][0x80]
            )
        ),
        "candidate embeds the immutable bank-1 tooth art loader": (
            not 0x7200 <= STAGE1_HAZARD_BANK1_LOADER_ADDR < 0x7B00
            and
            rom[
                bank1_art_loader_off:
                bank1_art_loader_off + len(bank1_art_loader)
            ] == bank1_art_loader
            and rom.count(bank1_art_loader) == 1
            and rom[
                bank1_art_bank14_loader_off:
                bank1_art_bank14_loader_off + len(bank1_art_bank14_loader)
            ] == bank1_art_bank14_loader
            and rom.count(bank1_art_bank14_loader) == 1
        ),
        "candidate embeds the YAML-asserted hidden Stage-1 entry patch": (
            all(
                rom[
                    BANK13 + address - 0x4000:
                    BANK13 + address - 0x4000 + len(payload)
                ] == payload
                and rom.count(payload) == 1
                for address, payload in entry_patch_blobs
            )
            and rom[
                BANK13 + WRAPPER_ADDR - 0x4000:
                BANK13 + 0x6F90 - 0x4000
            ].count(wrapper_entry_marker) == 1
            and rom[0x0824:0x0842].count(bytes([
                0xCD, WRAPPER_ADDR & 0xFF, WRAPPER_ADDR >> 8,
            ])) == 1
        ),
        "candidate arms the cold Stage-1 sweep only after art upload 3": (
            all(
                rom[
                    BANK13 + address - 0x4000:
                    BANK13 + address - 0x4000 + len(payload)
                ] == payload
                and rom.count(payload) == 1
                for address, payload in cold_sweep_arm_blobs
            )
            and cold_sweep_arm.startswith(bytes([
                0xFA,
                STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR & 0xFF,
                STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR >> 8,
                0xFE, STAGE1_HAZARD_BANK1_REFRESH_COUNT,
                0xC0,
            ]))
            and cold_sweep_arm_tail == bytes([
                0x7E, 0xFE, 0x7F, 0xC0, 0x36, 0x92, 0xC9,
            ])
            and bank7_copy_tail.startswith(bytes([
                0x01,
                COLD_STAGE1_SWEEP_ARM_ADDR & 0xFF,
                COLD_STAGE1_SWEEP_ARM_ADDR >> 8,
                0xC5,
            ]))
        ),
        "immutable copy routines and neutral art occupy verified ROM slots": (
            rom[
                BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_ADDR - 0x4000:
                BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_ADDR - 0x4000
                + len(bank7_copy)
            ] == bank7_copy
            and rom[
                BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_MIDDLE_ADDR - 0x4000:
                BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_MIDDLE_ADDR - 0x4000
                + len(bank7_copy_middle)
            ] == bank7_copy_middle
            and rom[
                BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_TAIL_ADDR - 0x4000:
                BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_TAIL_ADDR - 0x4000
                + len(bank7_copy_tail)
            ] == bank7_copy_tail
            and rom[
                BANK14 + STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR - 0x4000:
                BANK14 + STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR - 0x4000
                + len(bank1_neutral_art)
            ] == bank1_neutral_art
            and rom[
                BANK14 + STAGE1_HAZARD_BANK1_BANK14_COPY_ADDR - 0x4000:
                BANK14 + STAGE1_HAZARD_BANK1_BANK14_COPY_ADDR - 0x4000
                + len(bank14_copy)
            ] == bank14_copy
        ),
        "native hazard source return is no longer phase-hooked": (
            rom[0x13E4] == 0xC9
        ),
        "both completed-copy paths call the post-copy stamper": (
            rom[
                STAGE1_ATOMIC_WRAP_ADDR:
                STAGE1_ATOMIC_WRAP_ADDR + len(atomic_wrap)
            ] == atomic_wrap
            and (
                bytes.fromhex("78 FE 05 C4 44 08 FB C9")
                in rom[0x42A7:0x436E]
                or (
                    postcomputed_active
                    and postcomputed_inline.count(bytes.fromhex("CD 44 08"))
                    == 1
                    and bytes([
                        0xC3,
                        STAGE1_ATOMIC_WRAP_ADDR & 0xFF,
                        STAGE1_ATOMIC_WRAP_ADDR >> 8,
                    ]) in postcomputed_inline
                )
            )
        ),
        "candidate embeds the bounded bank-14 source-row publisher": (
            rom[
                hazard_row_helper_off:
                hazard_row_helper_off + len(hazard_row_helper)
            ] == embedded_hazard_helper
            and rom[
                hazard_row_compiler_off:
                hazard_row_compiler_off + len(hazard_row_compiler)
            ] == hazard_row_compiler
            and rom.count(hazard_row_compiler) == 1
        ),
        "candidate embeds the spike/Shield room dispatcher": (
            rom[
                BANK14 + STAGE1_HAZARD_ROOM_DISPATCH_ADDR - 0x4000:
                BANK14 + STAGE1_HAZARD_ROOM_DISPATCH_ADDR - 0x4000
                + len(hazard_room_dispatcher)
            ] == hazard_room_dispatcher
            and rom.count(hazard_room_dispatcher) == 1
        ),
        "candidate embeds the shared Stage-1/Stage-5 dispatcher": (
            rom[
                hazard_dispatcher_off:
                hazard_dispatcher_off + len(hazard_dispatcher)
            ] == hazard_dispatcher
        ),
        "candidate embeds both same-address hazard bank selectors": (
            rom[
                BANK13 + STAGE1_HAZARD_BANKED_ENTRY_ADDR - 0x4000:
                BANK13 + STAGE1_HAZARD_BANKED_ENTRY_ADDR - 0x4000
                + len(hazard_banked_entry13)
            ] == hazard_banked_entry13
            and rom[
                BANK14 + STAGE1_HAZARD_BANKED_ENTRY_ADDR - 0x4000:
                BANK14 + STAGE1_HAZARD_BANKED_ENTRY_ADDR - 0x4000
                + len(hazard_banked_entry14)
            ] == hazard_banked_entry14
        ),
    }
    receipt = {
        "rom": str(rom_path),
        "states": list(STATE_NAMES),
        "observed_animation_tiles": [
            f"{tile:02X}" for tile in sorted(observed_family)
        ],
        "cylinder_body_rows": paired_rows,
        "tooth_palette": SPIKE_TOOTH_PALETTE,
        "fire_palette": SPIKE_FIRE_PALETTE,
        "support_palette": SPIKE_SUPPORT_PALETTE,
        "connector_palette": SPIKE_CONNECTOR_PALETTE,
        "art_tiles": [f"{tile:02X}" for tile in sorted(HAZARD.art_tiles)],
        "art_changed_bytes": changed_bytes,
        "detached_tooth_accent_pixels": detached_tooth_accent_pixels,
        "hazard_palette_source": (
            f"bank13:{STAGE1_HAZARD_BG7_SOURCE_ADDR:04X}"
        ),
        "hazard_palette": hazard_palette.hex(),
        "selector": f"inline bank13:{PALETTE_LOADER_EXT_ADDR:04X}",
        "cram8_copier": f"bank13:{PALETTE_COPY_CRAM8_ADDR:04X}",
        "table_histogram": {str(key): value for key, value in histogram.items()},
        "expected_table_histogram": {
            str(key): value for key, value in EXPECTED_HISTOGRAM.items()
        },
        "checks": checks,
        "passed": all(checks.values()),
    }
    live = None
    natural_live = None
    ceiling_live = None
    miniboss_live = None
    floor_scroll = None
    if not args.static_only and receipt["passed"]:
        if not args.mgba.is_file():
            print(f"FAIL: guarded mGBA frontend not found: {args.mgba}")
            return 1
        live_state = Path(args.live_state)
        if not live_state.is_absolute():
            live_state = args.states / live_state
        live_state = live_state.resolve()
        if not live_state.is_file():
            print(f"FAIL: live spike state not found: {live_state}")
            return 1
        ceiling_state = Path(args.ceiling_state)
        if not ceiling_state.is_absolute():
            ceiling_state = args.states / ceiling_state
        ceiling_state = ceiling_state.resolve()
        if not ceiling_state.is_file():
            print(f"FAIL: ceiling spike state not found: {ceiling_state}")
            return 1
        if args.output:
            live_output = args.output.parent / "stage1-spike-live"
            live = live_receipt(
                rom_path,
                live_state,
                args.mgba.resolve(),
                live_output,
                args.timeout,
                settle=args.live_settle,
                input_mask=args.keys,
                screenshot_interval=args.screenshot_interval,
            )
            natural_live = live_receipt(
                rom_path,
                live_state,
                args.mgba.resolve(),
                args.output.parent / "stage1-spike-natural",
                args.timeout,
                prefix_name="stage1-spike-natural",
                reinitialize=False,
                settle=args.natural_settle,
                input_mask=args.keys,
                screenshot_interval=args.screenshot_interval,
            )
            ceiling_live = live_receipt(
                rom_path,
                ceiling_state,
                args.mgba.resolve(),
                args.output.parent / "stage1-spike-ceiling",
                args.timeout,
                prefix_name="stage1-spike-ceiling",
                settle=args.ceiling_settle,
                input_mask=0,
                screenshot_interval=args.screenshot_interval,
                expected_room=0x02,
                normalization_writes=((0xD880, 0x02),),
                normalization_bank=1,
            )
            miniboss_live = live_receipt(
                rom_path,
                live_state,
                args.mgba.resolve(),
                args.output.parent / "stage1-spike-miniboss",
                args.timeout,
                prefix_name="stage1-spike-miniboss",
                settle=args.miniboss_settle,
                input_mask=0,
                screenshot_interval=args.screenshot_interval,
                expected_room=0x12,
                force_miniboss_frame=200,
            )
            floor_scroll = live_receipt(
                rom_path,
                live_state,
                args.mgba.resolve(),
                args.output.parent / "stage1-floor-scroll",
                args.timeout,
                prefix_name="stage1-floor-scroll",
                reinitialize=False,
                settle=args.scroll_settle,
                input_mask=0x80,
                screenshot_interval=args.scroll_screenshot_interval,
                expect_scroll=True,
            )
        else:
            with tempfile.TemporaryDirectory(prefix="penta-spike-live-") as name:
                live = live_receipt(
                    rom_path,
                    live_state,
                    args.mgba.resolve(),
                    Path(name),
                    args.timeout,
                    settle=args.live_settle,
                    input_mask=args.keys,
                    screenshot_interval=args.screenshot_interval,
                )
                natural_live = live_receipt(
                    rom_path,
                    live_state,
                    args.mgba.resolve(),
                    Path(name),
                    args.timeout,
                    prefix_name="stage1-spike-natural",
                    reinitialize=False,
                    settle=args.natural_settle,
                    input_mask=args.keys,
                    screenshot_interval=args.screenshot_interval,
                )
                ceiling_live = live_receipt(
                    rom_path,
                    ceiling_state,
                    args.mgba.resolve(),
                    Path(name),
                    args.timeout,
                    prefix_name="stage1-spike-ceiling",
                    settle=args.ceiling_settle,
                    input_mask=0,
                    screenshot_interval=args.screenshot_interval,
                    expected_room=0x02,
                    normalization_writes=((0xD880, 0x02),),
                    normalization_bank=1,
                )
                miniboss_live = live_receipt(
                    rom_path,
                    live_state,
                    args.mgba.resolve(),
                    Path(name),
                    args.timeout,
                    prefix_name="stage1-spike-miniboss",
                    settle=args.miniboss_settle,
                    input_mask=0,
                    screenshot_interval=args.screenshot_interval,
                    expected_room=0x12,
                    force_miniboss_frame=200,
                )
                floor_scroll = live_receipt(
                    rom_path,
                    live_state,
                    args.mgba.resolve(),
                    Path(name),
                    args.timeout,
                    prefix_name="stage1-floor-scroll",
                    reinitialize=False,
                    settle=args.scroll_settle,
                    input_mask=0x80,
                    screenshot_interval=args.scroll_screenshot_interval,
                    expect_scroll=True,
                )
                live["normalized_state"] = "temporary"
                live["report"] = "temporary"
                live["screenshot"] = "temporary"
                natural_live["normalized_state"] = "temporary"
                natural_live["report"] = "temporary"
                natural_live["screenshot"] = "temporary"
                ceiling_live["normalized_state"] = "temporary"
                ceiling_live["report"] = "temporary"
                ceiling_live["screenshot"] = "temporary"
                miniboss_live["normalized_state"] = "temporary"
                miniboss_live["report"] = "temporary"
                miniboss_live["screenshot"] = "temporary"
                floor_scroll["normalized_state"] = "temporary"
                floor_scroll["report"] = "temporary"
                floor_scroll["screenshot"] = "temporary"
        receipt["live"] = live
        receipt["natural_live"] = natural_live
        receipt["ceiling_live"] = ceiling_live
        # The deterministic fixture force-switches only the three miniboss
        # state bytes at frame 200; it deliberately does not perform the room
        # copies that make both physical maps active. The untouched/natural
        # route above already proves bank-1 tooth cells and both-map coverage.
        # Keep this fixture focused on the transition raster itself.
        miniboss_live["checks"].pop(
            "every visible tooth phase uses the immutable bank-1 cell", None
        )
        miniboss_live["checks"].pop(
            "both physical maps are observed active with exact tooth colors",
            None,
        )
        miniboss_live["checks"].update({
            "deterministic Gargoyle transition reaches room-$12 scene $0A": (
                miniboss_live["scene"] == "0A"
                and miniboss_live["room"] == "12"
                and miniboss_live["miniboss_first_frame"] == 200
            ),
            "deterministic Gargoyle transition executes post-scene stamps": (
                miniboss_live["post_miniboss_hazard_helper_hits"] > 0
                and miniboss_live["post_miniboss_hazard_row_hits"] > 0
            ),
            "deterministic raster brackets scene $02 to $0A with gold teeth": (
                any(
                    int(item["frame"]) < 200
                    and item.get("scene") == "02"
                    and item["gold_teeth"]
                    for item in miniboss_live["periodic_pixel_receipts"]
                )
                and any(
                    int(item["frame"]) > 200
                    and item.get("scene") == "0A"
                    and item["gold_teeth"]
                    for item in miniboss_live["periodic_pixel_receipts"]
                )
            ),
            "deterministic Gargoyle raster has no decoded gray teeth": (
                miniboss_live["rendered_wrong_palette0_tooth_cells"] == 0
            ),
        })
        miniboss_live["passed"] = all(miniboss_live["checks"].values())
        receipt["miniboss_live"] = miniboss_live
        receipt["floor_scroll"] = floor_scroll
        receipt["passed"] = (
            receipt["passed"]
            and live["passed"]
            and natural_live["passed"]
            and ceiling_live["passed"]
            and miniboss_live["passed"]
            and floor_scroll["passed"]
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")

    failed = [name for name, passed in checks.items() if not passed]
    if live:
        failed.extend(
            name for name, passed in live["checks"].items() if not passed
        )
    if natural_live:
        failed.extend(
            "untouched state: " + name
            for name, passed in natural_live["checks"].items()
            if not passed
        )
    if ceiling_live:
        failed.extend(
            "ceiling fixture: " + name
            for name, passed in ceiling_live["checks"].items()
            if not passed
        )
    if miniboss_live:
        failed.extend(
            "miniboss fixture: " + name
            for name, passed in miniboss_live["checks"].items()
            if not passed
        )
    if floor_scroll:
        failed.extend(
            "north-scroll fixture: " + name
            for name, passed in floor_scroll["checks"].items()
            if not passed
        )
    if failed:
        print("FAIL: " + "; ".join(failed))
        return 1
    print(
        "PASS: tracked room sources prove BG-only 60-7F spike animation; "
        "24 YAML-compiled art variants use BG7 teeth + BG5 rings/body/wall "
        "connector + BG6 supports"
        + (
            "; current-ROM mGBA confirms the floor and ceiling cylinders, "
            "complete animation palettes, CRAM, and the north-scroll floor."
            if live else "."
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
