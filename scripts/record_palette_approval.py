#!/usr/bin/env python3
"""Record an explicit, hash-bound audience palette approval after the stream."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_PALETTES = ROOT / "palettes/penta_palettes_v097.yaml"
LEGACY_BUILDER = ROOT / "scripts/build_v302_title_fix.py"
EXPANDED_BUILDER = ROOT / "scripts/build_ted_expanded_candidate.py"
ORIGINAL_REPLAY_BUILDER = ROOT / "scripts/diagnostics/rebuild_r534_from_original.py"
CONFIRMATION = "AUDIENCE APPROVED"


def hash_file(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"FAIL: {message}")


def verify_original_replay(rom: Path, palettes: Path, manifest: Path, output: Path) -> int:
    """Verify experimental source reconstruction without recording an approval."""
    expected_rom = rom.read_bytes()
    palette_sha = hash_file(palettes, "sha256")
    sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
    from rebuild_r534_from_original import verify_receipt, lineage
    if hashlib.sha256(expected_rom).hexdigest() != lineage.CANDIDATE_SHA256:
        fail("experimental source profile requires the exact pinned r534 ROM")
    command = [sys.executable, str(ORIGINAL_REPLAY_BUILDER),
               "--palette-yaml", str(palettes.resolve()),
               "--historical-input-manifest", str(manifest.resolve()),
               "--out-dir", str(output.resolve())]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=600)
    if result.returncode:
        fail(f"original-cartridge reconstruction failed: {result.stderr.strip() or result.stdout.strip()}")
    receipt_path = output.resolve() / "build-receipt.json"
    verified = verify_receipt(receipt_path, expected_rom, palettes)
    if rom.read_bytes() != expected_rom or hash_file(palettes, "sha256") != palette_sha:
        fail("requested ROM or palette YAML changed during source verification")
    verification = {
        "schema": "penta-r534-palette-source-verification-v1", "status": "source-replay-pass",
        "audience_approval_recorded": False, "release_qualification": False,
        "rom_path": str(rom.resolve()), "rom_sha256": hash_file(rom, "sha256"),
        "palette_yaml": str(palettes.resolve()), "palette_yaml_sha256": palette_sha,
        "reconstruction_receipt": str(receipt_path),
        "reconstruction_receipt_sha256": hash_file(receipt_path, "sha256"),
        "source_fingerprint": verified["source_fingerprint"],
    }
    verification_path = output.resolve() / "palette-verification.json"
    if verification_path.exists():
        fail("source-verification receipt already exists")
    verification_path.write_text(json.dumps(verification, indent=2) + "\n")
    print("PASS: experimental r534 source replay rebuilds the exact ROM; no audience approval was recorded")
    print(f"Source verification receipt: {verification_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--palettes", type=Path, default=DEFAULT_PALETTES)
    parser.add_argument(
        "--output",
        type=Path,
        help="approval JSON destination (required unless --verify-only)",
    )
    parser.add_argument(
        "--confirm",
        default="",
        help=f"must be the exact phrase {CONFIRMATION!r}",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="optional short summary of the livestream vote",
    )
    parser.add_argument(
        "--expanded-ted",
        action="store_true",
        help="rebuild the 512 KiB native-sparse/native-pose release profile",
    )
    parser.add_argument(
        "--menu-icon-colors",
        action="store_true",
        help="include the isolated expanded-bank item-menu publisher",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help=(
            "prove that YAML rebuilds the exact ROM without recording an "
            "audience approval"
        ),
    )
    parser.add_argument("--r534-original-replay", action="store_true",
                        help="verify-only: use the traced experimental r534 original-cartridge replay")
    parser.add_argument("--r534-source", action="store_true",
                        help="use the exact r534 original-cartridge source-only profile")
    parser.add_argument("--r536-source", action="store_true",
                        help="use the exact r536 original-cartridge source-only profile")
    parser.add_argument("--source-output", type=Path,
                        help="fresh repository tmp directory for an original-source profile's traced evidence")
    parser.add_argument("--historical-input-manifest", type=Path,
                        help="explicit historical input bundle for --r534-original-replay")
    parser.add_argument("--replay-output", type=Path,
                        help="fresh repository tmp directory retaining both traced builds and receipts")
    args = parser.parse_args()

    if args.r534_source and args.r536_source:
        fail("select only one original-source profile")
    if args.r534_source:
        if (args.r534_original_replay or args.historical_input_manifest is not None
                or args.replay_output is not None or args.expanded_ted or args.menu_icon_colors):
            fail("r534 source is a distinct complete profile; do not combine historical or legacy options")
        if args.source_output is None:
            fail("r534 source requires --source-output")
        if args.verify_only and (args.confirm or args.output is not None):
            fail("r534 source verification-only cannot record audience approval")
        if not args.verify_only and (args.confirm != CONFIRMATION or args.output is None):
            fail(f"r534 source approval requires --output and --confirm {CONFIRMATION!r}")
        if args.output is not None and args.output.exists():
            fail("r534 audience approval output already exists; use a fresh immutable path")
        return record_r534_source(args)
    if args.r536_source:
        if (args.r534_original_replay or args.historical_input_manifest is not None
                or args.replay_output is not None or args.expanded_ted or args.menu_icon_colors):
            fail("r536 source is a distinct complete profile; do not combine historical or legacy options")
        if args.source_output is None:
            fail("r536 source requires --source-output")
        if args.verify_only and (args.confirm or args.output is not None):
            fail("r536 source verification-only cannot record audience approval")
        if not args.verify_only and (args.confirm != CONFIRMATION or args.output is None):
            fail(f"r536 source approval requires --output and --confirm {CONFIRMATION!r}")
        if args.output is not None and args.output.exists():
            fail("r536 audience approval output already exists; use a fresh immutable path")
        return record_r536_source(args)
    if args.source_output is not None:
        fail("--source-output requires --r534-source or --r536-source")

    if args.r534_original_replay:
        if not args.verify_only or args.confirm or args.output is not None:
            fail("experimental r534 replay is verification-only and cannot record audience approval")
        if args.expanded_ted or args.menu_icon_colors:
            fail("r534 original replay is a distinct complete profile; do not combine legacy profile flags")
        if args.historical_input_manifest is None or args.replay_output is None:
            fail("r534 original replay requires --historical-input-manifest and --replay-output")
        return verify_original_replay(args.rom, args.palettes, args.historical_input_manifest, args.replay_output)
    if args.historical_input_manifest is not None or args.replay_output is not None:
        fail("historical input and replay output options require --r534-original-replay")

    if not args.verify_only and args.confirm != CONFIRMATION:
        fail(f"--confirm must be the exact phrase {CONFIRMATION!r}")
    if not args.verify_only and args.output is None:
        fail("--output is required when recording audience approval")
    if args.menu_icon_colors and not args.expanded_ted:
        fail("--menu-icon-colors requires --expanded-ted")
    builder = EXPANDED_BUILDER if args.expanded_ted else LEGACY_BUILDER
    for label, path in (
        ("release ROM", args.rom),
        ("palette YAML", args.palettes),
        ("production builder", builder),
    ):
        if not path.is_file():
            fail(f"{label} not found: {path}")

    # Prove that the approved YAML deterministically builds the exact ROM being
    # approved. This uses only temporary outputs and never overwrites FIXED.gb.
    local_tmp = ROOT / "tmp"
    local_tmp.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="penta-palette-approval-", dir=local_tmp
    ) as temp:
        temp_path = Path(temp)
        rebuilt = temp_path / "approved.gb"
        intermediate = temp_path / "approved-base.gb"
        if args.expanded_ted:
            command = [
                sys.executable,
                str(builder),
                "--palette-yaml",
                str(args.palettes),
                "--output",
                str(rebuilt),
                "--native-sparse",
                "--native-pose-table",
                "--work",
                str(temp_path / "expanded-work"),
            ]
            if args.menu_icon_colors:
                command.append("--menu-icon-colors")
        else:
            command = [
                sys.executable,
                str(builder),
                "--palette-yaml",
                str(args.palettes),
                "--output",
                str(rebuilt),
                "--base-output",
                str(intermediate),
            ]
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            detail = result.stdout.strip() or result.stderr.strip()
            fail(f"production palette rebuild failed: {detail}")
        if rebuilt.read_bytes() != args.rom.read_bytes():
            fail(
                "approved palette YAML does not rebuild the exact release ROM; "
                "rebuild FIXED.gb, regenerate the IPS, and rerun the release matrix"
            )

    if args.verify_only:
        print(
            "PASS: palette YAML rebuilds the exact ROM; "
            "no audience approval was recorded"
        )
        return 0

    approval = {
        "schema": "penta-dragon-dx-palette-approval-v1",
        "status": "audience-approved",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "confirmation": CONFIRMATION,
        "rom_md5": hash_file(args.rom, "md5"),
        "rom_sha256": hash_file(args.rom, "sha256"),
        "palette_yaml": str(args.palettes.resolve()),
        "palette_yaml_sha256": hash_file(args.palettes, "sha256"),
        "build_profile": {
            "name": (
                "expanded-ted-menu" if args.menu_icon_colors
                else "expanded-ted" if args.expanded_ted
                else "legacy-256k"
            ),
            "expanded_ted": args.expanded_ted,
            "native_sparse": args.expanded_ted,
            "native_pose_table": args.expanded_ted,
            "menu_icon_colors": args.menu_icon_colors,
        },
        "notes": args.notes,
    }
    assert args.output is not None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(approval, indent=2) + "\n")
    temporary.replace(args.output)
    print(f"PASS: recorded hash-bound audience palette approval {args.output}")
    print(f"PASS: approved ROM MD5 {approval['rom_md5']}")
    return 0


def record_r534_source(args: argparse.Namespace) -> int:
    """Record only an explicitly requested approval after exact source proof."""
    if args.verify_only and (args.confirm or args.output is not None):
        fail("r534 source verification-only cannot record audience approval")
    if not args.verify_only and (args.confirm != CONFIRMATION or args.output is None):
        fail("r534 audience approval requires explicit confirmation and an output path")
    sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
    from r534_source_profile import PROFILE, build_verification, verify_binding
    verification = build_verification(args.rom, args.palettes, args.source_output)
    if args.verify_only:
        print("PASS: r534 original source rebuilds the exact ROM; no audience approval was recorded")
        print(f"Source verification receipt: {args.source_output.resolve() / 'palette-verification.json'}")
        return 0
    # Recheck confirmation here too: direct callers cannot skip the CLI guard.
    if args.confirm != CONFIRMATION or args.output is None:
        fail("r534 audience approval requires explicit confirmation and an output path")
    rom = args.rom.read_bytes()
    if (hashlib.sha256(rom).hexdigest() != verification["rom_sha256"]
            or hash_file(args.palettes, "sha256") != verification["palette_yaml_sha256"]):
        fail("approved ROM or palette changed after r534 source verification")
    verify_binding(verification["source_build"], rom, args.palettes)
    if args.rom.read_bytes() != rom or hash_file(args.palettes, "sha256") != verification["palette_yaml_sha256"]:
        fail("approved ROM or palette changed during r534 source binding verification")
    approval = {
        "schema": "penta-dragon-dx-palette-approval-v1", "status": "audience-approved",
        "approved_at": datetime.now(timezone.utc).isoformat(), "confirmation": CONFIRMATION,
        "rom_md5": hashlib.md5(rom).hexdigest(), "rom_sha256": verification["rom_sha256"],
        "palette_yaml": str(args.palettes.resolve()),
        "palette_yaml_sha256": verification["palette_yaml_sha256"],
        "build_profile": dict(PROFILE), "source_build": verification["source_build"],
        "notes": args.notes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        handle.write(json.dumps(approval, indent=2) + "\n")
    print(f"PASS: recorded hash-bound r534 audience palette approval {args.output}")
    return 0


def record_r536_source(args: argparse.Namespace) -> int:
    """Record explicit audience approval only after exact r536 source proof."""
    if args.verify_only and (args.confirm or args.output is not None):
        fail("r536 source verification-only cannot record audience approval")
    if not args.verify_only and (args.confirm != CONFIRMATION or args.output is None):
        fail("r536 audience approval requires explicit confirmation and an output path")
    sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
    from r536_source_profile import PROFILE, build_verification, verify_binding

    verification = build_verification(args.rom, args.palettes, args.source_output)
    if args.verify_only:
        print("PASS: r536 original source rebuilds the exact ROM; no audience approval was recorded")
        print(f"Source verification receipt: {args.source_output.resolve() / 'palette-verification.json'}")
        return 0
    if args.confirm != CONFIRMATION or args.output is None:
        fail("r536 audience approval requires explicit confirmation and an output path")
    rom = args.rom.read_bytes()
    if (
        hashlib.sha256(rom).hexdigest() != verification["rom_sha256"]
        or hash_file(args.palettes, "sha256") != verification["palette_yaml_sha256"]
    ):
        fail("approved ROM or palette changed after r536 source verification")
    verify_binding(verification["source_build"], rom, args.palettes)
    if (
        args.rom.read_bytes() != rom
        or hash_file(args.palettes, "sha256") != verification["palette_yaml_sha256"]
    ):
        fail("approved ROM or palette changed during r536 source binding verification")
    approval = {
        "schema": "penta-dragon-dx-palette-approval-v1",
        "status": "audience-approved",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "confirmation": CONFIRMATION,
        "rom_md5": hashlib.md5(rom).hexdigest(),
        "rom_sha256": verification["rom_sha256"],
        "palette_yaml": str(args.palettes.resolve()),
        "palette_yaml_sha256": verification["palette_yaml_sha256"],
        "build_profile": dict(PROFILE),
        "source_build": verification["source_build"],
        "notes": args.notes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        handle.write(json.dumps(approval, indent=2) + "\n")
    print(f"PASS: recorded hash-bound r536 audience palette approval {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
