#!/usr/bin/env python3
"""Build the exact Game Over/restart fix from original source (issues #7–#10).

A traced original-source r536 build is followed by two authenticated overlays.
No retained candidate is an input. Source evidence is not hardware approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]

import build_r536_candidate as parent_builder
import build_gameover_row_guard as row_guard
import build_spike_death_trial as spike_death
from suite_contract import source_snapshot


DEFAULT_PALETTE = parent_builder.DEFAULT_PALETTE
CONTRACT = {
    "schema": "penta-restart-original-source-build-v1",
    "status": "source-build-pass",
    "source_parent_profile": parent_builder.CONTRACT["schema"],
    "construction_order": [
        "gameover-row-attribute-retirement",
        "spike-death-cleanup-and-title-prelude-rearm",
    ],
    "historical_evidence_consumed": False,
    "retained_candidate_roms_read": False,
    "fresh_live_qualification": False,
    "audience_approval_recorded": False,
    "release_qualification": False,
    "candidate_sha256": (
        "c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d"
    ),
}
RECEIPT_KEYS = set(CONTRACT) | {
    "original_rom",
    "palette",
    "python",
    "strace",
    "source_fingerprint",
    "source_files",
    "source_parent",
    "construction",
}
PARENT_BINDING_KEYS = {"receipt", "receipt_sha256", "source_fingerprint"}
OVERLAYS = (
    (CONTRACT["construction_order"][0], row_guard),
    (CONTRACT["construction_order"][1], spike_death),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identity(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": digest(path.read_bytes())}


def overlay_identity(name: str, module: object) -> dict[str, object]:
    path = Path(module.__file__)
    return {"name": name, "builder": identity(path)}


def apply_overlays(parent: bytes) -> tuple[bytes, list[dict[str, object]]]:
    current = parent
    records: list[dict[str, object]] = []
    for name, module in OVERLAYS:
        before = digest(current)
        result = module.build(current)
        changed = sum(a != b for a, b in zip(current, result, strict=True))
        records.append(
            {
                **overlay_identity(name, module),
                "source_sha256": before,
                "candidate_sha256": digest(result),
                "changed_byte_count": changed,
            }
        )
        current = result
    return current, records


def build(output: Path, palette: Path = DEFAULT_PALETTE) -> dict:
    output, palette = output.resolve(), palette.resolve()
    if output == ROOT / "tmp" or not output.is_relative_to(ROOT / "tmp") or output.exists():
        raise ValueError("use a fresh repository-local tmp output directory")

    snapshot = source_snapshot()
    output.mkdir(parents=True)
    parent_output = output / "r536-parent"
    parent_receipt = parent_builder.build(parent_output, palette)
    parent_path = parent_output / "build-receipt.json"
    parent_rom = (parent_output / "candidate.gb").read_bytes()
    parent_builder.verify_receipt(parent_path, parent_rom, palette)

    if parent_receipt["source_fingerprint"] != snapshot[0]:
        raise ValueError("r536 parent source fingerprint differs from restart build")
    candidate, construction = apply_overlays(parent_rom)
    if digest(candidate) != CONTRACT["candidate_sha256"]:
        raise ValueError("original-source overlay chain did not reproduce exact restart")
    if snapshot != source_snapshot():
        raise ValueError("source identity changed during restart construction")

    source_parent = {
        "receipt": str(parent_path.resolve()),
        "receipt_sha256": digest(parent_path.read_bytes()),
        "source_fingerprint": parent_receipt["source_fingerprint"],
    }
    receipt = {
        **CONTRACT,
        "original_rom": parent_receipt["original_rom"],
        "palette": parent_receipt["palette"],
        "python": parent_receipt["python"],
        "strace": parent_receipt["strace"],
        "source_fingerprint": snapshot[0],
        "source_files": snapshot[1],
        "source_parent": source_parent,
        "construction": construction,
    }
    (output / "candidate.gb").write_bytes(candidate)
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def verify_receipt(path: Path, expected_rom: bytes, palette: Path = DEFAULT_PALETTE) -> dict:
    path, palette = path.resolve(), palette.resolve()
    receipt = json.loads(path.read_text())
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS:
        raise ValueError("restart original-source receipt field inventory differs")
    for name, expected in CONTRACT.items():
        actual = receipt.get(name)
        if actual != expected or type(actual) is not type(expected):
            raise ValueError(f"restart original-source receipt {name} differs")
    if digest(expected_rom) != CONTRACT["candidate_sha256"]:
        raise ValueError("verification requires exact pinned restart ROM")

    output = path.parent
    if output == ROOT / "tmp" or not output.is_relative_to(ROOT / "tmp"):
        raise ValueError("restart source receipt must belong to repository-local tmp output")
    if (output / "candidate.gb").read_bytes() != expected_rom:
        raise ValueError("restart source candidate bytes differ")

    snapshot = source_snapshot()
    if snapshot != (receipt["source_fingerprint"], receipt["source_files"]):
        raise ValueError("restart source receipt source snapshot is stale")

    binding = receipt["source_parent"]
    if not isinstance(binding, dict) or set(binding) != PARENT_BINDING_KEYS:
        raise ValueError("restart source-parent binding field inventory differs")
    if not all(isinstance(value, str) and value for value in binding.values()):
        raise ValueError("restart source-parent binding requires nonempty strings")
    parent_path = output / "r536-parent/build-receipt.json"
    if binding["receipt"] != str(parent_path.resolve()):
        raise ValueError("restart source-parent receipt path differs")
    if digest(parent_path.read_bytes()) != binding["receipt_sha256"]:
        raise ValueError("restart source-parent receipt hash differs")
    parent_rom = (parent_path.parent / "candidate.gb").read_bytes()
    parent = parent_builder.verify_receipt(parent_path, parent_rom, palette)
    if parent["source_fingerprint"] != binding["source_fingerprint"]:
        raise ValueError("restart source-parent fingerprint binding differs")
    if binding["source_fingerprint"] != receipt["source_fingerprint"]:
        raise ValueError("restart source and parent fingerprints differ")

    for name in ("original_rom", "palette", "python", "strace"):
        if receipt[name] != parent[name]:
            raise ValueError(f"restart source receipt {name} differs from parent proof")
    candidate, construction = apply_overlays(parent_rom)
    if construction != receipt["construction"]:
        raise ValueError("restart overlay construction evidence differs")
    if candidate != expected_rom:
        raise ValueError("restart overlay reconstruction differs from candidate")
    if snapshot != source_snapshot():
        raise ValueError("source identity changed during restart verification")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--palette-yaml", type=Path, default=DEFAULT_PALETTE)
    args = parser.parse_args()
    receipt = build(args.out_dir, args.palette_yaml)
    output = args.out_dir.resolve()
    candidate = (output / "candidate.gb").read_bytes()
    verify_receipt(output / "build-receipt.json", candidate, args.palette_yaml)
    print(
        json.dumps(
            {
                "candidate_sha256": receipt["candidate_sha256"],
                "source_parent_profile": receipt["source_parent_profile"],
                "construction_order": receipt["construction_order"],
                "historical_evidence_consumed": False,
                "status": receipt["status"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
