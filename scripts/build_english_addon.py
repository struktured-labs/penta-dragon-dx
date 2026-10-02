#!/usr/bin/env python3
"""Compose HTI v1.00 as a deterministic, ROM-free DX add-on patch.

The historical translation edits a small part of the stock title table that
Penta Dragon DX intentionally replaces.  Applying the IPS files blindly would
therefore damage the reviewed DX title/footer.  This builder preserves every
known DX-owned title byte, imports all non-conflicting HTI text/font data, fixes
the Game Boy checksums, and emits an IPS whose required input is one exact DX
ROM.  No ROM is written unless ``--output-rom`` is explicitly supplied.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import json
from itertools import groupby
from pathlib import Path
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from penta_dragon_dx.patch_builder import (  # noqa: E402
    apply_ips_patch,
    build_ips_patch,
)


SUPPORTED_BASE_MD5 = "df43e0adfdc74b2829c7e95e91c71a28"
HTI_V100_PATCH_SHA256 = (
    "9ac36c13e6e4bd97de23f00480d2aa1b0e437f62b604d6e65ff5a9680767051d"
)
HTI_PROJECT_URL = "https://hti.rpgclassics.com/penta.shtml"
ENGLISH_ADDON_STEM = "Penta_Dragon_DX_v3.01_English_HTI_v1.00_ADDON"
ENGLISH_ADDON_PATCH_NAME = f"{ENGLISH_ADDON_STEM}.ips"
EXPECTED_ENGLISH_GATE_COUNT = 78

# These are the only non-checksum bytes jointly owned by the HTI v1.00 patch
# and the current DX line.  They are the stock title table that DX replaces
# with PENTA DRAGON DX and its version footer.  Any new overlap is a hard error
# so future visual/code edits cannot be silently discarded.
EXPECTED_DX_TITLE_CONFLICTS = frozenset(
    {
        0x004EDF,
        0x004EE3,
        0x004EF2,
        0x004EF6,
        *range(0x004F0D, 0x004F1A),
        *range(0x004F1B, 0x004F21),
    }
)
CHECKSUM_OFFSETS = frozenset({0x014D, 0x014E, 0x014F})

# HTI's longer translated OPENING leaves DX's Stage-1 immutable-art counter at
# its legacy $FF sentinel.  The normal GAME START route enters with zero, so
# this ownership collision is visible only when OPENING is allowed to finish.
# Keep the repair in the optional English layer, but do it on DX's rare
# OPENING-only story branch.  An earlier prototype redirected a hot Stage-1
# entry tail; although functionally correct, its extra cycles shifted boss
# animation/capture phases.  Normal gameplay must stay byte-for-byte on the
# performance-qualified DX path.
#
# A is known zero at the opening branch.  Redirect its first instruction to an
# otherwise unreachable, asserted-zero bank-13 pad.  The helper clears DF5B,
# recreates the original DCFD=1/B=2 setup and jumps to the original story
# guard.  The pre-final entry at $7E65 is left untouched.
BANK13_FILE_OFFSET = 13 * 0x4000
ENGLISH_OPENING_REARM_ENTRY_ADDR = 0x7E5D
ENGLISH_OPENING_REARM_HELPER_ADDR = 0x6ED0
ENGLISH_OPENING_REARM_ENTRY_PREIMAGE = bytes.fromhex(
    "3C EA FD DC 3C 47 18 02 06 04"
)
ENGLISH_OPENING_REARM_REDIRECT = bytes.fromhex("C3 D0 6E")
ENGLISH_OPENING_REARM_HELPER_PREIMAGE = bytes(12)
ENGLISH_OPENING_REARM_HELPER = bytes.fromhex(
    "EA 5B DF 3C EA FD DC 3C 47 C3 67 7E"
)


def digest(data: bytes, algorithm: str) -> str:
    return hashlib.new(algorithm, data).hexdigest()


def checksums(data: bytes) -> dict[str, str | int]:
    return {
        "size": len(data),
        "md5": digest(data, "md5"),
        "sha1": digest(data, "sha1"),
        "sha256": digest(data, "sha256"),
        "crc32": f"{binascii.crc32(data) & 0xFFFFFFFF:08x}",
    }


def header_checksum(rom: bytes | bytearray) -> int:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def global_checksum(rom: bytes | bytearray) -> int:
    return (
        sum(rom[:0x014E]) + sum(rom[0x0150:])
    ) & 0xFFFF


def offset_ranges(offsets: set[int] | frozenset[int]) -> list[str]:
    result: list[str] = []
    for _, values in groupby(
        enumerate(sorted(offsets)), lambda pair: pair[1] - pair[0]
    ):
        group = [offset for _, offset in values]
        first, last = group[0], group[-1]
        result.append(
            f"{first:06X}" if first == last else f"{first:06X}-{last:06X}"
        )
    return result


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"FAIL: {message}")


def bank13_offset(address: int) -> int:
    if not 0x4000 <= address < 0x8000:
        fail(f"invalid bank-13 address ${address:04X}")
    return BANK13_FILE_OFFSET + address - 0x4000


def install_english_opening_rearm(merged: bytearray) -> dict[str, object]:
    redirect_offset = bank13_offset(ENGLISH_OPENING_REARM_ENTRY_ADDR)
    helper_offset = bank13_offset(ENGLISH_OPENING_REARM_HELPER_ADDR)
    redirect_end = redirect_offset + len(ENGLISH_OPENING_REARM_ENTRY_PREIMAGE)
    helper_end = helper_offset + len(ENGLISH_OPENING_REARM_HELPER_PREIMAGE)

    if bytes(merged[redirect_offset:redirect_end]) != (
        ENGLISH_OPENING_REARM_ENTRY_PREIMAGE
    ):
        fail(
            "English OPENING redirect preimage changed at "
            f"bank13:${ENGLISH_OPENING_REARM_ENTRY_ADDR:04X}"
        )
    if bytes(merged[helper_offset:helper_end]) != (
        ENGLISH_OPENING_REARM_HELPER_PREIMAGE
    ):
        fail(
            "English OPENING helper pad is no longer empty at "
            f"bank13:${ENGLISH_OPENING_REARM_HELPER_ADDR:04X}"
        )

    merged[
        redirect_offset:
        redirect_offset + len(ENGLISH_OPENING_REARM_REDIRECT)
    ] = ENGLISH_OPENING_REARM_REDIRECT
    merged[helper_offset:helper_end] = ENGLISH_OPENING_REARM_HELPER
    return {
        "name": "translated-opening-stage1-art-rearm",
        "scope": "optional-english-layer-only",
        "entry_redirect": (
            f"bank13:${ENGLISH_OPENING_REARM_ENTRY_ADDR:04X}"
        ),
        "helper": f"bank13:${ENGLISH_OPENING_REARM_HELPER_ADDR:04X}",
        "bytes_changed": (
            len(ENGLISH_OPENING_REARM_REDIRECT)
            + len(ENGLISH_OPENING_REARM_HELPER)
        ),
        "effect": (
            "clear $DF5B on the translated OPENING-only path while leaving "
            "normal gameplay, bosses, and the prerecorded demo untouched"
        ),
    }


def validate_emulator_manifest(path: Path, merged: bytes) -> dict:
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"could not read English emulator manifest {path}: {exc}")
    if not isinstance(manifest, dict):
        fail("English emulator manifest must contain one JSON object")

    expected_md5 = digest(merged, "md5")
    expected = {
        "status": "emulator-pass",
        "scope": "full",
        "failures": 0,
        "rom_md5": expected_md5,
        "rom_size": len(merged),
        "source_rom_md5_after": expected_md5,
        "tested_rom_md5_after": expected_md5,
        "rom_hashes_intact": True,
        "source_inputs_intact": True,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            fail(f"English emulator manifest {key} is not {value!r}")
    if (
        not manifest.get("source_fingerprint")
        or manifest.get("source_fingerprint")
        != manifest.get("source_fingerprint_after")
    ):
        fail("English emulator matrix did not preserve its source fingerprint")

    results = manifest.get("results")
    if not isinstance(results, list) or len(results) != EXPECTED_ENGLISH_GATE_COUNT:
        fail(
            f"expected {EXPECTED_ENGLISH_GATE_COUNT} English emulator gates, "
            f"found {len(results) if isinstance(results, list) else 'invalid'}"
        )
    names = [item.get("name") for item in results if isinstance(item, dict)]
    if len(names) != len(results) or len(set(names)) != len(names):
        fail("English emulator manifest has invalid or duplicate gate names")
    if manifest.get("selected_gates") != names:
        fail("English emulator selected_gates does not match its result order")
    failed = [
        item.get("name")
        for item in results
        if item.get("status") != "passed" or item.get("returncode") != 0
    ]
    if failed:
        fail(f"English emulator gates are not all passed: {failed}")
    return manifest


def zip_entry(name: str, data: bytes) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    info.create_system = 3
    return info, data


def write_optional_bundle(
    path: Path,
    addon_patch: bytes,
    dx: bytes,
    merged: bytes,
) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    dx_hashes = checksums(dx)
    patch_hashes = checksums(addon_patch)
    merged_hashes = checksums(merged)
    readme = f"""PENTA DRAGON DX v3.01 — OPTIONAL ENGLISH ADD-ON
==================================================

This ROM-free add-on layers the HTI v1.00 English translation onto one exact
Penta Dragon DX v3.01 ROM. It is optional; the core DX patch remains Japanese.

Install
-------
1. Apply the core Penta_Dragon_DX_v3.01.ips to the supported clean Japanese ROM.
2. Verify the resulting DX ROM SHA-256 is:
   {dx_hashes['sha256']}
3. Apply {ENGLISH_ADDON_PATCH_NAME} to that exact DX ROM.
4. Verify the English DX ROM SHA-256 is:
   {merged_hashes['sha256']}

Do not apply this add-on directly to the clean Japanese ROM or to another DX
build. No original or modified game ROM is included.

Translation credits
-------------------
Hacking: Hiryuu / HTI
Translation: Tyrome Williams
Additional thanks: Kero Hazel
Project page: {HTI_PROJECT_URL}
""".encode("utf-8")
    checksum_text = f"""Penta Dragon DX v3.01 optional English add-on checksums

REQUIRED DX INPUT ROM (not included)
Size:    {dx_hashes['size']} bytes
MD5:     {dx_hashes['md5']}
SHA-1:   {dx_hashes['sha1']}
SHA-256: {dx_hashes['sha256']}
CRC32:   {dx_hashes['crc32']}

OPTIONAL ENGLISH ADD-ON IPS
File:    {ENGLISH_ADDON_PATCH_NAME}
Size:    {patch_hashes['size']} bytes
MD5:     {patch_hashes['md5']}
SHA-1:   {patch_hashes['sha1']}
SHA-256: {patch_hashes['sha256']}
CRC32:   {patch_hashes['crc32']}

EXPECTED ENGLISH DX ROM (not included)
Size:    {merged_hashes['size']} bytes
MD5:     {merged_hashes['md5']}
SHA-1:   {merged_hashes['sha1']}
SHA-256: {merged_hashes['sha256']}
CRC32:   {merged_hashes['crc32']}
""".encode("ascii")
    files = {
        "CHECKSUMS.txt": checksum_text,
        ENGLISH_ADDON_PATCH_NAME: addon_patch,
        "README.txt": readme,
    }

    with tempfile.NamedTemporaryFile(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=path.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for name in sorted(files):
                info, data = zip_entry(f"{ENGLISH_ADDON_STEM}/{name}", data=files[name])
                archive.writestr(info, data, compresslevel=9)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)

    with zipfile.ZipFile(path, "r") as archive:
        expected_names = [
            f"{ENGLISH_ADDON_STEM}/{name}" for name in sorted(files)
        ]
        if archive.namelist() != expected_names:
            fail("optional English archive differs from its file allowlist")
        for name, expected_data in files.items():
            if archive.read(f"{ENGLISH_ADDON_STEM}/{name}") != expected_data:
                fail(f"optional English archive payload changed: {name}")

    archive_bytes = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "bytes": len(archive_bytes),
        "sha256": digest(archive_bytes, "sha256"),
        "rom_included": False,
        "files": sorted(files),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        type=Path,
        default=ROOT / "rom/Penta Dragon (J).gb",
        help="verified clean Japanese ROM (read-only)",
    )
    parser.add_argument("--dx-rom", type=Path, required=True)
    parser.add_argument("--hti-patch", type=Path, required=True)
    parser.add_argument("--output-patch", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--output-rom",
        type=Path,
        help="optional ignored scratch ROM for emulator verification",
    )
    parser.add_argument(
        "--require-dx-sha256",
        help="fail unless --dx-rom has this exact SHA-256",
    )
    parser.add_argument(
        "--bundle-output",
        type=Path,
        help="optional ROM-free English add-on ZIP (requires full matrix)",
    )
    parser.add_argument(
        "--emulator-manifest",
        type=Path,
        help="full English release-matrix manifest required by --bundle-output",
    )
    args = parser.parse_args()

    if bool(args.bundle_output) != bool(args.emulator_manifest):
        fail("--bundle-output and --emulator-manifest must be supplied together")

    for label, path in (
        ("clean Japanese ROM", args.base),
        ("DX ROM", args.dx_rom),
        ("HTI patch", args.hti_patch),
    ):
        if not path.is_file():
            fail(f"{label} not found: {path}")

    base = args.base.read_bytes()
    dx = args.dx_rom.read_bytes()
    hti_patch = args.hti_patch.read_bytes()
    base_md5 = digest(base, "md5")
    dx_sha256 = digest(dx, "sha256")
    hti_sha256 = digest(hti_patch, "sha256")

    if base_md5 != SUPPORTED_BASE_MD5:
        fail(
            f"unsupported base MD5 {base_md5}; expected {SUPPORTED_BASE_MD5}"
        )
    if len(dx) < len(base):
        fail(f"DX ROM shrank: {len(base)} -> {len(dx)} bytes")
    if args.require_dx_sha256 and dx_sha256 != args.require_dx_sha256.lower():
        fail(
            f"DX SHA-256 {dx_sha256} does not match required "
            f"{args.require_dx_sha256.lower()}"
        )
    if hti_sha256 != HTI_V100_PATCH_SHA256:
        fail(
            f"unsupported HTI patch SHA-256 {hti_sha256}; expected "
            f"{HTI_V100_PATCH_SHA256}"
        )

    try:
        english_base = apply_ips_patch(base, hti_patch)
    except ValueError as exc:
        fail(f"HTI IPS parser rejected the patch: {exc}")
    if len(english_base) != len(base):
        fail(
            f"HTI v1.00 unexpectedly resized the base: "
            f"{len(base)} -> {len(english_base)}"
        )

    english_offsets = {
        index
        for index, (stock, english) in enumerate(zip(base, english_base))
        if stock != english
    }
    conflicts = {
        index
        for index in english_offsets
        if index < len(dx) and dx[index] != base[index]
    }
    semantic_conflicts = conflicts - CHECKSUM_OFFSETS
    if semantic_conflicts != EXPECTED_DX_TITLE_CONFLICTS:
        missing = EXPECTED_DX_TITLE_CONFLICTS - semantic_conflicts
        unexpected = semantic_conflicts - EXPECTED_DX_TITLE_CONFLICTS
        fail(
            "English/DX ownership map changed; "
            f"missing={offset_ranges(missing)}, "
            f"unexpected={offset_ranges(unexpected)}"
        )

    merged = bytearray(dx)
    imported_offsets = english_offsets - conflicts
    for index in imported_offsets:
        merged[index] = english_base[index]

    compatibility_shim = install_english_opening_rearm(merged)

    # The translation's historical global checksum targets a 256 KiB ROM.
    # Recompute both fields over the actual expanded DX+English image.
    merged[0x014D] = header_checksum(merged)
    merged[0x014E:0x0150] = b"\x00\x00"
    merged[0x014E:0x0150] = global_checksum(merged).to_bytes(2, "big")
    merged_bytes = bytes(merged)
    if merged_bytes[0x014D] != header_checksum(merged_bytes):
        fail("header checksum repair is not self-consistent")
    if int.from_bytes(merged_bytes[0x014E:0x0150], "big") != global_checksum(
        merged_bytes
    ):
        fail("global checksum repair is not self-consistent")

    for index in EXPECTED_DX_TITLE_CONFLICTS:
        if merged_bytes[index] != dx[index]:
            fail(f"DX title ownership lost at {index:06X}")
    for index in imported_offsets:
        if index not in CHECKSUM_OFFSETS and merged_bytes[index] != english_base[index]:
            fail(f"HTI payload not imported at {index:06X}")

    addon_patch = build_ips_patch(dx, merged_bytes)
    if build_ips_patch(dx, merged_bytes) != addon_patch:
        fail("optional add-on IPS generation is nondeterministic")
    if apply_ips_patch(dx, addon_patch) != merged_bytes:
        fail("optional add-on IPS does not reconstruct the merged ROM")

    args.output_patch.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_patch.write_bytes(addon_patch)
    if args.output_rom is not None:
        args.output_rom.parent.mkdir(parents=True, exist_ok=True)
        args.output_rom.write_bytes(merged_bytes)

    emulator_manifest = None
    optional_bundle = None
    if args.bundle_output is not None:
        if not args.emulator_manifest.is_file():
            fail(f"English emulator manifest not found: {args.emulator_manifest}")
        emulator_manifest = validate_emulator_manifest(
            args.emulator_manifest,
            merged_bytes,
        )
        optional_bundle = write_optional_bundle(
            args.bundle_output,
            addon_patch,
            dx,
            merged_bytes,
        )

    manifest = {
        "schema": "penta-dragon-dx-english-addon-v1",
        "status": "pass",
        "patch_order": ["clean-japanese", "penta-dragon-dx", "hti-v1.00"],
        "attribution": {
            "project": "Penta Dragon English Translation Patch v1.00",
            "hacking": "Hiryuu / HTI",
            "translation": "Tyrome Williams",
            "additional_thanks": "Kero Hazel",
            "source": HTI_PROJECT_URL,
        },
        "base": {
            "bytes": len(base),
            "md5": base_md5,
            "sha256": digest(base, "sha256"),
        },
        "dx_input": {
            "bytes": len(dx),
            "md5": digest(dx, "md5"),
            "sha256": dx_sha256,
        },
        "hti_patch": {
            "bytes": len(hti_patch),
            "sha256": hti_sha256,
            "changed_base_bytes": len(english_offsets),
        },
        "merge": {
            "imported_english_bytes": len(imported_offsets),
            "preserved_dx_title_bytes": len(EXPECTED_DX_TITLE_CONFLICTS),
            "preserved_dx_title_ranges": offset_ranges(
                EXPECTED_DX_TITLE_CONFLICTS
            ),
            "checksum_conflicts_rebuilt": offset_ranges(
                conflicts & CHECKSUM_OFFSETS
            ),
            "compatibility_shims": [compatibility_shim],
        },
        "addon_patch": {
            "path": str(args.output_patch.resolve()),
            "bytes": len(addon_patch),
            "md5": digest(addon_patch, "md5"),
            "sha256": digest(addon_patch, "sha256"),
        },
        "merged_rom": {
            "included": False,
            "bytes": len(merged_bytes),
            "md5": digest(merged_bytes, "md5"),
            "sha256": digest(merged_bytes, "sha256"),
            "scratch_path": (
                str(args.output_rom.resolve())
                if args.output_rom is not None
                else None
            ),
        },
        "emulator_verification": (
            {
                "manifest": str(args.emulator_manifest.resolve()),
                "sha256": digest(args.emulator_manifest.read_bytes(), "sha256"),
                "gates_passed": len(emulator_manifest["results"]),
            }
            if emulator_manifest is not None
            else {"status": "pending"}
        ),
        "optional_bundle": (
            optional_bundle
            if optional_bundle is not None
            else {"status": "pending-full-matrix"}
        ),
    }
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"PASS: clean Japanese base MD5 {base_md5}")
    print(f"PASS: HTI v1.00 patch SHA-256 {hti_sha256}")
    print(
        "PASS: preserved DX title ownership at "
        + ", ".join(offset_ranges(EXPECTED_DX_TITLE_CONFLICTS))
    )
    print(
        f"PASS: imported {len(imported_offsets)} English bytes and built "
        f"{len(addon_patch)}-byte add-on IPS for DX SHA-256 {dx_sha256}"
    )
    print(f"Manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
