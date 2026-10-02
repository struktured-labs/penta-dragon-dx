#!/usr/bin/env python3
"""Build the exact-r279 paired-page cache-signature speed diagnostic.

The shared later-stage cache samples ``$C1B3`` and ``$C29B`` consecutively.
This candidate replaces the final sample with ``$C2B3`` and reuses HL via
``INC H``.  The two-byte compaction moves the cache-hit return two bytes
earlier.  Two NOPs immediately before the unchanged ``$DAB6`` dirty redirect
pay those cycles back on dirty publications, so the Stage-7 dirty route and
its lifecycle-owned redirect retain their exact r279 timing and addresses.

This script is static only.  It binds the exact r279 ROM and archived 8,000-
frame later-stage layout corpora, then emits only beneath repository ``tmp/``.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
DEFAULT_BASE = TMP / "stage7-lazy-disarm-r279/candidate.gb"
DEFAULT_OUT = TMP / "later-signature-pagepair-r280"

BASE_SHA256 = "649dab3b8895e680ff9e64005641de89b3ac1f66bcb417d6a1c42ce98bc30a9d"
CANDIDATE_SHA256 = "7fd7c3434d1d9336c08a9dbf0c7f00690c476bc8ae03e31eb9dd214b66d18589"
CANDIDATE_MD5 = "3e566b11f023a47c29767ff690f1c860"

BANK_SIZE = 0x4000
MIRROR_BANKS = (13, 16)
SOURCE_A = 0x7BB2
SOURCE_A_SIZE = 46
SOURCE_B = 0x7C4D
SOURCE_B_SIZE = 114
RUNTIME_ADDR = 0xDA60
RUNTIME_SIZE = SOURCE_A_SIZE + SOURCE_B_SIZE
OLD_RUNTIME_SHA256 = "d813c49c60df17c0169d9c571a3dd21c18b398357d1002a929866f94fff58b6d"
NEW_RUNTIME_SHA256 = "0a226e4fd5cf83345e82369460830e9f7798f0d905ac4acd03fb9912b7658c87"

PATCH_START = 0xDA72
PATCH_END = 0xDAB8
OLD_PATCH_SHA256 = "1f790262a7bdfe817c158ddf9e10c885cae4950a3b7b945117f689634f78f89e"
NEW_PATCH_SHA256 = "eb92fa434af21ab58fde2d94dffdee174c9d8a8876ab8e5ce49450774224de30"

OLD_A = (444, 149, 19, 251)
NEW_A = (444, 149, 19, 275)
KEY_B = (0, 59, 333, 201)

CORPORA = {
    2: (
        "stage2-isolated-entry-r263/stage2-semantic-soak-8000-r3/"
        "stage2.layout-events.tsv",
        "e88ed409a78db08ca653586c14bf99e1bfc4c9183455ee4a69999378f72ca4f2",
        77,
    ),
    3: (
        "stage2-isolated-entry-r263/stage346-semantic-soak-8000/"
        "stage3.layout-events.tsv",
        "ec176c9e1923e0438d59f4ffd37614fd8af3dba079e997ec66a67b660fc6f1da",
        314,
    ),
    4: (
        "stage2-isolated-entry-r263/stage346-semantic-soak-8000/"
        "stage4.layout-events.tsv",
        "54becf276a33dc9f51cce123d39c8ce80f58be04f4b186a534c34ae2a672c90a",
        328,
    ),
    5: (
        "stage2-isolated-entry-r263/stage57-semantic-soak-8000-r2/"
        "stage5.layout-events.tsv",
        "b9b245da250a93c7706c1be72b89d7e9ce978b8d286f7507db2de67f45f3959c",
        211,
    ),
    6: (
        "stage2-isolated-entry-r263/stage346-semantic-soak-8000/"
        "stage6.layout-events.tsv",
        "3820d3f3655e1eeac33234d9c03ae291e2115a2f0956803d14dfda124baf4d32",
        379,
    ),
    7: (
        "stage2-isolated-entry-r263/stage57-semantic-soak-8000-r2/"
        "stage7.layout-events.tsv",
        "e4ffa75069faf036db407ca7774d61077c20ffa7a21342c2825f1987b1e91c7b",
        150,
    ),
}

HEALTH = {tile: 1 for tile in (0x88, 0x89, 0x96, 0x98, 0x99)}
RARE = {
    tile: 2 for tile in (0xAE, 0xAF, 0xBE, 0xBF, 0xC6, 0xC7, 0xD6, 0xD7)
}
ARROW = {tile: 4 for tile in (0xA0, 0xA1, 0xB0, 0xB1)}
SEMANTIC = {
    2: RARE,
    3: HEALTH,
    4: {**{tile: 4 for tile in range(0x01, 0x09)}, 0x2D: 2, 0x2E: 2},
    5: HEALTH | RARE,
    6: HEALTH,
    7: ARROW | RARE,
}
LAVA = {
    5: set(range(0x02, 0x08)) | set(range(0x12, 0x18)),
    7: {0x19, 0x1A},
}


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
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
    total = (sum(rom) - rom[0x014E] - rom[0x014F]) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def runtime_from(rom: bytes, bank: int) -> bytes:
    first = bank_offset(bank, SOURCE_A)
    second = bank_offset(bank, SOURCE_B)
    return (
        rom[first:first + SOURCE_A_SIZE]
        + rom[second:second + SOURCE_B_SIZE]
    )


def build_runtime(old: bytes) -> bytes:
    if len(old) != RUNTIME_SIZE or digest(old) != OLD_RUNTIME_SHA256:
        raise AssertionError("r279 DA60 runtime preimage changed")
    start = PATCH_START - RUNTIME_ADDR
    end = PATCH_END - RUNTIME_ADDR + 1
    old_patch = old[start:end]
    if digest(old_patch) != OLD_PATCH_SHA256:
        raise AssertionError("r279 signature/compare patch preimage changed")

    # Preserve the first three sample reads in exact order.  The fourth read
    # now advances H from C1B3 to C2B3 instead of reloading HL with C29B.
    signature_a = bytes.fromhex(
        "FA 5C C3 21 35 C2 AE 21 B3 C1 AE 24 AE 47"
    )
    signature_b = old[0x22:0x32]       # $DA82-$DA91
    compare_and_dirty = old[0x32:0x56] # $DA92-$DAB5
    redirect_and_pad = old[0x56:0x59]  # $DAB6-$DAB8
    if redirect_and_pad != bytes.fromhex("18 EB 00"):
        raise AssertionError("r279 default dirty redirect moved")
    new_patch = (
        signature_a
        + signature_b
        + compare_and_dirty
        + b"\x00\x00"
        + redirect_and_pad
    )
    if len(new_patch) != len(old_patch) or digest(new_patch) != NEW_PATCH_SHA256:
        raise AssertionError("paired-page patch construction changed")
    result = old[:start] + new_patch + old[end:]
    if digest(result) != NEW_RUNTIME_SHA256:
        raise AssertionError("paired-page runtime construction changed")

    # The three mismatch branches move with the compare block and retain their
    # relative targets.  The whole dirty body moves two bytes earlier, then
    # executes two NOPs before the still-address-stable redirect.
    expected_targets = {
        0xDA92: 0xDAA7,
        0xDA97: 0xDAA6,
        0xDA9F: 0xDAA5,
    }
    for instruction, target in expected_targets.items():
        position = instruction - RUNTIME_ADDR
        if result[position] != 0x20:
            raise AssertionError(f"JR NZ opcode moved at ${instruction:04X}")
        displacement = result[position + 1]
        decoded = instruction + 2 + (displacement - 256 if displacement & 0x80 else displacement)
        if decoded != target:
            raise AssertionError(
                f"JR NZ target changed at ${instruction:04X}: ${decoded:04X}"
            )
    if result[0x54:0x59] != bytes.fromhex("00 00 18 EB 00"):
        raise AssertionError("dirty timing pad/redirect address changed")
    if result[0x59:] != old[0x59:]:
        raise AssertionError("dispatcher, arena path, or Stage7 router changed")
    return result


def xor_key(raw: bytes, offsets: tuple[int, ...]) -> int:
    value = 0
    for offset in offsets:
        value ^= raw[offset]
    return value


def semantic_plane(stage: int, raw: bytes) -> bytes:
    lut = SEMANTIC[stage]
    lava = LAVA.get(stage, set())
    return bytes(lut.get(tile, 5 if tile in lava else 0) for tile in raw)


def parse_corpus(stage: int, relative: str, expected_sha: str, expected_rows: int):
    path = TMP / relative
    payload = path.read_bytes()
    if digest(payload) != expected_sha:
        raise AssertionError(f"Stage {stage} corpus preimage changed")
    rows = []
    for number, line in enumerate(payload.decode().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) != 14:
            raise AssertionError(f"{path}:{number}: expected 14 fields")
        raw = bytes.fromhex(fields[13])
        if len(raw) != 24 * 24:
            raise AssertionError(f"{path}:{number}: raw plane is truncated")
        rows.append((
            int(fields[2], 16),
            int(fields[1], 16),
            raw,
            semantic_plane(stage, raw),
        ))
    if len(rows) != expected_rows:
        raise AssertionError(f"Stage {stage} corpus row count changed")
    return path, rows


def key_metrics(rows, samples_a: tuple[int, ...]) -> dict[str, int]:
    by_key: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
    by_plane: dict[tuple[int, bytes], set[tuple[int, int, int]]] = defaultdict(set)
    for _, room, raw, plane in rows:
        key = (room, xor_key(raw, samples_a), xor_key(raw, KEY_B))
        by_key[key].add(plane)
        by_plane[(room, plane)].add(key)
    return {
        "keys": len(by_key),
        "collisions": sum(len(values) - 1 for values in by_key.values()),
        "false_variants": sum(len(values) - 1 for values in by_plane.values()),
    }


def decision_sequence(rows, samples_a: tuple[int, ...]):
    cache: dict[int, tuple[int, int, int]] = {}
    planes: dict[int, bytes] = {}
    decisions = []
    false_hits = 0
    for map_base, room, raw, plane in rows:
        key = (xor_key(raw, samples_a), xor_key(raw, KEY_B), room)
        hit = cache.get(map_base) == key
        if hit and planes.get(map_base) != plane:
            false_hits += 1
        decisions.append(hit)
        if not hit:
            cache[map_base] = key
            planes[map_base] = plane
    return decisions, false_hits


def corpus_proof() -> dict[str, object]:
    report: dict[str, object] = {}
    for stage, (relative, expected_sha, expected_rows) in CORPORA.items():
        path, rows = parse_corpus(stage, relative, expected_sha, expected_rows)
        old_metrics = key_metrics(rows, OLD_A)
        new_metrics = key_metrics(rows, NEW_A)
        if new_metrics["collisions"] > old_metrics["collisions"] \
                or new_metrics["false_variants"] > old_metrics["false_variants"]:
            raise AssertionError(f"Stage {stage} key quality regressed")
        old_decisions, old_false = decision_sequence(rows, OLD_A)
        new_decisions, new_false = decision_sequence(rows, NEW_A)
        if new_false > old_false:
            raise AssertionError(f"Stage {stage} semantic false-hit count regressed")
        differing = [
            index for index, pair in enumerate(zip(old_decisions, new_decisions), 1)
            if pair[0] != pair[1]
        ]
        if stage == 4 and differing:
            raise AssertionError("Stage 4 cache decision sequence changed")
        if stage != 5 and differing:
            raise AssertionError(f"Stage {stage} cache decision sequence changed")
        if stage == 5 and len(differing) != 1:
            raise AssertionError("expected one safe Stage 5 decision coalescing")
        report[f"stage{stage}"] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": expected_sha,
            "rows": len(rows),
            "old": old_metrics,
            "new": new_metrics,
            "decision_differences": differing,
            "semantic_false_hits_old_new": [old_false, new_false],
        }
    return report


def build_candidate(base: bytes, runtime: bytes) -> tuple[bytes, dict[str, object]]:
    rom = bytearray(base)
    functional: set[int] = set()
    for bank in MIRROR_BANKS:
        first = bank_offset(bank, SOURCE_A)
        second = bank_offset(bank, SOURCE_B)
        old_runtime = runtime_from(base, bank)
        if old_runtime != runtime_from(base, MIRROR_BANKS[0]):
            raise AssertionError("r279 runtime source mirrors differ")
        for offset, (before, after) in enumerate(zip(old_runtime, runtime)):
            if before == after:
                continue
            source_offset = (
                first + offset if offset < SOURCE_A_SIZE
                else second + offset - SOURCE_A_SIZE
            )
            functional.add(source_offset)
        rom[first:first + SOURCE_A_SIZE] = runtime[:SOURCE_A_SIZE]
        rom[second:second + SOURCE_B_SIZE] = runtime[SOURCE_A_SIZE:]
    update_checksums(rom)
    candidate = bytes(rom)
    if digest(candidate) != CANDIDATE_SHA256 \
            or hashlib.md5(candidate).hexdigest() != CANDIDATE_MD5:
        raise AssertionError("r280 candidate identity changed")
    changed = {
        index for index, pair in enumerate(zip(base, candidate))
        if pair[0] != pair[1]
    }
    allowed = functional | {0x014D, 0x014E, 0x014F}
    if not changed <= allowed:
        raise AssertionError("r280 diff escaped source mirrors/checksums")
    return candidate, {
        "functional_bytes_changed": len(functional),
        "total_bytes_changed": len(changed),
        "changed_by_bank": {
            str(bank): sum(
                bank * BANK_SIZE <= offset < (bank + 1) * BANK_SIZE
                for offset in functional
            )
            for bank in MIRROR_BANKS
        },
        "checksum_offsets_allowed": ["$014D", "$014E", "$014F"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out_dir = require_tmp(args.out_dir)
    raise AssertionError(
        "REJECTED: compaction moves the native epilogue to $DAA1 while the "
        "r279 $DAB6 JR $EB still targets $DAA3; this corrupts the saved-register "
        "stack. Do not emit or qualify this candidate."
    )
    base = args.base.read_bytes()
    if digest(base) != BASE_SHA256:
        raise AssertionError(f"wrong exact r279 base: {digest(base)}")
    old_runtime = runtime_from(base, MIRROR_BANKS[0])
    if any(runtime_from(base, bank) != old_runtime for bank in MIRROR_BANKS):
        raise AssertionError("r279 DA60 runtime mirrors diverged")
    runtime = build_runtime(old_runtime)
    corpora = corpus_proof()
    candidate, diff = build_candidate(base, runtime)

    report = {
        "schema": "penta-later-signature-pagepair-r280-build-v1",
        "status": "STATIC_PASS_SPEED_AND_VISUAL_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "candidate_md5": CANDIDATE_MD5,
        "runtime_old_sha256": OLD_RUNTIME_SHA256,
        "runtime_new_sha256": NEW_RUNTIME_SHA256,
        "patch": {
            "range": "$DA72-$DAB8 in bank13/bank16 source mirrors",
            "old_signature_a_offsets": list(OLD_A),
            "new_signature_a_offsets": list(NEW_A),
            "signature_b_offsets_unchanged": list(KEY_B),
            "instruction": "LD HL,$C1B3; XOR [HL]; INC H; XOR [HL]",
            "cache_hit_delta_t": -8,
            "dirty_timing_pad": "$DAB4-$DAB5 NOP/NOP",
            "dirty_delta_t": 0,
        },
        "corpus_proof": corpora,
        "contracts": {
            "first_three_signature_a_reads_keep_exact_order": True,
            "stage4_decision_sequence_exact_over_8000_frame_corpus": True,
            "candidate_key_never_worsens_corpus_collision_or_variant_counts": True,
            "dirty_path_register_flag_memory_and_cycle_behavior_exact": True,
            "redirect_instruction_and_operand_remain_at_DAB6_DAB7": True,
            "dispatcher_arena_path_stage7_router_and_lazy_disarm_byte_exact": True,
            "stage7_valid_dirty_hot_path_cycle_exact_to_r279": True,
        },
        "diff": diff,
        "required_gates": [
            "Stage4 target3/right/2800 strict 0.99 speed",
            "Stage5 and Stage7 strict speed containment",
            "candidate-bound later-stage semantic/visual soak",
            "candidate-bound Stage1 visual/menu/hazard regression suite",
        ],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = out_dir / "candidate.gb"
    receipt_path = out_dir / "build-receipt.json"
    candidate_path.write_bytes(candidate)
    receipt_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
