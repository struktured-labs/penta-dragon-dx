#!/usr/bin/env python3
"""Replay the exact r120 -> r534 lineage from maintained generators.

This is an experimental source-closure audit, not the production builder:
The earliest start requires retained r120, twenty-eight authentic historical
evidence files, and the original cartridge. r210/r264 need twenty-two files;
r199 also needs twenty-eight; r273 needs twenty; r287 needs five.
r314 requires its static receipt and
the cartridge; r343/r442 remain single-ROM starting points.
No saved intermediate artifact is consumed. Success confers no live or
hardware qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]

import build_later_stage_deferred_dma_r443 as dma
import build_reload_flag_dealias_r443e as reload
import build_title_nightfall_port as title
import compose_stage1_wide_copy_r445 as wide
import compose_d82_later_stage_copy_recovery_r453 as recovery
import compose_boss_sync_dma_r454 as boss_dma
import compose_arena_palette_storage_r455 as arena
import compose_attract_blank_r456d as attract
import compose_boss_stage7_r475 as combined
import compose_stage4_cache_key_r534 as final
import r534_lineage_prefix as prefix
import r534_lineage_ancestry as ancestry
import r534_stage4_ancestry as stage4
import r534_stage7_ancestry as stage7
import r534_stage2_ancestry as stage2
import r534_stage1_phase_ancestry as phase

BASE_SHA256 = "ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46"
CANDIDATE_SHA256 = "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b"
STEPS = (
    ("r443f", "074f6ae494c2d478fa6be3630cf635b24a8dff1236b4d734cc6122b93b0342a6",
     lambda source: dma.build(source, isr_pretest_on=True)),
    ("r443e3f2", "950cddda3179c020536aea8b0427ee3efa0abab86475b6b0b7f93ed10cc25e5a",
     lambda source: reload.build(source, reload.CAVE_TEST_F, reload.CAVE_SET_F,
                                 base_sha=STEPS[0][1])),
    ("nightfall-v6", "20db07d52dbfdfd760dd3270dd8280cbe5bd882fddc70e2fdf24cede822f7127",
     lambda source: title.build(source, code_bank=25, apply_fix_a=False,
                                isr_merge=True, merge_head="v6")),
    ("r449f-helper", recovery.BASE_SHA,
     lambda source: wide.build(source, class_gate=True, ei_gap=True, fused=True)),
    ("r453", boss_dma.BASE_SHA, recovery.build),
    ("r454", arena.BASE_SHA, boss_dma.build),
    ("r455", attract.BASE_SHA, arena.build),
    ("r456d", combined.BASE_SHA256, attract.build),
    ("r475", "59384e3c0ea5508ade2ff8d08af2f3012c4eff1f5f9cf1cebb2f04273cd1693f",
     combined.build),
    ("r534", CANDIDATE_SHA256, final.build),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(source: bytes, *, base_receipt: bytes | None = None,
          original_rom: bytes | None = None,
          historical_evidence: dict[str, bytes] | None = None) -> tuple[bytes, dict]:
    """Build in memory, failing on any input, output, size, or receipt drift."""
    input_sha = digest(source)
    components = []
    early_steps = []
    early_starts = {phase.EARLY_BASE_SHA256: "r120", phase.BASE_SHA256: "r199",
                    stage2.BASE_SHA256: "r210", stage7.BASE_SHA256: "r264",
                    stage4.BASE_SHA256: "r273", ancestry.BASE_SHA256: "r287"}
    if input_sha not in early_starts and historical_evidence is not None:
        raise ValueError("historical evidence is consumed only by the r120/r199/r210/r264/r273/r287 replay")
    if input_sha in early_starts:
        input_name = early_starts[input_sha]
        if base_receipt is not None:
            raise ValueError(f"{input_name} replay generates its own static build receipts")
        if original_rom is None or digest(original_rom) != prefix.ORIGINAL_SHA256:
            raise ValueError(f"{input_name} requires the exact original cartridge")
        evidence = historical_evidence or {}
        if input_name in ("r120", "r199", "r210", "r264", "r273"):
            required = set(stage4.HISTORICAL_INPUTS) | set(ancestry.HISTORICAL_INPUTS)
            if input_name in ("r120", "r199", "r210", "r264"):
                required |= set(stage7.HISTORICAL_INPUTS)
            if input_name in ("r120", "r199"):
                required |= set(phase.HISTORICAL_INPUTS)
            if set(evidence) != required:
                count = "twenty" if input_name == "r273" else "twenty-two"
                if input_name in ("r120", "r199"):
                    count = "twenty-eight"
                raise ValueError(f"{input_name} requires exactly the {count} historical evidence inputs")
            if input_name in ("r120", "r199"):
                source, early_steps = phase.build(source, {name: evidence[name] for name in phase.HISTORICAL_INPUTS})
            if input_name in ("r120", "r199", "r210"):
                source, stage2_steps = stage2.build(source)
                early_steps.extend(stage2_steps)
            if input_name in ("r120", "r199", "r210", "r264"):
                source, stage7_steps = stage7.build(
                    source, {name: evidence[name] for name in stage7.HISTORICAL_INPUTS},
                    base_is_generated=input_name in ("r120", "r199", "r210"))
                early_steps.extend(stage7_steps)
            source, stage4_steps = stage4.build(source, {name: evidence[name] for name in stage4.HISTORICAL_INPUTS})
            early_steps.extend(stage4_steps)
            evidence = {name: evidence[name] for name in ancestry.HISTORICAL_INPUTS}
        r314, r314_receipt, steps, components = ancestry.build(source, evidence)
        steps = early_steps + steps
        result, following = prefix.build(r314, base_receipt=r314_receipt,
                                          original_rom=original_rom)
        steps.extend(following)
    elif input_sha in (prefix.EARLY_BASE_SHA256, prefix.BASE_SHA256):
        result, steps = prefix.build(source, base_receipt=base_receipt,
                                     original_rom=original_rom)
        input_name = "r314" if input_sha == prefix.EARLY_BASE_SHA256 else "r343"
    elif input_sha == BASE_SHA256:
        if base_receipt is not None or original_rom is not None:
            raise ValueError("r442 replay does not consume extra input artifacts")
        result, steps = source, []
        input_name = "r442"
    else:
        raise ValueError("requires exact retained r120, r199, r210, r264, r273, r287, r314, r343, or r442 input")
    for name, expected, compose in STEPS:
        previous = result
        output = compose(previous)
        metadata = None
        if isinstance(output, tuple):
            result, metadata = output
        else:
            result = output
        if not isinstance(result, bytes) or len(result) != len(source):
            raise ValueError(f"{name}: output type or size changed")
        if digest(result) != expected:
            raise ValueError(f"{name}: output hash differs from pinned lineage")
        if isinstance(metadata, dict):
            for key, actual in (("base_sha256", digest(previous)),
                                ("candidate_sha256", expected)):
                if key in metadata and metadata[key] != actual:
                    raise ValueError(f"{name}: receipt {key} differs from actual bytes")
        offsets = [i for i, (a, b) in enumerate(zip(previous, result)) if a != b]
        steps.append({
            "name": name, "base_sha256": digest(previous),
            "candidate_sha256": expected,
            "changed_bytes": len(offsets),
            "changed_banks_excluding_checksums": sorted({
                i // 0x4000 for i in offsets if i not in (0x14D, 0x14E, 0x14F)
            }),
        })
    if digest(result) != CANDIDATE_SHA256:
        raise ValueError("lineage did not reproduce exact r534")
    return result, {
        "schema": "penta-r534-source-lineage-v9",
        "experimental": True, "promotable": False,
        "base_sha256": input_sha, "candidate_sha256": digest(result),
        "retained_input": f"{input_name} (not original cartridge)",
        "intermediate_artifacts_read": False,
        "base_receipt_sha256": digest(base_receipt) if base_receipt is not None else None,
        "original_rom_sha256": digest(original_rom) if original_rom is not None else None,
        "historical_evidence": {
            name: {"sha256": digest(payload), "fresh_live_qualification": False}
            for name, payload in (historical_evidence or {}).items()
        },
        "component_builds": components,
        "steps": steps,
    }


def historical_paths(payload: str, explicit: dict[str, Path]) -> dict[str, Path]:
    """Decode a name-to-path bundle; relative bundle paths are repository-relative."""
    def unique(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError(f"duplicate historical input: {name}")
            result[name] = value
        return result

    entries = json.loads(payload, object_pairs_hook=unique)
    if not isinstance(entries, dict):
        raise ValueError("historical input manifest must be a name-to-path object")
    allowed = (set(phase.HISTORICAL_INPUTS) | set(stage7.HISTORICAL_INPUTS)
               | set(stage4.HISTORICAL_INPUTS) | set(ancestry.HISTORICAL_INPUTS))
    if set(entries) - allowed or set(explicit) - allowed:
        raise ValueError("unknown historical input name")
    if set(entries) & set(explicit):
        raise ValueError("duplicate historical input in manifest and command line")
    result = dict(explicit)
    for name, path in entries.items():
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"{name}: historical input path must be a nonempty string")
        result[name] = ROOT / path
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True,
                        help="exact retained r120, r199, r210, r264, r273, r287, r314, r343, or r442 ROM")
    parser.add_argument("--base-receipt", type=Path,
                        help="required for r314 only: its pinned static build receipt")
    parser.add_argument("--original-rom", type=Path,
                        help="required for r120/r199/r210/r264/r273/r287/r314: the original cartridge ROM")
    parser.add_argument("--historical-input-manifest", type=Path,
                        help="JSON name-to-path object; relative paths resolve against the repository")
    for name in ancestry.HISTORICAL_INPUTS:
        option = name if name == "room01_capture" else name + "_receipt"
        parser.add_argument("--" + option.replace("_", "-"), dest=name, type=Path,
                            help=f"r120/r199/r210/r264/r273/r287 historical {name} input, unless supplied in the manifest")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    source = args.base.read_bytes()
    explicit_paths = {
        name: getattr(args, name) for name in ancestry.HISTORICAL_INPUTS
        if getattr(args, name) is not None
    }
    manifest_bytes = args.historical_input_manifest.read_bytes() if args.historical_input_manifest else b"{}"
    paths = historical_paths(manifest_bytes.decode(), explicit_paths)
    inputs = {
        "base_receipt": args.base_receipt.read_bytes() if args.base_receipt else None,
        "original_rom": args.original_rom.read_bytes() if args.original_rom else None,
        "historical_evidence": ({name: path.read_bytes() for name, path in paths.items()}
                                if paths else None),
    }
    result, receipt = build(source, **inputs)
    again, second = build(source, **inputs)
    if result != again or receipt != second:
        raise ValueError("lineage double build was not deterministic")
    from suite_contract import source_snapshot
    fingerprint, sources = source_snapshot()
    receipt.update({
        "base_path": str(args.base.resolve()), "double_build_identical": True,
        "source_fingerprint": fingerprint, "source_files": sources,
        "base_receipt_path": str(args.base_receipt.resolve()) if args.base_receipt else None,
        "original_rom_path": str(args.original_rom.resolve()) if args.original_rom else None,
        "historical_input_manifest": {
            "path": str(args.historical_input_manifest.resolve()), "sha256": digest(manifest_bytes),
        } if args.historical_input_manifest else None,
    })
    for name, path in paths.items():
        receipt["historical_evidence"][name]["path"] = str(path.resolve())
    args.out_dir.mkdir(parents=True, exist_ok=True)
    target = args.out_dir / "candidate.gb"
    receipt_path = args.out_dir / "build-receipt.json"
    if target.exists() or receipt_path.exists():
        raise ValueError("use a fresh output directory; lineage artifacts are immutable")
    target.write_bytes(result)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"candidate_sha256": digest(result), "steps": len(receipt["steps"]),
                      "component_builds": len(receipt["component_builds"]),
                      "double_build_identical": True, "promotable": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
