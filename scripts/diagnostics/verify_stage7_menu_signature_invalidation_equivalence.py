#!/usr/bin/env python3
"""Prove r265 is e048-equivalent outside the isolated Window helper.

This is a static identity bridge for the existing Stage-7 ABI, visual, and
speed gates.  It does not run an emulator and does not make r265 promotable.
Consumers must still bind the r265 ROM SHA and prove FFE4 remains zero for any
gate that inherits e048's helper/transport contract.  The dedicated r265 menu
receipt separately covers the only nonzero-FFE4 route in scope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
BASE = ROOT / "tmp/stage7-dual-plane-hdma-r264/candidate.gb"
BASE_RECEIPT = ROOT / "tmp/stage7-dual-plane-hdma-r264/static-receipt.json"
R265 = ROOT / "tmp/stage7-menu-signature-invalidation-r265/candidate.gb"
R265_BUILD_RECEIPT = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/static-receipt.json"
)
R265_MENU_RECEIPT = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/menu-fixed-r1/receipt.json"
)
DEFAULT_OUTPUT = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "helper-equivalence-static-receipt.json"
)

BASE_SHA = "e04801c8b8b0c1eb5ddaddce31a9581ad5c1fc83e3f1b043c581afa33df216a0"
BASE_RECEIPT_SHA = "b724cfae07e8e72cda8629778bef9d4f85a9ad7c3f1413eb691a06e6e1ef7272"
R265_SHA = "a4c772624f16bc9ef23873726cbbafa169ee93869a95a17431367895273bd273"
R265_BUILD_RECEIPT_SHA = "9567c8babe7be863ecbd5a7c6ba9a8234cd81aef7508a1f6e3c184773c3a6ab7"
R265_MENU_RECEIPT_SHA = "17c2d8a5a6b2d1d36ce5cb9d931db03534b2dbf7cacf5fae06be4cf3dbfdb7e5"

BANK13_HELPER_START = 13 * 0x4000 + 0x6A40 - 0x4000
WINDOW_HELPER_RANGE = range(BANK13_HELPER_START, BANK13_HELPER_START + 23)
CHECKSUM_OFFSETS = {0x014D, 0x014E, 0x014F}
ALLOWED_OFFSETS = set(WINDOW_HELPER_RANGE) | CHECKSUM_OFFSETS


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    return digest(path.read_bytes())


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address <= 0x7FFF,
            "invalid switchable bank address")
    return bank * 0x4000 + address - 0x4000


def scratch(path: Path) -> Path:
    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(any(resolved != root and resolved.is_relative_to(root)
                for root in roots),
            "receipt must be a child of repo tmp/ or /mnt/data/tmp/")
    return resolved


def exact_spans() -> dict[str, tuple[int, int]]:
    return {
        "fixed_mapper_wrapper": (0x0845, 0x0850),
        "primary_publisher": (0x12DD, 0x1303),
        "secondary_publisher": (0x0AB5, 0x0AC0),
        "shared_copier_and_ABI_tail": (bank_offset(1, 0x4295),
                                        bank_offset(1, 0x436E)),
        "bank13_window_caller": (bank_offset(13, 0x6EB1),
                                   bank_offset(13, 0x6EC6)),
        "runtime_DA60_source_part1": (bank_offset(13, 0x7BB2),
                                       bank_offset(13, 0x7BE0)),
        "runtime_DA60_source_part2": (bank_offset(13, 0x7C4D),
                                       bank_offset(13, 0x7CBF)),
        "bank22_helper": (bank_offset(22, 0x6C80),
                           bank_offset(22, 0x7233)),
        "bank22_descriptors": (bank_offset(22, 0x7500),
                                bank_offset(22, 0x7560)),
        "bank22_immutable_LUT": (bank_offset(22, 0x7600),
                                 bank_offset(22, 0x7700)),
    }


def payload_checksum_valid(rom: bytes) -> bool:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    return rom[0x014D] == header and int.from_bytes(
        rom[0x014E:0x0150], "big"
    ) == total


def audit_equivalence(base: bytes, candidate: bytes) -> dict[str, Any]:
    require(len(base) == len(candidate) == 0x80000,
            "ROM sizes are not exact 512 KiB")
    differences = [index for index, pair in enumerate(zip(base, candidate))
                   if pair[0] != pair[1]]
    require(differences and set(differences) <= ALLOWED_OFFSETS,
            "r265 differs outside Window helper/checksums")
    require(any(index >= 0x0150 for index in differences),
            "r265 has no payload difference")
    old = bytes.fromhex(
        "F0 E4 B7 C8 FA 80 D8 D6 02 C0 AF EA 53 DF EA 57 DF 3C C9 00 00 00 00"
    )
    new = bytes.fromhex(
        "F0 E4 B7 C8 FA 80 D8 FE 02 28 03 FE 08 C0 AF EA 53 DF EA 57 DF 3C C9"
    )
    require(base[BANK13_HELPER_START:BANK13_HELPER_START + 23] == old,
            "e048 Window helper preimage changed")
    require(candidate[BANK13_HELPER_START:BANK13_HELPER_START + 23] == new,
            "r265 Window helper payload changed")
    # FFE4==0 executes LDH/OR/RET Z and never reaches any changed byte.
    require(base[BANK13_HELPER_START:BANK13_HELPER_START + 7]
            == candidate[BANK13_HELPER_START:BANK13_HELPER_START + 7],
            "no-Window prefix changed")
    require(candidate[BANK13_HELPER_START:BANK13_HELPER_START + 4]
            == bytes.fromhex("F0 E4 B7 C8"),
            "FFE4-zero return path changed")
    spans: dict[str, Any] = {}
    for name, (start, end) in exact_spans().items():
        require(base[start:end] == candidate[start:end],
                f"r265 changed protected span {name}")
        spans[name] = {
            "start_file_offset": f"0x{start:05X}",
            "end_exclusive_file_offset": f"0x{end:05X}",
            "length": end - start,
            "sha256": digest(base[start:end]),
        }
    require(payload_checksum_valid(candidate), "r265 checksums are invalid")
    return {
        "changed_offsets": [f"0x{index:05X}" for index in differences],
        "changed_count": len(differences),
        "allowed_region": "bank13:$6A40-$6A56 + header/global checksums",
        "FFE4_zero_path": "byte-exact 36T LDH/OR/RET-Z before first diff",
        "protected_spans": spans,
    }


def mutation_controls(base: bytes, candidate: bytes) -> dict[str, bool]:
    controls: dict[str, bool] = {}
    mutations = {
        "bank22_helper": bank_offset(22, 0x6C80),
        "bank22_LUT": bank_offset(22, 0x7600),
        "primary_publisher": 0x12DD,
        "runtime_DA60_source": bank_offset(13, 0x7BB2),
        "FFE4_zero_prefix": BANK13_HELPER_START,
    }
    for name, offset in mutations.items():
        mutant = bytearray(candidate)
        mutant[offset] ^= 1
        try:
            audit_equivalence(base, bytes(mutant))
        except AssertionError:
            controls[f"mutated_{name}_rejected"] = True
        else:
            controls[f"mutated_{name}_rejected"] = False
    require(all(controls.values()), "equivalence mutation escaped")
    return controls


def build_receipt() -> dict[str, Any]:
    identities = {
        "e048_rom": sha256(BASE),
        "e048_static_receipt": sha256(BASE_RECEIPT),
        "r265_rom": sha256(R265),
        "r265_build_receipt": sha256(R265_BUILD_RECEIPT),
        "r265_menu_live_receipt": sha256(R265_MENU_RECEIPT),
        "verifier": sha256(SELF),
    }
    require(identities == {
        "e048_rom": BASE_SHA,
        "e048_static_receipt": BASE_RECEIPT_SHA,
        "r265_rom": R265_SHA,
        "r265_build_receipt": R265_BUILD_RECEIPT_SHA,
        "r265_menu_live_receipt": R265_MENU_RECEIPT_SHA,
        "verifier": identities["verifier"],
    }, "equivalence input identity changed")
    base_receipt = json.loads(BASE_RECEIPT.read_text())
    build_receipt = json.loads(R265_BUILD_RECEIPT.read_text())
    menu_receipt = json.loads(R265_MENU_RECEIPT.read_text())
    require(base_receipt.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED"
            and base_receipt.get("in_memory_candidate", {}).get("sha256")
            == BASE_SHA, "e048 helper receipt is not green/exact")
    require(build_receipt.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED"
            and build_receipt.get("candidate_sha256") == R265_SHA,
            "r265 build receipt is not green/exact")
    require(menu_receipt.get("status") == "PASS"
            and menu_receipt.get("rom_sha256") == R265_SHA,
            "r265 menu fix has not passed its bound live gate")
    base, candidate = BASE.read_bytes(), R265.read_bytes()
    equivalence = audit_equivalence(base, candidate)
    controls = mutation_controls(base, candidate)
    return {
        "schema": "penta-stage7-r265-helper-equivalence-static-v1",
        "status": "STATIC_PASS_REBIND_WRAPPERS_REQUIRED",
        "promotable": False,
        "emulator_run": False,
        "identities": identities,
        "equivalence": equivalence,
        "mutation_controls": controls,
        "transferable_contracts": [
            "bank22 helper/guards/phases/DMA sites/descriptor/LUT bytes",
            "DA60 installed-runtime source and bank1 copier/ABI bytes",
            "primary/secondary publisher and fixed mapper bytes",
            "all e048 strict preimages outside the isolated Window helper",
        ],
        "consumer_requirements": {
            "candidate_identity": R265_SHA,
            "nonmenu_ABI_visual_speed": "require FFE4==$00 throughout",
            "menu_route": (
                "use exact r265 menu live receipt " + R265_MENU_RECEIPT_SHA
            ),
            "strict_speed_policy": (
                "retain .98 strict target; explicit >=.95 compromise only"
            ),
        },
        "remaining_promotion_gates": [
            "r265-bound short Stage7 ABI",
            "r265-bound duplicate Stage7 visual",
            "r265-bound safe-boundary Stage7 speed/finalizer",
            "r265-bound Stage1 item-menu/hazard regression",
            "non-02/08 Window timing/headroom control",
        ],
        "decision": "STATIC_GO_TO_BUILD_STRICT_R265_GATE_WRAPPERS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = scratch(args.output)
    receipt = build_receipt()
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload)
    print("STATIC PASS: r265 helper/transport equivalence")
    print(f"Receipt: {output.relative_to(ROOT)}")
    print(f"Receipt SHA-256: {digest(payload.encode())}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
