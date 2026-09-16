#!/usr/bin/env python3
"""Build an exact r265 identity transfer for the frozen Stage-7 gates.

The r265 ROM differs from the frozen e048 Stage-7 candidate only in the
bank-13 Window helper and global checksum.  This offline builder copies the
fully audited b724 Stage-7 static contract, replaces only its candidate
identity metadata, and binds the independent 295ce equivalence proof plus the
candidate-owned menu receipts.  The emitted JSON deliberately keeps the
original static schema so the existing ABI and visual gates can consume it
without weakening any of their structural checks.

This script never launches an emulator.  The transferred receipt remains
non-promotable until candidate-bound ABI, visual, and speed runs prove that
FFE4 stayed zero throughout their non-menu measurement windows.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
R264 = ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb"
BASE = ROOT / "tmp/stage7-dual-plane-hdma-r264/candidate.gb"
BASE_STATIC = ROOT / "tmp/stage7-dual-plane-hdma-r264/static-receipt.json"
R265 = ROOT / "tmp/stage7-menu-signature-invalidation-r265/candidate.gb"
R265_BUILD = ROOT / "tmp/stage7-menu-signature-invalidation-r265/static-receipt.json"
EQUIVALENCE = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "helper-equivalence-static-receipt.json"
)
MENU_LIVE = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "menu-fixed-r1/receipt.json"
)
WINDOW_LIVE = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "generic-menu-natural-receipt.json"
)
ABI_VERIFIER = ROOT / "scripts/diagnostics/verify_stage7_dual_plane_abi.py"
VISUAL_VERIFIER = (
    ROOT / "scripts/diagnostics/verify_stage7_dual_plane_visual_receipts.py"
)
DEFAULT_OUTPUT = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "transferred-stage7-static-receipt.json"
)

R264_SHA = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
BASE_SHA = "e04801c8b8b0c1eb5ddaddce31a9581ad5c1fc83e3f1b043c581afa33df216a0"
BASE_STATIC_SHA = "b724cfae07e8e72cda8629778bef9d4f85a9ad7c3f1413eb691a06e6e1ef7272"
R265_SHA = "a4c772624f16bc9ef23873726cbbafa169ee93869a95a17431367895273bd273"
R265_BUILD_SHA = "9567c8babe7be863ecbd5a7c6ba9a8234cd81aef7508a1f6e3c184773c3a6ab7"
EQUIVALENCE_SHA = "295ce612d6dc1dead72e776f44dafb3bd22b6bc0e44b101435b27d7ddafe0583"
MENU_LIVE_SHA = "17c2d8a5a6b2d1d36ce5cb9d931db03534b2dbf7cacf5fae06be4cf3dbfdb7e5"
WINDOW_LIVE_SHA = "f32977eb72a3030b21015b089db00d93420dd1c7c58613b78a6a234b59415019"


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


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None,
            f"cannot load verifier module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def checksum_valid(rom: bytes) -> bool:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    global_sum = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    return (rom[0x014D] == header
            and int.from_bytes(rom[0x014E:0x0150], "big") == global_sum)


def exact_inputs() -> dict[str, str]:
    identities = {
        "r264_rom": sha256(R264),
        "e048_rom": sha256(BASE),
        "e048_static_receipt": sha256(BASE_STATIC),
        "r265_rom": sha256(R265),
        "r265_build_receipt": sha256(R265_BUILD),
        "r265_equivalence_receipt": sha256(EQUIVALENCE),
        "r265_menu_live_receipt": sha256(MENU_LIVE),
        "r265_window_live_receipt": sha256(WINDOW_LIVE),
        "transfer_builder": sha256(SELF),
    }
    require(identities == {
        "r264_rom": R264_SHA,
        "e048_rom": BASE_SHA,
        "e048_static_receipt": BASE_STATIC_SHA,
        "r265_rom": R265_SHA,
        "r265_build_receipt": R265_BUILD_SHA,
        "r265_equivalence_receipt": EQUIVALENCE_SHA,
        "r265_menu_live_receipt": MENU_LIVE_SHA,
        "r265_window_live_receipt": WINDOW_LIVE_SHA,
        "transfer_builder": identities["transfer_builder"],
    }, "r265 transfer input identity changed")
    return identities


def validate_equivalence(base: bytes, candidate: bytes) -> dict[str, Any]:
    receipt = json.loads(EQUIVALENCE.read_text())
    require(receipt.get("schema")
            == "penta-stage7-r265-helper-equivalence-static-v1",
            "wrong helper-equivalence schema")
    require(receipt.get("status") == "STATIC_PASS_REBIND_WRAPPERS_REQUIRED"
            and receipt.get("promotable") is False,
            "helper-equivalence receipt is not the frozen static GO")
    require(receipt.get("decision")
            == "STATIC_GO_TO_BUILD_STRICT_R265_GATE_WRAPPERS",
            "helper-equivalence decision changed")
    consumer = receipt.get("consumer_requirements", {})
    require(consumer == {
        "candidate_identity": R265_SHA,
        "menu_route": "use exact r265 menu live receipt " + MENU_LIVE_SHA,
        "nonmenu_ABI_visual_speed": "require FFE4==$00 throughout",
        "strict_speed_policy": (
            "retain .98 strict target; explicit >=.95 compromise only"
        ),
    }, "helper-equivalence consumer contract changed")
    expected_offsets = {
        int(raw, 16)
        for raw in receipt.get("equivalence", {}).get("changed_offsets", [])
    }
    observed_offsets = {
        index for index, pair in enumerate(zip(base, candidate))
        if pair[0] != pair[1]
    }
    require(len(base) == len(candidate) == 0x80000,
            "candidate ROM size changed")
    require(observed_offsets == expected_offsets
            and len(observed_offsets) == 17,
            "r265/e048 exact difference set changed")
    require(base[0x36A40:0x36A47] == candidate[0x36A40:0x36A47]
            == bytes.fromhex("F0 E4 B7 C8 FA 80 D8"),
            "FFE4-zero Window-helper prefix changed")
    require(checksum_valid(candidate), "r265 checksum is invalid")
    return {
        "changed_offsets": [f"0x{value:05X}"
                            for value in sorted(observed_offsets)],
        "changed_count": len(observed_offsets),
        "FFE4_zero_prefix": "bank13:$6A40-$6A46 byte-exact",
        "FFE4_zero_cycles": 36,
    }


def build_transfer(output: Path) -> dict[str, Any]:
    identities = exact_inputs()
    base = BASE.read_bytes()
    candidate = R265.read_bytes()
    equivalence = validate_equivalence(base, candidate)
    r264 = R264.read_bytes()
    changed_from_r264 = sum(a != b for a, b in zip(r264, candidate))
    require(changed_from_r264 == 1871,
            "r265/r264 exact changed-byte count changed")

    build = json.loads(R265_BUILD.read_text())
    menu = json.loads(MENU_LIVE.read_text())
    window = json.loads(WINDOW_LIVE.read_text())
    require(build.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED"
            and build.get("candidate_sha256") == R265_SHA,
            "r265 build receipt is not exact/static-green")
    require(menu.get("status") == "PASS"
            and menu.get("rom_sha256") == R265_SHA,
            "candidate-owned Stage7 menu fix did not pass")
    require(window.get("status") == "PASS"
            and window.get("identities", {}).get("candidate") == R265_SHA,
            "candidate-owned generic Window receipt did not pass")

    transferred = deepcopy(json.loads(BASE_STATIC.read_text()))
    require(transferred.get("schema")
            == "penta-stage7-hidden-dual-plane-hdma-r264-static-v1",
            "frozen Stage7 static schema changed")
    require(transferred.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED"
            and transferred.get("promotable") is False
            and transferred.get("emulator_run") is False,
            "frozen Stage7 static receipt is not static-green/nonpromotable")
    built = transferred.get("in_memory_candidate", {})
    require(built.get("sha256") == BASE_SHA
            and built.get("changed_byte_count") == 1856,
            "frozen Stage7 candidate metadata changed")
    built["sha256"] = R265_SHA
    built["path"] = str(R265.relative_to(ROOT))
    built["changed_byte_count"] = changed_from_r264
    built["checksums"] = {
        "header": f"${candidate[0x014D]:02X}",
        "global": f"${int.from_bytes(candidate[0x014E:0x0150], 'big'):04X}",
    }
    transferred["r265_identity_transfer"] = {
        "schema": "penta-stage7-r265-static-identity-transfer-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_run": False,
        "identities": identities,
        "equivalence": equivalence,
        "condition": "FFE4==$00 throughout each non-menu live gate",
        "separate_menu_evidence": {
            "stage7_roundtrip": MENU_LIVE_SHA,
            "generic_stage1_window_and_mutations": WINDOW_LIVE_SHA,
        },
        "transferred_contracts": [
            "bank22 helper/guards/phases/DMA/descriptor/LUT",
            "DA60 installed runtime and bank1 copier/ABI",
            "primary/secondary publishers and mapper wrapper",
            "every strict b724 preimage outside bank13:$6A40-$6A56",
        ],
        "required_live_order": [
            "r265-bound short Stage7 ABI with FFE4-zero telemetry",
            "r265-bound duplicate Stage7 exact visual with FFE4-zero telemetry",
            "r265-bound duplicate safe-boundary speed with FFE4-zero telemetry",
        ],
        "strict_speed_policy": {
            "target": 0.98,
            "release_compromise_floor": 0.95,
            "target_miss_must_remain_explicit": True,
        },
    }
    payload = json.dumps(transferred, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload)
    return {
        "receipt": transferred,
        "path": str(output.relative_to(ROOT)),
        "sha256": digest(payload.encode()),
    }


def verifier_static_acceptance(output: Path, candidate: Path) -> dict[str, Any]:
    """Run the two existing pure static consumers against the transfer."""

    args = SimpleNamespace(
        compiler_bank=22,
        entry_addr=0x6C80,
        compiler_start=0x6C80,
        compiler_end=0x7232,
        phase_addr=[0x7108, 0x714B],
        fallback_addr=0x71B3,
        caller_reject_addr=0x71BD,
        atomic_fallback_addr=0x71C1,
        outer_return_addr=[0x0AB8, 0x12E0],
        exit_bank=1,
        exit_addr=0x436D,
        dma_command_addr=[0x713D, 0x7187],
        expected_dma_command=[0xAF, 0x81],
    )
    abi = load_module(ABI_VERIFIER, "penta_r265_transfer_abi")
    abi_contract = abi.validate_static_receipt(
        output, candidate, R265_SHA, args
    )
    visual = load_module(VISUAL_VERIFIER, "penta_r265_transfer_visual")
    visual.EXPECTED_STATIC_RECEIPT_SHA256 = sha256(output)
    visual.EXPECTED_CANDIDATE_SHA256 = R265_SHA
    visual_contract = visual.static_rejection_contract(
        output, candidate.read_bytes(), R265_SHA
    )
    return {
        "ABI_static_consumer": abi_contract,
        "visual_static_consumer": visual_contract,
        "ABI_verifier_sha256": sha256(ABI_VERIFIER),
        "visual_verifier_sha256": sha256(VISUAL_VERIFIER),
    }


def mutation_controls() -> dict[str, bool]:
    base = BASE.read_bytes()
    candidate = R265.read_bytes()
    controls: dict[str, bool] = {}
    mutations = {
        "changed_set_expansion": 0x5AC80,
        "FFE4_zero_prefix": 0x36A40,
        "primary_publisher": 0x12DD,
    }
    for name, offset in mutations.items():
        mutant = bytearray(candidate)
        mutant[offset] ^= 1
        try:
            validate_equivalence(base, bytes(mutant))
        except AssertionError:
            controls[f"mutated_{name}_rejected"] = True
        else:
            controls[f"mutated_{name}_rejected"] = False
    require(all(controls.values()), "identity-transfer mutation escaped")
    return controls


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = scratch(args.output)
    result = build_transfer(output)
    consumers = verifier_static_acceptance(output, R265)
    controls = mutation_controls()
    print("PASS: exact r265 Stage7 static identity transfer")
    print(f"Receipt: {result['path']}")
    print(f"Receipt SHA-256: {result['sha256']}")
    print(f"ABI verifier: {consumers['ABI_verifier_sha256']}")
    print(f"Visual verifier: {consumers['visual_verifier_sha256']}")
    print(f"Mutation controls: {len(controls)}/{len(controls)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
