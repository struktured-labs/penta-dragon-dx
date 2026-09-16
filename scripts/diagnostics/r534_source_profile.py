"""Source evidence for the r534 palette profile; never an audience approval."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_r534_candidate as builder

PROFILE = {"name": "r534-original-source-v1", "expanded_ted": True,
           "native_sparse": True, "native_pose_table": True, "menu_icon_colors": True}
VERIFICATION_SCHEMA = "penta-r534-palette-original-source-verification-v1"
BINDING_KEYS = {"receipt", "receipt_sha256", "source_fingerprint"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_binding(binding: dict, rom: bytes, palette: Path) -> dict:
    """Authenticate and reconstruct source evidence independently of approval."""
    if not isinstance(binding, dict) or set(binding) != BINDING_KEYS:
        raise ValueError("r534 source-build binding field inventory differs")
    if not all(isinstance(value, str) and value for value in binding.values()):
        raise ValueError("r534 source-build binding requires nonempty strings")
    path = Path(binding["receipt"])
    if str(path.resolve()) != binding["receipt"]:
        raise ValueError("r534 source-build receipt requires its exact canonical path")
    if digest(path.read_bytes()) != binding["receipt_sha256"]:
        raise ValueError("r534 source-build receipt hash differs")
    verified = builder.verify_receipt(path, rom, palette)
    if verified["source_fingerprint"] != binding["source_fingerprint"]:
        raise ValueError("r534 source-build fingerprint binding differs")
    if digest(path.read_bytes()) != binding["receipt_sha256"]:
        raise ValueError("r534 source-build receipt changed during verification")
    return verified


def build_verification(rom: Path, palette: Path, output: Path) -> dict:
    """Fresh traced double-build plus verification; no approval flags or writes."""
    expected = rom.read_bytes()
    palette_sha = digest(palette.read_bytes())
    if digest(expected) != builder.CONTRACT["candidate_sha256"]:
        raise ValueError("r534 source profile requires the exact pinned r534 ROM")
    command = [sys.executable, str(ROOT / "scripts/build_r534_candidate.py"),
               "--palette-yaml", str(palette.resolve()), "--out-dir", str(output.resolve())]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise ValueError(f"r534 source build failed: {result.stderr.strip() or result.stdout.strip()}")
    path = output.resolve() / "build-receipt.json"
    # Only the independently validated receipt supplies the fingerprint.
    verified = builder.verify_receipt(path, expected, palette)
    binding = {"receipt": str(path), "receipt_sha256": digest(path.read_bytes()),
               "source_fingerprint": verified["source_fingerprint"]}
    verify_binding(binding, expected, palette)
    if rom.read_bytes() != expected or digest(palette.read_bytes()) != palette_sha:
        raise ValueError("requested ROM or palette changed during r534 source verification")
    verification = {
        "schema": VERIFICATION_SCHEMA, "status": "source-build-pass",
        "audience_approval_recorded": False, "release_qualification": False,
        "historical_evidence_consumed": False, "build_profile": dict(PROFILE),
        "rom_path": str(rom.resolve()), "rom_sha256": digest(expected),
        "palette_yaml": str(palette.resolve()), "palette_yaml_sha256": palette_sha,
        "source_build": binding,
    }
    with (output.resolve() / "palette-verification.json").open("x") as handle:
        handle.write(json.dumps(verification, indent=2) + "\n")
    return verification
