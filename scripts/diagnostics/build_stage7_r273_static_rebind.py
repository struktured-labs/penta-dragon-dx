#!/usr/bin/env python3
"""Rebind r269's exact Stage-7 ABI proof to the r273 cropped helper."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_STATIC_SHA256 = (
    "cec0f8cc90f3d55cf48da9312e6547361ada4490f3a43effbb0ad7f590ea1543"
)
BASE_SHA256 = "4abe94ee1d782c66c1ee79f5c45c5a0875f66ee384c60161db712bff17b87711"
CANDIDATE_SHA256 = "09d75d4461d911f4ed55c929c676346b1f7851e015bdbd867f307f8d9f1cc1d8"
R264_SHA256 = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
HELPER_ADDR = 0x6C80
HELPER_SIZE = 1459
HELPER_SHA256 = "5da2866e88a520bd67fd18b984a1cf4b6c7f6c1cb8bf93402d6fadd64f8afebd"
R271_BUILD_SHA256 = (
    "dc56587cdb434dbce681157689fbbdae15457deb708d6549e0b962c5f653071d"
)
R273_BUILD_SHA256 = (
    "5db8dabe87170fd20d3938ff576718c6be60da6a4d58c9fa100a69dd24de7218"
)
R271_SHA256 = "1eefb4bd7963928303ffe7dda9ff4875d6f438eda3721934b4fb439ae09e97e9"


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    return bank * 0x4000 + address - 0x4000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate", type=Path,
        default=ROOT / "tmp/stage7-skip-invisible-padding-r273/candidate.gb",
    )
    parser.add_argument(
        "--r264", type=Path,
        default=ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb",
    )
    parser.add_argument(
        "--base-static", type=Path,
        default=ROOT / "tmp/stage7-transition-state-r269/abi-static-receipt.json",
    )
    parser.add_argument(
        "--r271-build", type=Path,
        default=ROOT / "tmp/stage7-visible-rows-r271/build-receipt.json",
    )
    parser.add_argument(
        "--r273-build", type=Path,
        default=ROOT / "tmp/stage7-skip-invisible-padding-r273/build-receipt.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage7-skip-invisible-padding-r273/abi-static-receipt.json",
    )
    arguments = parser.parse_args()

    candidate = arguments.candidate.read_bytes()
    r264 = arguments.r264.read_bytes()
    static_payload = arguments.base_static.read_bytes()
    if digest(candidate) != CANDIDATE_SHA256:
        raise AssertionError("r273 candidate changed")
    if digest(r264) != R264_SHA256:
        raise AssertionError("r264 comparison changed")
    if digest(static_payload) != BASE_STATIC_SHA256:
        raise AssertionError("r269 static receipt changed")
    helper_offset = bank_offset(22, HELPER_ADDR)
    helper = candidate[helper_offset:helper_offset + HELPER_SIZE]
    if digest(helper) != HELPER_SHA256:
        raise AssertionError("r273 helper changed")
    r271_payload = arguments.r271_build.read_bytes()
    r273_payload = arguments.r273_build.read_bytes()
    if digest(r271_payload) != R271_BUILD_SHA256:
        raise AssertionError("r271 build receipt identity changed")
    if digest(r273_payload) != R273_BUILD_SHA256:
        raise AssertionError("r273 build receipt identity changed")
    r271 = json.loads(r271_payload)
    r273 = json.loads(r273_payload)
    if r271.get("schema") != "penta-stage7-visible-rows-r271-build-v1" \
            or r271.get("status") != "STATIC_PASS_SPEED_DIAGNOSTIC_ONLY" \
            or r271.get("promotable") is not False \
            or r271.get("base_sha256") != BASE_SHA256 \
            or r271.get("candidate_sha256") != R271_SHA256:
        raise AssertionError("wrong r271 build receipt")
    if r273.get("schema") \
            != "penta-stage7-skip-invisible-padding-r273-build-v1" \
            or r273.get("status") != "STATIC_PASS_SPEED_DIAGNOSTIC_ONLY" \
            or r273.get("promotable") is not False \
            or r273.get("base_sha256") != R271_SHA256 \
            or r273.get("candidate_sha256") != CANDIDATE_SHA256:
        raise AssertionError("wrong r273 build receipt")
    required_r271_contracts = {
        "exact_r269_base",
        "all_potentially_visible_rows_compiled_and_transferred",
        "complete_32_byte_padded_width_retained",
        "primary_publisher_scy_low_nibble_proof_inherited",
        "ffc1_00_01_transition_guard_byte_exact",
        "all_other_guards_and_r265_menu_repairs_byte_exact",
        "helper_labels_and_length_unchanged",
    }
    required_r273_contracts = {
        "exact_r271_base",
        "all_visible_and_semantic_attributes_still_compiled",
        "only_never_visible_padding_writes_removed",
        "row_stride_and_40_block_transfer_unchanged",
        "r271_transport_timing_and_r269_guards_otherwise_byte_exact",
        "r265_menu_repairs_byte_exact",
    }
    if set(r271.get("contracts", {})) != required_r271_contracts \
            or not all(r271["contracts"].values()):
        raise AssertionError("r271 build contracts changed")
    if set(r273.get("contracts", {})) != required_r273_contracts \
            or not all(r273["contracts"].values()):
        raise AssertionError("r273 build contracts changed")

    receipt = copy.deepcopy(json.loads(static_payload))
    if receipt.get("schema") \
            != "penta-stage7-hidden-dual-plane-hdma-r264-static-v1":
        raise AssertionError("wrong static schema")
    built = receipt.get("in_memory_candidate")
    if not isinstance(built, dict) or built.get("sha256") != BASE_SHA256:
        raise AssertionError("static receipt is not bound to r269")
    helper_record = receipt.get("helper")
    if not isinstance(helper_record, dict):
        raise AssertionError("helper record changed type")
    helper_record["sha256"] = HELPER_SHA256
    built["path"] = str(arguments.candidate)
    built["sha256"] = CANDIDATE_SHA256
    built["changed_byte_count"] = sum(
        left != right for left, right in zip(r264, candidate)
    )
    global_checksum = sum(candidate[:0x14E] + candidate[0x150:]) & 0xFFFF
    if int.from_bytes(candidate[0x14E:0x150], "big") != global_checksum:
        raise AssertionError("r273 global checksum is invalid")
    if candidate[0x14D] != 0xF9:
        raise AssertionError("r273 header checksum changed")
    built["checksums"] = {
        "global": f"${global_checksum:04X}",
        "header": f"${candidate[0x14D]:02X}",
    }
    for region in built.get("installed_regions", []):
        if isinstance(region, dict) and region.get("name") == "helper":
            region["sha256"] = HELPER_SHA256
    built["runtime_source_patches"] = [
        "exact r265 runtime sources and DAE9 dual-plane router tail unchanged",
        "FFC1 guards admit exactly transition/gameplay states 00/01",
        "helper compiles/transfers exact visible row union 0..19",
        "attribute padding columns 24..31 are advanced without writes",
    ]

    dma = receipt.get("dma_contract")
    if not isinstance(dma, dict):
        raise AssertionError("DMA contract changed type")
    dma["active_lcd_commands"] = {"attrs": "$A7", "tile_rows": "$81 x20"}
    dma["lcd_off_commands"] = {"attrs": "$27", "tile_rows": "$01 x20"}

    memory = receipt.get("memory_ownership")
    if not isinstance(memory, dict):
        raise AssertionError("memory ownership changed type")
    memory["attrs"] = (
        "SVBK3:$D000-$D27F; rows 0..19 semantic columns 0..23 "
        "overwritten; padding columns 24..31 intentionally retained/stale"
    )
    memory["odd_tiles"] = (
        "SVBK2:$D000-$D13F; all ten potentially visible odd rows overwritten"
    )

    timing = receipt.get("timing")
    if not isinstance(timing, dict):
        raise AssertionError("timing contract changed type")
    phase1 = timing.get("phase1")
    phase2 = timing.get("phase2_attribute_transport")
    phase3 = timing.get("phase3_tile_transport")
    if not isinstance(phase1, dict) or not isinstance(phase2, dict) \
            or not isinstance(phase3, dict):
        raise AssertionError("timing phases changed type")
    if phase1.get("padded_attribute_compile_t") != 24356 \
            or phase1.get("unrolled_odd_tile_stage_t") != 7904 \
            or phase1.get("core_t") != 32368 \
            or phase1.get("full_interrupt_closed_upper_t") != 33024:
        raise AssertionError("r269 phase-1 timing preimage changed")
    del phase1["padded_attribute_compile_t"]
    phase1.update({
        "semantic_attribute_compile_and_padding_advance_t": 19668,
        "unrolled_odd_tile_stage_t": 6608,
        "core_t": 26384,
        "full_interrupt_closed_upper_t": 27040,
        "timer_margin_t": 20064,
    })
    phase2.update({
        "blocks": 40,
        "hblank_wall_t": 40 * 456,
        "conservative_wall_upper_t": 41 * 456 + 10 * 456,
    })
    phase3.update({
        "commands": 20,
        "total_blocks": 40,
        "hblank_wall_t": 40 * 456,
        "conservative_wall_upper_t": 41 * 456 + 10 * 456,
    })
    if timing.get("candidate_dirty_conservative_typical_upper_t") != 80000 \
            or timing.get("current_dirty_approx_t") != 110984 \
            or timing.get("saving_per_dirty_approx_t") != 30984 \
            or timing.get("stage7_patrol_dirty_compiles") != 351:
        raise AssertionError("r269 aggregate timing preimage changed")
    timing.update({
        "candidate_dirty_conservative_typical_upper_t": 65920,
        "saving_per_dirty_approx_t": 45064,
        "patrol_saving_projection_t": 15817464,
        "projection": (
            "r273 static timing projection only; exact live speed and route "
            "receipts remain mandatory"
        ),
    })
    receipt["visible_crop_rebind"] = {
        "schema": "penta-stage7-r273-static-rebind-v1",
        "base_candidate_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "r271_build_sha256": R271_BUILD_SHA256,
        "r273_build_sha256": R273_BUILD_SHA256,
        "visible_rows": list(range(20)),
        "visible_columns": list(range(22)),
        "semantic_columns_compiled": list(range(24)),
        "invisible_padding_columns_not_written": list(range(24, 32)),
        "attribute_blocks": 40,
        "tile_rows": 20,
        "tile_blocks": 40,
        "contracts": {
            **r271["contracts"],
            **r273["contracts"],
        },
    }
    receipt["visible_crop_rebind"]["proof_inputs"] = {
        "r271": {
            "schema": r271["schema"],
            "base_sha256": r271["base_sha256"],
            "candidate_sha256": r271["candidate_sha256"],
            "receipt_sha256": R271_BUILD_SHA256,
        },
        "r273": {
            "schema": r273["schema"],
            "base_sha256": r273["base_sha256"],
            "candidate_sha256": r273["candidate_sha256"],
            "receipt_sha256": R273_BUILD_SHA256,
        },
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({
        "status": receipt["status"],
        "candidate_sha256": CANDIDATE_SHA256,
        "helper_sha256": HELPER_SHA256,
        "receipt_sha256": digest(arguments.output.read_bytes()),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
