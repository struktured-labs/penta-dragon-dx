#!/usr/bin/env python3
"""Make r278's Stage-7 runtime redirect lazily self-disarm off Stage 7.

The Stage-7 arm remains transition-owned.  While armed, a dirty publication
whose D880/FFBA identity is no longer exact Stage 7 now enters the existing
bank-22 pre-mutation guards, writes the native ``$DAB7=$EB`` redirect, and
rejoins the established native fallback.  Valid Stage-7 gameplay and its
SELECT-menu fallback skip every new byte and retain exact timing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_SHA256 = "1bb98e252995a4da9080bcc7aeeb27237762eb2d0713d9ed7e43409c978efd47"
EXPECTED_CANDIDATE_SHA256 = (
    "649dab3b8895e680ff9e64005641de89b3ac1f66bcb417d6a1c42ce98bc30a9d"
)
BANK_SIZE = 0x4000
RUNTIME_BANKS = (13, 16)
RUNTIME_TAIL_SOURCE_ADDR = 0x7CA8
RUNTIME_TAIL_ADDR = 0xDAE9
NONSTAGE_JOIN_ADDR = 0xDAF4
NONSTAGE_JOIN_OFFSET = NONSTAGE_JOIN_ADDR - RUNTIME_TAIL_ADDR
HELPER_BANK = 0x16
FIRST_GUARD_OPERAND_ADDR = 0x6C86
SECOND_GUARD_OPERAND_ADDR = 0x6C8D
FALLBACK_NATIVE_ADDR = 0x71B3
DISARM_CAVE_ADDR = 0x7233
CLASSIFIER_CAVE_ADDR = 0x723B
DESCRIPTORS_ADDR = 0x7500

OLD_ROUTER_TAIL = bytes.fromhex(
    "E1 D1 C1 F5 FA 80 D8 FE 08 28 02 F1 C9 "
    "F3 F1 F1 F1 3E 16 C3 47 08"
)
OLD_NONSTAGE_RETURN = bytes.fromhex("F1 C9")
NEW_NONSTAGE_JOIN = bytes.fromhex("18 00")
OLD_GUARD_TARGET = FALLBACK_NATIVE_ADDR.to_bytes(2, "little")
FIRST_GUARD_TARGET = CLASSIFIER_CAVE_ADDR.to_bytes(2, "little")
SECOND_GUARD_TARGET = DISARM_CAVE_ADDR.to_bytes(2, "little")
DISARM = bytes.fromhex("3E EB EA B7 DA C3 B3 71")
CLASSIFIER = bytes.fromhex("F0 BA FE 06 CA B3 71 C3 33 72")
OLD_CAVE = bytes([0xFF]) * (len(DISARM) + len(CLASSIFIER))


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


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    base_sha = digest(base)
    if base_sha != BASE_SHA256:
        raise AssertionError(f"wrong exact r278 base: {base_sha}")
    if NONSTAGE_JOIN_OFFSET != 11:
        raise AssertionError("runtime nonstage join offset changed")
    if OLD_ROUTER_TAIL[NONSTAGE_JOIN_OFFSET:NONSTAGE_JOIN_OFFSET + 2] \
            != OLD_NONSTAGE_RETURN:
        raise AssertionError("router-tail model lost nonstage return")
    if CLASSIFIER_CAVE_ADDR != DISARM_CAVE_ADDR + len(DISARM):
        raise AssertionError("classifier is not adjacent to disarm")
    if CLASSIFIER_CAVE_ADDR + len(CLASSIFIER) > DESCRIPTORS_ADDR:
        raise AssertionError("disarm escaped the asserted expansion-bank cave")

    rom = bytearray(base)
    allowed = {0x014D, 0x014E, 0x014F}
    runtime_records: list[dict[str, object]] = []
    for bank in RUNTIME_BANKS:
        tail_offset = bank_offset(bank, RUNTIME_TAIL_SOURCE_ADDR)
        actual_tail = base[tail_offset:tail_offset + len(OLD_ROUTER_TAIL)]
        if actual_tail != OLD_ROUTER_TAIL:
            raise AssertionError(f"bank{bank} router tail changed")
        join_offset = tail_offset + NONSTAGE_JOIN_OFFSET
        rom[join_offset:join_offset + 2] = NEW_NONSTAGE_JOIN
        allowed.update(range(join_offset, join_offset + 2))
        new_tail = bytearray(OLD_ROUTER_TAIL)
        new_tail[NONSTAGE_JOIN_OFFSET:NONSTAGE_JOIN_OFFSET + 2] = (
            NEW_NONSTAGE_JOIN
        )
        runtime_records.append({
            "bank": bank,
            "source_address": "$7CB3-$7CB4",
            "runtime_address": "$DAF4-$DAF5",
            "old_tail_sha256": digest(OLD_ROUTER_TAIL),
            "new_tail_sha256": digest(new_tail),
        })

    guard_records: list[dict[str, object]] = []
    for name, address, predicate, target in (
        ("D880", FIRST_GUARD_OPERAND_ADDR, "$D880 == $08",
         CLASSIFIER_CAVE_ADDR),
        ("FFBA", SECOND_GUARD_OPERAND_ADDR, "$FFBA == $06",
         DISARM_CAVE_ADDR),
    ):
        offset = bank_offset(HELPER_BANK, address)
        actual = base[offset:offset + 2]
        if actual != OLD_GUARD_TARGET:
            raise AssertionError(
                f"{name} guard target moved at ${address:04X}: {actual.hex()}"
            )
        new_target = target.to_bytes(2, "little")
        rom[offset:offset + 2] = new_target
        allowed.update(range(offset, offset + 2))
        guard_records.append({
            "guard": name,
            "operand_address": f"${address:04X}-${address + 1:04X}",
            "required_for_stage7": predicate,
            "old_target": f"${FALLBACK_NATIVE_ADDR:04X}",
            "new_target": f"${target:04X}",
        })

    cave_offset = bank_offset(HELPER_BANK, DISARM_CAVE_ADDR)
    if base[cave_offset:cave_offset + len(OLD_CAVE)] != OLD_CAVE:
        raise AssertionError("bank22 disarm cave is not exact erased space")
    cave = DISARM + CLASSIFIER
    rom[cave_offset:cave_offset + len(cave)] = cave
    allowed.update(range(cave_offset, cave_offset + len(cave)))

    update_checksums(rom)
    candidate = bytes(rom)
    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND" \
            and candidate_sha != EXPECTED_CANDIDATE_SHA256:
        raise AssertionError(
            f"candidate identity drift: {candidate_sha} != "
            f"{EXPECTED_CANDIDATE_SHA256}"
        )
    changed = [index for index, pair in enumerate(zip(base, candidate))
               if pair[0] != pair[1]]
    unexpected = sorted(set(changed) - allowed)
    if unexpected:
        raise AssertionError(
            "unexpected changed offsets: "
            + ", ".join(f"0x{value:X}" for value in unexpected)
        )

    receipt: dict[str, object] = {
        "schema": "penta-stage7-lazy-disarm-r279-build-v1",
        "status": "STATIC_PASS_LIFECYCLE_AND_LIVE_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": base_sha,
        "candidate_sha256": candidate_sha,
        "changed_bytes_including_checksums": len(changed),
        "runtime_join": runtime_records,
        "guard_retargets": guard_records,
        "disarm": {
            "bank": HELPER_BANK,
            "address": f"${DISARM_CAVE_ADDR:04X}-${DISARM_CAVE_ADDR + len(cave) - 1:04X}",
            "disarm_bytes": DISARM.hex(" ").upper(),
            "classifier_bytes": CLASSIFIER.hex(" ").upper(),
            "preimage_sha256": digest(OLD_CAVE),
            "postimage_sha256": digest(cave),
            "effect": (
                "D880 mismatch classifies FFBA; FFBA=$06 preserves the arm, "
                "otherwise $DAB7=$EB; both rejoin $71B3 fallback_native"
            ),
        },
        "route_proof": {
            "fresh_nonstage": (
                "DAB7 already $EB; native $DAA3 path never reaches new bytes"
            ),
            "stage7_gameplay": (
                "D880=$08 and FFBA=$06; router JR Z and both helper guards "
                "take their original Stage7 path with exact timing"
            ),
            "stage7_select_menu": (
                "first two guards pass; unchanged FFC1 guard falls native "
                "without disarming the Stage7 session"
            ),
            "post_stage7_d880_change": (
                "armed router joins mapper; first helper guard classifies "
                "FFBA before SVBK/VBK/VRAM mutation"
            ),
            "post_stage7_ffba_change": (
                "either helper guard reaches disarm when FFBA is no longer "
                "$06, then replays native dirty"
            ),
            "stage7_transient_d880_change": (
                "death/retry and miniboss paths retain FFBA=$06; classifier "
                "rejoins native fallback without clearing the Stage7 arm"
            ),
            "subsequent_nonstage_dirty": (
                "DAB7=$EB restores direct native $DAA3 return"
            ),
        },
        "contracts": {
            "exact_r278_base": True,
            "valid_stage7_hot_path_byte_and_cycle_exact_to_r278": True,
            "stage7_menu_path_byte_and_cycle_exact_to_r278": True,
            "disarm_precedes_atomic_setup": True,
            "disarm_executes_with_svbk1_and_ime_closed": True,
            "native_fallback_stack_and_mapper_path_reused": True,
            "pointer_speed_patch_byte_exact_to_r278": True,
            "vblank_services_dma_palette_menu_crop_and_pickups_unchanged": True,
        },
        "required_gates": [
            "forced D880 and FFBA lazy-disarm execution matrix",
            "Stage7 SELECT-menu roundtrip retains DAB7=$31",
            "Stage5/7 strict speed replay",
            "candidate-bound ABI, visual, Crystal, and fallback containment",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", type=Path,
        default=ROOT / "tmp/stage7-pointer-advance-r278/candidate.gb",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage7-lazy-disarm-r279/candidate.gb",
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=ROOT / "tmp/stage7-lazy-disarm-r279/build-receipt.json",
    )
    args = parser.parse_args()
    candidate, receipt = install(args.base.read_bytes())
    for path, payload in (
        (args.output, candidate),
        (args.receipt, json.dumps(receipt, indent=2).encode() + b"\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
