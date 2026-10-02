#!/usr/bin/env python3
"""Make r273's dirty redirect transition-owned by exact Stage 7.

The r273 DA60 runtime source now defaults to its native `$DAB6 -> $DAA3`
return.  Only the existing Stage-7 transition arm detours through a short
installer that writes the live redirect byte to `$31`, reproduces the exact
arrow/rare-pickup setup, and rejoins its original target.  Every non-Stage-7
transition remains byte- and cycle-exact.  Both mirrored banks are patched.

No VBlank service, compiler, DMA, palette, menu, or helper byte changes.  This
isolates the Stage-7 transport without importing the timing-sensitive service
router experiments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_SHA256 = "09d75d4461d911f4ed55c929c676346b1f7851e015bdbd867f307f8d9f1cc1d8"
EXPECTED_CANDIDATE_SHA256 = (
    "0c317aa69425ca3ca6f49b3e65a1671fb4fc4ee50d8b15d4900f12cf4493eb3f"
)
BANK_SIZE = 0x4000
BANKS = (13, 16)
RUNTIME_REDIRECT_SOURCE_ADDR = 0x7C76
RUNTIME_TAIL_SOURCE_ADDR = 0x7CA8
STAGE7_FRONT_ADDR = 0x5407
SELECTOR_ADDR = 0x570E

OLD_REDIRECT = bytes((0x31,))              # JR $DAE9 from $DAB6
NATIVE_REDIRECT = bytes((0xEB,))           # JR $DAA3 from $DAB6
ROUTER_TAIL = bytes.fromhex(
    "E1 D1 C1 F5 FA 80 D8 FE 08 28 02 F1 C9 F3 F1 F1 F1 3E 16 C3 47 08"
)
OLD_STAGE7_FRONT = bytes.fromhex("CD 9C 54 C3 22 54")
NEW_STAGE7_FRONT = bytes.fromhex("C3 0E 57 00 00 00")
OLD_SELECTOR_CAVE = bytes(16)
SELECTOR = bytes.fromhex(
    "3E 31 EA B7 DA CD 9C 54 C3 22 54 00 00 00 00 00"
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


def require_at(source: bytes, bank: int, address: int, expected: bytes,
               label: str) -> int:
    offset = bank_offset(bank, address)
    actual = source[offset:offset + len(expected)]
    if actual != expected:
        raise AssertionError(
            f"{label} preimage moved at bank{bank}:${address:04X}: "
            f"{actual.hex()} != {expected.hex()}"
        )
    return offset


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    base_sha = digest(base)
    if base_sha != BASE_SHA256:
        raise AssertionError(f"wrong exact r273 base: {base_sha}")
    if len(SELECTOR) != 16:
        raise AssertionError("selector width changed")

    rom = bytearray(base)
    allowed = {0x014D, 0x014E, 0x014F}
    bank_records: list[dict[str, object]] = []
    for bank in BANKS:
        redirect = require_at(
            base, bank, RUNTIME_REDIRECT_SOURCE_ADDR, OLD_REDIRECT,
            "r273 dirty redirect",
        )
        require_at(
            base, bank, RUNTIME_TAIL_SOURCE_ADDR, ROUTER_TAIL,
            "r273 router tail",
        )
        stage7_front = require_at(
            base, bank, STAGE7_FRONT_ADDR, OLD_STAGE7_FRONT,
            "Stage-7 arrow/rare transition arm",
        )
        selector = require_at(
            base, bank, SELECTOR_ADDR, OLD_SELECTOR_CAVE,
            "transition selector cave",
        )
        for offset, old, new in (
            (redirect, OLD_REDIRECT, NATIVE_REDIRECT),
            (stage7_front, OLD_STAGE7_FRONT, NEW_STAGE7_FRONT),
            (selector, OLD_SELECTOR_CAVE, SELECTOR),
        ):
            rom[offset:offset + len(new)] = new
            allowed.update(range(offset, offset + len(old)))
        bank_records.append({
            "bank": bank,
            "runtime_source_operand": "$7C76: $31->$EB",
            "stage7_transition_arm": "$5407: JP $570E; NOP x3",
            "stage7_redirect_installer": "$570E-$571D",
            "router_tail_sha256": digest(ROUTER_TAIL),
        })

    update_checksums(rom)
    candidate = bytes(rom)
    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND" \
            and candidate_sha != EXPECTED_CANDIDATE_SHA256:
        raise AssertionError(
            f"r277 rematerialization changed: {candidate_sha}"
        )
    changed = [
        index
        for index, (before, after) in enumerate(zip(base, candidate, strict=True))
        if before != after
    ]
    escaped = sorted(set(changed) - allowed)
    if escaped:
        raise AssertionError(f"change escaped owned regions: {escaped[:8]}")

    receipt: dict[str, object] = {
        "schema": "penta-stage7-isolated-router-r277-build-v1",
        "status": "STATIC_PASS_SPEED_AND_LIVE_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": base_sha,
        "candidate_sha256": candidate_sha,
        "changed_bytes_including_checksums": len(changed),
        "bank_copies": bank_records,
        "selector": {
            "bytes": SELECTOR.hex(" ").upper(),
            "entry_owner": "existing Stage-7-only FFBA=$06 front arm",
            "live_write": "$DAB7=$31 -> $DAE9",
            "reproduced_tail": "CALL $549C arrow; JP $5422 rare",
            "all_other_stage_entries": "do not execute installer",
        },
        "contracts": {
            "exact_r273_base": True,
            "rom_and_cold_default_is_native": True,
            "both_runtime_sources_default_native": True,
            "both_Stage7_transition_arms_install_identically": True,
            "nonstage_dirty_path_byte_and_cycle_exact_to_r264": True,
            "nonstage_transition_paths_byte_and_cycle_exact_to_r273": True,
            "stage7_router_tail_and_helper_byte_exact_to_r273": True,
            "vblank_service_pair_byte_exact_to_r273": True,
            "compiler_dma_palette_menu_crop_and_pickup_bytes_unchanged": True,
        },
        "required_first_gates": [
            "Stage5 target4/right/2800 strict 0.99 speed",
            "Stage7 target6/right/2800 exact route measurement",
            "Stage4 target3/right/2800 strict 0.99 speed",
            "corrected all-stage speed matrix",
            "selector execution plus live DAB7 attribution for Stage5/7",
            "candidate-bound ABI, visual, menu, and Crystal containment",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", type=Path,
        default=ROOT / "tmp/stage7-skip-invisible-padding-r273/candidate.gb",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage7-isolated-router-r277/candidate.gb",
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=ROOT / "tmp/stage7-isolated-router-r277/build-receipt.json",
    )
    arguments = parser.parse_args()
    candidate, receipt = install(arguments.base.read_bytes())
    for path, payload in (
        (arguments.output, candidate),
        (arguments.receipt, json.dumps(receipt, indent=2).encode() + b"\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
