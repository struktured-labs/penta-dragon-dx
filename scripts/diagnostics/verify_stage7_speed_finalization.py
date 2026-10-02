#!/usr/bin/env python3
"""Finalize r265 Stage 7's explicit speed compromise at a safe boundary.

This is an offline gate.  It binds the exact strict 2% r265 patrol receipt,
the r265 helper-equivalence context and short ABI receipt, two r265-only
2,800-frame ABI finalizer receipts, and the duplicate exact r265 Stage-7 visual
receipt.  The safe receipts must reproduce that r265 patrol's exact measured
throughput and route trace.  The strict target remains a visible failure; the separate
release policy accepts only the user's explicit 0.95 floor.  Any unmeasured
drain may finish only the helper already active at frame 2,800 and must reach
the admitted $12E0 return with FF55/VBK/SVBK/IE restored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ABI_VERIFIER = ROOT / "scripts/diagnostics/verify_stage7_dual_plane_abi.py"
SPEED_PROBE = ROOT / "scripts/diagnostics/probe_stage_speed.lua"
EXPECTED_CANDIDATE_SHA256 = (
    "a4c772624f16bc9ef23873726cbbafa169ee93869a95a17431367895273bd273"
)
EXPECTED_STATIC_RECEIPT_SHA256 = (
    "3bf962c18274ba8c5efe1e1ee9673ba19401dbebfc970782efed5e9e96673661"
)
EXPECTED_STRICT_RECEIPT_SHA256 = (
    "251dc27c817d4e042fd50d836aac9c5674524a784a474cb19df25bc3b8e28910"
)
EXPECTED_VISUAL_RECEIPT_SHA256 = (
    "af7316a81fae06fb22e484e9fbee02c63d377b2f20823a4239726b519b3315b0"
)
EXPECTED_HELPER_EQUIVALENCE_SHA256 = (
    "295ce612d6dc1dead72e776f44dafb3bd22b6bc0e44b101435b27d7ddafe0583"
)
EXPECTED_SHORT_ABI_RECEIPT_SHA256 = (
    "49561196551f825cb3f235b2081320ea59c133b7acb20e7cce0633f8a0859f90"
)
EXPECTED_SHORT_ABI_VERIFIER_SHA256 = (
    "f4815c5717a92a32eb47c898fa6aa56579acc8e75c66a9dd64c62babeebcf804"
)
EXPECTED_SPEED_PROBE_SHA256 = (
    "3b3643da1a42ba4d6d23ee161fc6914b3b655e308d39ec22042ce359ec68cdc6"
)
EXPECTED_ABI_VERIFIER_SHA256 = (
    "d94142e0e9876080dddcb119ce3b2b45c84278296eb6c4434184c96a562ef275"
)
STRICT_FLOOR = 0.98
RELEASE_FLOOR = 0.95
MEASUREMENT_FRAMES = 2800


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_bound(path: Path, expected_sha256: str, label: str) -> dict:
    require(path.is_file(), f"{label} is missing: {path}")
    observed = sha256(path)
    require(observed == expected_sha256,
            f"{label} SHA-256 {observed} != {expected_sha256}")
    value = json.loads(path.read_text())
    require(isinstance(value, dict), f"{label} is not a JSON object")
    return value


def classify_ratio(ratio: float) -> dict[str, bool]:
    strict_target_met = STRICT_FLOOR <= ratio <= 2.0 - STRICT_FLOOR
    release_compromise_accepted = (
        not strict_target_met and RELEASE_FLOOR <= ratio < 1.0
    )
    return {
        "strict_target_met": strict_target_met,
        "release_compromise_accepted": release_compromise_accepted,
    }


def policy_controls() -> dict[str, bool]:
    at_release = classify_ratio(RELEASE_FLOOR)
    below_release = classify_ratio(RELEASE_FLOOR - 0.0001)
    at_strict = classify_ratio(STRICT_FLOOR)
    fast_outlier = classify_ratio(1.021)
    return {
        "strict_target_remains_0_98": STRICT_FLOOR == 0.98,
        "release_floor_is_separate_0_95": RELEASE_FLOOR == 0.95,
        "release_floor_passes_only_as_compromise": (
            not at_release["strict_target_met"]
            and at_release["release_compromise_accepted"]
        ),
        "below_release_floor_rejected": not any(below_release.values()),
        "strict_floor_is_not_labeled_compromise": (
            at_strict["strict_target_met"]
            and not at_strict["release_compromise_accepted"]
        ),
        "speedup_outlier_rejected": not any(fast_outlier.values()),
    }


def validate_helper_equivalence(path: Path) -> dict:
    receipt = load_bound(
        path, EXPECTED_HELPER_EQUIVALENCE_SHA256,
        "r265 helper-equivalence receipt",
    )
    require(
        receipt.get("schema")
        == "penta-stage7-r265-helper-equivalence-static-v1"
        and receipt.get("status") == "STATIC_PASS_REBIND_WRAPPERS_REQUIRED"
        and receipt.get("promotable") is False
        and receipt.get("emulator_run") is False,
        "r265 helper-equivalence receipt overclaims or changed schema",
    )
    identities = receipt.get("identities", {})
    require(
        identities.get("e048_rom")
        == "e04801c8b8b0c1eb5ddaddce31a9581ad5c1fc83e3f1b043c581afa33df216a0"
        and identities.get("r265_rom") == EXPECTED_CANDIDATE_SHA256,
        "r265 helper-equivalence ROM identities changed",
    )
    protected = receipt.get("equivalence", {}).get("protected_spans", {})
    exact_spans = {
        "bank22_helper": (
            1459,
            "a309de635c97a80c2dc551b5046218e6163dcb96e00afcfb137724c73df17003",
        ),
        "bank22_immutable_LUT": (
            256,
            "cfb5fe66cecfb2887abd8f8e828d311265217831888713ddeb50d8b0f4a6a84a",
        ),
        "shared_copier_and_ABI_tail": (
            217,
            "e74bc3591a39bc07dd842dee9b0533605b316f2965e276296bf56345a7defb17",
        ),
    }
    for name, (length, digest) in exact_spans.items():
        span = protected.get(name, {})
        require(span.get("length") == length and span.get("sha256") == digest,
                f"r265 protected span changed: {name}")
    require(all(receipt.get("mutation_controls", {}).values()),
            "r265 helper-equivalence mutation controls failed")
    return {
        "path": str(path),
        "sha256": EXPECTED_HELPER_EQUIVALENCE_SHA256,
        "static_base_candidate": identities["e048_rom"],
        "r265_candidate": EXPECTED_CANDIDATE_SHA256,
        "protected_spans": sorted(exact_spans),
        "transfer_policy": (
            "static byte identity is context only; the direct r265 strict and "
            "safe runs must reproduce throughput/trace and prove the isolated "
            "Window helper has zero executions, or FFE4=0 at every exact entry"
        ),
    }


def validate_short_abi(path: Path) -> dict:
    """Bind the preserved r265 short ABI run without calling it current-tool."""

    receipt = load_bound(
        path, EXPECTED_SHORT_ABI_RECEIPT_SHA256,
        "r265 short ABI receipt",
    )
    require(
        receipt.get("schema") == "penta-stage7-dual-plane-abi-smoke-v1"
        and receipt.get("status") == "PASS",
        "r265 short ABI receipt is not PASS",
    )
    require(
        receipt.get("expected_candidate_sha256") == EXPECTED_CANDIDATE_SHA256
        and receipt.get("expected_static_receipt_sha256")
        == EXPECTED_STATIC_RECEIPT_SHA256,
        "r265 short ABI receipt targets another candidate/static contract",
    )
    before = receipt.get("identity_before", {})
    require(before == receipt.get("identity_after"),
            "r265 short ABI inputs changed during its run")
    require(
        before.get("probe_sha256") == EXPECTED_SPEED_PROBE_SHA256
        and before.get("verifier_sha256")
        == EXPECTED_SHORT_ABI_VERIFIER_SHA256,
        "r265 short ABI historical tool identity changed",
    )
    observed = receipt.get("observed", {})
    fallbacks = observed.get("fallbacks", {})
    require(
        observed.get("frames") == 300
        and observed.get("entries") == 45
        and observed.get("admitted_entries") == 45
        and observed.get("exits") == 45
        and observed.get("phase_hits") == {"0x7108": 45, "0x714B": 45}
        and fallbacks.get("native") == 0
        and fallbacks.get("caller_reject") == 0
        and fallbacks.get("after_atomic") == 0
        and observed.get("timer_isr_pairs") == 61
        and observed.get("timer_source_changes") == 0
        and observed.get("timer_bank_state_changes") == 0
        and observed.get("dma_site_hits")
        == {"0x713D": 45, "0x7187": 1080},
        "r265 short ABI exact live counters changed",
    )
    raw_path, raw = raw_result(receipt, path)
    require(
        raw.get("ffe4_zero_play_frames") == 300
        and raw.get("ffe4_nonzero_play_frames") == 0
        and raw.get("window_helper_hits") == 0
        and raw.get("window_helper_ffe4_nonzero_hits") == 0,
        "r265 short ABI no-Window execution evidence changed",
    )
    return {
        "path": str(path),
        "sha256": EXPECTED_SHORT_ABI_RECEIPT_SHA256,
        "raw_result": str(raw_path),
        "raw_result_sha256": receipt["raw_result_sha256"],
        "probe_sha256": before["probe_sha256"],
        "historical_verifier_sha256": before["verifier_sha256"],
        "classification": (
            "preserved short live ABI evidence; current-tool evidence is "
            "provided separately by both safe-boundary runs"
        ),
    }


def raw_result(receipt: dict, receipt_path: Path) -> tuple[Path, dict]:
    raw_text = receipt.get("raw_result")
    require(isinstance(raw_text, str) and raw_text,
            f"ABI receipt lacks raw_result: {receipt_path}")
    raw_path = Path(raw_text)
    if not raw_path.is_absolute():
        raw_path = (receipt_path.parent / raw_path).resolve()
    require(raw_path.is_file(), f"ABI raw result is missing: {raw_path}")
    require(sha256(raw_path) == receipt.get("raw_result_sha256"),
            f"ABI raw-result SHA changed: {raw_path}")
    value = json.loads(raw_path.read_text())
    require(isinstance(value, dict), f"ABI raw result is invalid: {raw_path}")
    return raw_path, value


def validate_abi_receipt(
    receipt: dict,
    receipt_path: Path,
    *,
    candidate_sha256: str,
    static_receipt_sha256: str,
    strict_dx: dict,
) -> tuple[dict, dict]:
    require(receipt.get("schema") == "penta-stage7-dual-plane-abi-smoke-v1",
            f"wrong ABI schema: {receipt_path}")
    require(receipt.get("status") == "PASS",
            f"ABI finalizer did not pass: {receipt_path}")
    require(receipt.get("expected_candidate_sha256") == candidate_sha256,
            f"ABI finalizer targets another ROM: {receipt_path}")
    require(
        receipt.get("expected_static_receipt_sha256")
        == static_receipt_sha256,
        f"ABI finalizer targets another static receipt: {receipt_path}",
    )
    before = receipt.get("identity_before", {})
    after = receipt.get("identity_after", {})
    require(before == after, f"ABI inputs changed during run: {receipt_path}")
    require(before.get("candidate_sha256") == candidate_sha256,
            f"ABI candidate identity mismatch: {receipt_path}")
    require(before.get("static_receipt_sha256") == static_receipt_sha256,
            f"ABI static identity mismatch: {receipt_path}")

    contract = receipt.get("contract", {})
    boundary_spec = contract.get("safe_boundary_drain", {})
    require(boundary_spec == {
        "enabled": True,
        "measurement_frames": MEASUREMENT_FRAMES,
        "maximum_unmeasured_drain_frames": 120,
        "admitted_outer_return": "fixed:$12E0",
        "measurement_counters_frozen_during_drain": True,
    }, f"wrong safe-boundary ABI contract: {receipt_path}")
    require(contract.get("outer_returns") == ["fixed:$0AB8", "fixed:$12E0"],
            f"ABI caller census changed: {receipt_path}")
    require(contract.get("dma_commands") == ["bank22:$713D", "bank22:$7187"],
            f"ABI DMA sites changed: {receipt_path}")

    controls = receipt.get("safe_boundary_policy_controls", {})
    require(isinstance(controls, dict) and controls and all(controls.values()),
            f"safe-boundary mutation controls failed: {receipt_path}")
    observed = receipt.get("observed", {})
    ffe4_contract = observed.get("FFE4_transfer", {})
    require(ffe4_contract.get("passed") is True
            and all(ffe4_contract.get("checks", {}).values()),
            f"r265 Window execution-equivalence contract failed: {receipt_path}")
    ffe4_controls = receipt.get("FFE4_transfer_policy_controls", {})
    require(isinstance(ffe4_controls, dict) and ffe4_controls
            and all(ffe4_controls.values()),
            f"r265 Window execution-equivalence controls failed: {receipt_path}")
    fallbacks = observed.get("fallbacks", {})
    require(isinstance(fallbacks.get("native"), int)
            and fallbacks.get("native") > 0,
            f"long patrol did not cover native guard fallback: {receipt_path}")
    require(observed.get("native_fallback_exits") == fallbacks.get("native")
            and observed.get("fast_exits")
            == observed.get("entries", 0) - fallbacks.get("native", 0),
            f"fast/native exits are not exactly classified: {receipt_path}")
    boundary = observed.get("safe_boundary", {})
    require(boundary.get("passed") is True,
            f"safe-boundary live contract failed: {receipt_path}")
    checks = boundary.get("checks", {})
    require(isinstance(checks, dict) and checks and all(checks.values()),
            f"safe-boundary live checks failed: {receipt_path}")
    require(boundary.get("drain_required") is True,
            "the deterministic frame-2800 active-DMA cutoff was not reproduced")
    require(boundary.get("status") == "completed",
            f"active helper did not reach its exact boundary: {receipt_path}")

    raw_path, raw = raw_result(receipt, receipt_path)
    require(raw.get("frames") == MEASUREMENT_FRAMES,
            f"unmeasured drain changed frame count: {receipt_path}")
    ffe4_counts = tuple(raw.get(name) for name in (
        "ffe4_zero_play_frames", "ffe4_nonzero_play_frames",
        "window_helper_hits", "window_helper_ffe4_nonzero_hits",
        "safe_boundary_drain_ffe4_nonzero_frames",
    ))
    require(all(isinstance(value, int) and not isinstance(value, bool)
                for value in ffe4_counts),
            f"r265 Window execution telemetry is not integer: {receipt_path}")
    zero_frames, nonzero_frames, helper_hits, helper_nonzero, drain_nonzero = (
        ffe4_counts
    )
    require(zero_frames >= 0 and nonzero_frames >= 0
            and zero_frames + nonzero_frames == MEASUREMENT_FRAMES,
            f"r265 FFE4 callback accounting is incomplete: {receipt_path}")
    require(helper_hits >= 0 and helper_nonzero == 0
            and helper_nonzero <= helper_hits and drain_nonzero >= 0,
            f"r265 changed Window helper ran with nonzero FFE4: {receipt_path}")
    require(raw.get("main_loop_hits") == strict_dx.get("main_loop_hits"),
            f"safe run changed fixed-window throughput: {receipt_path}")
    require(raw.get("attr_dma_commands") == strict_dx.get("attr_dma_commands"),
            f"safe run changed fixed-window DMA count: {receipt_path}")
    require(raw.get("attr_hblank_commands") == strict_dx.get(
        "attr_hblank_commands"
    ), f"safe run changed fixed-window HBlank count: {receipt_path}")
    require(raw.get("attr_gdma_commands") == 0,
            f"safe run observed GDMA: {receipt_path}")
    require(receipt.get("attr_trace_sha256") == strict_dx.get(
        "attr_events_sha256"
    ), f"safe run changed the measured route trace: {receipt_path}")
    require(raw.get("safe_boundary_start_ff55") == strict_dx.get(
        "final_hdma5"
    ), f"safe run did not reproduce terminal FF55: {receipt_path}")
    require(raw.get("safe_boundary_start_vbk")
            == (strict_dx.get("final_vbk", 0xFF) & 1),
            f"safe run did not reproduce terminal VBK: {receipt_path}")
    require(raw.get("safe_boundary_start_svbk")
            == (strict_dx.get("final_svbk", 0xFF) & 7),
            f"safe run did not reproduce terminal SVBK: {receipt_path}")
    require(raw.get("safe_boundary_start_ie") == strict_dx.get("final_ie"),
            f"safe run did not reproduce terminal IE: {receipt_path}")
    require(raw.get("safe_boundary_extra_entries") == 0,
            f"safe run admitted a new helper after cutoff: {receipt_path}")
    require(raw.get("safe_boundary_drain_fallback_hits") == 0,
            f"safe run entered native fallback during drain: {receipt_path}")
    require(raw.get("safe_boundary_last_outer_return") == 0x12E0,
            f"safe run completed through wrong publisher: {receipt_path}")
    require(raw.get("final_cpu_pc") == 0x12E0,
            f"safe run did not stop at exact $12E0 boundary: {receipt_path}")
    require(raw.get("final_hdma5") == 0xFF
            and raw.get("final_vbk", 0xFF) & 1 == 0
            and raw.get("final_svbk", 0xFF) & 7 == 1
            and raw.get("final_ie") == 7,
            f"safe run did not restore hardware state: {receipt_path}")
    return raw, {
        "receipt": str(receipt_path),
        "receipt_sha256": sha256(receipt_path),
        "raw_result": str(raw_path),
        "raw_result_sha256": sha256(raw_path),
        "probe_sha256": before.get("probe_sha256"),
        "abi_verifier_sha256": before.get("verifier_sha256"),
        "launcher_sha256": before.get("launcher_sha256"),
        "drain_frames": boundary.get("drain_frames"),
        "window_execution_equivalence": {
            "callback_context_zero_frames": zero_frames,
            "callback_context_nonzero_frames": nonzero_frames,
            "window_helper_entries": helper_hits,
            "window_helper_nonzero_FFE4_entries": helper_nonzero,
            "safe_drain_nonzero_FFE4_callbacks": drain_nonzero,
        },
        "boundary": boundary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--static-receipt", type=Path, required=True)
    parser.add_argument("--strict-receipt", type=Path, required=True)
    parser.add_argument("--visual-receipt", type=Path, required=True)
    parser.add_argument(
        "--helper-equivalence-receipt", type=Path, required=True,
    )
    parser.add_argument("--short-abi-receipt", type=Path, required=True)
    parser.add_argument("--abi-receipt", type=Path, action="append", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    require(len(args.abi_receipt) == 2,
            "exactly two independent safe-boundary ABI receipts are required")

    candidate = args.candidate.resolve()
    static_path = args.static_receipt.resolve()
    strict_path = args.strict_receipt.resolve()
    visual_path = args.visual_receipt.resolve()
    equivalence_path = args.helper_equivalence_receipt.resolve()
    short_abi_path = args.short_abi_receipt.resolve()
    abi_paths = [path.resolve() for path in args.abi_receipt]
    output = args.receipt.resolve()
    require(len(set(abi_paths)) == 2,
            "safe-boundary ABI receipt paths must be distinct")
    allowed_scratch = [ROOT / "tmp", Path("/mnt/data/tmp")]
    require(any(output != root.resolve()
                and output.is_relative_to(root.resolve())
                for root in allowed_scratch if root.exists()),
            "output must be below repository tmp/ or /mnt/data/tmp/")
    require(candidate.is_file(), f"candidate is missing: {candidate}")
    initial_identity = {
        "candidate_sha256": sha256(candidate),
        "static_receipt_sha256": sha256(static_path),
        "strict_speed_receipt_sha256": sha256(strict_path),
        "exact_visual_receipt_sha256": sha256(visual_path),
        "helper_equivalence_receipt_sha256": sha256(equivalence_path),
        "short_abi_receipt_sha256": sha256(short_abi_path),
        "abi_verifier_sha256": sha256(ABI_VERIFIER),
        "speed_probe_sha256": sha256(SPEED_PROBE),
        "finalizer_sha256": sha256(Path(__file__).resolve()),
    }
    candidate_sha = sha256(candidate)
    require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
            f"candidate SHA-256 {candidate_sha} is not frozen r265")
    require(sha256(static_path) == EXPECTED_STATIC_RECEIPT_SHA256,
            "static receipt is not frozen r265 transfer 3bf962")
    require(sha256(ABI_VERIFIER) == EXPECTED_ABI_VERIFIER_SHA256,
            "safe-boundary ABI verifier is not frozen d94142")
    require(sha256(SPEED_PROBE) == EXPECTED_SPEED_PROBE_SHA256,
            "safe-boundary speed probe is not frozen 3b3643")

    equivalence = validate_helper_equivalence(equivalence_path)
    short_abi = validate_short_abi(short_abi_path)

    strict = load_bound(
        strict_path, EXPECTED_STRICT_RECEIPT_SHA256, "strict speed receipt"
    )
    require(strict.get("schema") == "penta-stage-speed-matrix-v2",
            "wrong strict speed schema")
    require(strict.get("status") == "fail",
            "strict receipt must retain the honest 2% failure")
    require(strict.get("mode") == "patrol"
            and strict.get("frames") == MEASUREMENT_FRAMES,
            "strict receipt is not the 2,800-frame patrol")
    require(strict.get("target_ratio_floor") == STRICT_FLOOR
            and strict.get("target_ratio_ceiling") == 1.02,
            "strict receipt no longer encodes the 2% target")
    require(strict.get("accepted_slowdown_floor") is None
            and strict.get("accepted_slow_stages") == {},
            "strict receipt improperly embeds a compromise")
    require(strict.get("dx_rom_sha256") == candidate_sha,
            "strict receipt is not the frozen r265 measurement")
    require(all(strict.get("input_identity_controls", {}).values()),
            "strict capture inputs changed during its run")
    rows = strict.get("rows", [])
    require(isinstance(rows, list) and len(rows) == 1,
            "strict receipt must contain Stage 7 only")
    row = rows[0]
    original = row.get("original", {})
    dx = row.get("dx", {})
    ratio = dx.get("main_loop_hits", 0) / original.get("main_loop_hits", 1)
    require(abs(ratio - row.get("ratio_exact", -1)) < 1e-15,
            "strict ratio is not recomputable from exact hit counts")
    classification = classify_ratio(ratio)
    require(not classification["strict_target_met"]
            and classification["release_compromise_accepted"],
            "measured ratio is outside the explicit 0.95 release compromise")
    require(row.get("target_met") is False
            and row.get("throughput_accepted") is False,
            "strict receipt hid its target miss")
    require(row.get("deterministic_replay") is True,
            "strict speed patrol was not deterministic")
    require(row.get("candidate_scene_ok") is True
            and row.get("candidate_non_dma_scene_mismatch_frames") == 0,
            "strict patrol escaped Stage 7")
    require(row.get("baseline_continuity_ok") is True
            and row.get("candidate_continuity_ok") is True,
            "strict patrol lost main-loop continuity")
    require(row.get("central_output_telemetry_ok") is True,
            "strict patrol lost gameplay output telemetry")
    dma_checks = row.get("candidate_dma_command_contract", {}).get("checks", {})
    require(dma_checks.get("dma_idle_at_finish") is False,
            "strict receipt no longer reproduces the arbitrary active cutoff")
    require(all(value for key, value in dma_checks.items()
                if key != "dma_idle_at_finish"),
            "strict patrol has a DMA defect beyond its arbitrary cutoff")
    require(row.get("route_coverage_ok") is False,
            "strict fixed-time route mismatch unexpectedly disappeared")

    visual = load_bound(
        visual_path, EXPECTED_VISUAL_RECEIPT_SHA256, "exact visual receipt"
    )
    require(visual.get("status") == "PASS_EXACT_VISUAL_RECEIPTS",
            "exact Stage-7 visual receipt did not pass")
    require(visual.get("candidate_sha256") == candidate_sha,
            "visual receipt targets another candidate")
    rejection = visual.get("static_rejection_contract", {})
    require(rejection.get("sha256") == EXPECTED_STATIC_RECEIPT_SHA256,
            "visual receipt targets another static contract")
    require(visual.get("deterministic_artifacts_and_gbas_payloads") is True,
            "visual receipt was not deterministic")
    require(len(visual.get("runs", [])) == 2,
            "visual receipt does not contain duplicate runs")
    require(all(run.get("active_visible_write_trails") == 0
                for run in visual.get("runs", [])),
            "visual receipt contains a semantic write trail")

    abi_evidence = []
    raw_results = []
    for path in abi_paths:
        receipt = json.loads(path.read_text())
        raw, evidence = validate_abi_receipt(
            receipt,
            path,
            candidate_sha256=candidate_sha,
            static_receipt_sha256=EXPECTED_STATIC_RECEIPT_SHA256,
            strict_dx=dx,
        )
        raw_results.append(raw)
        abi_evidence.append(evidence)
    require(raw_results[0] == raw_results[1],
            "duplicate safe-boundary raw receipts are not byte-semantic equal")
    require(abi_evidence[0]["probe_sha256"] == abi_evidence[1]["probe_sha256"],
            "safe-boundary probes differ")
    require(
        abi_evidence[0]["abi_verifier_sha256"]
        == abi_evidence[1]["abi_verifier_sha256"],
        "safe-boundary ABI verifiers differ",
    )
    require(abi_evidence[0]["probe_sha256"]
            == initial_identity["speed_probe_sha256"],
            "safe-boundary receipt probe is not the current checked-in probe")
    require(abi_evidence[0]["abi_verifier_sha256"]
            == initial_identity["abi_verifier_sha256"],
            "safe-boundary receipt verifier is not the current verifier")

    controls = policy_controls()
    require(all(controls.values()), "internal release-speed policy controls failed")
    receipt = {
        "schema": "penta-stage7-r265-speed-safe-finalization-v2",
        "status": "PASS_EXPLICIT_RELEASE_COMPROMISE",
        "promotable_by_itself": False,
        "candidate": str(candidate),
        "candidate_sha256": candidate_sha,
        "static_receipt": str(static_path),
        "static_receipt_sha256": EXPECTED_STATIC_RECEIPT_SHA256,
        "strict_speed_receipt": str(strict_path),
        "strict_speed_receipt_sha256": EXPECTED_STRICT_RECEIPT_SHA256,
        "strict_speed_candidate_sha256": candidate_sha,
        "exact_visual_receipt": str(visual_path),
        "exact_visual_receipt_sha256": EXPECTED_VISUAL_RECEIPT_SHA256,
        "helper_equivalence": equivalence,
        "short_abi": short_abi,
        "input_identity_before": initial_identity,
        "measurement": {
            "frames": MEASUREMENT_FRAMES,
            "original_main_loop_hits": original["main_loop_hits"],
            "dx_main_loop_hits": dx["main_loop_hits"],
            "ratio_exact": ratio,
            "ratio_display": round(ratio, 4),
            "strict_target_floor": STRICT_FLOOR,
            "strict_target_met": False,
            "operator_release_floor": RELEASE_FLOOR,
            "release_compromise_accepted": True,
            "strict_route_parity": "FAIL_RETAINED",
            "route_note": (
            "Fixed host time gives the 3.84% slower build fewer route "
                "iterations; the direct r265 patrol is preserved and exact "
                "dual-map visual coverage is bound separately."
            ),
        },
        "safe_boundary": {
            "measurement_counters_frozen_at_frame": MEASUREMENT_FRAMES,
            "duplicate_receipts_semantic_equal": True,
            "new_helper_entries_after_measurement": 0,
            "completion_outer_return": "fixed:$12E0",
            "final": {"FF55": "FF", "VBK": 0, "SVBK": 1, "IE": 7},
            "runs": abi_evidence,
        },
        "policy_controls": controls,
        "covered": [
            "strict 2% target miss remains explicit",
            "separate operator-approved 0.95 release floor",
            "r265 fixed 2,800-frame throughput and route trace reproduced twice",
            "r265 short ABI 495611 is preserved as historical live evidence",
            "both safe runs use the current frozen ABI verifier and speed probe",
            "isolated r265 Window helper has zero executions, or FFE4=0 at every exact entry",
            "arbitrary active-DMA cutoff reproduced twice",
            "only the already-active helper drains to exact $12E0",
            "FF55/VBK/SVBK/IE restored with zero extra helper entries",
            "duplicate full-plane visual receipt bound for Stage-7 route output",
        ],
        "not_covered": [
            "the strict 0.98 throughput target (still failed at 0.9616)",
            "menu and Crystal scene containment (separate gates)",
        ],
    }
    final_identity = {
        "candidate_sha256": sha256(candidate),
        "static_receipt_sha256": sha256(static_path),
        "strict_speed_receipt_sha256": sha256(strict_path),
        "exact_visual_receipt_sha256": sha256(visual_path),
        "helper_equivalence_receipt_sha256": sha256(equivalence_path),
        "short_abi_receipt_sha256": sha256(short_abi_path),
        "abi_verifier_sha256": sha256(ABI_VERIFIER),
        "speed_probe_sha256": sha256(SPEED_PROBE),
        "finalizer_sha256": sha256(Path(__file__).resolve()),
    }
    require(final_identity == initial_identity,
            "a finalization input changed during offline verification")
    receipt["input_identity_after"] = final_identity
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
