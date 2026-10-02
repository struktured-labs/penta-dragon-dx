#!/usr/bin/env python3
"""Double-build exact experimental r534 from the original cartridge and source.

No retained factory ROM, historical-input bundle, capture, or savestate is an
input. Both factory runs are syscall-traced; subsequent construction forbids
artifact reads. Success is source reconstruction, not approval or qualification.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import build_r534_source_candidate as source
import rebuild_r534_from_original as factory_stage
from suite_contract import source_snapshot

ORIGINAL = ROOT / "rom/Penta Dragon (J).gb"
DEFAULT_PALETTE = ROOT / "palettes/penta_palettes_v097.yaml"
CONTRACT = {
    "schema": "penta-r534-original-source-build-v1",
    "status": "source-build-pass", "experimental": True, "promotable": False,
    "double_build_identical": True, "historical_evidence_consumed": False,
    "retained_candidate_roms_read": False, "generated_intermediate_artifacts_read": True,
    "in_memory_artifact_reads_forbidden": True, "fresh_live_qualification": False,
    "audience_approval_recorded": False, "release_qualification": False,
    "candidate_sha256": source.continuation.CANDIDATE_SHA256,
}
RUN_KEYS = {"command", "factory_sha256", "environment_policy", "file_access_trace",
            "file_access_trace_sha256", "filesystem_audit"}


def identity(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": source.digest(path.read_bytes())}


def tools_identity() -> dict:
    tracer = shutil.which("strace")
    if tracer is None:
        raise ValueError("strace is required for original-source construction")
    return {"python": identity(Path(sys.executable)), "strace": identity(Path(tracer))}


def construction_json(metadata: dict) -> str:
    """Compare the persisted JSON contract, including JSON key/list conversion.

    Sort only after conversion: source metadata can contain integer map keys.
    Comparing serialized values also distinguishes booleans from integers.
    """
    persisted = json.loads(json.dumps(metadata, allow_nan=False))
    return json.dumps(persisted, sort_keys=True, allow_nan=False)


@contextmanager
def construction_guard():
    active = True
    def audit(event, arguments):
        if active and event == "open" and isinstance(arguments[0], (str, bytes)):
            raw = arguments[0].decode() if isinstance(arguments[0], bytes) else arguments[0]
            path = Path(raw).resolve()
            if path.is_relative_to(ROOT / "tmp") or path.suffix.lower() in {".gb", ".gbc", ".ss0", ".ss1"}:
                raise ValueError(f"in-memory source build accessed an undeclared artifact: {path}")
    sys.addaudithook(audit)
    try:
        yield
    finally:
        active = False


def build(output: Path, palette: Path) -> dict:
    output, palette = output.resolve(), palette.resolve()
    if output == ROOT / "tmp" or not output.is_relative_to(ROOT / "tmp") or output.exists():
        raise ValueError("use a fresh repository-local tmp output directory")
    tools = tools_identity()
    original = ORIGINAL.read_bytes()
    if source.digest(original) != source.ORIGINAL_SHA256:
        raise ValueError("exact original cartridge identity differs")
    inputs = {"original_rom": identity(ORIGINAL), "palette": identity(palette)}
    snapshot = source_snapshot()
    output.mkdir(parents=True)
    runs, first, construction = [], None, None
    for index in (1, 2):
        generated = output / f"build-{index}"
        generated.mkdir()
        factory, run = factory_stage.run_factory(generated, palette, tools["strace"]["path"])
        with construction_guard():
            result, metadata = source.build(factory, original)
        if first is None:
            first, construction = result, metadata
        elif (result, metadata) != (first, construction):
            raise ValueError("complete original-source double build differs")
        runs.append(run)
    if source.digest(first) != CONTRACT["candidate_sha256"]:
        raise ValueError("original-source build did not reproduce exact r534")
    if snapshot != source_snapshot() or tools != tools_identity():
        raise ValueError("source or tool identity changed during construction")
    if inputs != {"original_rom": identity(ORIGINAL), "palette": identity(palette)}:
        raise ValueError("original cartridge or palette changed during construction")
    receipt = {**CONTRACT, **inputs, **tools,
               "source_fingerprint": snapshot[0], "source_files": snapshot[1],
               "factory_runs": runs, "construction": json.loads(construction_json(construction))}
    (output / "candidate.gb").write_bytes(first)
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def verify_receipt(path: Path, expected_rom: bytes, palette: Path) -> dict:
    """Recheck current source/tools, traced inputs, both factories, and all steps."""
    receipt = json.loads(path.read_text())
    expected_keys = set(CONTRACT) | {"original_rom", "palette", "python", "strace",
                                   "source_fingerprint", "source_files", "factory_runs", "construction"}
    if not isinstance(receipt, dict) or set(receipt) != expected_keys:
        raise ValueError("original-source receipt field inventory differs")
    for name, expected in CONTRACT.items():
        actual = receipt.get(name)
        if actual != expected or type(actual) is not type(expected):
            raise ValueError(f"original-source receipt {name} differs")
    if source.digest(expected_rom) != CONTRACT["candidate_sha256"]:
        raise ValueError("verification requires exact pinned r534 ROM")
    output = path.resolve().parent
    if output == ROOT / "tmp" or not output.is_relative_to(ROOT / "tmp"):
        raise ValueError("original-source receipt must belong to repository-local tmp output")
    if (output / "candidate.gb").read_bytes() != expected_rom:
        raise ValueError("original-source candidate bytes differ")
    snapshot = source_snapshot()
    if snapshot != (receipt["source_fingerprint"], receipt["source_files"]):
        raise ValueError("original-source receipt source snapshot is stale")
    tools = tools_identity()
    if any(receipt[name] != item for name, item in tools.items()):
        raise ValueError("original-source tool identity is not current")
    inputs = {"original_rom": identity(ORIGINAL), "palette": identity(palette)}
    if any(receipt[name] != item for name, item in inputs.items()):
        raise ValueError("original-source input identity differs")
    if inputs["original_rom"]["sha256"] != source.ORIGINAL_SHA256:
        raise ValueError("exact original cartridge identity differs")
    original = ORIGINAL.read_bytes()
    runs = receipt["factory_runs"]
    if not isinstance(runs, list) or len(runs) != 2:
        raise ValueError("original-source receipt requires two traced factory runs")
    for index, run in enumerate(runs, 1):
        if not isinstance(run, dict) or set(run) != RUN_KEYS:
            raise ValueError("original-source factory record inventory differs")
        factory = factory_stage.verify_factory_run(run, output / f"build-{index}", palette)
        with construction_guard():
            result, metadata = source.build(factory, original)
        if result != expected_rom or construction_json(metadata) != construction_json(receipt["construction"]):
            raise ValueError("original-source generated construction differs")
    if snapshot != source_snapshot() or tools != tools_identity():
        raise ValueError("source or tool identity changed during verification")
    if inputs != {"original_rom": identity(ORIGINAL), "palette": identity(palette)}:
        raise ValueError("original cartridge or palette changed during verification")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--palette-yaml", type=Path, default=DEFAULT_PALETTE)
    args = parser.parse_args()
    receipt = build(args.out_dir, args.palette_yaml)
    candidate = (args.out_dir.resolve() / "candidate.gb").read_bytes()
    verify_receipt(args.out_dir.resolve() / "build-receipt.json", candidate, args.palette_yaml)
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"],
                      "double_build_identical": True, "historical_evidence_consumed": False,
                      "construction_steps": receipt["construction"]["total_steps"],
                      "status": receipt["status"], "promotable": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
