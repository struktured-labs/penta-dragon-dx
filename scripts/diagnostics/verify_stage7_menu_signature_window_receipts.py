#!/usr/bin/env python3
"""Offline audit of duplicate r265 generic Stage-1 Window-order runs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
R1 = ROOT / "tmp/stage7-menu-signature-invalidation-r265/generic-menu-natural-r1"
R2 = ROOT / "tmp/stage7-menu-signature-invalidation-r265/generic-menu-natural-r2"
ALIAS = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "generic-menu-alias-control-r1"
)
STALE = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "generic-menu-stale-control-r1"
)
CANDIDATE = ROOT / "tmp/stage7-menu-signature-invalidation-r265/candidate.gb"
EQUIVALENCE = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "helper-equivalence-static-receipt.json"
)
VERIFIER = ROOT / "scripts/diagnostics/verify_menu_window_order.py"
PROBE = ROOT / "scripts/diagnostics/probe_menu_window_order.lua"
LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"
DEFAULT_OUTPUT = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "generic-menu-natural-receipt.json"
)

CANDIDATE_SHA = "a4c772624f16bc9ef23873726cbbafa169ee93869a95a17431367895273bd273"
EQUIVALENCE_SHA = "295ce612d6dc1dead72e776f44dafb3bd22b6bc0e44b101435b27d7ddafe0583"
VERIFIER_SHA = "3e243e1d65e0eaf599831955b0f43e8cb6ea6bb9e12ce732a1df82207501d614"
PROBE_SHA = "bb21703ed4e17a14057d8d100fb9bec73f5597b9b413e5addfa6f28eb6f1106e"
LAUNCHER_SHA = "46fe5b57771627e9141e359bd93c9d821c2b873d34162e355dfec33896649570"
REPORT_SHA = "61b293209f5cc3f3c416f2ccb079bc26ec430b430621ddd42a60f427a11eb056"
ALIAS_REPORT_SHA = "7d99e9104aa13ac9b532821673e9e8d8049a36b53455d3d4207246122825fbcc"
STALE_REPORT_SHA = "bc3ce7ee6855a7c38cec80fd00ac3f7c0d2155734cd308c41e047f118723a0e6"

ARTIFACTS = {
    "report": ("report.txt", 1561),
    "first_visible_png": ("report.first_visible.png", 2873),
    "final_png": ("report.txt.final.png", 2727),
    "c1a0": ("report.txt.c1a0.bin", 576),
    "vram9800": ("report.txt.vram9800.bin", 1024),
    "vram9c00": ("report.txt.vram9c00.bin", 1024),
    "runtime_rom": ("report.runtime/candidate.gb", 524288),
    "runtime_sav": ("report.runtime/candidate.sav", 8192),
}

FINAL_PATTERN = re.compile(
    r"^scene:02 room:05 ffe4:00 lcdc:8B scx:0C scy:00 "
    r"wx:07 wy:60 dc00:3C dc01:00 dc02:20 dc03:07 c1a4:03$"
)
STALE_FINAL_PATTERN = re.compile(
    r"^scene:02 room:05 ffe4:00 lcdc:83 scx:0C scy:00 "
    r"wx:07 wy:60 dc00:3C dc01:00 dc02:20 dc03:07 c1a4:03$"
)
VISIBLE_PATTERN = re.compile(
    r"^frame:1205 scene:02 room:05 lcdc:E3 wy:60 map:9C00 mismatches:0$"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    return digest(path.read_bytes())


def scratch(path: Path) -> Path:
    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(any(resolved != root and resolved.is_relative_to(root)
                for root in roots),
            "output must be a child of repo tmp/ or /mnt/data/tmp/")
    return resolved


def parse_report(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        require("=" in line, f"malformed report line: {line!r}")
        key, value = line.split("=", 1)
        require(key and key not in result, f"duplicate report key {key}")
        result[key] = value
    return result


def audit_report(report: dict[str, str]) -> dict[str, Any]:
    integer_keys = (
        "frames", "window_frames", "bad_frames",
        "window_frames_after_close", "stale_injected",
        "stale_window_frames_after_grace", "worst_mismatches",
        "map_alias_frames",
    )
    try:
        values = {key: int(report[key], 10) for key in integer_keys}
    except (KeyError, ValueError) as error:
        raise AssertionError(f"missing/invalid integer field: {error}") from error
    require(values["frames"] == 1400, "wrong fixed frame budget")
    require(values["window_frames"] >= 30,
            "native Window visibility is vacuous")
    for key in (
        "bad_frames", "window_frames_after_close", "stale_injected",
        "stale_window_frames_after_grace", "worst_mismatches",
        "map_alias_frames",
    ):
        require(values[key] == 0, f"nonzero Window containment field {key}")
    require(report.get("stale_scene") == "native", "wrong native scene tag")
    require(report.get("first_bad") == "none", "a bad Window frame occurred")
    require(report.get("first_alias") == "none", "Window/BG maps aliased")
    require(FINAL_PATTERN.fullmatch(report.get("final_state", "")) is not None,
            "final Stage1/menu-close hardware state changed")
    require(VISIBLE_PATTERN.fullmatch(report.get("first_visible", "")) is not None,
            "first visible native Window boundary changed")
    return {**values, "first_visible": report["first_visible"],
            "final_state": report["final_state"],
            "transition_log_entries": len(
                [item for item in report.get("transitions", "").split(";")
                 if item]
            )}


def png_geometry(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    require(payload.startswith(b"\x89PNG\r\n\x1a\n"),
            f"not a PNG: {path}")
    require(payload[12:16] == b"IHDR" and len(payload) >= 24,
            f"PNG lacks IHDR: {path}")
    return struct.unpack(">II", payload[16:24])


def audit_run(path: Path) -> dict[str, Any]:
    require(path.is_dir(), f"run directory missing: {path}")
    artifacts: dict[str, Any] = {}
    for name, (relative, size) in ARTIFACTS.items():
        artifact = path / relative
        require(artifact.is_file(), f"missing {name}: {artifact}")
        require(artifact.stat().st_size == size,
                f"wrong {name} size: {artifact.stat().st_size}")
        artifacts[name] = {
            "path": str(artifact.relative_to(ROOT)),
            "size": size,
            "sha256": sha256(artifact),
        }
    require(artifacts["report"]["sha256"] == REPORT_SHA,
            "generic menu report identity changed")
    require(artifacts["runtime_rom"]["sha256"] == CANDIDATE_SHA,
            "runtime did not execute exact r265")
    for name in ("first_visible_png", "final_png"):
        require(png_geometry(path / ARTIFACTS[name][0]) == (160, 144),
                f"{name} is not an exact Game Boy frame")
    report = parse_report(path / "report.txt")
    thresholds = audit_report(report)
    return {"path": str(path.relative_to(ROOT)), "artifacts": artifacts,
            "thresholds": thresholds, "report": report}


def audit_control_report(report: dict[str, str], kind: str) -> dict[str, Any]:
    keys = (
        "frames", "window_frames", "bad_frames",
        "window_frames_after_close", "stale_injected",
        "stale_window_frames_after_grace", "worst_mismatches",
        "map_alias_frames",
    )
    try:
        values = {key: int(report[key], 10) for key in keys}
    except (KeyError, ValueError) as error:
        raise AssertionError(f"invalid {kind} control field: {error}") from error
    if kind == "alias":
        require(values == {
            "frames": 1280, "window_frames": 76, "bad_frames": 0,
            "window_frames_after_close": 0, "stale_injected": 0,
            "stale_window_frames_after_grace": 0, "worst_mismatches": 0,
            "map_alias_frames": 1,
        }, "forced-alias control thresholds changed")
        require(report.get("first_alias")
                == "frame:1250 lcdc:EB map:9C00",
                "forced alias was not injected exactly once at frame1250")
        require(report.get("first_bad") == "none",
                "forced alias corrupted Window contents")
        require(VISIBLE_PATTERN.fullmatch(report.get("first_visible", "")),
                "forced-alias native Window boundary changed")
        require(report.get("final_state", "").startswith(
            "scene:02 room:05 ffe4:01 lcdc:E3 "),
            "forced-alias Window did not recover/remain native")
    else:
        require(values == {
            "frames": 805, "window_frames": 1, "bad_frames": 1,
            "window_frames_after_close": 0, "stale_injected": 1,
            "stale_window_frames_after_grace": 0,
            "worst_mismatches": 117, "map_alias_frames": 0,
        }, "stale-Window control thresholds changed")
        require(report.get("first_bad") == (
            "frame:800 scene:02 room:05 lcdc:AB wy:60 map:9800 "
            "dc0b:01 ffda:00 mismatches:117"
        ), "stale Window injection boundary changed")
        require(report.get("first_visible") == (
            "frame:800 scene:02 room:05 lcdc:AB wy:60 map:9800 "
            "mismatches:117"
        ), "stale Window nonvacuity changed")
        require(report.get("first_alias") == "none",
                "stale Window aliased the gameplay BG map")
        require(STALE_FINAL_PATTERN.fullmatch(report.get("final_state", "")),
                "stale Window did not recover to its exact frame-805 "
                "Stage1 hardware state")
    return values


def audit_control(path: Path, kind: str) -> dict[str, Any]:
    require(path.is_dir(), f"{kind} control directory missing")
    report_path = path / "report.txt"
    require(report_path.is_file(), f"{kind} report missing")
    expected_report_sha = (
        ALIAS_REPORT_SHA if kind == "alias" else STALE_REPORT_SHA
    )
    require(sha256(report_path) == expected_report_sha,
            f"{kind} report identity changed")
    runtime = path / "report.runtime/candidate.gb"
    require(runtime.is_file() and runtime.stat().st_size == 524288
            and sha256(runtime) == CANDIDATE_SHA,
            f"{kind} control did not execute exact r265")
    common = (
        "report.first_visible.png", "report.txt.final.png",
        "report.txt.c1a0.bin", "report.txt.vram9800.bin",
        "report.txt.vram9c00.bin",
    )
    special = (("report.txt.first_alias.png",) if kind == "alias" else (
        "report.txt.first_bad.png", "report.txt.recovered.png",
        "report.txt.hud.bin", "report.txt.window.bin",
    ))
    hashes: dict[str, str] = {}
    for relative in common + special:
        artifact = path / relative
        require(artifact.is_file() and artifact.stat().st_size > 0,
                f"missing {kind} artifact {relative}")
        hashes[relative] = sha256(artifact)
        if artifact.suffix == ".png":
            require(png_geometry(artifact) == (160, 144),
                    f"{kind} PNG is not an exact Game Boy frame")
    report = parse_report(report_path)
    thresholds = audit_control_report(report, kind)
    # Nonvacuity mutation: removing the one injected event must fail this
    # exact control contract rather than being accepted as a clean run.
    mutant = dict(report)
    mutant["map_alias_frames" if kind == "alias" else "bad_frames"] = "0"
    try:
        audit_control_report(mutant, kind)
    except AssertionError:
        mutation_rejected = True
    else:
        mutation_rejected = False
    require(mutation_rejected, f"{kind} nonvacuity mutation escaped")
    return {
        "path": str(path.relative_to(ROOT)),
        "report_sha256": expected_report_sha,
        "runtime_candidate_sha256": CANDIDATE_SHA,
        "thresholds": thresholds,
        "artifacts": hashes,
        "mutated_injection_nonvacuity_rejected": mutation_rejected,
    }


def mutation_controls(report: dict[str, str]) -> dict[str, bool]:
    changes = {
        "window_nonvacuity": ("window_frames", "0"),
        "bad_frame": ("bad_frames", "1"),
        "worst_mismatch": ("worst_mismatches", "1"),
        "map_alias": ("map_alias_frames", "1"),
        "close_liveness": ("window_frames_after_close", "1"),
        "final_FFE4": (
            "final_state", report["final_state"].replace("ffe4:00", "ffe4:01"),
        ),
        "final_Window": (
            "final_state", report["final_state"].replace("lcdc:8B", "lcdc:AB"),
        ),
        "first_visible_semantics": (
            "first_visible", report["first_visible"].replace(
                "mismatches:0", "mismatches:1"
            ),
        ),
    }
    controls: dict[str, bool] = {}
    for name, (key, value) in changes.items():
        mutant = dict(report)
        mutant[key] = value
        try:
            audit_report(mutant)
        except AssertionError:
            controls[f"mutated_{name}_rejected"] = True
        else:
            controls[f"mutated_{name}_rejected"] = False
    require(all(controls.values()), "Window receipt mutation escaped")
    return controls


def build_receipt(r1: Path, r2: Path, alias: Path, stale: Path) -> dict[str, Any]:
    identities = {
        "candidate": sha256(CANDIDATE),
        "equivalence_receipt": sha256(EQUIVALENCE),
        "live_verifier": sha256(VERIFIER),
        "live_probe": sha256(PROBE),
        "single_flight_launcher": sha256(LAUNCHER),
        "offline_verifier": sha256(SELF),
    }
    require(identities == {
        "candidate": CANDIDATE_SHA,
        "equivalence_receipt": EQUIVALENCE_SHA,
        "live_verifier": VERIFIER_SHA,
        "live_probe": PROBE_SHA,
        "single_flight_launcher": LAUNCHER_SHA,
        "offline_verifier": identities["offline_verifier"],
    }, "tool/candidate identity changed")
    runs = [audit_run(r1), audit_run(r2)]
    for name in ARTIFACTS:
        require(runs[0]["artifacts"][name]["sha256"]
                == runs[1]["artifacts"][name]["sha256"],
                f"duplicate artifact differs: {name}")
    require(runs[0]["report"] == runs[1]["report"],
            "parsed duplicate reports differ")
    controls = mutation_controls(runs[0]["report"])
    release_controls = {
        "forced_map_alias": audit_control(alias, "alias"),
        "stale_gameplay_window": audit_control(stale, "stale"),
    }
    return {
        "schema": "penta-stage7-r265-generic-window-receipt-v2",
        "status": "PASS",
        "promotable": False,
        "emulator_run_by_offline_verifier": False,
        "identities": identities,
        "invocation": {
            "command_shape": (
                "verify_menu_window_order.py a4c --frames 1400 "
                "--open-frame 1200 --close-frame 1320 --key select "
                "--move none --fire-every 0"
            ),
            "duplicate_sequential_runs": 2,
        },
        "runs": runs,
        "duplicate_artifacts_exact": list(ARTIFACTS),
        "mutation_controls": controls,
        "release_controls": release_controls,
        "decision": "GENERIC_STAGE1_WINDOW_AND_RECOVERY_CONTROLS_PASS",
        "remaining_before_integration": [
            "r265 ABI/visual/speed gates listed by equivalence receipt",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r1", type=Path, default=R1)
    parser.add_argument("--r2", type=Path, default=R2)
    parser.add_argument("--alias", type=Path, default=ALIAS)
    parser.add_argument("--stale", type=Path, default=STALE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = scratch(args.output)
    receipt = build_receipt(
        args.r1.resolve(), args.r2.resolve(), args.alias.resolve(),
        args.stale.resolve(),
    )
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload)
    print("PASS: duplicate r265 generic Window open/close receipts")
    print(f"Receipt: {output.relative_to(ROOT)}")
    print(f"Receipt SHA-256: {digest(payload.encode())}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
