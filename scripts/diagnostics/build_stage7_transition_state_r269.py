#!/usr/bin/env python3
"""Admit exact Stage-7 transition/gameplay FFC1 states on exact r265.

Long patrol evidence shows 112 otherwise-safe primary publications falling
back only because FFC1 is 00.  The helper's independent scene, dungeon,
Window, inherited-DMA, caller, camera, and hidden-target guards remain exact.
This diagnostic changes both FFC1 predicates from ``== 01`` to ``< 02``,
thereby admitting exactly 00/01 and rejecting every value 02..FF.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_SHA256 = "a4c772624f16bc9ef23873726cbbafa169ee93869a95a17431367895273bd273"
R264_SHA256 = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
STATIC_TEMPLATE_SHA256 = (
    "3bf962c18274ba8c5efe1e1ee9673ba19401dbebfc970782efed5e9e96673661"
)
BANK_SIZE = 0x4000
HELPER_BANK = 22
HELPER_ADDR = 0x6C80
HELPER_SIZE = 1459
OLD_HELPER_SHA256 = (
    "a309de635c97a80c2dc551b5046218e6163dcb96e00afcfb137724c73df17003"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if bank <= 0 or not 0x4000 <= address < 0x8000:
        raise AssertionError((bank, address))
    return bank * BANK_SIZE + address - 0x4000


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def rebind_static_receipt(
    template_payload: bytes,
    candidate: bytes,
    candidate_path: Path,
    helper: bytes,
    receipt: dict[str, object],
    changed_from_r264: int,
) -> dict[str, object]:
    if digest(template_payload) != STATIC_TEMPLATE_SHA256:
        raise AssertionError("r265 Stage-7 static template changed")
    template = json.loads(template_payload)
    if template.get("schema") \
            != "penta-stage7-hidden-dual-plane-hdma-r264-static-v1":
        raise AssertionError("wrong static template schema")
    if template.get("status") != "STATIC_PASS_LIVE_GATES_REQUIRED":
        raise AssertionError("static template did not pass")
    built = template.get("in_memory_candidate")
    if not isinstance(built, dict) or built.get("sha256") != BASE_SHA256:
        raise AssertionError("static template is not bound to exact r265")

    rebound = copy.deepcopy(template)
    rebound_helper = rebound.get("helper")
    if not isinstance(rebound_helper, dict):
        raise AssertionError("static helper record changed type")
    rebound_helper["sha256"] = digest(helper)

    emitted = rebound.get("emitted_guard_verification")
    if not isinstance(emitted, dict):
        raise AssertionError("static emitted-guard record changed type")
    patterns = emitted.get("patterns")
    post_patterns = emitted.get("post_service_patterns")
    if not isinstance(patterns, dict) or not isinstance(post_patterns, dict):
        raise AssertionError("static guard pattern records changed type")
    patterns["gameplay_FFC1_exact"] = "F0 C1 FE 02 D2 B3 71"
    post_patterns["post_service_gameplay"] = "F0 C1 FE 02 D2 31 72"
    emitted["guarded_prefix_sha256"] = digest(helper[:0x64])

    runtime_guards = rebound.get("runtime_guards")
    if not isinstance(runtime_guards, dict):
        raise AssertionError("static runtime-guard record changed type")
    runtime_guards["gameplay_guard"] = "$FFC1 < $02 (exactly $00/$01)"

    rebound_built = rebound.get("in_memory_candidate")
    if not isinstance(rebound_built, dict):
        raise AssertionError("static candidate record changed type")
    rebound_built["path"] = str(candidate_path)
    rebound_built["sha256"] = digest(candidate)
    rebound_built["changed_byte_count"] = changed_from_r264
    for region in rebound_built.get("installed_regions", []):
        if isinstance(region, dict) and region.get("name") == "helper":
            region["sha256"] = digest(helper)
    rebound_built["runtime_source_patches"] = [
        "exact r265 runtime sources and DAE9 dual-plane router tail unchanged",
        "bank22 helper entry/post-service FFC1 guards admit exactly 00/01",
    ]
    rebound["transition_state_rebind"] = {
        "schema": receipt["schema"],
        "base_sha256": BASE_SHA256,
        "candidate_sha256": digest(candidate),
        "old_domain": ["$01"],
        "new_domain": ["$00", "$01"],
        "rejected_domain": "$02-$FF",
        "contracts": receipt["contracts"],
    }
    return rebound


def construct(
    base: bytes,
    r264: bytes,
) -> tuple[bytes, dict[str, object]]:
    """Emit exact transition guards without rebinding historical evidence."""
    if digest(base) != BASE_SHA256:
        raise AssertionError(f"wrong exact r265 base: {digest(base)}")
    if digest(r264) != R264_SHA256:
        raise AssertionError(f"wrong exact r264 comparison: {digest(r264)}")

    helper_offset = bank_offset(HELPER_BANK, HELPER_ADDR)
    old_helper = base[helper_offset:helper_offset + HELPER_SIZE]
    if digest(old_helper) != OLD_HELPER_SHA256:
        raise AssertionError("r265 helper changed")

    old_pattern = bytes.fromhex("F0 C1 FE 01 C2")
    new_pattern = bytes.fromhex("F0 C1 FE 02 D2")
    positions: list[int] = []
    start = 0
    while True:
        position = old_helper.find(old_pattern, start)
        if position < 0:
            break
        positions.append(position)
        start = position + 1
    if positions != [0x0F, 0x569] or old_helper.count(new_pattern):
        raise AssertionError((positions, old_helper.count(new_pattern)))

    helper = bytearray(old_helper)
    for position in positions:
        helper[position:position + len(new_pattern)] = new_pattern
    admitted = [value for value in range(256) if value < 2]
    rejected = [value for value in range(256) if value >= 2]
    if admitted != [0, 1] or len(rejected) != 254:
        raise AssertionError("FFC1 truth table changed")

    rom = bytearray(base)
    rom[helper_offset:helper_offset + HELPER_SIZE] = helper
    update_checksums(rom)
    candidate = bytes(rom)
    changed = [
        index for index, (before, after) in enumerate(zip(base, candidate))
        if before != after
    ]
    allowed = {0x014D, 0x014E, 0x014F}
    for position in positions:
        allowed.update((helper_offset + position + 3, helper_offset + position + 4))
    if any(index not in allowed for index in changed):
        raise AssertionError("change escaped FFC1 guards/checksums")

    changed_from_r264 = sum(left != right for left, right in zip(r264, candidate))
    receipt: dict[str, object] = {
        "schema": "penta-stage7-transition-state-r269-construction-v1",
        "status": "construction-only",
        "promotable": False,
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "base_sha256": digest(base),
        "candidate_sha256": digest(candidate),
        "changed_bytes_from_r265_including_checksums": len(changed),
        "changed_bytes_from_r264_including_checksums": changed_from_r264,
        "helper": {
            "bank": HELPER_BANK,
            "range": "$6C80-$7232",
            "old_sha256": digest(old_helper),
            "new_sha256": digest(helper),
            "patched_predicates": [
                f"${HELPER_ADDR + position:04X}: CP 01/JP NZ -> CP 02/JP NC"
                for position in positions
            ],
        },
        "ffc1_truth_table": {
            "admitted": ["$00", "$01"],
            "rejected_count": len(rejected),
            "rejected_range": "$02-$FF",
        },
        "contracts": {
            "exact_r265_base": True,
            "entry_and_both_post_service_guards_changed_identically": True,
            "only_FFC1_00_and_01_admitted": True,
            "scene_dungeon_window_dma_camera_target_caller_guards_byte_exact": True,
            "dual_plane_compiler_and_transport_byte_exact": True,
            "r265_runtime_router_tail_and_menu_repairs_byte_exact": True,
        },
        "required_first_gates": [
            "Stage7 target6/patrol/2800 throughput and route diagnostics",
            "Stage7 2800-frame ABI accounting with zero native fallback",
            "duplicate Stage7 8000-frame exact visual/menu receipts",
        ],
    }
    return candidate, receipt


def install(
    base: bytes,
    r264: bytes,
    candidate_path: Path,
    template_payload: bytes,
) -> tuple[bytes, dict[str, object], dict[str, object]]:
    candidate, construction = construct(base, r264)
    # Preserve the historical receipt exactly, including its historical patrol
    # summary. The source-only API above must not present that as fresh evidence.
    receipt = {
        "schema": "penta-stage7-transition-state-r269-build-v1",
        "status": "STATIC_PASS_EMULATOR_REQUIRED",
        "promotable": False,
        **{key: construction[key] for key in (
            "base_sha256", "candidate_sha256", "changed_bytes_from_r265_including_checksums",
            "changed_bytes_from_r264_including_checksums", "helper", "ffc1_truth_table")},
        "patrol_evidence": {
            "exact_r265_entries": 339,
            "exact_r265_fast_entries": 227,
            "exact_r265_native_fallbacks": 112,
            "all_recorded_native_fallback_examples_have_FFC1_00": True,
            "all_other_recorded_guard_fields_pass": True,
        },
        "contracts": construction["contracts"],
        "required_first_gates": construction["required_first_gates"],
    }
    helper_offset = bank_offset(HELPER_BANK, HELPER_ADDR)
    static_receipt = rebind_static_receipt(
        template_payload,
        candidate,
        candidate_path,
        candidate[helper_offset:helper_offset + HELPER_SIZE],
        receipt,
        construction["changed_bytes_from_r264_including_checksums"],
    )
    return candidate, receipt, static_receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        type=Path,
        default=ROOT / "tmp/stage7-menu-signature-invalidation-r265/candidate.gb",
    )
    parser.add_argument(
        "--r264",
        type=Path,
        default=ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb",
    )
    parser.add_argument(
        "--static-template",
        type=Path,
        default=(ROOT / "tmp/stage7-menu-signature-invalidation-r265"
                 / "transferred-stage7-static-receipt.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tmp/stage7-transition-state-r269/candidate.gb",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=ROOT / "tmp/stage7-transition-state-r269/build-receipt.json",
    )
    parser.add_argument(
        "--abi-static-receipt",
        type=Path,
        default=ROOT / "tmp/stage7-transition-state-r269/abi-static-receipt.json",
    )
    arguments = parser.parse_args()
    candidate, receipt, static_receipt = install(
        arguments.base.read_bytes(),
        arguments.r264.read_bytes(),
        arguments.output,
        arguments.static_template.read_bytes(),
    )
    for path, payload in (
        (arguments.output, candidate),
        (arguments.receipt, json.dumps(receipt, indent=2).encode() + b"\n"),
        (arguments.abi_static_receipt,
         json.dumps(static_receipt, indent=2).encode() + b"\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
