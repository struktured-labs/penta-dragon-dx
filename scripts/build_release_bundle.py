#!/usr/bin/env python3
"""Build a deterministic, ROM-free Penta Dragon DX release archive.

By default this emits a conspicuously named PREHARDWARE candidate. Final mode
requires both a hash-bound MiSTer hardware-pass manifest and a hash-bound
audience palette approval. Nothing in this script uploads or publishes files.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import shutil
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from penta_dragon_dx.patch_builder import apply_ips_patch, build_ips_patch


VERSION = "v3.01"
STEM = "Penta_Dragon_DX_v3.01"
DEFAULT_BASE = ROOT / "rom/Penta Dragon (J).gb"
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_PATCH = ROOT / "rom/penta_dragon_dx.ips"
DEFAULT_PALETTES = ROOT / "palettes/penta_palettes_v097.yaml"
DEFAULT_OUTPUT = ROOT / "dist"
README_TEMPLATE = ROOT / "docs/release/README.txt.in"
SUPPORTED_BASE_MD5 = "df43e0adfdc74b2829c7e95e91c71a28"
REQUIRED_GATES = {
    "emulator_singleflight_guard",
    "title_footer_integration",
    "title_animation_frames",
    "flash_attribution",
    "title_color",
    "title_showcase",
    "title_visual_receipts",
    "title_cursor",
    "stage_intro_timing",
    "menu_hud_and_combo",
    "levelselect_screen",
    "game_start_routes",
    "game_start_after_attract",
    "gameplay_speed_parity",
    "gameplay_bg_palettes",
    "pickup_class_palettes",
    "stage1_no_color_bleed",
    "gameplay_obj_palettes",
    "frame_flicker",
    "miniboss_color",
    "later_stage_integrity",
    "later_stage_soak",
    "boss_arenas",
    "death_gameover",
    "title_idle_reel",
    "spotlight_full_roster",
    "opening_cutscene",
    "final_cutscene_mgba",
    "ending_inventory_a",
    "ending_inventory_b",
    "ending_discriminators",
    "scroll_stability",
    "phantom_sound",
    "live_palette_deck",
    "story_attr_production",
    "palette_build_roundtrip",
    "candidate_ips_roundtrip",
    "mister_reservation_guard",
}
EXPECTED_GATE_COUNT = len(REQUIRED_GATES)
REQUIRED_HARDWARE_CHECKPOINTS = {
    "gbc_core",
    "deployed_rom_hash",
    "title",
    "opening_route",
    "game_start_route",
    "stage_intro",
    "stage1_gameplay",
    "item_menu",
    "later_stage",
    "boss_arena",
    "death_gameover",
}
FORBIDDEN_RELEASE_SUFFIXES = {
    ".gb",
    ".gbc",
    ".gba",
    ".sav",
    ".ss",
    ".ss0",
    ".ss1",
    ".ss2",
    ".ss3",
    ".ss4",
}
SCREENSHOT_SPECS = (
    (
        "01_title_opening.png",
        "title-cursor/default-opening.first.png",
    ),
    (
        "02_opening_sara.png",
        "story-attr-production/opening_sara.png",
    ),
    (
        "03_ted_boss.png",
        "boss-arenas/boss4_ted.png",
    ),
    (
        "04_penta_dragon_boss.png",
        "boss-arenas/boss8_penta_dragon.png",
    ),
)


def digest(data: bytes, algorithm: str) -> str:
    return hashlib.new(algorithm, data).hexdigest()


def file_digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def checksums(data: bytes) -> dict[str, str | int]:
    return {
        "size": len(data),
        "md5": digest(data, "md5"),
        "sha1": digest(data, "sha1"),
        "sha256": digest(data, "sha256"),
        "crc32": f"{binascii.crc32(data) & 0xFFFFFFFF:08x}",
    }


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"FAIL: {message}")


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"could not read {label} {path}: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must contain one JSON object: {path}")
    return value


def validate_emulator_manifest(path: Path, rom: bytes) -> dict:
    manifest = load_json(path, "emulator manifest")
    rom_md5 = digest(rom, "md5")

    if manifest.get("status") != "emulator-pass":
        fail("emulator manifest status is not emulator-pass")
    if manifest.get("scope") != "full":
        fail("emulator manifest is not a full-matrix run")
    if manifest.get("failures") != 0:
        fail("emulator manifest reports failures")
    if manifest.get("rom_md5") != rom_md5:
        fail("emulator manifest is bound to a different ROM")
    if manifest.get("rom_size") != len(rom):
        fail("emulator manifest ROM size does not match the candidate")
    if manifest.get("source_rom_md5_after") != rom_md5:
        fail("source ROM hash was not intact after the emulator matrix")
    if manifest.get("tested_rom_md5_after") != rom_md5:
        fail("tested ROM hash was not intact after the emulator matrix")
    if manifest.get("rom_hashes_intact") is not True:
        fail("emulator manifest did not prove intact ROM hashes")

    results = manifest.get("results")
    if not isinstance(results, list) or len(results) != EXPECTED_GATE_COUNT:
        fail(
            f"expected {EXPECTED_GATE_COUNT} emulator gate results, "
            f"found {len(results) if isinstance(results, list) else 'invalid'}"
        )
    names = [result.get("name") for result in results if isinstance(result, dict)]
    if len(names) != len(results) or len(set(names)) != len(names):
        fail("emulator manifest contains invalid or duplicate gate names")
    if set(names) != REQUIRED_GATES:
        missing = sorted(REQUIRED_GATES - set(names))
        extra = sorted(set(names) - REQUIRED_GATES)
        fail(f"emulator gate set mismatch; missing={missing}, extra={extra}")
    failed = [
        result.get("name")
        for result in results
        if result.get("status") != "passed" or result.get("returncode") != 0
    ]
    if failed:
        fail(f"emulator gates are not all passed: {failed}")
    if manifest.get("selected_gates") != names:
        fail("selected_gates does not exactly match the completed gate order")
    return manifest


def validate_hardware_manifest(
    path: Path,
    rom: bytes,
    patch: bytes,
    emulator_manifest_path: Path,
) -> dict:
    manifest = load_json(path, "hardware manifest")
    expected = {
        "schema": "penta-dragon-dx-mister-release-v1",
        "status": "hardware-pass",
        "rom_md5": digest(rom, "md5"),
        "rom_sha256": digest(rom, "sha256"),
        "release_patch_sha256": digest(patch, "sha256"),
        "emulator_manifest_sha256": file_digest(
            emulator_manifest_path, "sha256"
        ),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            fail(f"hardware manifest {key} does not match {value!r}")

    checkpoints = manifest.get("checkpoints")
    if not isinstance(checkpoints, list):
        fail("hardware manifest checkpoints must be a list")
    checkpoint_names = [
        item.get("name") for item in checkpoints if isinstance(item, dict)
    ]
    if (
        len(checkpoint_names) != len(checkpoints)
        or len(set(checkpoint_names)) != len(checkpoint_names)
    ):
        fail("hardware manifest contains invalid or duplicate checkpoints")
    incomplete = [
        item.get("name")
        for item in checkpoints
        if item.get("status") != "passed"
    ]
    if incomplete:
        fail(f"hardware manifest contains incomplete checkpoints: {incomplete}")
    passed = {
        item.get("name")
        for item in checkpoints
        if item.get("status") == "passed"
    }
    missing = sorted(REQUIRED_HARDWARE_CHECKPOINTS - passed)
    if missing:
        fail(f"hardware manifest is missing passed checkpoints: {missing}")
    return manifest


def validate_palette_approval(path: Path, rom: bytes, palette_path: Path) -> dict:
    manifest = load_json(path, "palette approval")
    expected = {
        "schema": "penta-dragon-dx-palette-approval-v1",
        "status": "audience-approved",
        "rom_md5": digest(rom, "md5"),
        "rom_sha256": digest(rom, "sha256"),
        "palette_yaml_sha256": file_digest(palette_path, "sha256"),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            fail(f"palette approval {key} does not match {value!r}")
    return manifest


def validate_png(path: Path) -> dict[str, int | float]:
    try:
        header = path.read_bytes()[:24]
    except OSError as exc:
        fail(f"could not read screenshot {path}: {exc}")
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        fail(f"screenshot is not a PNG: {path}")
    if header[12:16] != b"IHDR":
        fail(f"screenshot has no PNG IHDR: {path}")
    width, height = struct.unpack(">II", header[16:24])
    if (width, height) != (160, 144):
        fail(f"screenshot must be native 160x144, got {width}x{height}: {path}")
    try:
        with Image.open(path) as source:
            source.load()
            rgb = source.convert("RGB")
    except (OSError, UnidentifiedImageError) as exc:
        fail(f"screenshot cannot be decoded: {path}: {exc}")
    colors = rgb.getcolors(maxcolors=160 * 144 + 1)
    unique_colors = len(colors) if colors is not None else 160 * 144
    nonwhite_pixels = sum(
        1
        for red, green, blue in rgb.getdata()
        if red < 248 or green < 248 or blue < 248
    )
    nonwhite_percent = nonwhite_pixels * 100.0 / (160 * 144)
    # Native Game Boy screens can legitimately be binary artwork: the exact
    # title/footer gate validates this package screenshot before the manifest
    # is accepted. Reject only truly flat captures here, while the independent
    # nonwhite-coverage check still catches blank white frames.
    if unique_colors < 2:
        fail(
            f"screenshot has only {unique_colors} colors and looks blank: {path}"
        )
    if nonwhite_percent < 5.0:
        fail(
            f"screenshot has only {nonwhite_percent:.2f}% nonwhite pixels: {path}"
        )
    return {
        "unique_colors": unique_colors,
        "nonwhite_percent": round(nonwhite_percent, 3),
    }


def render_readme(final: bool, rom_hashes: dict[str, str | int]) -> bytes:
    try:
        template = README_TEMPLATE.read_text()
    except OSError as exc:
        fail(f"could not read release readme template: {exc}")

    if final:
        release_notice = (
            "PUBLIC RELEASE ARCHIVE. Hardware verification and the audience "
            "palette lock are bound to this exact build."
        )
        hardware_notice = (
            "MiSTer FPGA: PASS on the exact output ROM listed below."
        )
        palette_notice = (
            "Audience palette lock: APPROVED and baked into this exact ROM."
        )
    else:
        release_notice = (
            "PREHARDWARE TEST PACKAGE - DO NOT PUBLISH AS THE FINAL RELEASE. "
            "This archive exists only to prove the packaging path."
        )
        hardware_notice = (
            "MiSTer FPGA: PENDING a reservation-backed physical sweep."
        )
        palette_notice = (
            "Audience palette lock: PENDING the livestream color vote."
        )

    body = template.format(
        release_notice=release_notice,
        hardware_notice=hardware_notice,
        palette_notice=palette_notice,
    )
    body += (
        "\nExpected patched ROM\n"
        "--------------------\n"
        f"Size:   {rom_hashes['size']} bytes\n"
        f"MD5:    {rom_hashes['md5']}\n"
        f"SHA-1:  {rom_hashes['sha1']}\n"
        f"SHA-256: {rom_hashes['sha256']}\n"
        f"CRC32:  {rom_hashes['crc32']}\n"
    )
    return body.encode("utf-8")


def render_checksums(
    base_hashes: dict[str, str | int],
    patch_hashes: dict[str, str | int],
    rom_hashes: dict[str, str | int],
) -> bytes:
    text = f"""Penta Dragon DX {VERSION} checksums

SUPPORTED UNMODIFIED BASE ROM (not included)
Size:    {base_hashes['size']} bytes
MD5:     {base_hashes['md5']}
SHA-1:   {base_hashes['sha1']}
SHA-256: {base_hashes['sha256']}
CRC32:   {base_hashes['crc32']}

IPS PATCH
File:    Penta_Dragon_DX_v3.01.ips
Size:    {patch_hashes['size']} bytes
MD5:     {patch_hashes['md5']}
SHA-1:   {patch_hashes['sha1']}
SHA-256: {patch_hashes['sha256']}
CRC32:   {patch_hashes['crc32']}

EXPECTED PATCHED ROM (not included)
Size:    {rom_hashes['size']} bytes
MD5:     {rom_hashes['md5']}
SHA-1:   {rom_hashes['sha1']}
SHA-256: {rom_hashes['sha256']}
CRC32:   {rom_hashes['crc32']}
"""
    return text.encode("ascii")


def zip_entry(name: str, data: bytes) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info, data


def write_deterministic_zip(path: Path, root_name: str, files: dict[str, bytes]) -> None:
    with tempfile.NamedTemporaryFile(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for name in sorted(files):
                info, data = zip_entry(f"{root_name}/{name}", files[name])
                archive.writestr(info, data, compresslevel=9)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_archive(path: Path, expected_files: dict[str, bytes], root_name: str) -> None:
    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        expected_names = [f"{root_name}/{name}" for name in sorted(expected_files)]
        if names != expected_names:
            fail(f"archive entries differ from the release allowlist: {names}")
        for name, expected in expected_files.items():
            archived_name = f"{root_name}/{name}"
            suffix = Path(name).suffix.lower()
            if suffix in FORBIDDEN_RELEASE_SUFFIXES:
                fail(f"forbidden ROM/save artifact entered archive: {name}")
            if archive.read(archived_name) != expected:
                fail(f"archive payload changed while packaging: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emulator-manifest", type=Path, required=True)
    parser.add_argument("--hardware-manifest", type=Path)
    parser.add_argument("--palette-approval", type=Path)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--patch", type=Path, default=DEFAULT_PATCH)
    parser.add_argument("--palettes", type=Path, default=DEFAULT_PALETTES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--final",
        action="store_true",
        help="Permit the final filename only with hardware and palette approval",
    )
    args = parser.parse_args()

    for label, path in (
        ("base ROM", args.base),
        ("release ROM", args.rom),
        ("IPS patch", args.patch),
        ("palette YAML", args.palettes),
        ("readme template", README_TEMPLATE),
    ):
        if not path.is_file():
            fail(f"{label} not found: {path}")

    if args.final and (not args.hardware_manifest or not args.palette_approval):
        fail("--final requires --hardware-manifest and --palette-approval")
    if not args.final and (args.hardware_manifest or args.palette_approval):
        fail("approval manifests are accepted only together with --final")

    base = args.base.read_bytes()
    rom = args.rom.read_bytes()
    patch = args.patch.read_bytes()
    base_hashes = checksums(base)
    rom_hashes = checksums(rom)
    patch_hashes = checksums(patch)

    if base_hashes["md5"] != SUPPORTED_BASE_MD5:
        fail(
            f"unsupported base ROM MD5 {base_hashes['md5']}; "
            f"expected {SUPPORTED_BASE_MD5}"
        )
    if len(base) != len(rom):
        fail(f"base/release size mismatch: {len(base)} != {len(rom)}")
    if build_ips_patch(base, rom) != patch:
        fail("checked-in IPS is stale or nondeterministic")
    if apply_ips_patch(base, patch) != rom:
        fail("IPS does not reconstruct the exact candidate ROM")

    emulator = validate_emulator_manifest(args.emulator_manifest, rom)
    hardware = None
    palette_approval = None
    if args.final:
        hardware = validate_hardware_manifest(
            args.hardware_manifest, rom, patch, args.emulator_manifest
        )
        palette_approval = validate_palette_approval(
            args.palette_approval, rom, args.palettes
        )

    label = STEM if args.final else f"{STEM}_PREHARDWARE"
    root_name = label
    args.output.mkdir(parents=True, exist_ok=True)
    archive_path = args.output / f"{label}.zip"
    screenshot_dir = args.output / f"{label}_screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    artifact_root = args.emulator_manifest.parent / "artifacts"
    screenshot_audit = []
    for output_name, relative_source in SCREENSHOT_SPECS:
        source = artifact_root / relative_source
        if not source.is_file():
            fail(f"required release screenshot missing: {source}")
        image_metrics = validate_png(source)
        target = screenshot_dir / output_name
        temporary = target.with_suffix(target.suffix + ".tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(target)
        screenshot_audit.append(
            {
                "file": str(target),
                "source": str(source),
                "size": target.stat().st_size,
                "sha256": file_digest(target, "sha256"),
                "dimensions": [160, 144],
                **image_metrics,
            }
        )
    screenshot_hashes = {
        item["sha256"] for item in screenshot_audit
    }
    if len(screenshot_hashes) != len(SCREENSHOT_SPECS):
        fail("release screenshot set contains duplicate images")
    expected_screenshot_names = {name for name, _source in SCREENSHOT_SPECS}
    actual_screenshot_names = {
        path.name for path in screenshot_dir.iterdir() if path.is_file()
    }
    if actual_screenshot_names != expected_screenshot_names:
        fail(
            "screenshot directory differs from the release allowlist; "
            f"expected={sorted(expected_screenshot_names)}, "
            f"actual={sorted(actual_screenshot_names)}"
        )

    files = {
        "CHECKSUMS.txt": render_checksums(base_hashes, patch_hashes, rom_hashes),
        "Penta_Dragon_DX_v3.01.ips": patch,
        "README.txt": render_readme(args.final, rom_hashes),
    }
    write_deterministic_zip(archive_path, root_name, files)
    validate_archive(archive_path, files, root_name)

    audit = {
        "schema": "penta-dragon-dx-release-bundle-v1",
        "status": "final" if args.final else "prehardware-do-not-publish",
        "version": VERSION,
        "archive": str(archive_path),
        "archive_sha256": file_digest(archive_path, "sha256"),
        "archive_size": archive_path.stat().st_size,
        "rom_included": False,
        "base_rom": base_hashes,
        "release_rom": rom_hashes,
        "release_patch": patch_hashes,
        "emulator_manifest": {
            "file": str(args.emulator_manifest),
            "sha256": file_digest(args.emulator_manifest, "sha256"),
            "status": emulator["status"],
            "gates_passed": len(emulator["results"]),
        },
        "hardware_manifest": (
            {
                "file": str(args.hardware_manifest),
                "sha256": file_digest(args.hardware_manifest, "sha256"),
                "status": hardware["status"],
            }
            if hardware is not None
            else {"status": "pending"}
        ),
        "palette_approval": (
            {
                "file": str(args.palette_approval),
                "sha256": file_digest(args.palette_approval, "sha256"),
                "status": palette_approval["status"],
            }
            if palette_approval is not None
            else {"status": "pending"}
        ),
        "screenshots": screenshot_audit,
    }
    audit_path = args.output / f"{label}.manifest.json"
    temporary_audit = audit_path.with_suffix(audit_path.suffix + ".tmp")
    temporary_audit.write_text(json.dumps(audit, indent=2) + "\n")
    temporary_audit.replace(audit_path)

    print(
        f"PASS: built {'FINAL' if args.final else 'PREHARDWARE'} ROM-free "
        f"archive {archive_path}"
    )
    print(
        f"PASS: IPS reconstructs release ROM MD5 {rom_hashes['md5']} "
        f"after {EXPECTED_GATE_COUNT} emulator gates"
    )
    print(f"PASS: copied {len(screenshot_audit)} native 160x144 screenshots")
    if not args.final:
        print(
            "PENDING: MiSTer hardware pass and audience palette approval; "
            "do not publish this archive."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
