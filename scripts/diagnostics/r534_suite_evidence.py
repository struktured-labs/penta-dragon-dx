"""Revalidate retained r534 deterministic-suite evidence without an emulator."""
import json
from pathlib import Path

from r534_source_profile import PROFILE, builder, digest, verify_binding
from suite_release_ledger import collect_release_ledger


def source_builds(bindings: list, candidate: dict) -> bytes:
    if not isinstance(bindings, list) or len(bindings) != 2:
        raise ValueError("r534 suite requires two independent source-build bindings")
    if not all(isinstance(item, dict) for item in bindings):
        raise ValueError("r534 suite source-build bindings must be objects")
    if bindings[0].get("receipt") == bindings[1].get("receipt"):
        raise ValueError("r534 suite source builds must be distinct")
    first = None
    for binding in bindings:
        path = Path(binding["receipt"])
        rom = (path.parent / "candidate.gb").read_bytes()
        verified = verify_binding(binding, rom, builder.DEFAULT_PALETTE)
        if (candidate.get("sha256") != digest(rom) or candidate.get("size") != len(rom)
                or (first is not None and first != rom)):
            raise ValueError("r534 suite candidate differs from its source builds")
        if verified["source_fingerprint"] != bindings[0]["source_fingerprint"]:
            raise ValueError("r534 suite source builds have different fingerprints")
        first = rom
    return first


def matrix_evidence(path: Path, rom: bytes) -> dict:
    from build_release_bundle import validate_emulator_manifest
    matrix = validate_emulator_manifest(path, rom)
    for name in ("source_rom", "tested_rom"):
        if digest(Path(matrix[name]).read_bytes()) != digest(rom):
            raise ValueError(f"r534 suite matrix {name} bytes differ")
    return matrix


def verify(receipt: dict) -> None:
    if json.dumps(receipt.get("build_profile"), sort_keys=True) != json.dumps(PROFILE, sort_keys=True):
        raise ValueError("r534 suite build profile differs")
    bindings = receipt.get("source_builds")
    rom = source_builds(bindings, receipt["candidate"])
    if receipt["source_fingerprint"] != bindings[0]["source_fingerprint"]:
        raise ValueError("r534 suite source fingerprint binding differs")
    summary = receipt["matrix"]
    path = Path(summary["manifest_path"])
    if str(path.resolve()) != summary["manifest_path"]:
        raise ValueError("r534 suite matrix requires its exact canonical path")
    before = digest(path.read_bytes())
    if before != summary["manifest_sha256"]:
        raise ValueError("r534 suite matrix manifest hash differs")
    matrix = matrix_evidence(path, rom)
    expected = [{key: row[key] for key in ("name", "status", "returncode", "duration_seconds")}
                for row in matrix["results"]]
    if summary["results"] != expected:
        raise ValueError("r534 suite matrix summary differs from actual results")
    if receipt["release_ledger"] != collect_release_ledger(path.parent, expanded=True, r534=True):
        raise ValueError("r534 suite release ledger differs from nested evidence")
    if digest(path.read_bytes()) != before:
        raise ValueError("r534 suite matrix changed during verification")
