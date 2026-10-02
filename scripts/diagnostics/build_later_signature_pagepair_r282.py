#!/usr/bin/env python3
"""Build the exact-r281 paired-page cache signature with a fixed epilogue.

The rejected r280 diagnostic correctly shortened the shared signature by
sampling ``$C1B3`` and ``$C2B3`` with one ``INC H``.  It did not retarget the
native dirty-path redirect after moving the saved-register epilogue two bytes
earlier, so ``JR $EB`` landed on ``POP BC`` and corrupted the stack.

r282 keeps that eight-T-cycle cache-hit saving, pads the dirty path by the
same eight cycles, retargets the cold/native redirect to the relocated full
epilogue, and updates the lazy-disarm writer to restore that new native byte.
The Stage-7 arm byte remains ``$31`` and still targets ``$DAE9`` exactly.

This is a static candidate builder.  It emits only below repository ``tmp/``
and deliberately leaves promotion to live speed, lifecycle, and visual gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_later_signature_pagepair_r280 as r280


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
DEFAULT_BASE = TMP / "stage1-metallic-teeth-r281/candidate.gb"
DEFAULT_OUT = TMP / "later-signature-pagepair-r282"

BASE_SHA256 = "6b2bb22129011d06a1d5f5eb07a34c04f5dc09c35d9df65afa4a000546a8cf49"
R279_SHA256 = "649dab3b8895e680ff9e64005641de89b3ac1f66bcb417d6a1c42ce98bc30a9d"
CANDIDATE_SHA256 = "1beb03834c3008973a6abab585f9ce7bf86aafe6e6c110c1237fb1589a372d9d"
CANDIDATE_MD5 = "e5db5d3df23ce5a1667b6028cd814261"

BANK_SIZE = 0x4000
MIRROR_BANKS = (13, 16)
HELPER_BANK = 0x16
DISARM_ADDR = 0x7233
RUNTIME_ADDR = 0xDA60
REDIRECT_ADDR = 0xDAB7
REDIRECT_OFFSET = REDIRECT_ADDR - RUNTIME_ADDR
OLD_NATIVE_REDIRECT = 0xEB
NEW_NATIVE_REDIRECT = 0xE9
STAGE7_ARM_REDIRECT = 0x31
OLD_DISARM = bytes.fromhex("3E EB EA B7 DA C3 B3 71")
NEW_DISARM = bytes.fromhex("3E E9 EA B7 DA C3 B3 71")

OLD_RUNTIME_SHA256 = r280.OLD_RUNTIME_SHA256
REJECTED_RUNTIME_SHA256 = r280.NEW_RUNTIME_SHA256
NEW_RUNTIME_SHA256 = "b09ed26236ceb55d310c020b953ac3093ecb906097fbaecd8e972fd2c6449d89"

R281_VISUAL_DELTA = {
    0x014E: (0x7E, 0x7D),
    0x014F: (0xFD, 0xDF),
    0x0368CC: (0xFF, 0x4A),
    0x0368CD: (0x03, 0x29),
    0x0428CC: (0xFF, 0x4A),
    0x0428CD: (0x03, 0x29),
}


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if bank <= 0 or not 0x4000 <= address < 0x8000:
        raise AssertionError((bank, address))
    return bank * BANK_SIZE + address - 0x4000


def require_tmp(path: Path) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    if resolved != scratch and scratch not in resolved.parents:
        raise AssertionError(f"output must remain under {scratch}: {resolved}")
    return resolved


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def relative_target(address: int, displacement: int) -> int:
    signed = displacement - 0x100 if displacement & 0x80 else displacement
    return address + 2 + signed


def fixed_runtime(old: bytes) -> bytes:
    if digest(old) != OLD_RUNTIME_SHA256:
        raise AssertionError("r281 shared runtime preimage changed")
    rejected = bytearray(r280.build_runtime(old))
    if digest(rejected) != REJECTED_RUNTIME_SHA256:
        raise AssertionError("rejected r280 reconstruction changed")
    if rejected[REDIRECT_OFFSET] != OLD_NATIVE_REDIRECT:
        raise AssertionError("rejected native redirect preimage changed")
    rejected[REDIRECT_OFFSET] = NEW_NATIVE_REDIRECT
    runtime = bytes(rejected)
    if digest(runtime) != NEW_RUNTIME_SHA256:
        raise AssertionError("fixed paired-page runtime identity changed")

    # The compacted compare block starts at $DA90.  A cache hit returns through
    # the complete relocated POP HL/POP DE/POP BC/RET sequence at $DAA1.
    if runtime[0x41:0x45] != bytes.fromhex("E1 D1 C1 C9"):
        raise AssertionError("relocated full epilogue changed")
    if runtime[0x54:0x56] != b"\x00\x00":
        raise AssertionError("dirty-path cycle repayment moved")
    if relative_target(0xDAB6, runtime[REDIRECT_OFFSET]) != 0xDAA1:
        raise AssertionError("native redirect does not target the full epilogue")
    if relative_target(0xDAB6, STAGE7_ARM_REDIRECT) != 0xDAE9:
        raise AssertionError("Stage-7 arm no longer targets its router")

    # All mismatch branches must enter the relocated dirty body in stack-safe
    # order; no branch may land inside the epilogue.
    expected_targets = {
        0xDA92: 0xDAA7,
        0xDA97: 0xDAA6,
        0xDA9F: 0xDAA5,
    }
    for address, target in expected_targets.items():
        offset = address - RUNTIME_ADDR
        if runtime[offset] != 0x20:
            raise AssertionError(f"mismatch JR moved at ${address:04X}")
        if relative_target(address, runtime[offset + 1]) != target:
            raise AssertionError(f"mismatch target changed at ${address:04X}")
    return runtime


def verify_r281_lineage(base: bytes) -> None:
    r279 = (TMP / "stage7-lazy-disarm-r279/candidate.gb").read_bytes()
    if digest(r279) != R279_SHA256:
        raise AssertionError("exact r279 lineage ROM changed")
    differences = {
        index: (before, after)
        for index, (before, after) in enumerate(zip(r279, base, strict=True))
        if before != after
    }
    if differences != R281_VISUAL_DELTA:
        raise AssertionError("r281 is not the exact palette-only r279 successor")


def build(base: bytes) -> tuple[bytes, dict[str, object]]:
    if len(base) != 32 * BANK_SIZE or digest(base) != BASE_SHA256:
        raise AssertionError(f"wrong exact r281 base: {digest(base)}")
    verify_r281_lineage(base)

    old = r280.runtime_from(base, MIRROR_BANKS[0])
    if any(r280.runtime_from(base, bank) != old for bank in MIRROR_BANKS):
        raise AssertionError("r281 DA60 source mirrors diverged")
    runtime = fixed_runtime(old)
    corpora = r280.corpus_proof()

    rom = bytearray(base)
    functional: set[int] = set()
    for bank in MIRROR_BANKS:
        first = bank_offset(bank, r280.SOURCE_A)
        second = bank_offset(bank, r280.SOURCE_B)
        for offset, (before, after) in enumerate(zip(old, runtime, strict=True)):
            if before == after:
                continue
            source_offset = (
                first + offset if offset < r280.SOURCE_A_SIZE
                else second + offset - r280.SOURCE_A_SIZE
            )
            functional.add(source_offset)
        rom[first:first + r280.SOURCE_A_SIZE] = runtime[:r280.SOURCE_A_SIZE]
        rom[second:second + r280.SOURCE_B_SIZE] = runtime[r280.SOURCE_A_SIZE:]

    disarm = bank_offset(HELPER_BANK, DISARM_ADDR)
    if base[disarm:disarm + len(OLD_DISARM)] != OLD_DISARM:
        raise AssertionError("r281 lazy-disarm writer preimage changed")
    rom[disarm:disarm + len(NEW_DISARM)] = NEW_DISARM
    functional.add(disarm + 1)
    update_checksums(rom)
    candidate = bytes(rom)
    if digest(candidate) != CANDIDATE_SHA256:
        raise AssertionError("r282 candidate SHA-256 changed")
    if hashlib.md5(candidate).hexdigest() != CANDIDATE_MD5:
        raise AssertionError("r282 candidate MD5 changed")

    changed = {
        index for index, pair in enumerate(zip(base, candidate, strict=True))
        if pair[0] != pair[1]
    }
    allowed = functional | {0x014D, 0x014E, 0x014F}
    if not changed <= allowed or len(functional) != 117 or len(changed) != 119:
        raise AssertionError("r282 change set escaped its exact owned regions")
    for offset in (0x0368CC, 0x0368CD, 0x0428CC, 0x0428CD):
        if candidate[offset] != base[offset]:
            raise AssertionError("r281 metallic-tooth palette delta changed")

    receipt: dict[str, object] = {
        "schema": "penta-later-signature-pagepair-r282-build-v1",
        "status": "STATIC_PASS_SPEED_LIFECYCLE_VISUAL_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "candidate_md5": CANDIDATE_MD5,
        "runtime_old_sha256": OLD_RUNTIME_SHA256,
        "runtime_new_sha256": NEW_RUNTIME_SHA256,
        "patch": {
            "source_mirrors": [13, 16],
            "runtime_range": "$DA72-$DAB7",
            "old_signature_a_offsets": list(r280.OLD_A),
            "new_signature_a_offsets": list(r280.NEW_A),
            "signature_b_offsets_unchanged": list(r280.KEY_B),
            "cache_hit_delta_t": -8,
            "dirty_delta_t": 0,
            "dirty_timing_pad": "$DAB4-$DAB5 NOP/NOP",
            "native_redirect": "$DAB7=$E9 -> full epilogue $DAA1",
            "stage7_arm": "$DAB7=$31 -> router $DAE9 (unchanged)",
            "lazy_disarm": "bank22:$7233 LD A,$E9; LD [$DAB7],A",
        },
        "corpus_proof": corpora,
        "diff": {
            "functional_bytes_changed": len(functional),
            "total_bytes_changed_including_checksums": len(changed),
        },
        "contracts": {
            "exact_r281_palette_only_base": True,
            "r281_metallic_tooth_palette_rows_preserved": True,
            "stage4_decision_sequence_exact_over_8000_frame_corpus": True,
            "no_stage_semantic_false_hit_count_increased": True,
            "only_one_safe_stage5_cache_decision_coalesced": True,
            "cache_hit_path_saves_exactly_8T": True,
            "dirty_path_repaid_to_exact_r281_timing": True,
            "native_redirect_targets_full_relocated_epilogue": True,
            "lazy_disarm_restores_new_native_redirect": True,
            "stage7_arm_target_and_router_bytes_unchanged": True,
        },
        "required_gates": [
            "Stage4 target3/right/2800 strict 0.99 speed",
            "Stage5 and Stage7 strict speed containment",
            "all-stage strict 0.99 speed matrix",
            "Stage7 lazy-disarm and menu lifecycle with native $E9",
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
    out_dir = require_tmp(args.out_dir)
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
