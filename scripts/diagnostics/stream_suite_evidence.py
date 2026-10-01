"""Revalidate retained 126dd stream deterministic-suite evidence without an emulator."""
from __future__ import annotations

import json
from pathlib import Path

from stream_source_profile import PROFILE, builder, digest, verify_binding
from suite_release_ledger import collect_release_ledger


def source_builds(bindings: list, candidate: dict) -> bytes:
    if not isinstance(bindings, list) or len(bindings) != 2:
        raise ValueError("stream suite requires two independent source-build bindings")
    if not all(isinstance(item, dict) for item in bindings):
        raise ValueError("stream suite source-build bindings must be objects")
    if bindings[0].get("receipt") == bindings[1].get("receipt"):
        raise ValueError("stream suite source builds must be distinct")
    first = None
    for binding in bindings:
        path = Path(binding["receipt"])
        rom = (path.parent / "candidate.gb").read_bytes()
        verified = verify_binding(binding, rom, builder.DEFAULT_PALETTE)
        if (
            candidate.get("sha256") != digest(rom)
            or candidate.get("size") != len(rom)
            or (first is not None and first != rom)
        ):
            raise ValueError("stream suite candidate differs from its source builds")
        if verified["source_fingerprint"] != bindings[0]["source_fingerprint"]:
            raise ValueError("stream suite source builds have different fingerprints")
        first = rom
    return first


def matrix_evidence(path: Path, rom: bytes) -> dict:
    from build_release_bundle import validate_emulator_manifest

    matrix = validate_emulator_manifest(path, rom)
    for name in ("source_rom", "tested_rom"):
        if digest(Path(matrix[name]).read_bytes()) != digest(rom):
            raise ValueError(f"stream suite matrix {name} bytes differ")
    return matrix


def verify(receipt: dict) -> None:
    if json.dumps(receipt.get("build_profile"), sort_keys=True) != json.dumps(PROFILE, sort_keys=True):
        raise ValueError("stream suite build profile differs")
    bindings = receipt.get("source_builds")
    rom = source_builds(bindings, receipt["candidate"])
    if receipt["source_fingerprint"] != bindings[0]["source_fingerprint"]:
        raise ValueError("stream suite source fingerprint binding differs")
    summary = receipt["matrix"]
    path = Path(summary["manifest_path"])
    if str(path.resolve()) != summary["manifest_path"]:
        raise ValueError("stream suite matrix requires its exact canonical path")
    before = digest(path.read_bytes())
    if before != summary["manifest_sha256"]:
        raise ValueError("stream suite matrix manifest hash differs")
    matrix = matrix_evidence(path, rom)
    expected = [
        {key: row[key] for key in ("name", "status", "returncode", "duration_seconds")}
        for row in matrix["results"]
    ]
    if summary["results"] != expected:
        raise ValueError("stream suite matrix summary differs from actual results")
    ledger = collect_release_ledger(
        path.parent, expanded=True, source_profile=PROFILE["name"]
    )
    if receipt["release_ledger"] != ledger:
        raise ValueError("stream suite release ledger differs from nested evidence")
    if digest(path.read_bytes()) != before:
        raise ValueError("stream suite matrix changed during verification")
