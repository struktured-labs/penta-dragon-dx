#!/usr/bin/env python3
"""Build an exact-r265 Stage-7 signature-phase diagnostic candidate.

The later-stage signature decider deliberately carries three NOPs on its
nonzero-stage arm.  This diagnostic keeps the complete two-byte/eight-sample
signature and room check intact while varying only that phase padding.  The
r265 dual-plane helper, menu repair, and router tail remain byte-exact.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_SHA256 = "a4c772624f16bc9ef23873726cbbafa169ee93869a95a17431367895273bd273"
BANK_SIZE = 0x4000
RUNTIME_BANKS = (13, 16)
RUNTIME_SOURCE_A = 0x7BB2
RUNTIME_SOURCE_A_SIZE = 46
RUNTIME_SOURCE_B = 0x7C4D
RUNTIME_SOURCE_B_SIZE = 114
RUNTIME_SIZE = RUNTIME_SOURCE_A_SIZE + RUNTIME_SOURCE_B_SIZE
RUNTIME_BASE = 0xDA60
DISPATCHER = 0xDAB9
ROUTER_TAIL = 0xDAE9
R265_RUNTIME_SHA256 = (
    "a8152a016148c2a497cd63cd8f4e9b5a6682c19d0300f9b49fc58253299b819c"
)
R265_HELPER_SHA256 = (
    "a309de635c97a80c2dc551b5046218e6163dcb96e00afcfb137724c73df17003"
)
HELPER_BANK = 22
HELPER_ADDR = 0x6C80
HELPER_SIZE = 1459


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if bank <= 0 or not 0x4000 <= address < 0x8000:
        raise AssertionError((bank, address))
    return bank * BANK_SIZE + address - 0x4000


def runtime_from_source(payload: bytes, bank: int) -> bytes:
    a = bank_offset(bank, RUNTIME_SOURCE_A)
    b = bank_offset(bank, RUNTIME_SOURCE_B)
    return (
        payload[a:a + RUNTIME_SOURCE_A_SIZE]
        + payload[b:b + RUNTIME_SOURCE_B_SIZE]
    )


def write_runtime_source(payload: bytearray, bank: int, runtime: bytes) -> None:
    if len(runtime) != RUNTIME_SIZE:
        raise AssertionError(len(runtime))
    a = bank_offset(bank, RUNTIME_SOURCE_A)
    b = bank_offset(bank, RUNTIME_SOURCE_B)
    payload[a:a + RUNTIME_SOURCE_A_SIZE] = runtime[:RUNTIME_SOURCE_A_SIZE]
    payload[b:b + RUNTIME_SOURCE_B_SIZE] = runtime[RUNTIME_SOURCE_A_SIZE:]


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def build_source_runtime(phase_nops: int) -> bytes:
    os.environ["PENTA_LATER_SIGNATURE_PHASE_NOPS"] = str(phase_nops)
    module_path = ROOT / "scripts/build_v302_title_fix.py"
    spec = importlib.util.spec_from_file_location("penta_build_v302", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("cannot load production builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    runtime = module.build_lava_attr_stage7_runtime(always_stage1=False)
    if len(runtime) != RUNTIME_SIZE:
        raise AssertionError(len(runtime))
    return runtime


def install(base: bytes, phase_nops: int) -> tuple[bytes, dict[str, object]]:
    if digest(base) != BASE_SHA256:
        raise AssertionError(f"wrong exact r265 base: {digest(base)}")
    if not 0 <= phase_nops <= 3:
        raise AssertionError("phase NOP count must be in 0..3")

    current = runtime_from_source(base, RUNTIME_BANKS[0])
    if digest(current) != R265_RUNTIME_SHA256:
        raise AssertionError("r265 runtime source changed")
    for bank in RUNTIME_BANKS[1:]:
        if runtime_from_source(base, bank) != current:
            raise AssertionError(f"bank {bank} runtime mirror differs")

    helper_offset = bank_offset(HELPER_BANK, HELPER_ADDR)
    helper = base[helper_offset:helper_offset + HELPER_SIZE]
    if digest(helper) != R265_HELPER_SHA256:
        raise AssertionError("r265 dual-plane helper changed")

    reference = bytearray(build_source_runtime(3))
    redirect_index = 0xDAB7 - RUNTIME_BASE
    reference[redirect_index] = current[redirect_index]
    prefix_end = DISPATCHER - RUNTIME_BASE + 37
    if reference[:prefix_end] != current[:prefix_end]:
        differences = [
            index for index, (left, right) in
            enumerate(zip(reference[:prefix_end], current[:prefix_end]))
            if left != right
        ]
        raise AssertionError(f"production runtime drift before $DADE: {differences}")

    generated = build_source_runtime(phase_nops)
    new_runtime = bytearray(current)
    # The decider and fixed scene dispatcher occupy DA60-DADE.  Preserve the
    # exact r265 lower dispatcher/tail bytes, which differ from today's source
    # builder only because they are frozen historical installation evidence.
    new_runtime[:prefix_end] = generated[:prefix_end]

    marker = bytes.fromhex("3E 01 E0 E0 18")
    marker_limit = DISPATCHER - RUNTIME_BASE
    marker_positions = []
    start = 0
    while True:
        position = new_runtime.find(marker, start, marker_limit)
        if position < 0:
            break
        marker_positions.append(position)
        start = position + 1
    if len(marker_positions) != 1:
        raise AssertionError(f"dirty redirect marker census: {marker_positions}")
    redirect_opcode = marker_positions[0] + len(marker) - 1
    redirect_operand = redirect_opcode + 1
    target_index = ROUTER_TAIL - RUNTIME_BASE
    delta = target_index - (redirect_operand + 1)
    if not -128 <= delta <= 127:
        raise AssertionError(delta)
    new_runtime[redirect_operand] = delta & 0xFF

    if new_runtime[target_index:] != current[target_index:]:
        raise AssertionError("r265 router tail changed")
    if new_runtime[DISPATCHER - RUNTIME_BASE:target_index] \
            != current[DISPATCHER - RUNTIME_BASE:target_index]:
        raise AssertionError("scene dispatcher changed")

    rom = bytearray(base)
    for bank in RUNTIME_BANKS:
        write_runtime_source(rom, bank, bytes(new_runtime))
    update_checksums(rom)
    candidate = bytes(rom)

    for bank in RUNTIME_BANKS:
        if runtime_from_source(candidate, bank) != bytes(new_runtime):
            raise AssertionError(f"bank {bank} runtime write failed")
    if candidate[helper_offset:helper_offset + HELPER_SIZE] != helper:
        raise AssertionError("dual-plane helper changed after install")

    changed = [
        index for index, (before, after) in enumerate(zip(base, candidate))
        if before != after
    ]
    expected_regions = {
        0x014E, 0x014F,
        *range(
            bank_offset(13, RUNTIME_SOURCE_A),
            bank_offset(13, RUNTIME_SOURCE_A) + RUNTIME_SOURCE_A_SIZE,
        ),
        *range(
            bank_offset(13, RUNTIME_SOURCE_B),
            bank_offset(13, RUNTIME_SOURCE_B) + RUNTIME_SOURCE_B_SIZE,
        ),
        *range(
            bank_offset(16, RUNTIME_SOURCE_A),
            bank_offset(16, RUNTIME_SOURCE_A) + RUNTIME_SOURCE_A_SIZE,
        ),
        *range(
            bank_offset(16, RUNTIME_SOURCE_B),
            bank_offset(16, RUNTIME_SOURCE_B) + RUNTIME_SOURCE_B_SIZE,
        ),
    }
    if any(index not in expected_regions for index in changed):
        raise AssertionError("change escaped runtime mirrors/checksums")

    receipt = {
        "schema": "penta-stage7-signature-phase-r266-build-v1",
        "status": "STATIC_PASS_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(base),
        "candidate_sha256": digest(candidate),
        "phase_nops": phase_nops,
        "hot_path_t_cycles_saved_per_stage7_signature": (3 - phase_nops) * 4,
        "changed_bytes_including_checksums": len(changed),
        "runtime": {
            "old_sha256": digest(current),
            "new_sha256": digest(new_runtime),
            "mirrors": list(RUNTIME_BANKS),
            "dirty_redirect": f"${RUNTIME_BASE + redirect_opcode:04X} -> ${ROUTER_TAIL:04X}",
        },
        "contracts": {
            "exact_r265_base": True,
            "two_independent_four_sample_signature_bytes_preserved": True,
            "all_eight_signature_sample_addresses_preserved": True,
            "room_identity_check_preserved": True,
            "signature_cache_update_preserved": True,
            "both_runtime_source_mirrors_exact": True,
            "r265_router_tail_byte_exact": True,
            "r265_dual_plane_helper_byte_exact": True,
            "r265_menu_repair_untouched": True,
            "changes_confined_to_runtime_sources_and_checksums": True,
        },
        "required_first_gate": (
            "Stage7 target6/stationary/2800 strict 0.99 speed with two replays"
        ),
    }
    return candidate, receipt


def rebind_abi_static_receipt(
    template: dict[str, object], candidate: bytes, candidate_path: Path,
    build_receipt: dict[str, object],
) -> dict[str, object]:
    if template.get("schema") \
            != "penta-stage7-hidden-dual-plane-hdma-r264-static-v1":
        raise AssertionError("wrong ABI static-receipt template schema")
    if template.get("status") != "STATIC_PASS_LIVE_GATES_REQUIRED":
        raise AssertionError("ABI static-receipt template did not pass")
    built = template.get("in_memory_candidate")
    if not isinstance(built, dict) or built.get("sha256") != BASE_SHA256:
        raise AssertionError("ABI static-receipt template is not bound to r265")
    helper = template.get("helper")
    if not isinstance(helper, dict) or helper.get("sha256") != R265_HELPER_SHA256:
        raise AssertionError("ABI static-receipt helper identity changed")

    rebound = copy.deepcopy(template)
    rebound_built = rebound["in_memory_candidate"]
    if not isinstance(rebound_built, dict):
        raise AssertionError("rebound candidate record changed type")
    rebound_built["path"] = str(candidate_path)
    rebound_built["sha256"] = digest(candidate)
    rebound_built["runtime_source_patches"] = [
        "bank13/bank16 DA60 runtime: three Stage3-7 phase NOPs reduced to two",
        "dirty redirect rebound to the exact r265 DAE9 dual-plane router tail",
    ]
    rebound["phase_rebind"] = {
        "schema": build_receipt["schema"],
        "base_sha256": BASE_SHA256,
        "candidate_sha256": digest(candidate),
        "phase_nops": build_receipt["phase_nops"],
        "runtime": build_receipt["runtime"],
        "contracts": build_receipt["contracts"],
        "static_scope": (
            "helper, descriptors, LUT, guards, mapper ABI, and r265 router tail "
            "are byte-exact; only the pre-router signature phase pad changed"
        ),
    }
    return rebound


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=ROOT / "tmp/stage7-menu-signature-invalidation-r265/candidate.gb",
    )
    parser.add_argument("--phase-nops", type=int, default=0)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage7-signature-phase-r266/candidate.gb",
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=ROOT / "tmp/stage7-signature-phase-r266/build-receipt.json",
    )
    parser.add_argument(
        "--abi-static-template", type=Path,
        default=(
            ROOT
            / "tmp/stage7-menu-signature-invalidation-r265"
            / "transferred-stage7-static-receipt.json"
        ),
    )
    parser.add_argument(
        "--abi-static-receipt", type=Path,
        default=ROOT / "tmp/stage7-signature-phase-r266/abi-static-receipt.json",
    )
    arguments = parser.parse_args()
    candidate, receipt = install(arguments.base.read_bytes(), arguments.phase_nops)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_bytes(candidate)
    arguments.receipt.parent.mkdir(parents=True, exist_ok=True)
    arguments.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    template = json.loads(arguments.abi_static_template.read_text())
    rebound = rebind_abi_static_receipt(
        template, candidate, arguments.output, receipt,
    )
    arguments.abi_static_receipt.parent.mkdir(parents=True, exist_ok=True)
    arguments.abi_static_receipt.write_text(json.dumps(rebound, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
