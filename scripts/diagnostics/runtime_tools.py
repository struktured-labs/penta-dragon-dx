"""Fingerprint the guarded emulator and its actually resolved shared libraries."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]

# Register-level audit: this build drops CGB FF72–FF74 writes and sends Ted's
# GDMA to the wrong destination. Binary identity alone cannot detect it.
BROKEN_CGB_LATCH_LIBRARY = "df25d1ecfdd1bb3acab3be96e0c2c00848c475c51ecfb4354828fda334e355e4"


def reject_known_broken_cgb_runtime(snapshot: dict) -> None:
    """Reject the demonstrated bad instrument, not unknown future builds.

    Other builds still require the full matrix and recorded runtime identity;
    absence from this denylist is not a qualification or a test pass.
    """
    for mode in ("qt", "headless"):
        for library in snapshot[mode]["libraries"]:
            if library["sha256"] == BROKEN_CGB_LATCH_LIBRARY:
                raise RuntimeError(
                    f"{mode} resolves the known-broken CGB latch library: "
                    f"{library['path']}. Select the corrected runtime with "
                    'LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build"; '
                    "see docs/audit/mgba_cgb_latches_r454.md. "
                    "No emulator tests were started."
                )


def identity(path: Path) -> dict:
    resolved = path.resolve(strict=True)
    return {"path": str(resolved), "size": resolved.stat().st_size,
            "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest()}


def library_paths(output: str) -> list[Path]:
    if "not found" in output:
        raise RuntimeError("emulator has an unresolved shared library")
    paths = set()
    for line in output.splitlines():
        match = re.search(r"(?:=>\s+)?(/\S+)\s+\(0x[0-9a-f]+\)", line)
        if match:
            paths.add(Path(match.group(1)).resolve(strict=True))
    return sorted(paths)


def canonical_loader_search_path(value: str) -> str:
    """Normalize existing loader directories without weakening comparison.

    The checkout is commonly reached through both ``penta-dragon-dx`` and its
    physical ``penta-dragon-dx-claude`` target.  The dynamic loader treats
    those spellings identically, so a provenance comparison must not reject
    one merely because the other was recorded.  Missing entries and empty
    entries remain literal so genuinely different loader search behavior is
    still rejected.
    """

    normalized: list[str] = []
    for entry in value.split(":"):
        if not entry:
            normalized.append(entry)
            continue
        candidate = Path(entry).expanduser()
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        try:
            normalized.append(str(candidate.resolve(strict=True)))
        except OSError:
            normalized.append(entry)
    return ":".join(normalized)


def normalized_runtime_snapshot(snapshot: object) -> object:
    """Return a comparison view that canonicalizes only loader path aliases."""

    if not isinstance(snapshot, dict):
        return snapshot
    normalized = dict(snapshot)
    loader_path = normalized.get("LD_LIBRARY_PATH")
    if isinstance(loader_path, str):
        normalized["LD_LIBRARY_PATH"] = canonical_loader_search_path(loader_path)
    return normalized


def runtime_snapshots_match(*snapshots: object) -> bool:
    """Compare runtime identities while accepting equivalent symlink paths."""

    if not snapshots:
        return True
    expected = normalized_runtime_snapshot(snapshots[0])
    return all(
        normalized_runtime_snapshot(snapshot) == expected
        for snapshot in snapshots[1:]
    )


def emulator_runtime_snapshot() -> dict:
    guard_path = ROOT / "scripts/mgba_singleflight.py"
    spec = importlib.util.spec_from_file_location("penta_runtime_guard", guard_path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    result = {"guard": identity(guard_path),
              "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH", ""),
              "LD_PRELOAD": os.environ.get("LD_PRELOAD", "")}
    for mode in ("qt", "headless"):
        binary = guard.resolve_binary(mode).resolve(strict=True)
        listing = subprocess.run(["ldd", str(binary)], text=True,
                                 capture_output=True, check=True)
        libraries = library_paths(listing.stdout)
        if not libraries:
            raise RuntimeError(f"no runtime dependencies resolved for {binary}")
        result[mode] = {"binary": identity(binary),
                        "libraries": [identity(path) for path in libraries]}
    return result
