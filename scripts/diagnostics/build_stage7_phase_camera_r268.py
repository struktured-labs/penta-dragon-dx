#!/usr/bin/env python3
"""Combine the qualified r266/n1 signature phase with r267 camera guards.

The r266/n1 diagnostic reached 100.1% stationary throughput but lost patrol
throughput and exposed non-aligned low-nibble cameras in longer ABI coverage.
The r267 proof established that every SCX/SCY pair in 00..0F avoids padding.
This candidate changes only the four helper masks F3->F0 on exact r266/n1.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_SHA256 = "d6ce1e8fcc55daf66ae82514d134648023957d2fc7cf221970c555c07d7fbe5e"
R264_SHA256 = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
STATIC_TEMPLATE_SHA256 = (
    "b5e752fda14a170d6e0b7efec5144c60c14130688e99739a17f566cd8ad125f2"
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


def viewport_cells(scx: int, scy: int) -> set[tuple[int, int]]:
    first_column, first_row = scx // 8, scy // 8
    columns = 20 + bool(scx & 7)
    rows = 18 + bool(scy & 7)
    return {
        (first_row + row, first_column + column)
        for row in range(rows)
        for column in range(columns)
    }


def rebind_static_receipt(
    template_payload: bytes,
    candidate: bytes,
    candidate_path: Path,
    helper: bytes,
    build_receipt: dict[str, object],
    changed_from_r264: int,
) -> dict[str, object]:
    if digest(template_payload) != STATIC_TEMPLATE_SHA256:
        raise AssertionError("r266/n1 ABI static template changed")
    template = json.loads(template_payload)
    if template.get("schema") \
            != "penta-stage7-hidden-dual-plane-hdma-r264-static-v1":
        raise AssertionError("wrong static template schema")
    if template.get("status") != "STATIC_PASS_LIVE_GATES_REQUIRED":
        raise AssertionError("static template did not pass")
    built = template.get("in_memory_candidate")
    if not isinstance(built, dict) or built.get("sha256") != BASE_SHA256:
        raise AssertionError("static template is not bound to exact r266/n1")

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
    patterns["SCX_domain"] = "F0 43 E6 F0 C2 B3 71"
    patterns["SCY_domain"] = "F0 42 E6 F0 C2 B3 71"
    post_patterns["post_service_SCX"] = "F0 43 E6 F0 C2 31 72"
    post_patterns["post_service_SCY"] = "F0 42 E6 F0 C2 31 72"
    emitted["guarded_prefix_sha256"] = digest(helper[:0x64])

    runtime_guards = rebound.get("runtime_guards")
    if not isinstance(runtime_guards, dict):
        raise AssertionError("static runtime-guard record changed type")
    runtime_guards["camera_domain"] = [f"${value:02X}" for value in range(16)]

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
        "bank13/bank16 DA60 runtime: three Stage3-7 phase NOPs reduced to one",
        "dirty redirect rebound to the exact r265 DAE9 dual-plane router tail",
        "bank22 helper SCX/SCY entry and post-service masks F3->F0",
    ]

    phase = rebound.get("phase_rebind")
    if not isinstance(phase, dict) or phase.get("phase_nops") != 1:
        raise AssertionError("r266/n1 phase rebind changed")
    phase["candidate_sha256"] = digest(candidate)
    phase["static_scope"] = (
        "descriptors, LUT, mapper ABI, router tail, and signature decider are "
        "byte-exact to r266/n1; only the four proven camera masks changed"
    )
    rebound["camera_domain_rebind"] = {
        "schema": build_receipt["schema"],
        "base_sha256": BASE_SHA256,
        "candidate_sha256": digest(candidate),
        "old_domain": ["$00", "$04", "$08", "$0C"],
        "new_domain": [f"${value:02X}" for value in range(16)],
        "all_256_low_nibble_pairs_padding_safe": True,
        "all_240_high_nibble_values_rejected_per_axis": True,
        "contracts": build_receipt["contracts"],
    }
    return rebound


def install(
    base: bytes,
    r264: bytes,
    candidate_path: Path,
    template_payload: bytes,
) -> tuple[bytes, dict[str, object], dict[str, object]]:
    if digest(base) != BASE_SHA256:
        raise AssertionError(f"wrong exact r266/n1 base: {digest(base)}")
    if digest(r264) != R264_SHA256:
        raise AssertionError(f"wrong exact r264 comparison: {digest(r264)}")

    helper_offset = bank_offset(HELPER_BANK, HELPER_ADDR)
    old_helper = base[helper_offset:helper_offset + HELPER_SIZE]
    if digest(old_helper) != OLD_HELPER_SHA256:
        raise AssertionError("r266/n1 helper changed")

    helper = bytearray(old_helper)
    patched_addresses: list[int] = []
    for register in (0x43, 0x42):
        old_pattern = bytes((0xF0, register, 0xE6, 0xF3))
        new_pattern = bytes((0xF0, register, 0xE6, 0xF0))
        positions: list[int] = []
        start = 0
        while True:
            position = helper.find(old_pattern, start)
            if position < 0:
                break
            positions.append(position)
            start = position + 1
        if len(positions) != 2 or helper.count(new_pattern) != 0:
            raise AssertionError((register, positions, helper.count(new_pattern)))
        for position in positions:
            helper[position + 3] = 0xF0
            patched_addresses.append(HELPER_ADDR + position + 3)

    exposures = sum(
        row >= 24 or column >= 24
        for scx in range(16)
        for scy in range(16)
        for row, column in viewport_cells(scx, scy)
    )
    if exposures:
        raise AssertionError(f"low-nibble camera exposes padding: {exposures}")

    rom = bytearray(base)
    rom[helper_offset:helper_offset + HELPER_SIZE] = helper
    update_checksums(rom)
    candidate = bytes(rom)
    changed = [
        index for index, (before, after) in enumerate(zip(base, candidate))
        if before != after
    ]
    allowed = {0x014D, 0x014E, 0x014F}
    allowed.update(
        helper_offset + address - HELPER_ADDR for address in patched_addresses
    )
    if any(index not in allowed for index in changed):
        raise AssertionError("change escaped helper guards/checksums")

    changed_from_r264 = sum(left != right for left, right in zip(r264, candidate))
    receipt: dict[str, object] = {
        "schema": "penta-stage7-phase-camera-r268-build-v1",
        "status": "STATIC_PASS_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(base),
        "candidate_sha256": digest(candidate),
        "phase_nops": 1,
        "changed_bytes_from_r266_n1_including_checksums": len(changed),
        "changed_bytes_from_r264_including_checksums": changed_from_r264,
        "helper": {
            "bank": HELPER_BANK,
            "range": "$6C80-$7232",
            "old_sha256": digest(old_helper),
            "new_sha256": digest(helper),
            "patched_immediates": [
                f"${address:04X}: F3->F0" for address in sorted(patched_addresses)
            ],
        },
        "camera_truth_table": {
            "admitted_values_per_axis": [f"${value:02X}" for value in range(16)],
            "rejected_values_per_axis": 240,
            "admitted_pairs": 256,
            "padding_exposures": exposures,
        },
        "contracts": {
            "exact_r266_n1_base": True,
            "one_nop_signature_phase_byte_exact": True,
            "primary_pending_scroll_is_masked_to_low_nibble": True,
            "all_low_nibble_viewports_avoid_padding": True,
            "all_high_nibble_values_fail_closed": True,
            "entry_and_both_post_service_guards_widened_identically": True,
            "dual_plane_compiler_and_transport_byte_exact": True,
            "r265_router_tail_and_menu_repairs_byte_exact": True,
        },
        "required_first_gates": [
            "Stage7 target6/patrol/2800 throughput and route diagnostics",
            "Stage7 target6/stationary/2800 strict 0.99 replay",
            "Stage7 300-frame dual-plane ABI with zero native fallback",
        ],
    }
    static_receipt = rebind_static_receipt(
        template_payload,
        candidate,
        candidate_path,
        bytes(helper),
        receipt,
        changed_from_r264,
    )
    return candidate, receipt, static_receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        type=Path,
        default=ROOT / "tmp/stage7-signature-phase-r266/n1/candidate.gb",
    )
    parser.add_argument(
        "--r264",
        type=Path,
        default=ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb",
    )
    parser.add_argument(
        "--static-template",
        type=Path,
        default=ROOT / "tmp/stage7-signature-phase-r266/n1/abi-static-receipt.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tmp/stage7-phase-camera-r268/candidate.gb",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=ROOT / "tmp/stage7-phase-camera-r268/build-receipt.json",
    )
    parser.add_argument(
        "--abi-static-receipt",
        type=Path,
        default=ROOT / "tmp/stage7-phase-camera-r268/abi-static-receipt.json",
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
        (
            arguments.abi_static_receipt,
            json.dumps(static_receipt, indent=2).encode() + b"\n",
        ),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
