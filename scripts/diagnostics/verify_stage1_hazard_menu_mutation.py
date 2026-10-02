#!/usr/bin/env python3
"""Prove the Stage-1 menu gate catches gray spike teeth after menu close."""

# PENTA_CHECKED_SINGLEFLIGHT_DELEGATION: live_receipt receives DEFAULT_MGBA
# from verify_stage1_spike_palettes, which is the checked-in guarded wrapper.

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from stage1_hazard_semantic_row import (
    HELPER_BANK as SEMANTIC_BANK,
    LUT_ADDR as SEMANTIC_LUT_ADDR,
    TOOTH_TILES,
    bank_offset,
)
from verify_stage1_hazard_menu import replay_is_clean, stable_summary
from verify_stage1_spike_palettes import (
    CEILING_LIVE_STATE,
    DEFAULT_MGBA,
    STATE_DIR,
    live_receipt,
)


GOLD_TOOTH_ATTR = 0x0F
GRAY_TOOTH_ATTR = 0x07


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_pair(
    rom: Path,
    output: Path,
    state: Path,
    timeout: float,
) -> tuple[list[dict], list[dict]]:
    raw = []
    summaries = []
    for replay_index in (1, 2):
        receipt = live_receipt(
            rom,
            state,
            DEFAULT_MGBA.resolve(),
            output / f"replay-{replay_index}",
            timeout,
            prefix_name="hazard-menu-mutation",
            reinitialize=False,
            settle=520,
            input_mask=0,
            screenshot_interval=5,
            expected_room=0x02,
            normalization_writes=((0xD880, 0x02),),
            normalization_bank=1,
            menu_open=True,
            # Phase 160 is the smallest deterministic witness for the old
            # DF58 typo. Nearby phases 160-163 also fail in the full matrix;
            # 158-159 happen to republish before the stale plane is exposed.
            menu_open_frame=160,
            menu_close_frame=320,
            trace_routes=False,
        )
        receipt["final_screenshot_sha256"] = hashlib.sha256(
            Path(receipt["screenshot"]).read_bytes()
        ).hexdigest()
        raw.append(receipt)
        summaries.append(stable_summary(receipt))
    return raw, summaries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--states", type=Path, default=STATE_DIR)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    source = args.rom.resolve().read_bytes()
    lut_offset = bank_offset(SEMANTIC_BANK, SEMANTIC_LUT_ADDR)
    tooth_offsets = tuple(lut_offset + tile for tile in sorted(TOOTH_TILES))
    wrong_preimages = [
        offset for offset in tooth_offsets if source[offset] != GOLD_TOOTH_ATTR
    ]
    if wrong_preimages:
        raise SystemExit(
            "FAIL: input ROM does not contain gold bank-1 attributes at every "
            "semantic spike-tooth LUT entry: "
            + ", ".join(f"0x{offset:05X}" for offset in wrong_preimages)
        )

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    mutant = bytearray(source)
    for offset in tooth_offsets:
        mutant[offset] = GRAY_TOOTH_ATTR
    mutant_path = output / "candidate-with-gray-spike-teeth.gb"
    mutant_path.write_bytes(mutant)

    state = (args.states / CEILING_LIVE_STATE).resolve()
    clean_raw, clean = run_pair(
        args.rom.resolve(), output / "clean", state, args.timeout
    )
    mutant_raw, mutated = run_pair(
        mutant_path, output / "mutated", state, args.timeout
    )
    mutant_has_visible_residue = all(
        receipt["post_menu_transient_mismatch_frames"] > 0
        or receipt["post_menu_endpoint_mismatch_frames"] > 0
        or receipt["post_menu_palette_mismatch_frames"] > 0
        for receipt in mutant_raw
    )
    checks = {
        "clean repair replays are byte-deterministic": clean[0] == clean[1],
        "clean repair replays pass the stationary menu contract": all(
            replay_is_clean(receipt, 320) for receipt in clean_raw
        ),
        "mutant replays are byte-deterministic": mutated[0] == mutated[1],
        "gray semantic tooth LUT produces visible residue": (
            mutant_has_visible_residue
        ),
        "stationary menu contract rejects both gray-tooth replays": all(
            not replay_is_clean(receipt, 320) for receipt in mutant_raw
        ),
        "mutation changes only the twelve semantic spike-tooth entries": (
            sum(left != right for left, right in zip(source, mutant))
            == len(tooth_offsets)
            and all(mutant[offset] == GRAY_TOOTH_ATTR for offset in tooth_offsets)
        ),
    }
    receipt = {
        "schema": "penta-stage1-hazard-menu-gray-tooth-mutation-v1",
        "source_rom": str(args.rom.resolve()),
        "source_sha256": digest(source),
        "mutant_rom": str(mutant_path),
        "mutant_sha256": digest(mutant),
        "mutated_offsets": [f"0x{offset:05X}" for offset in tooth_offsets],
        "expected_gold_attr": f"0x{GOLD_TOOTH_ATTR:02X}",
        "mutated_gray_attr": f"0x{GRAY_TOOTH_ATTR:02X}",
        "clean_replays": clean,
        "mutant_replays": mutated,
        "checks": checks,
        "passed": all(checks.values()),
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    if not receipt["passed"]:
        failed = [name for name, passed in checks.items() if not passed]
        print("FAIL: " + "; ".join(failed))
        print(f"Receipt: {receipt_path}")
        return 1
    print(
        "PASS: removing gold from every semantic tooth entry produces a "
        "deterministic visible failure, and the menu gate rejects it"
    )
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
