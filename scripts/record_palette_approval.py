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
BUILDER = ROOT / "scripts/build_v302_title_fix.py"
CONFIRMATION = "AUDIENCE APPROVED"


def hash_file(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"FAIL: {message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--palettes", type=Path, default=DEFAULT_PALETTES)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--confirm",
        required=True,
        help=f"must be the exact phrase {CONFIRMATION!r}",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="optional short summary of the livestream vote",
    )
    args = parser.parse_args()

    if args.confirm != CONFIRMATION:
        fail(f"--confirm must be the exact phrase {CONFIRMATION!r}")
    for label, path in (
        ("release ROM", args.rom),
        ("palette YAML", args.palettes),
        ("production builder", BUILDER),
    ):
        if not path.is_file():
            fail(f"{label} not found: {path}")

    # Prove that the approved YAML deterministically builds the exact ROM being
    # approved. This uses only temporary outputs and never overwrites FIXED.gb.
    with tempfile.TemporaryDirectory(prefix="penta-palette-approval-") as temp:
        temp_path = Path(temp)
        rebuilt = temp_path / "approved.gb"
        intermediate = temp_path / "approved-base.gb"
        result = subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--palette-yaml",
                str(args.palettes),
                "--output",
                str(rebuilt),
                "--base-output",
                str(intermediate),
            ],
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

    approval = {
        "schema": "penta-dragon-dx-palette-approval-v1",
        "status": "audience-approved",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "confirmation": CONFIRMATION,
        "rom_md5": hash_file(args.rom, "md5"),
        "rom_sha256": hash_file(args.rom, "sha256"),
        "palette_yaml": str(args.palettes.resolve()),
        "palette_yaml_sha256": hash_file(args.palettes, "sha256"),
        "notes": args.notes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(approval, indent=2) + "\n")
    temporary.replace(args.output)
    print(f"PASS: recorded hash-bound audience palette approval {args.output}")
    print(f"PASS: approved ROM MD5 {approval['rom_md5']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
