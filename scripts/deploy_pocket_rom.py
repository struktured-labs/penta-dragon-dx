#!/usr/bin/env python3
"""Hash-bound Pocket deployment with mandatory regression receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECEIPT = ROOT / "docs/release/verification/latest.json"
DEFAULT_MOUNT = Path("/media/struktured/POCKET-SD")
DEST_DIRECTORY = Path("Assets/gbc/common")
DEST_PREFIX = "Penta Dragon DX v3.01"
NORTH_VERIFIER = ROOT / "scripts/diagnostics/verify_stage1_north_integrity.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def append_only_destination(mount: Path, rom_hash: str) -> Path:
    """Return a unique, content-addressed path; deployments never replace ROMs."""
    return mount / DEST_DIRECTORY / f"{DEST_PREFIX}-{rom_hash[:12]}.gbc"


def require_full_receipt(path: Path, rom_hash: str) -> None:
    data = json.loads(path.read_text())
    receipt_hash = data.get("candidate", {}).get("sha256")
    matrix = data.get("matrix", {})
    results = {item.get("name"): item.get("status") for item in matrix.get("results", [])}
    failures: list[str] = []
    if data.get("status") != "passed":
        failures.append(f"receipt status is {data.get('status')!r}")
    if receipt_hash != rom_hash:
        failures.append(f"receipt ROM is {receipt_hash}, candidate is {rom_hash}")
    if matrix.get("status") != "emulator-pass" or matrix.get("failures") != 0:
        failures.append("full emulator matrix did not pass")
    required_stage1_gates = (
        "stage1_north_route_integrity",
        "stage1_spike_palettes",
        "stage1_spike_miniboss_transition",
        "low_health_flicker",
    )
    for gate in required_stage1_gates:
        if results.get(gate) != "passed":
            failures.append(f"{gate} is not passed")
    if failures:
        raise SystemExit("REFUSED: " + "; ".join(failures))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy a verified ROM to the Pocket; failed-suite ROMs are refused."
    )
    parser.add_argument("rom", type=Path)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--mount", type=Path, default=DEFAULT_MOUNT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rom = args.rom.resolve()
    if not rom.is_file():
        raise SystemExit(f"REFUSED: ROM does not exist: {rom}")
    rom_hash = sha256(rom)
    require_full_receipt(args.receipt.resolve(), rom_hash)

    # Re-run the historically fragile route on the exact bytes being deployed.
    north_output = ROOT / "tmp" / "pocket-deploy" / rom_hash[:12] / "stage1-north"
    north_output.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, str(NORTH_VERIFIER), str(rom), "--output", str(north_output)],
        cwd=ROOT,
        check=True,
    )
    north = json.loads((north_output / "receipt.json").read_text())
    if north.get("status") != "pass" or north.get("candidate_sha256") != rom_hash:
        raise SystemExit("REFUSED: hash-bound Stage 1 north-route receipt did not pass")

    destination = append_only_destination(args.mount.resolve(), rom_hash)
    if not destination.parent.is_dir():
        raise SystemExit(f"REFUSED: Pocket SameBoy directory is unavailable: {destination.parent}")
    if destination.exists():
        raise SystemExit(f"REFUSED: append-only Pocket ROM already exists: {destination}")
    if args.dry_run:
        print(f"PASS: {rom_hash} is eligible for append-only Pocket deployment -> {destination} (dry run)")
        return 0

    shutil.copy2(rom, destination)
    if sha256(destination) != rom_hash:
        raise SystemExit("ERROR: post-copy Pocket hash mismatch")
    print(f"PASS: deployed and verified {rom_hash} -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
