#!/usr/bin/env python3
"""Build the exact-r281 shared-signature reorder speed candidate.

r282 proved that moving the compare/return block is viable and recovered the
Stage-4 loop, but its substituted sample produced live-only Stage-5/7 work.
r283 keeps the exact original eight sampled source bytes for every possible
layout.  It only reorders them so three same-page loads can use ``LD L,n``:

* signature A: ``$C235`` then ``$C29B``;
* signature B: reuse ``H=$C1`` for ``$C1DB`` after ``$C1A0``;
* signature B: ``$C2ED`` then ``$C269``.

That removes three bytes and twelve T-cycles from every cache hit without
changing either signature value.  Three dirty-only NOPs repay all twelve
cycles.  The relocated full epilogue is at ``$DAA0``, so the native redirect
and lazy-disarm byte become ``$E8``; the Stage-7 ``$31`` arm still targets
``$DAE9`` unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_later_signature_pagepair_r280 as r280
import build_later_signature_pagepair_r282 as r282


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
DEFAULT_BASE = TMP / "stage1-metallic-teeth-r281/candidate.gb"
DEFAULT_OUT = TMP / "later-signature-reorder-r283"

BASE_SHA256 = r282.BASE_SHA256
CANDIDATE_SHA256 = "22f032259382ed0e72e68d3e48fed9de50fd448b2a23aa34c848cf8a599effec"
CANDIDATE_MD5 = "9a588d67ddce4be57de7f3ea79c89e8e"
OLD_RUNTIME_SHA256 = r280.OLD_RUNTIME_SHA256
NEW_RUNTIME_SHA256 = "ad34cc16df53ede54471827dd88b6f856fc867636d0730857bb4eb875f35ebae"

MIRROR_BANKS = (13, 16)
HELPER_BANK = 0x16
DISARM_ADDR = 0x7233
RUNTIME_ADDR = 0xDA60
REDIRECT_ADDR = 0xDAB7
REDIRECT_OFFSET = REDIRECT_ADDR - RUNTIME_ADDR
NEW_NATIVE_REDIRECT = 0xE8
STAGE7_ARM_REDIRECT = 0x31
OLD_DISARM = r282.OLD_DISARM
NEW_DISARM = bytes.fromhex("3E E8 EA B7 DA C3 B3 71")

OLD_SIGNATURE_A = (0xC35C, 0xC235, 0xC1B3, 0xC29B)
NEW_SIGNATURE_A = (0xC35C, 0xC235, 0xC29B, 0xC1B3)
OLD_SIGNATURE_B = (0xC1A0, 0xC1DB, 0xC2ED, 0xC269)
NEW_SIGNATURE_B = OLD_SIGNATURE_B

SIGNATURE_A = bytes.fromhex(
    "FA 5C C3 "       # LD A,[$C35C]
    "21 35 C2 AE "    # LD HL,$C235; XOR [HL]
    "2E 9B AE "       # LD L,$9B; XOR [HL] -> $C29B
    "21 B3 C1 AE "    # LD HL,$C1B3; XOR [HL]
    "47"              # LD B,A; H remains $C1
)
SIGNATURE_B = bytes.fromhex(
    "FA A0 C1 "       # LD A,[$C1A0]; H remains $C1
    "2E DB AE "       # LD L,$DB; XOR [HL] -> $C1DB
    "21 ED C2 AE "    # LD HL,$C2ED; XOR [HL]
    "2E 69 AE "       # LD L,$69; XOR [HL] -> $C269
    "4F"              # LD C,A; final HL remains $C269
)


def exact_signature_equivalence() -> dict[str, object]:
    if sorted(OLD_SIGNATURE_A) != sorted(NEW_SIGNATURE_A):
        raise AssertionError("signature-A sample multiset changed")
    if sorted(OLD_SIGNATURE_B) != sorted(NEW_SIGNATURE_B):
        raise AssertionError("signature-B sample multiset changed")

    # Exhaustively exercise each source position as an independent basis byte.
    # XOR is commutative, so equality for all 256 values at each basis position
    # proves equality for every possible 24x24 source plane.
    addresses = sorted(set(OLD_SIGNATURE_A + OLD_SIGNATURE_B))
    for address in addresses:
        for value in range(256):
            memory = {item: 0 for item in addresses}
            memory[address] = value
            old_a = 0
            new_a = 0
            old_b = 0
            new_b = 0
            for item in OLD_SIGNATURE_A:
                old_a ^= memory[item]
            for item in NEW_SIGNATURE_A:
                new_a ^= memory[item]
            for item in OLD_SIGNATURE_B:
                old_b ^= memory[item]
            for item in NEW_SIGNATURE_B:
                new_b ^= memory[item]
            if (old_a, old_b) != (new_a, new_b):
                raise AssertionError(
                    f"signature basis mismatch at ${address:04X}={value:02X}"
                )
    return {
        "proof": "exhaustive 8-address x 256-value XOR basis",
        "basis_cases": len(addresses) * 256,
        "signature_a_old": [f"${value:04X}" for value in OLD_SIGNATURE_A],
        "signature_a_new": [f"${value:04X}" for value in NEW_SIGNATURE_A],
        "signature_b_old": [f"${value:04X}" for value in OLD_SIGNATURE_B],
        "signature_b_new": [f"${value:04X}" for value in NEW_SIGNATURE_B],
        "all_possible_source_planes_exact": True,
    }


def build_runtime(old: bytes) -> bytes:
    if len(old) != r280.RUNTIME_SIZE or r282.digest(old) != OLD_RUNTIME_SHA256:
        raise AssertionError("r281 shared runtime preimage changed")
    if old[0x12:0x32] != bytes.fromhex(
        "FA 5C C3 21 35 C2 AE 21 B3 C1 AE 21 9B C2 AE 47 "
        "FA A0 C1 21 DB C1 AE 21 ED C2 AE 21 69 C2 AE 4F"
    ):
        raise AssertionError("r281 signature instruction block changed")

    compare_and_dirty = old[0x32:0x56]
    redirect_and_tail = old[0x56:]
    runtime = bytearray(
        old[:0x12]
        + SIGNATURE_A
        + SIGNATURE_B
        + compare_and_dirty
        + b"\x00\x00\x00"
        + redirect_and_tail
    )
    if len(runtime) != r280.RUNTIME_SIZE:
        raise AssertionError("r283 runtime size changed")
    if runtime[REDIRECT_OFFSET] != r282.OLD_NATIVE_REDIRECT:
        raise AssertionError("native redirect preimage changed")
    runtime[REDIRECT_OFFSET] = NEW_NATIVE_REDIRECT
    result = bytes(runtime)
    if r282.digest(result) != NEW_RUNTIME_SHA256:
        raise AssertionError("r283 runtime identity changed")

    if result[0x40:0x44] != bytes.fromhex("E1 D1 C1 C9"):
        raise AssertionError("relocated full epilogue changed")
    if result[0x53:0x56] != b"\x00\x00\x00":
        raise AssertionError("three dirty-only timing NOPs moved")
    if r282.relative_target(0xDAB6, result[REDIRECT_OFFSET]) != 0xDAA0:
        raise AssertionError("native redirect misses the full epilogue")
    if r282.relative_target(0xDAB6, STAGE7_ARM_REDIRECT) != 0xDAE9:
        raise AssertionError("Stage-7 arm target changed")

    expected_targets = {
        0xDA91: 0xDAA6,
        0xDA96: 0xDAA5,
        0xDA9E: 0xDAA4,
    }
    for address, target in expected_targets.items():
        offset = address - RUNTIME_ADDR
        if result[offset] != 0x20:
            raise AssertionError(f"mismatch JR moved at ${address:04X}")
        if r282.relative_target(address, result[offset + 1]) != target:
            raise AssertionError(f"mismatch target changed at ${address:04X}")

    # The final HL value, B/C cache values, stack shape, and flags reaching the
    # compare block are exact.  Every LD/LD L is flag-neutral and each changed
    # pointer load is followed by XOR [HL], which overwrites flags.
    if result[0x2B:0x30] != bytes.fromhex("2E 69 AE 4F 1A"):
        raise AssertionError("final $C269 load/LD C/compare join changed")
    return result


def build(base: bytes) -> tuple[bytes, dict[str, object]]:
    if len(base) != 32 * r282.BANK_SIZE or r282.digest(base) != BASE_SHA256:
        raise AssertionError(f"wrong exact r281 base: {r282.digest(base)}")
    r282.verify_r281_lineage(base)
    equivalence = exact_signature_equivalence()

    old = r280.runtime_from(base, MIRROR_BANKS[0])
    if any(r280.runtime_from(base, bank) != old for bank in MIRROR_BANKS):
        raise AssertionError("r281 DA60 source mirrors diverged")
    runtime = build_runtime(old)

    rom = bytearray(base)
    functional: set[int] = set()
    for bank in MIRROR_BANKS:
        first = r282.bank_offset(bank, r280.SOURCE_A)
        second = r282.bank_offset(bank, r280.SOURCE_B)
        for offset, (before, after) in enumerate(zip(old, runtime, strict=True)):
            if before == after:
                continue
            functional.add(
                first + offset if offset < r280.SOURCE_A_SIZE
                else second + offset - r280.SOURCE_A_SIZE
            )
        rom[first:first + r280.SOURCE_A_SIZE] = runtime[:r280.SOURCE_A_SIZE]
        rom[second:second + r280.SOURCE_B_SIZE] = runtime[r280.SOURCE_A_SIZE:]

    disarm = r282.bank_offset(HELPER_BANK, DISARM_ADDR)
    if base[disarm:disarm + len(OLD_DISARM)] != OLD_DISARM:
        raise AssertionError("r281 lazy-disarm writer preimage changed")
    rom[disarm:disarm + len(NEW_DISARM)] = NEW_DISARM
    functional.add(disarm + 1)
    r282.update_checksums(rom)
    candidate = bytes(rom)
    if r282.digest(candidate) != CANDIDATE_SHA256:
        raise AssertionError("r283 candidate SHA-256 changed")
    if hashlib.md5(candidate).hexdigest() != CANDIDATE_MD5:
        raise AssertionError("r283 candidate MD5 changed")

    changed = {
        index for index, pair in enumerate(zip(base, candidate, strict=True))
        if pair[0] != pair[1]
    }
    allowed = functional | {0x014D, 0x014E, 0x014F}
    if not changed <= allowed or len(functional) != 121 or len(changed) != 123:
        raise AssertionError("r283 change set escaped exact owned regions")
    for offset in (0x0368CC, 0x0368CD, 0x0428CC, 0x0428CD):
        if candidate[offset] != base[offset]:
            raise AssertionError("r281 metallic-tooth palette delta changed")

    receipt: dict[str, object] = {
        "schema": "penta-later-signature-reorder-r283-build-v1",
        "status": "STATIC_PASS_SPEED_LIFECYCLE_VISUAL_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "candidate_md5": CANDIDATE_MD5,
        "runtime_old_sha256": OLD_RUNTIME_SHA256,
        "runtime_new_sha256": NEW_RUNTIME_SHA256,
        "signature_equivalence": equivalence,
        "patch": {
            "source_mirrors": list(MIRROR_BANKS),
            "runtime_range": "$DA72-$DAB7",
            "cache_hit_delta_t": -12,
            "dirty_delta_t": 0,
            "dirty_timing_pad": "$DAB3-$DAB5 NOP/NOP/NOP",
            "native_redirect": "$DAB7=$E8 -> full epilogue $DAA0",
            "stage7_arm": "$DAB7=$31 -> router $DAE9 (unchanged)",
            "lazy_disarm": "bank22:$7233 LD A,$E8; LD [$DAB7],A",
        },
        "diff": {
            "functional_bytes_changed": len(functional),
            "total_bytes_changed_including_checksums": len(changed),
        },
        "contracts": {
            "exact_r281_palette_only_base": True,
            "r281_metallic_tooth_palette_rows_preserved": True,
            "both_cache_signatures_exact_for_all_source_planes": True,
            "cache_hit_and_dirty_decision_sequence_must_be_exact": True,
            "cache_hit_path_saves_exactly_12T": True,
            "dirty_path_repaid_to_exact_r281_timing": True,
            "native_redirect_targets_full_relocated_epilogue": True,
            "lazy_disarm_restores_new_native_redirect": True,
            "stage7_arm_target_and_router_bytes_unchanged": True,
        },
        "rejected_predecessor": {
            "candidate": "r282",
            "reason": (
                "replacement sample passed Stage 4 at 758/764 but caused "
                "Stage 5 769/790 and Stage 7 793/806 containment failures"
            ),
        },
        "required_gates": [
            "Stage4 target3/right/2800 strict 0.99 speed",
            "Stage5 and Stage7 strict speed containment",
            "all-stage strict 0.99 speed matrix",
            "Stage7 lazy-disarm and menu lifecycle with native $E8",
            "candidate-bound later-stage semantic/visual soak",
            "candidate-bound Stage1 visual/menu/hazard regression suite",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out_dir = r282.require_tmp(args.out_dir)
    candidate, receipt = build(args.base.read_bytes())
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "candidate.gb").write_bytes(candidate)
    (out_dir / "build-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
