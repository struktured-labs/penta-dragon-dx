#!/usr/bin/env python3
"""Build the exact 126dd stream-regression candidate as a release source profile.

Wraps scripts/build_stream_regression_candidate.py with the full experimental
chain (presentation, arena alias, completion-safe, secret sound alias, return
fade trial16) and binds the result to the suite source fingerprint. The chain
starts from the original-source restart build; no retained candidate ROM is an
input. The stages are hash-pinned and cannot be reordered, so this profile
necessarily includes the #33/#34/#35 bytes carried by the presentation chain.
Construction evidence only: not hardware approval and not audience approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]

import build_restart_candidate as restart
import build_stream_regression_candidate as stream
from suite_contract import source_snapshot


DEFAULT_PALETTE = ROOT / "palettes/penta_palettes_v097.yaml"
LEGACY_PALETTE = ROOT / "palettes/penta_palettes_restart_parent.yaml"
FLAGS = {
    "presentation": True,
    "arena_alias": True,
    "arena_completion_safe": True,
    "secret_sound_alias": True,
    "return_fade": True,
    "experimental_late_return_fade": False,
}
CONTRACT = {
    "schema": "penta-stream-126dd-original-source-build-v1",
    "status": "source-build-pass",
    "source_parent_profile": restart.CONTRACT["schema"],
    "source_parent_sha256": restart.CONTRACT["candidate_sha256"],
    "chain_flags": FLAGS,
    "construction_order": [
        "sara-atomic", "secret-stock-graphics", "secret-palette-source",
        "gameover-accent", "native-projectile-templates",
        "continue-input-after-visuals", "presentation-composition",
        "palette-window", "select-buffer", "handheld-palette",
        "title-local-guard", "ted-menu-reinstall", "five-point-star",
        "arena-sound-alias", "arena-graphics-owner", "arena-alias-fastpath",
        "arena-completion-safe", "secret-sound-alias-fast",
        "secret-alias-chunks", "return-initial-map", "return-cgb-fade",
        "return-card-deadline", "return-card-compact",
    ],
    "historical_evidence_consumed": False,
    "retained_candidate_roms_read": False,
    "fresh_live_qualification": False,
    "audience_approval_recorded": False,
    "release_qualification": False,
    "candidate_sha256": (
        "126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b"
    ),
}
RECEIPT_KEYS = set(CONTRACT) | {
    "source_fingerprint", "source_files", "stream_receipt", "stages",
}
STREAM_BINDING_KEYS = {"receipt", "receipt_sha256"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_output(output: Path) -> None:
    if output == ROOT / "tmp" or not output.is_relative_to(ROOT / "tmp"):
        raise ValueError("use a repository-local tmp output directory")


def build(output: Path, palette: Path = DEFAULT_PALETTE) -> dict:
    output, palette = output.resolve(), palette.resolve()
    _check_output(output)
    if output.exists():
        raise ValueError("use a fresh repository-local tmp output directory")
    if palette != DEFAULT_PALETTE.resolve():
        raise ValueError("stream source profile is bound to the release palette yaml")
    snapshot = source_snapshot()
    output.mkdir(parents=True)
    stream_output = output / "stream-source"
    nested = stream.build(stream_output, **FLAGS)
    candidate = (stream_output / "candidate.gb").read_bytes()
    if digest(candidate) != CONTRACT["candidate_sha256"]:
        raise ValueError("original-source stream chain did not reproduce exact 126dd")
    if [stage["name"] for stage in nested["stages"]] != CONTRACT["construction_order"]:
        raise ValueError("stream construction order differs from contract")
    if snapshot != source_snapshot():
        raise ValueError("source identity changed during stream construction")
    stream_path = stream_output / "build-receipt.json"
    receipt = {
        **CONTRACT,
        "source_fingerprint": snapshot[0],
        "source_files": snapshot[1],
        "stream_receipt": {
            "receipt": str(stream_path.resolve()),
            "receipt_sha256": digest(stream_path.read_bytes()),
        },
        "stages": nested["stages"],
    }
    (output / "candidate.gb").write_bytes(candidate)
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def verify_receipt(path: Path, expected_rom: bytes, palette: Path = DEFAULT_PALETTE) -> dict:
    """Authenticate the construction without re-running the 36 s chain.

    Verifies the nested original-source restart proof (which reconstructs its
    own overlays), the exact stage hash linkage from c693eafb to 126dd, the
    current bytes of every builder and every transitively loaded project
    Python source, and the suite source fingerprint.
    """
    path, palette = path.resolve(), palette.resolve()
    if palette != DEFAULT_PALETTE.resolve():
        raise ValueError("stream source profile is bound to the release palette yaml")
    receipt = json.loads(path.read_text())
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS:
        raise ValueError("stream source receipt field inventory differs")
    for name, expected in CONTRACT.items():
        actual = receipt.get(name)
        if actual != expected or type(actual) is not type(expected):
            raise ValueError(f"stream source receipt {name} differs")
    if digest(expected_rom) != CONTRACT["candidate_sha256"]:
        raise ValueError("verification requires exact pinned 126dd ROM")
    output = path.parent
    _check_output(output)
    if (output / "candidate.gb").read_bytes() != expected_rom:
        raise ValueError("stream source candidate bytes differ")
    snapshot = source_snapshot()
    if snapshot != (receipt["source_fingerprint"], receipt["source_files"]):
        raise ValueError("stream source receipt source snapshot is stale")

    binding = receipt["stream_receipt"]
    if not isinstance(binding, dict) or set(binding) != STREAM_BINDING_KEYS:
        raise ValueError("stream receipt binding field inventory differs")
    stream_path = output / "stream-source/build-receipt.json"
    if binding["receipt"] != str(stream_path.resolve()):
        raise ValueError("stream receipt path differs")
    if digest(stream_path.read_bytes()) != binding["receipt_sha256"]:
        raise ValueError("stream receipt hash differs")
    nested = json.loads(stream_path.read_text())
    if nested.get("schema") != "penta-stream-regressions-source-v1":
        raise ValueError("stream receipt schema differs")
    if nested.get("candidate_sha256") != CONTRACT["candidate_sha256"]:
        raise ValueError("stream receipt candidate differs")
    if (stream_path.parent / "candidate.gb").read_bytes() != expected_rom:
        raise ValueError("stream receipt candidate bytes differ")
    if nested.get("retained_candidate_inputs") is not False:
        raise ValueError("stream receipt consumed retained candidates")
    for key, value in FLAGS.items():
        name = key if key.startswith("experimental_") else "experimental_" + key
        name += "_chain"
        if nested.get(name) is not value:
            raise ValueError(f"stream receipt {name} differs")
    if nested.get("entrypoint_sha256") != digest(Path(stream.__file__).read_bytes()):
        raise ValueError("stream entrypoint bytes changed since construction")
    if nested.get("palette_sha256") != digest(DEFAULT_PALETTE.read_bytes()):
        raise ValueError("stream palette source bytes differ")
    if nested.get("derived_parent_palette_sha256") != digest(LEGACY_PALETTE.read_bytes()):
        raise ValueError("stream derived parent palette bytes differ")
    for relative, value in nested.get("loaded_project_python_sources", {}).items():
        if relative.startswith(".venv/"):
            continue
        if digest((ROOT / relative).read_bytes()) != value:
            raise ValueError(f"stream construction source changed: {relative}")
    stages = nested.get("stages")
    if stages != receipt["stages"]:
        raise ValueError("stream stage evidence differs from wrapper receipt")
    if [stage["name"] for stage in stages] != CONTRACT["construction_order"]:
        raise ValueError("stream stage order differs from contract")
    current = CONTRACT["source_parent_sha256"]
    for stage in stages:
        if stage["parent_sha256"] != current:
            raise ValueError(f"stream stage {stage['name']} parent linkage differs")
        # Presentation sub-stages record no builder; their modules are covered
        # by the loaded_project_python_sources check above.
        if "builder" in stage and digest(Path(stage["builder"]).read_bytes()) != stage["builder_sha256"]:
            raise ValueError(f"stream stage {stage['name']} builder bytes changed")
        current = stage["candidate_sha256"]
    if current != CONTRACT["candidate_sha256"]:
        raise ValueError("stream stage linkage does not end at 126dd")

    restart_path = stream_path.parent / "restart-source/build-receipt.json"
    if digest(restart_path.read_bytes()) != nested.get("restart_receipt_sha256"):
        raise ValueError("nested restart receipt hash differs")
    restart_rom = (restart_path.parent / "candidate.gb").read_bytes()
    restart.verify_receipt(restart_path, restart_rom, LEGACY_PALETTE)
    if snapshot != source_snapshot():
        raise ValueError("source identity changed during stream verification")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--palette-yaml", type=Path, default=DEFAULT_PALETTE)
    args = parser.parse_args()
    receipt = build(args.out_dir, args.palette_yaml)
    output = args.out_dir.resolve()
    verify_receipt(output / "build-receipt.json", (output / "candidate.gb").read_bytes(),
                   args.palette_yaml)
    print(json.dumps({
        "candidate_sha256": receipt["candidate_sha256"],
        "source_parent_profile": receipt["source_parent_profile"],
        "construction_order": receipt["construction_order"],
        "historical_evidence_consumed": False,
        "status": receipt["status"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
