"""Source evidence for the exact restart palette profile; never approval itself."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_restart_candidate as builder


PROFILE = {
    "name": "restart-original-source-v1",
    "expanded_ted": True,
    "native_sparse": True,
    "native_pose_table": True,
    "menu_icon_colors": True,
}
VERIFICATION_SCHEMA = "penta-restart-palette-original-source-verification-v1"
BINDING_KEYS = {"receipt", "receipt_sha256", "source_fingerprint"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_binding(binding: dict, rom: bytes, palette: Path) -> dict:
    if not isinstance(binding, dict) or set(binding) != BINDING_KEYS:
        raise ValueError("restart source-build binding field inventory differs")
    if not all(isinstance(value, str) and value for value in binding.values()):
        raise ValueError("restart source-build binding requires nonempty strings")
    path = Path(binding["receipt"])
    if str(path.resolve()) != binding["receipt"]:
        raise ValueError("restart source-build receipt requires its exact canonical path")
    if digest(path.read_bytes()) != binding["receipt_sha256"]:
        raise ValueError("restart source-build receipt hash differs")
    verified = builder.verify_receipt(path, rom, palette)
    if verified["source_fingerprint"] != binding["source_fingerprint"]:
        raise ValueError("restart source-build fingerprint binding differs")
    if digest(path.read_bytes()) != binding["receipt_sha256"]:
        raise ValueError("restart source-build receipt changed during verification")
    return verified
