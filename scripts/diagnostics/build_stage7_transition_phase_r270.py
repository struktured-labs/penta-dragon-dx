#!/usr/bin/env python3
"""Apply r269's exact FFC1 transition guard to an r266 phase candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BANK_SIZE = 0x4000
HELPER_BANK = 22
HELPER_ADDR = 0x6C80
HELPER_SIZE = 1459
OLD_HELPER_SHA256 = (
    "a309de635c97a80c2dc551b5046218e6163dcb96e00afcfb137724c73df17003"
)
PHASES = {
    0: (
        ROOT / "tmp/stage7-signature-phase-r266/candidate.gb",
        "e0c7ad870e3793df634b2f979fc44a154c11eeadb5bede851f205281d302e830",
        "8a738e9f6157e5eeffb0293727577b740109fdbbf62c1c53dd29c02e1430ff00",
    ),
    1: (
        ROOT / "tmp/stage7-signature-phase-r266/n1/candidate.gb",
        "d6ce1e8fcc55daf66ae82514d134648023957d2fc7cf221970c555c07d7fbe5e",
        "96433785d6c910a83ad46be06238b52ccab7d0d817df679ae821bdbac812ef11",
    ),
    2: (
        ROOT / "tmp/stage7-signature-phase-r266/n2/candidate.gb",
        "32507521e51e22f36e48a7a6dd87b26fa070c6fda6ae84a2612ea33c2ddce816",
        "4f342aa856a4d0c36599a56fd585f64b4d0992a6bb01dadd8f7cf71fde33bbb6",
    ),
}


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    return bank * BANK_SIZE + address - 0x4000


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def runtime_from_source(payload: bytes, bank: int) -> bytes:
    def offset(address: int) -> int:
        return bank_offset(bank, address)
    return (
        payload[offset(0x7BB2):offset(0x7BB2) + 46]
        + payload[offset(0x7C4D):offset(0x7C4D) + 114]
    )


def install(base: bytes, phase: int) -> tuple[bytes, dict[str, object]]:
    _path, expected_sha, expected_runtime_sha = PHASES[phase]
    if digest(base) != expected_sha:
        raise AssertionError(f"wrong exact r266/n{phase} base: {digest(base)}")
    for bank in (13, 16):
        if digest(runtime_from_source(base, bank)) != expected_runtime_sha:
            raise AssertionError(f"bank{bank} phase runtime changed")

    helper_offset = bank_offset(HELPER_BANK, HELPER_ADDR)
    old_helper = base[helper_offset:helper_offset + HELPER_SIZE]
    if digest(old_helper) != OLD_HELPER_SHA256:
        raise AssertionError("phase candidate helper changed")
    old_pattern = bytes.fromhex("F0 C1 FE 01 C2")
    new_pattern = bytes.fromhex("F0 C1 FE 02 D2")
    positions = [index for index in range(len(old_helper))
                 if old_helper.startswith(old_pattern, index)]
    if positions != [0x0F, 0x569] or old_helper.count(new_pattern):
        raise AssertionError((positions, old_helper.count(new_pattern)))
    helper = bytearray(old_helper)
    for position in positions:
        helper[position:position + 5] = new_pattern

    rom = bytearray(base)
    rom[helper_offset:helper_offset + HELPER_SIZE] = helper
    update_checksums(rom)
    candidate = bytes(rom)
    changed = [index for index, pair in enumerate(zip(base, candidate))
               if pair[0] != pair[1]]
    allowed = {0x014D, 0x014E, 0x014F}
    for position in positions:
        allowed.update((helper_offset + position + 3, helper_offset + position + 4))
    if any(index not in allowed for index in changed):
        raise AssertionError("change escaped transition guards/checksums")
    for bank in (13, 16):
        if digest(runtime_from_source(candidate, bank)) != expected_runtime_sha:
            raise AssertionError(f"bank{bank} runtime changed after helper patch")

    receipt: dict[str, object] = {
        "schema": "penta-stage7-transition-phase-r270-build-v1",
        "status": "STATIC_PASS_SPEED_DIAGNOSTIC_ONLY",
        "promotable": False,
        "phase_nops": phase,
        "base_sha256": expected_sha,
        "candidate_sha256": digest(candidate),
        "phase_runtime_sha256": expected_runtime_sha,
        "helper_old_sha256": digest(old_helper),
        "helper_new_sha256": digest(helper),
        "changed_bytes_including_checksums": len(changed),
        "contracts": {
            "exact_r266_phase_base": True,
            "phase_runtime_mirrors_byte_exact": True,
            "ffc1_domain_exactly_00_01": True,
            "only_entry_post_service_predicates_and_checksums_changed": True,
            "remaining_r265_helper_and_menu_repairs_byte_exact": True,
        },
        "required_first_gate": "Stage7 target6/patrol/2800 strict 0.99 speed",
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=int, choices=sorted(PHASES), required=True)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--receipt", type=Path)
    arguments = parser.parse_args()
    default_base = PHASES[arguments.phase][0]
    output = arguments.output or (
        ROOT / f"tmp/stage7-transition-phase-r270/n{arguments.phase}/candidate.gb"
    )
    receipt_path = arguments.receipt or output.with_name("build-receipt.json")
    candidate, receipt = install((arguments.base or default_base).read_bytes(),
                                 arguments.phase)
    for path, payload in (
        (output, candidate),
        (receipt_path, json.dumps(receipt, indent=2).encode() + b"\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
