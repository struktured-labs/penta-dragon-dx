#!/usr/bin/env python3
"""Experimental original-cartridge -> factory -> historical r120 -> r534 replay.

Uses maintained source and explicit historical evidence, never saved candidate
ROMs. Both complete builds run under a filesystem trace, failing closed on
reads of retained scratch artifacts. This is not release qualification.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import rebuild_r534_lineage as lineage
import r120_historical_profile as profile
from suite_contract import source_snapshot

FACTORY_OPTIONS = (
    "--native-sparse", "--native-pose-table", "--menu-icon-colors",
    "--stage-card-palette-handoff", "--stage1-tagged-destination",
    "--stage1-precomputed-attrs", "--stage1-wram-scene-guard",
)
QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"')


def audit_factory_access(text: str, generated: Path) -> dict:
    """Check actual child opens; reject unsupported relative-directory changes."""
    opened = set()
    calls = 0
    for line in text.splitlines():
        if "fchdir(" in line or "openat2(" in line:
            raise ValueError("unsupported filesystem-trace operation")
        if "chdir(" in line:
            match = QUOTED.search(line)
            if match is None or Path(ast.literal_eval(match.group())).resolve() != ROOT:
                raise ValueError("factory changed directory outside the fixed repository root")
        if not re.search(r"\b(?:open|openat)\(", line):
            continue
        if "<unfinished ...>" in line:
            raise ValueError("incomplete filesystem trace record")
        if "openat(" in line and "openat(AT_FDCWD," not in line:
            raise ValueError("unsupported relative directory descriptor in filesystem trace")
        match = QUOTED.search(line)
        if match is None:
            raise ValueError("unparseable filesystem open record")
        path = (ROOT / ast.literal_eval(match.group())).resolve()
        calls += 1
        if path.is_relative_to(ROOT / "tmp") and not path.is_relative_to(generated):
            raise ValueError(f"factory accessed a retained scratch artifact: {path}")
        if path.is_relative_to(ROOT) and path.suffix == ".pyc" and not path.is_relative_to(generated):
            raise ValueError(f"factory accessed cached repository bytecode: {path}")
        # No cartridge other than the explicit original may be read outside
        # this run's generated directory (including rom/versions fixtures).
        if path.suffix.lower() in (".gb", ".gbc", ".ss0", ".ss1"):
            if path != ROOT / "rom/Penta Dragon (J).gb" and not path.is_relative_to(generated):
                raise ValueError(f"factory accessed an undeclared ROM/state: {path}")
        if path.is_relative_to(ROOT) and path.is_file() and not path.is_relative_to(generated):
            opened.add(path)
    if calls == 0 or ROOT / "rom/Penta Dragon (J).gb" not in opened:
        raise ValueError("filesystem trace lacks original-cartridge reads")
    return {
        "open_calls_checked": calls, "retained_scratch_artifact_accesses": 0,
        "repository_inputs": {str(path.relative_to(ROOT)): lineage.digest(path.read_bytes())
                              for path in sorted(opened)},
    }


def factory_command(generated: Path, palette: Path) -> list[str]:
    return [sys.executable, str(ROOT / "scripts/build_ted_expanded_candidate.py"),
            "--output", str(generated / "factory.gb"), "--work", str(generated / "work"),
            "--palette-yaml", str(palette.resolve()), *FACTORY_OPTIONS]


def run_factory(generated: Path, palette: Path, tracer: str) -> tuple[bytes, dict]:
    """Shared traced factory stage; the caller owns a fresh generated directory."""
    command = factory_command(generated, palette)
    trace_path = generated / "file-access.trace"
    env = {name: value for name, value in os.environ.items() if not name.startswith("PENTA_")}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(ROOT / "tmp"),
                "PYTHONPYCACHEPREFIX": str(generated / "unused-bytecode")})
    completed = subprocess.run(
        [tracer, "-f", "-qq", "-s", "4096", "-e", "trace=open,openat,openat2,chdir,fchdir",
         "-o", str(trace_path), *command], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=180,
    )
    (generated / "factory.log").write_text(completed.stdout + completed.stderr)
    if completed.returncode:
        raise ValueError(f"factory build failed; see {generated / 'factory.log'}")
    access = audit_factory_access(trace_path.read_text(), generated)
    factory = (generated / "factory.gb").read_bytes()
    return factory, {
        "command": command, "factory_sha256": lineage.digest(factory),
        "environment_policy": {"inherited_PENTA_overrides_removed": True,
                               "bytecode_writes_disabled": True,
                               "pycache_prefix": env["PYTHONPYCACHEPREFIX"]},
        "file_access_trace": str(trace_path),
        "file_access_trace_sha256": lineage.digest(trace_path.read_bytes()),
        "filesystem_audit": access,
    }


def verify_factory_run(run: dict, generated: Path, palette: Path) -> bytes:
    """Revalidate the fixed invocation and the complete traced filesystem evidence."""
    command = run.get("command")
    expected = factory_command(generated, palette)
    # Issue #11: python and python3 can be aliases of the same authenticated
    # binary. Keep all arguments exact; only resolve the interpreter spelling.
    # The enclosing receipt independently checks its current path and SHA-256.
    if (not isinstance(command, list) or len(command) != len(expected)
            or not all(isinstance(argument, str) for argument in command)
            or not Path(command[0]).is_absolute()
            or Path(command[0]).resolve() != Path(expected[0]).resolve()
            or command[1:] != expected[1:]):
        raise ValueError("original replay factory invocation differs")
    if run.get("environment_policy") != {
        "inherited_PENTA_overrides_removed": True, "bytecode_writes_disabled": True,
        "pycache_prefix": str(generated / "unused-bytecode"),
    }:
        raise ValueError("original replay factory environment policy differs")
    trace = generated / "file-access.trace"
    if Path(run["file_access_trace"]).resolve() != trace:
        raise ValueError("original replay file-access trace path differs")
    if lineage.digest(trace.read_bytes()) != run["file_access_trace_sha256"]:
        raise ValueError("original replay file-access trace changed")
    if audit_factory_access(trace.read_text(), generated) != run["filesystem_audit"]:
        raise ValueError("original replay filesystem evidence differs")
    factory = (generated / "factory.gb").read_bytes()
    if lineage.digest(factory) != run["factory_sha256"]:
        raise ValueError("original replay factory bytes changed")
    return factory


def build(output: Path, manifest: Path, palette: Path) -> dict:
    output = output.resolve()
    if not output.is_relative_to(ROOT / "tmp") or output == ROOT / "tmp":
        raise ValueError("use a fresh repository-local tmp output directory")
    if output.exists():
        raise ValueError("output directory already exists; use a fresh immutable attempt")
    tracer = shutil.which("strace")
    if tracer is None:
        raise ValueError("strace is required for retained-artifact access verification")
    original_path = ROOT / "rom/Penta Dragon (J).gb"
    original = original_path.read_bytes()
    if lineage.digest(original) != lineage.prefix.ORIGINAL_SHA256:
        raise ValueError("exact original cartridge identity differs")
    manifest_bytes = manifest.read_bytes()
    paths = lineage.historical_paths(manifest_bytes.decode(), {})
    evidence = {name: path.read_bytes() for name, path in paths.items()}
    required = (lineage.phase.HISTORICAL_INPUTS | lineage.stage7.HISTORICAL_INPUTS
                | lineage.stage4.HISTORICAL_INPUTS | lineage.ancestry.HISTORICAL_INPUTS)
    if set(evidence) != set(required):
        raise ValueError("original-cartridge replay requires exactly twenty-eight historical inputs")
    for name, (_, expected) in required.items():
        if lineage.digest(evidence[name]) != expected:
            raise ValueError(f"{name}: historical evidence identity differs")
    palette = palette.resolve()
    palette_sha = lineage.digest(palette.read_bytes())
    fingerprint, sources = source_snapshot()
    output.mkdir(parents=True)
    guard_active = [False]

    def in_memory_audit(event, arguments):
        if guard_active[0] and event == "open" and isinstance(arguments[0], (str, bytes)):
            raw = arguments[0].decode() if isinstance(arguments[0], bytes) else arguments[0]
            path = (ROOT / raw).resolve()
            if path.is_relative_to(ROOT / "tmp") or path == original_path:
                raise ValueError(f"in-memory reconstruction accessed an undeclared artifact: {path}")

    sys.addaudithook(in_memory_audit)
    runs = []
    first = None
    first_metadata = None
    for index in (1, 2):
        generated = output / f"build-{index}"
        generated.mkdir()
        factory, run = run_factory(generated, palette, tracer)
        # From this point onward no generator may open any retained or generated
        # scratch artifact. Inputs are already explicit in-memory byte strings.
        guard_active[0] = True
        try:
            baseline, baseline_receipt = profile.build(factory)
            result, replay = lineage.build(baseline, original_rom=original, historical_evidence=evidence)
        finally:
            guard_active[0] = False
        replay["retained_input"] = None
        replay["generated_input"] = "r120 historical source profile"
        metadata = {"baseline": baseline_receipt, "replay": replay}
        if first is None:
            first, first_metadata = result, metadata
        elif (result, metadata) != (first, first_metadata):
            raise ValueError("complete original-cartridge double build differs")
        (generated / "baseline.gb").write_bytes(baseline)
        runs.append(run)
    if (fingerprint, sources) != source_snapshot():
        raise ValueError("maintained source changed during original-cartridge reconstruction")
    if original_path.read_bytes() != original or lineage.digest(palette.read_bytes()) != palette_sha:
        raise ValueError("original cartridge or palette changed during reconstruction")
    receipt = {
        "schema": "penta-r534-original-cartridge-replay-v1",
        "experimental": True, "promotable": False, "double_build_identical": True,
        "candidate_sha256": lineage.digest(first),
        "original_rom": {"path": str(original_path), "sha256": lineage.digest(original)},
        "palette": {"path": str(palette), "sha256": palette_sha},
        "historical_input_manifest": {"path": str(manifest.resolve()), "sha256": lineage.digest(manifest_bytes)},
        "historical_evidence": {name: {"path": str(paths[name].resolve()),
                                       "sha256": lineage.digest(data), "fresh_live_qualification": False}
                                for name, data in evidence.items()},
        "source_fingerprint": fingerprint, "source_files": sources,
        "strace": {"path": tracer, "sha256": lineage.digest(Path(tracer).read_bytes())},
        "python": {"path": sys.executable, "sha256": lineage.digest(Path(sys.executable).read_bytes())},
        "retained_candidate_roms_read": False, "generated_intermediate_artifacts_read": True,
        "in_memory_reconstruction_artifact_reads_forbidden": True,
        "factory_runs": runs, **first_metadata,
    }
    (output / "candidate.gb").write_bytes(first)
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def verify_receipt(path: Path, expected_rom: bytes, palette: Path) -> dict:
    """Recheck source/tool/input provenance and deterministic nested evidence."""
    receipt = json.loads(path.read_text())
    for name, expected in {
        "schema": "penta-r534-original-cartridge-replay-v1",
        "experimental": True, "promotable": False, "double_build_identical": True,
        "retained_candidate_roms_read": False, "generated_intermediate_artifacts_read": True,
        "in_memory_reconstruction_artifact_reads_forbidden": True,
        "candidate_sha256": lineage.digest(expected_rom),
    }.items():
        if receipt.get(name) != expected:
            raise ValueError(f"original replay receipt {name} differs")
    output = path.resolve().parent
    if (output / "candidate.gb").read_bytes() != expected_rom:
        raise ValueError("original replay candidate bytes differ from requested ROM")
    fingerprint, sources = source_snapshot()
    if (receipt.get("source_fingerprint"), receipt.get("source_files")) != (fingerprint, sources):
        raise ValueError("original replay source snapshot is stale")
    for name in ("original_rom", "palette", "historical_input_manifest", "strace", "python"):
        item = receipt[name]
        if lineage.digest(Path(item["path"]).read_bytes()) != item["sha256"]:
            raise ValueError(f"original replay {name} identity differs")
    if Path(receipt["palette"]["path"]).resolve() != palette.resolve():
        raise ValueError("original replay targets a different palette path")
    original_path = ROOT / "rom/Penta Dragon (J).gb"
    if Path(receipt["original_rom"]["path"]).resolve() != original_path:
        raise ValueError("original replay targets a different original cartridge path")
    if Path(receipt["python"]["path"]).resolve() != Path(sys.executable).resolve():
        raise ValueError("original replay Python identity is not current")
    tracer = shutil.which("strace")
    if tracer is None or Path(receipt["strace"]["path"]).resolve() != Path(tracer).resolve():
        raise ValueError("original replay filesystem tracer is not current")
    manifest = Path(receipt["historical_input_manifest"]["path"])
    paths = lineage.historical_paths(manifest.read_text(), {})
    evidence = {name: item.read_bytes() for name, item in paths.items()}
    expected_history = {name: {"path": str(paths[name].resolve()), "sha256": lineage.digest(data),
                               "fresh_live_qualification": False} for name, data in evidence.items()}
    if receipt.get("historical_evidence") != expected_history:
        raise ValueError("original replay historical input provenance differs")
    runs = receipt.get("factory_runs")
    if not isinstance(runs, list) or len(runs) != 2:
        raise ValueError("original replay requires two traced factory runs")
    original = original_path.read_bytes()
    for index, run in enumerate(runs, 1):
        generated = output / f"build-{index}"
        factory = verify_factory_run(run, generated, palette)
        baseline, baseline_receipt = profile.build(factory)
        if baseline_receipt != receipt["baseline"] or (generated / "baseline.gb").read_bytes() != baseline:
            raise ValueError("original replay baseline provenance differs")
        result, replay = lineage.build(baseline, original_rom=original, historical_evidence=evidence)
        replay["retained_input"] = None
        replay["generated_input"] = "r120 historical source profile"
        if result != expected_rom or replay != receipt["replay"]:
            raise ValueError("original replay generated lineage differs")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--historical-input-manifest", type=Path, required=True)
    parser.add_argument("--palette-yaml", type=Path, default=ROOT / "palettes/penta_palettes_v097.yaml")
    args = parser.parse_args()
    receipt = build(args.out_dir, args.historical_input_manifest, args.palette_yaml)
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"],
                      "double_build_identical": True, "retained_candidate_roms_read": False,
                      "replay_steps": len(receipt["replay"]["steps"]), "promotable": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
