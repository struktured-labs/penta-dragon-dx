#!/usr/bin/env python3
"""Independently reject the four reported Stage-1 rendered regressions.

The oracle is deliberately not built from candidate ROM palettes, remapped
tiles, VRAM, or expected maps.  It uses fixed rendered-color semantics,
hazard-row geometry, and temporal consistency against the pre-menu pixels in
the same stationary ROM-owned route.

Two byte-identical rendered replays are required.  ``--expect-known-bad`` is
an explicit negative-control mode: it succeeds only when the requested defect
class is detected and the normal continuity receipt is failing.  ``--self-test``
runs in-memory good and four-class bad controls without launching an emulator.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Sequence

from PIL import Image


SCHEMA = "penta-stage1-rendered-continuity-v1"
STATE_SCHEMA = "penta-stage1-hazard-state-v1"
MENU_SCHEMA = "penta-stage1-current-hazard-menu-v1"
ORACLE = "independent-rendered-continuity"
WIDTH = 160
HEIGHT = 144
PLAYFIELD_HEIGHT = 112
ROOT = Path(__file__).resolve().parents[2]
OPERATOR_CAPTURE_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures/stage1_rendered_operator_captures.json"
)
OPERATOR_CAPTURE_FIXTURE_SHA256 = (
    "2bdeefbcb71517b6b66786460956f153e25e82b5b68715ca1303990de74bd6d7"
)
OPERATOR_CAPTURE_SCHEMA = "penta-stage1-rendered-operator-captures-v1"
# The native item Window begins at scanline 96.  Pixels below this line are
# authored menu UI while SELECT is held, not the still-visible gameplay wall.
MENU_WINDOW_TOP = 96
FRAME_PATTERN = re.compile(r"-frame(\d{4})\.png$")


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    require(path.is_file(), f"required file is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file(), f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise VerificationError(f"invalid {label}: {error}") from error
    require(isinstance(value, dict), f"{label} is not a JSON object")
    return value


def all_true(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and bool(value)
        and all(item is True for item in value.values())
    )


def is_red_or_orange(color: tuple[int, int, int]) -> bool:
    red, green, blue = color
    return red >= 180 and red >= green + 50 and red >= blue + 40


def is_yellow(color: tuple[int, int, int]) -> bool:
    red, green, blue = color
    return red >= 220 and green >= 180 and blue <= 100


def is_gray(color: tuple[int, int, int]) -> bool:
    return 45 <= color[0] <= 200 and max(color) - min(color) <= 8


def is_achromatic_dark(color: tuple[int, int, int]) -> bool:
    return max(color) <= 200 and max(color) - min(color) <= 8


def is_saturated_red_or_green(color: tuple[int, int, int]) -> bool:
    red, green, blue = color
    return (
        (red >= 150 and red >= green + 60 and red >= blue + 50)
        or (green >= 120 and green >= red + 35 and green >= blue + 20)
    )


def is_floor_light(color: tuple[int, int, int]) -> bool:
    red, green, blue = color
    return (
        (red >= 145 and green >= 145 and blue >= 180)
        or min(color) >= 235
    )


def is_hazard_material(color: tuple[int, int, int]) -> bool:
    return is_red_or_orange(color) or is_yellow(color)


class RenderedFrame:
    def __init__(
        self,
        number: int,
        pixels: tuple[tuple[int, int, int], ...],
        *,
        path: Path | None = None,
        payload_sha256: str | None = None,
    ) -> None:
        require(len(pixels) == WIDTH * HEIGHT,
                f"frame {number} is not {WIDTH}x{HEIGHT}")
        self.number = number
        self.pixels = pixels
        self.path = path
        self.payload_sha256 = payload_sha256 or digest_bytes(
            bytes(channel for color in pixels for channel in color)
        )


def load_frames(directory: Path) -> list[RenderedFrame]:
    require(directory.is_dir(), f"rendered frame directory is missing: {directory}")
    paths: list[tuple[int, Path]] = []
    for path in directory.glob("*.png"):
        match = FRAME_PATTERN.search(path.name)
        if match is not None:
            paths.append((int(match.group(1)), path.resolve()))
    paths.sort()
    require(paths, f"no numbered rendered frames found in {directory}")
    numbers = [number for number, _ in paths]
    require(len(numbers) == len(set(numbers)),
            f"duplicate frame numbers in {directory}")

    frames: list[RenderedFrame] = []
    for number, path in paths:
        with Image.open(path) as source:
            image = source.convert("RGB")
            require(image.size == (WIDTH, HEIGHT),
                    f"wrong rendered size {image.size}: {path}")
            pixels = tuple(image.getdata())
        frames.append(RenderedFrame(
            number, pixels, path=path, payload_sha256=sha256(path)
        ))
    return frames


def manifest(frames: Sequence[RenderedFrame]) -> tuple[str, list[dict[str, Any]]]:
    rows = [
        {
            "frame": frame.number,
            "sha256": frame.payload_sha256,
            **({"path": str(frame.path)} if frame.path is not None else {}),
        }
        for frame in frames
    ]
    semantic_rows = [
        {"frame": row["frame"], "sha256": row["sha256"]} for row in rows
    ]
    encoded = json.dumps(
        semantic_rows, sort_keys=True, separators=(",", ":")
    ).encode()
    return digest_bytes(encoded), rows


def cell_pixels(
    pixels: Sequence[tuple[int, int, int]], x: int, y: int
) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        color
        for row in range(y, y + 8)
        for color in pixels[row * WIDTH + x:row * WIDTH + x + 8]
    )


def mask_sha256(indices: Iterable[int]) -> str:
    """Hash an LSB-first playfield bit mask without storing expected pixels."""
    packed = bytearray((WIDTH * PLAYFIELD_HEIGHT + 7) // 8)
    for index in indices:
        require(0 <= index < WIDTH * PLAYFIELD_HEIGHT,
                "rendered mask index is outside the playfield")
        packed[index // 8] |= 1 << (index % 8)
    return digest_bytes(bytes(packed))


def clear_hazard_cells(
    frame: RenderedFrame, occluded: frozenset[int] = frozenset(),
) -> list[tuple[int, int]]:
    """Return floor-clear BG cells bracketed by observable BG hazard cells.

    Hardware sprites are not background evidence.  Their full screen-space
    footprints are exclusion-only: no color underneath a sprite is accepted
    as good, but a moving sprite also cannot bracket an ordinary floor cell
    and turn it into a false clear-tile report.
    """
    bad_cells: list[tuple[int, int]] = []
    for y in range(0, PLAYFIELD_HEIGHT - 8, 8):
        material_counts = []
        floor_counts = []
        cells = []
        for x in range(0, WIDTH, 8):
            cell = cell_pixels(frame.pixels, x, y)
            cells.append(cell)
            indices = tuple(
                row * WIDTH + column
                for row in range(y, y + 8)
                for column in range(x, x + 8)
            )
            material_counts.append(sum(
                is_hazard_material(color) and index not in occluded
                for color, index in zip(cell, indices, strict=True)
            ))
            floor_counts.append(sum(
                is_floor_light(color) and index not in occluded
                for color, index in zip(cell, indices, strict=True)
            ))
        occupied = [
            index for index, count in enumerate(material_counts)
            if count >= 4
        ]
        if len(occupied) < 3:
            continue
        for index in range(min(occupied) + 1, max(occupied)):
            x = index * 8
            # The native item Window occupies this fixed screen box.
            if 64 <= x < 96 and 32 <= y < 64:
                continue
            if (
                material_counts[index] == 0
                and floor_counts[index] >= 58
            ):
                bad_cells.append((x, y))
    return bad_cells


def static_achromatic_mask(
    baseline: Sequence[RenderedFrame],
) -> tuple[bool, ...]:
    return tuple(
        all(is_achromatic_dark(frame.pixels[index]) for frame in baseline)
        for index in range(WIDTH * PLAYFIELD_HEIGHT)
    )


def edge_wall_component(pixels: Sequence[tuple[int, int, int]]) -> set[int]:
    usable = [
        is_achromatic_dark(color)
        for color in pixels[:WIDTH * PLAYFIELD_HEIGHT]
    ]
    seen: set[int] = set()
    queue: deque[int] = deque()
    for y in range(PLAYFIELD_HEIGHT):
        for x in (0, WIDTH - 1):
            index = y * WIDTH + x
            if usable[index] and index not in seen:
                seen.add(index)
                queue.append(index)
    while queue:
        index = queue.popleft()
        x = index % WIDTH
        y = index // WIDTH
        for next_x, next_y in (
            (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1),
        ):
            if not (0 <= next_x < WIDTH and 0 <= next_y < PLAYFIELD_HEIGHT):
                continue
            next_index = next_y * WIDTH + next_x
            if usable[next_index] and next_index not in seen:
                seen.add(next_index)
                queue.append(next_index)
    return seen


def stable_wall_mask(baseline: Sequence[RenderedFrame]) -> set[int]:
    counts = [0] * (WIDTH * PLAYFIELD_HEIGHT)
    for frame in baseline:
        for index in edge_wall_component(frame.pixels):
            counts[index] += 1
    threshold = max(1, (9 * len(baseline) + 9) // 10)
    return {index for index, count in enumerate(counts) if count >= threshold}


def expanded_indices(indices: Iterable[int], radius: int) -> set[int]:
    expanded: set[int] = set()
    for index in indices:
        x = index % WIDTH
        y = index // WIDTH
        for next_y in range(
            max(0, y - radius), min(PLAYFIELD_HEIGHT, y + radius + 1)
        ):
            expanded.update(range(
                next_y * WIDTH + max(0, x - radius),
                next_y * WIDTH + min(WIDTH, x + radius + 1),
            ))
    return expanded


def clear_cell_frames(
    frames: Sequence[RenderedFrame],
    oam_coverage: dict[int, frozenset[int]] | None = None,
) -> tuple[int, list[int]]:
    bad_numbers: list[int] = []
    for frame in frames:
        occluded = (
            oam_coverage.get(frame.number, frozenset())
            if oam_coverage is not None else frozenset()
        )
        bad_cells = len(clear_hazard_cells(frame, occluded))
        # A fully white cell is independently invalid even outside a hazard
        # row.  Authored Stage-1 floor cells retain lavender texture pixels.
        for y in range(0, PLAYFIELD_HEIGHT - 8, 8):
            for x in range(8, WIDTH - 8, 8):
                cell = cell_pixels(frame.pixels, x, y)
                indices = tuple(
                    row * WIDTH + column
                    for row in range(y, y + 8)
                    for column in range(x, x + 8)
                )
                if sum(
                    color == (255, 255, 255) and index not in occluded
                    for color, index in zip(cell, indices, strict=True)
                ) >= 62:
                    bad_cells += 1
        if bad_cells:
            bad_numbers.append(frame.number)
    return len(bad_numbers), bad_numbers


def yellow_trail_frames(frames: Sequence[RenderedFrame]) -> tuple[int, list[int]]:
    bad_numbers: list[int] = []
    for frame in frames:
        red_pixels = [
            index
            for index, color in enumerate(
                frame.pixels[:WIDTH * PLAYFIELD_HEIGHT]
            )
            if is_red_or_orange(color)
        ]
        red_neighborhood = expanded_indices(red_pixels, 16)
        unsupported_yellow = sum(
            is_yellow(color) and index not in red_neighborhood
            for index, color in enumerate(
                frame.pixels[:WIDTH * PLAYFIELD_HEIGHT]
            )
        )
        if unsupported_yellow >= 3:
            bad_numbers.append(frame.number)
    return len(bad_numbers), bad_numbers


def gray_spike_frames(
    frames: Sequence[RenderedFrame], baseline: Sequence[RenderedFrame]
) -> tuple[int, list[int]]:
    static_mask = static_achromatic_mask(baseline)
    bad_numbers: list[int] = []
    for frame in frames:
        material = [
            index
            for index, color in enumerate(
                frame.pixels[:WIDTH * PLAYFIELD_HEIGHT]
            )
            if is_hazard_material(color)
        ]
        neighborhood = expanded_indices(material, 5)
        suspect = sum(
            index in neighborhood
            and is_gray(color)
            and not static_mask[index]
            for index, color in enumerate(
                frame.pixels[:WIDTH * PLAYFIELD_HEIGHT]
            )
        )
        if suspect >= 3:
            bad_numbers.append(frame.number)
    return len(bad_numbers), bad_numbers


def wall_edge_artifact_frames(
    frames: Sequence[RenderedFrame],
    baseline: Sequence[RenderedFrame],
    first_menu_frame: int,
    menu_close_frame: int,
    oam_coverage: dict[int, frozenset[int]] | None = None,
) -> tuple[int, list[int]]:
    wall = stable_wall_mask(baseline)
    samples: list[tuple[int, set[int]]] = []
    for frame in frames:
        if frame.number < first_menu_frame:
            continue
        visible_gameplay_height = (
            MENU_WINDOW_TOP
            if frame.number <= menu_close_frame
            else PLAYFIELD_HEIGHT
        )
        saturated = {
            index
            for index in wall
            if index // WIDTH < visible_gameplay_height
            if oam_coverage is None
            or index not in oam_coverage.get(frame.number, frozenset())
            if is_saturated_red_or_green(frame.pixels[index])
            and not (
                64 <= index % WIDTH < 96
                and 32 <= index // WIDTH < 64
            )
        }
        samples.append((frame.number, saturated))

    runs: defaultdict[int, int] = defaultdict(int)
    maxima: defaultdict[int, int] = defaultdict(int)
    for _, saturated in samples:
        for index in list(runs):
            if index not in saturated:
                runs[index] = 0
        for index in saturated:
            runs[index] += 1
            maxima[index] = max(maxima[index], runs[index])
    persistent = {index for index, run in maxima.items() if run >= 6}
    bad_numbers = [
        number for number, saturated in samples
        if len(saturated & persistent) >= 2
    ]
    return len(bad_numbers), bad_numbers


def phase_count(frames: Sequence[RenderedFrame]) -> int:
    signatures: set[str] = set()
    for frame in frames:
        bits = bytearray()
        for y in range(0, PLAYFIELD_HEIGHT, 4):
            for x in range(0, WIDTH, 4):
                count = 0
                for next_y in range(y, min(y + 4, PLAYFIELD_HEIGHT)):
                    for next_x in range(x, min(x + 4, WIDTH)):
                        if is_hazard_material(
                            frame.pixels[next_y * WIDTH + next_x]
                        ):
                            count += 1
                bits.append(count)
        signatures.add(digest_bytes(bytes(bits)))
    return min(4, len(signatures))


def analyze(
    frames: Sequence[RenderedFrame], *, first_menu_frame: int,
    menu_close_frame: int,
    oam_coverage: dict[int, frozenset[int]] | None = None,
) -> tuple[dict[str, int], dict[str, list[int]]]:
    baseline = [frame for frame in frames if frame.number < first_menu_frame]
    require(len(frames) >= 120, "fewer than 120 rendered samples")
    require(len(baseline) >= 24, "fewer than 24 untouched pre-menu samples")
    clear_count, clear_numbers = clear_cell_frames(frames, oam_coverage)
    yellow_count, yellow_numbers = yellow_trail_frames(frames)
    gray_count, gray_numbers = gray_spike_frames(frames, baseline)
    wall_count, wall_numbers = wall_edge_artifact_frames(
        frames, baseline, first_menu_frame, menu_close_frame, oam_coverage
    )
    material_frames = sum(
        sum(
            is_hazard_material(color)
            for color in frame.pixels[:WIDTH * PLAYFIELD_HEIGHT]
        ) >= 32
        for frame in frames
    )
    metrics = {
        "rendered_frames": len(frames),
        "hazard_visible_frames": material_frames,
        "hazard_phases": phase_count(baseline),
        "clear_cell_frames": clear_count,
        "yellow_trail_frames": yellow_count,
        "gray_spike_frames": gray_count,
        "wall_edge_artifact_frames": wall_count,
    }
    failures = {
        "clear_cell_frames": clear_numbers,
        "yellow_trail_frames": yellow_numbers,
        "gray_spike_frames": gray_numbers,
        "wall_edge_artifact_frames": wall_numbers,
    }
    return metrics, failures


def load_pinned_operator_frame(specification: dict[str, Any]) -> RenderedFrame:
    """Load one reviewed PNG only after both file and RGB hashes match."""
    relative = specification.get("path")
    require(isinstance(relative, str) and relative,
            "operator rendered-capture path is invalid")
    path = (ROOT / relative).resolve()
    require(path.is_relative_to(ROOT),
            "operator rendered capture escapes the repository")
    require(sha256(path) == specification.get("sha256"),
            f"operator rendered capture hash changed: {relative}")
    with Image.open(path) as source:
        image = source.convert("RGB")
        require(image.size == (WIDTH, HEIGHT),
                f"wrong operator rendered size {image.size}: {path}")
        pixels = tuple(image.getdata())
    rgb = bytes(channel for color in pixels for channel in color)
    require(digest_bytes(rgb) == specification.get("rgb_sha256"),
            f"operator rendered RGB hash changed: {relative}")
    return RenderedFrame(
        0, pixels, path=path, payload_sha256=specification["sha256"]
    )


def load_operator_capture_controls(
) -> tuple[dict[str, Any], dict[str, RenderedFrame]]:
    """Authenticate the two PNG regressions not owned by the scene-$0B gate."""
    require(
        sha256(OPERATOR_CAPTURE_FIXTURE)
        == OPERATOR_CAPTURE_FIXTURE_SHA256,
        "rendered operator-capture fixture changed",
    )
    fixture = load_json(
        OPERATOR_CAPTURE_FIXTURE, "rendered operator-capture fixture"
    )
    require(fixture.get("schema") == OPERATOR_CAPTURE_SCHEMA,
            "wrong rendered operator-capture fixture schema")
    require(fixture.get("oracle") == "hash-pinned-rendered-pixels-only",
            "rendered operator-capture oracle changed")
    specifications = fixture.get("captures")
    require(isinstance(specifications, list) and len(specifications) == 2,
            "exactly two supplemental operator PNGs are required")
    by_label = {row.get("label"): row for row in specifications}
    require(set(by_label) == {
        "operator-busted-room", "operator-official-room01-wall-edge",
    }, "supplemental operator PNG labels changed")
    return fixture, {
        label: load_pinned_operator_frame(specification)
        for label, specification in by_label.items()
    }


def reviewed_region_indices(
    rectangles: Sequence[Sequence[int]],
) -> set[int]:
    """Decode reviewed half-open rectangles into a unique playfield mask."""
    indices: set[int] = set()
    area = 0
    require(bool(rectangles), "reviewed wall regions are missing")
    for rectangle in rectangles:
        require(len(rectangle) == 4 and all(
            isinstance(value, int) for value in rectangle
        ), "reviewed wall rectangle is invalid")
        left, top, right, bottom = rectangle
        require(0 <= left < right <= WIDTH
                and 0 <= top < bottom <= PLAYFIELD_HEIGHT,
                "reviewed wall rectangle is outside the playfield")
        area += (right - left) * (bottom - top)
        indices.update(
            y * WIDTH + x
            for y in range(top, bottom)
            for x in range(left, right)
        )
    require(len(indices) == area, "reviewed wall rectangles overlap")
    return indices


def reviewed_wall_palette_continuity(
    frame: RenderedFrame, rectangles: Sequence[Sequence[int]],
) -> dict[str, Any]:
    """Check reviewed room-$01 wall strips against fixed BG0/BG6 colors.

    These strips and colors are an archived human-reviewed negative control.
    They are never learned from a candidate ROM, VRAM, or candidate frame.
    """
    region = reviewed_region_indices(rectangles)
    bg0_dark = {
        index for index in region
        if frame.pixels[index] == (82, 82, 123)
    }
    bg6_dark = {
        index for index in region
        if frame.pixels[index] == (66, 66, 123)
    }
    return {
        "region_pixels": len(region),
        "region_mask_sha256": mask_sha256(region),
        "bg0_dark_pixels": len(bg0_dark),
        "bg0_dark_mask_sha256": mask_sha256(bg0_dark),
        "bg6_dark_pixels": len(bg6_dark),
        "bg6_dark_mask_sha256": mask_sha256(bg6_dark),
        "mixed_bg0_bg6": bool(bg0_dark) and bool(bg6_dark),
        "exact_bg6_wall": not bg0_dark and bool(bg6_dark),
    }


def operator_capture_controls() -> dict[str, bool]:
    """Exercise generic classifiers on the two supplemental real captures."""
    fixture, frames = load_operator_capture_controls()
    specifications = {
        row["label"]: row for row in fixture["captures"]
    }

    busted = frames["operator-busted-room"]
    busted_spec = specifications["operator-busted-room"]
    expected_clear = [
        tuple(cell) for cell in busted_spec["expected_clear_hazard_cells"]
    ]
    clear_cells = clear_hazard_cells(busted)
    clear_count, clear_frames = clear_cell_frames([busted])

    wall = frames["operator-official-room01-wall-edge"]
    wall_spec = specifications["operator-official-room01-wall-edge"]
    wall_result = reviewed_wall_palette_continuity(
        wall, wall_spec["reviewed_wall_regions"]
    )
    bg0_spec = wall_spec["bg0_dark"]
    bg6_spec = wall_spec["bg6_dark"]
    wall_fixture_exact = (
        wall_result["region_pixels"] == wall_spec["region_mask_pixels"]
        and wall_result["region_mask_sha256"]
        == wall_spec["region_mask_sha256"]
        and wall_result["bg0_dark_pixels"] == bg0_spec["pixels"]
        and wall_result["bg0_dark_mask_sha256"]
        == bg0_spec["mask_sha256"]
        and wall_result["bg6_dark_pixels"] == bg6_spec["pixels"]
        and wall_result["bg6_dark_mask_sha256"]
        == bg6_spec["mask_sha256"]
    )
    return {
        "supplemental_operator_pngs_are_file_and_rgb_hash_pinned": all(
            len(row["sha256"]) == 64 and len(row["rgb_sha256"]) == 64
            for row in fixture["captures"]
        ),
        "real_busted_room_clear_hazard_cells_match_reviewed_fixture": (
            clear_cells == expected_clear
        ),
        "real_busted_room_is_rejected_by_generic_clear_classifier": (
            clear_count == 1 and clear_frames == [busted.number]
        ),
        "real_official_wall_masks_match_reviewed_fixture": wall_fixture_exact,
        "real_official_mixed_room01_wall_ramp_is_rejected": (
            wall_result["mixed_bg0_bg6"]
            and not wall_result["exact_bg6_wall"]
        ),
    }


def mutation_controls() -> dict[str, bool]:
    good_metrics, _ = analyze(
        synthetic_frames(), first_menu_frame=185, menu_close_frame=440
    )
    controls = {
        "known_good_has_zero_reported_defects": all(
            good_metrics[name] == 0 for name in (
                "clear_cell_frames", "yellow_trail_frames",
                "gray_spike_frames", "wall_edge_artifact_frames",
            )
        )
    }
    for defect, metric in (
        ("clear", "clear_cell_frames"),
        ("yellow", "yellow_trail_frames"),
        ("gray", "gray_spike_frames"),
        ("wall", "wall_edge_artifact_frames"),
    ):
        metrics, _ = analyze(
            synthetic_frames(defect),
            first_menu_frame=185,
            menu_close_frame=440,
        )
        controls[f"known_bad_{defect}_is_rejected"] = metrics[metric] > 0
    controls.update(operator_capture_controls())
    return controls


def report_value(path: Path, requested_key: str) -> str:
    """Read one unique key from a hash-bound probe report."""
    require(path.is_file(), f"hazard-menu raw report is missing: {path}")
    matches: list[str] = []
    for line in path.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == requested_key:
            matches.append(value)
    require(len(matches) == 1,
            f"raw report does not contain exactly one {requested_key}")
    return matches[0]


def oam_coverage_by_frame(path: Path) -> dict[int, frozenset[int]]:
    """Decode hardware OAM receipts into clipped screen-space exclusions."""
    trace = report_value(path, "periodic_render_oam_trace")
    require(trace, "periodic hardware OAM trace is missing")
    result: dict[int, frozenset[int]] = {}
    for entry in trace.split(";"):
        match = re.fullmatch(r"f(\d+):h(8|16):(.*)", entry)
        require(match is not None, "malformed periodic hardware OAM entry")
        frame_number = int(match.group(1))
        require(frame_number not in result,
                f"duplicate periodic OAM frame {frame_number}")
        height = int(match.group(2))
        covered: set[int] = set()
        body = match.group(3)
        if body:
            sprites = body.split(",")
            require(all(re.fullmatch(
                r"\d+/\d+/\d+/[0-9A-F]{2}/[0-9A-F]{2}", sprite
            ) for sprite in sprites), "malformed hardware OAM sprite receipt")
            for sprite in sprites:
                slot, raw_x, raw_y, _tile, _flags = sprite.split("/")
                x = int(raw_x)
                y = int(raw_y)
                require(0 <= int(slot) < 40 and 0 <= x <= 255 and 0 <= y <= 255,
                        "hardware OAM sprite receipt is out of range")
                left = x - 8
                top = y - 16
                for screen_y in range(
                    max(0, top), min(PLAYFIELD_HEIGHT, top + height)
                ):
                    covered.update(range(
                        screen_y * WIDTH + max(0, left),
                        screen_y * WIDTH + min(WIDTH, left + 8),
                    ))
        result[frame_number] = frozenset(covered)
    return result


def validate_sources(
    rom: Path,
    state_receipt_path: Path,
    menu_receipt_path: Path,
    frame_dirs: Sequence[Path],
) -> tuple[
    str, dict[str, Any], dict[str, Any], list[list[RenderedFrame]],
    list[dict[int, frozenset[int]]],
]:
    rom_sha256 = sha256(rom)
    state_receipt = load_json(state_receipt_path, "hazard-state receipt")
    menu_receipt = load_json(menu_receipt_path, "hazard-menu receipt")
    require(state_receipt.get("schema") == STATE_SCHEMA,
            "wrong hazard-state receipt schema")
    require(state_receipt.get("passed") is True,
            "hazard-state receipt did not pass")
    require(state_receipt.get("rom_sha256") == rom_sha256,
            "hazard-state receipt targets another ROM")
    require(menu_receipt.get("schema") == MENU_SCHEMA,
            "wrong hazard-menu receipt schema")
    require(menu_receipt.get("passed") is True,
            "hazard-menu receipt did not pass")
    require(menu_receipt.get("rom_sha256") == rom_sha256,
            "hazard-menu receipt targets another ROM")
    require(menu_receipt.get("state_sha256") == state_receipt.get("state_sha256"),
            "hazard-menu receipt uses another state")
    require(
        menu_receipt.get("state_receipt_sha256") == sha256(state_receipt_path),
        "hazard-menu receipt is not bound to the supplied state receipt",
    )
    require(all_true(menu_receipt.get("checks")),
            "hazard-menu top-level checks did not all pass")
    replays = menu_receipt.get("replays")
    require(isinstance(replays, list) and len(replays) == 2,
            "exactly two hazard-menu replays are required")
    require(replays[0] == replays[1],
            "hazard-menu summaries are not deterministic")
    require(all_true(replays[0].get("checks")),
            "hazard-menu replay checks did not all pass")
    require(replays[0].get("scene") == "02" and replays[0].get("room") == "01",
            "hazard-menu replay is not Stage-1 hazard room 01")
    require(replays[0].get("post_menu_input_mask") == 0,
            "hazard-menu replay moved after menu close")
    require(len(frame_dirs) == 2, "exactly two rendered frame directories are required")
    raw_reports = menu_receipt.get("raw_reports")
    require(isinstance(raw_reports, list) and len(raw_reports) == 2,
            "hazard-menu raw report bindings are missing")
    resolved_dirs = [directory.resolve() for directory in frame_dirs]
    resolved_reports = [Path(report).resolve() for report in raw_reports]
    for directory, report in zip(resolved_dirs, resolved_reports, strict=True):
        require(report.parent == directory,
                "rendered frame directory is not bound by its raw report")
    loaded = [load_frames(directory) for directory in resolved_dirs]
    oam_coverage = [oam_coverage_by_frame(report) for report in resolved_reports]
    for frames, coverage in zip(loaded, oam_coverage, strict=True):
        require(
            set(coverage) == {frame.number for frame in frames},
            "hardware OAM trace does not cover the exact rendered frames",
        )
    first_manifest, _ = manifest(loaded[0])
    second_manifest, _ = manifest(loaded[1])
    require(first_manifest == second_manifest,
            "rendered replay frame manifests are not byte-identical")
    require(oam_coverage[0] == oam_coverage[1],
            "rendered replays have different hardware OAM footprints")
    return rom_sha256, state_receipt, menu_receipt, loaded, oam_coverage


def build_receipt(
    *,
    rom: Path,
    state_receipt_path: Path,
    menu_receipt_path: Path,
    frame_dirs: Sequence[Path],
    output: Path,
) -> dict[str, Any]:
    rom_sha256, state_receipt, menu_receipt, loaded, oam_coverage = validate_sources(
        rom, state_receipt_path, menu_receipt_path, frame_dirs
    )
    first_menu_frame = int(menu_receipt["replays"][0]["effective_menu_open_frame"])
    menu_close_frame = int(menu_receipt["replays"][0]["menu_closed_frame"])
    require(menu_close_frame > first_menu_frame,
            "hazard-menu close frame does not follow menu open")
    metrics, failures = analyze(
        loaded[0],
        first_menu_frame=first_menu_frame,
        menu_close_frame=menu_close_frame,
        oam_coverage=oam_coverage[0],
    )
    controls = mutation_controls()
    manifests = []
    for directory, frames in zip(frame_dirs, loaded, strict=True):
        manifest_sha256, rows = manifest(frames)
        manifests.append({
            "directory": str(directory.resolve()),
            "manifest_sha256": manifest_sha256,
            "frames": rows,
        })
    checks = {
        "source state and menu replay bind the exact candidate": True,
        "source state is ROM-owned and settled": (
            state_receipt.get("hardware", {}).get("settled") is True
        ),
        "two rendered replays are byte-identical": (
            manifests[0]["manifest_sha256"] == manifests[1]["manifest_sha256"]
        ),
        "at least 120 rendered samples are independently inspected": (
            metrics["rendered_frames"] >= 120
        ),
        "at least 60 rendered samples contain visible hazards": (
            metrics["hazard_visible_frames"] >= 60
        ),
        "four rendered hazard phases are observed": metrics["hazard_phases"] >= 4,
        "rendered hazard rows contain no clear cells": (
            metrics["clear_cell_frames"] == 0
        ),
        "rendered hazards leave no unsupported yellow trails": (
            metrics["yellow_trail_frames"] == 0
        ),
        "rendered spike teeth never use neutral gray": (
            metrics["gray_spike_frames"] == 0
        ),
        "menu and post-menu wall edges never gain persistent red or green": (
            metrics["wall_edge_artifact_frames"] == 0
        ),
        "independent synthetic and hash-pinned operator controls pass": (
            all(controls.values())
        ),
    }
    receipt = {
        "schema": SCHEMA,
        "passed": all(checks.values()),
        "rom": str(rom),
        "rom_sha256": rom_sha256,
        "oracle": ORACLE,
        "oracle_contract": {
            "candidate_palette_bytes_used": False,
            "candidate_remap_output_used": False,
            "candidate_vram_used_as_expected_output": False,
            "supplemental_operator_capture_fixture": str(
                OPERATOR_CAPTURE_FIXTURE.relative_to(ROOT)
            ),
            "supplemental_operator_capture_fixture_sha256": (
                OPERATOR_CAPTURE_FIXTURE_SHA256
            ),
            "fixed_render_semantics": [
                "red/orange hazard body", "gold/yellow tooth material",
                "neutral-gray tooth rejection", "lavender floor continuity",
                "edge-connected neutral wall continuity",
            ],
            "temporal_reference": "untouched pre-menu rendered pixels only",
            "menu_window_top": MENU_WINDOW_TOP,
            "sprite_occlusion_source": (
                "hash-bound per-frame hardware OAM footprints; exclusion-only"
            ),
        },
        "rom_owned_state": True,
        "vram_injection_bytes": 0,
        "df5b_injected": False,
        "state_sha256": state_receipt["state_sha256"],
        "state_receipt": str(state_receipt_path),
        "state_receipt_sha256": sha256(state_receipt_path),
        "hazard_menu_receipt": str(menu_receipt_path),
        "hazard_menu_receipt_sha256": sha256(menu_receipt_path),
        "rendered_manifests": manifests,
        "metrics": metrics,
        "failure_frames": failures,
        "mutation_controls": controls,
        "checks": checks,
        "tool": str(Path(__file__).resolve()),
        "tool_sha256": sha256(Path(__file__).resolve()),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt


def synthetic_frames(defect: str | None = None) -> list[RenderedFrame]:
    frames: list[RenderedFrame] = []
    floor_a = (255, 255, 255)
    floor_b = (165, 165, 255)
    black = (0, 0, 0)
    gray = (82, 82, 82)
    red = (255, 0, 0)
    yellow = (255, 255, 0)
    green = (0, 173, 0)
    for sample in range(1, 131):
        number = sample * 5
        pixels = [
            floor_a if ((x + y) // 2) % 2 else floor_b
            for y in range(HEIGHT)
            for x in range(WIDTH)
        ]
        for y in range(PLAYFIELD_HEIGHT):
            for x in range(8):
                pixels[y * WIDTH + x] = black if x < 3 else gray
            for x in range(WIDTH - 8, WIDTH):
                pixels[y * WIDTH + x] = black if x >= WIDTH - 3 else gray
        phase = sample % 4
        top = 48
        for x in range(40, 120):
            for y in range(top, top + 8):
                pixels[y * WIDTH + x] = red if y >= top + 3 else yellow
        # Four authored-looking shape phases without moving the tile grid.
        for x in range(40 + phase * 4, 44 + phase * 4):
            pixels[(top + 7) * WIDTH + x] = black
        # Mutations begin after the untouched baseline window.
        if number >= 185 and defect == "clear":
            for y in range(top, top + 8):
                for x in range(96, 104):
                    pixels[y * WIDTH + x] = (
                        floor_a if ((x + y) // 2) % 2 else floor_b
                    )
        elif number >= 185 and defect == "yellow":
            for y in range(88, 90):
                for x in range(20, 23):
                    pixels[y * WIDTH + x] = yellow
        elif number >= 185 and defect == "gray":
            for y in range(top, top + 3):
                for x in range(48, 112):
                    pixels[y * WIDTH + x] = gray
        elif number >= 185 and defect == "wall":
            for y in range(20, 24):
                pixels[y * WIDTH + 2] = red
                pixels[y * WIDTH + WIDTH - 3] = green
        frames.append(RenderedFrame(number, tuple(pixels)))
    return frames


def self_test() -> int:
    controls = mutation_controls()
    require(all(controls.values()), f"mutation controls failed: {controls}")
    print(
        "PASS: rendered-continuity synthetic controls and hash-pinned "
        "operator PNG controls"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, nargs="?")
    parser.add_argument("--state-receipt", type=Path)
    parser.add_argument("--hazard-menu-receipt", type=Path)
    parser.add_argument("--frames-dir", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--expect-known-bad",
        choices=("any", "clear", "yellow", "gray", "wall", "all"),
        help="negative control: succeed only when requested defects are caught",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        try:
            return self_test()
        except VerificationError as error:
            print(f"FAIL: {error}")
            return 1
    for value, label in (
        (args.rom, "ROM"),
        (args.state_receipt, "--state-receipt"),
        (args.hazard_menu_receipt, "--hazard-menu-receipt"),
        (args.output, "--output"),
    ):
        if value is None:
            parser.error(f"{label} is required outside --self-test")
    try:
        receipt = build_receipt(
            rom=args.rom.resolve(),
            state_receipt_path=args.state_receipt.resolve(),
            menu_receipt_path=args.hazard_menu_receipt.resolve(),
            frame_dirs=[path.resolve() for path in args.frames_dir],
            output=args.output.resolve(),
        )
    except (VerificationError, OSError, ValueError) as error:
        print(f"FAIL: {error}")
        return 1

    metrics = receipt["metrics"]
    if args.expect_known_bad:
        names = {
            "clear": ("clear_cell_frames",),
            "yellow": ("yellow_trail_frames",),
            "gray": ("gray_spike_frames",),
            "wall": ("wall_edge_artifact_frames",),
            "all": (
                "clear_cell_frames", "yellow_trail_frames",
                "gray_spike_frames", "wall_edge_artifact_frames",
            ),
            "any": (
                "clear_cell_frames", "yellow_trail_frames",
                "gray_spike_frames", "wall_edge_artifact_frames",
            ),
        }[args.expect_known_bad]
        detected = (
            any(metrics[name] > 0 for name in names)
            if args.expect_known_bad == "any"
            else all(metrics[name] > 0 for name in names)
        )
        if detected and receipt["passed"] is False:
            print(
                "PASS: known-bad rendered corpus rejected: "
                + ", ".join(f"{name}={metrics[name]}" for name in names)
            )
            print(f"Receipt: {args.output.resolve()}")
            return 0
        print("FAIL: requested known-bad rendered defect escaped")
        return 1

    if receipt["passed"]:
        print("PASS: independent Stage-1 rendered-continuity contract")
        print(f"Receipt: {args.output.resolve()}")
        return 0
    print("FAIL: independent Stage-1 rendered-continuity contract")
    for name, passed in receipt["checks"].items():
        if not passed:
            print(f"  failed check: {name}")
    print(f"Receipt: {args.output.resolve()}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
