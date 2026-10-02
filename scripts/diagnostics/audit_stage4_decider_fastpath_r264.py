#!/usr/bin/env python3
"""Statically audit a Stage-4-only cached-layout fast path on exact r264.

This is intentionally not a candidate builder.  It binds the current best ROM,
the archived 8,000-frame Stage 4 layout corpus, the installed DA60 runtime, and
the strict speed receipt.  It then records why the tempting cycle-equal router
is unsafe and specifies the emulator trace needed before a scoped candidate can
be justified.

No ROM, savestate, or emulator is written or launched by this script.  Its only
output is a JSON receipt under repository-local ``tmp/``.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

R264_SHA256 = (
    "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
)
R264_MD5 = "cd025fd5c3ccdf49ac5a9ebebceff8e5"
RUNTIME_SHA256 = (
    "765d22df24f270dd5210500f05ae101278edab35ee0c8707bed26738f90c8b5a"
)

BANK_SIZE = 0x4000
BANK13 = 13 * BANK_SIZE
SOURCE_A = 0x7BB2
SOURCE_A_END = 0x7BE0
SOURCE_B = 0x7C4D
SOURCE_B_END = 0x7CBF
RUNTIME = 0xDA60
DISPATCH = 0xDAB9
COMPARE = 0xDA92

RAW_SIZE = 24 * 24
CURRENT_A = (444, 149, 19, 251)
CURRENT_B = (0, 59, 333, 201)
STAGE4_A = (1,)
STAGE4_B = (357,)

EXPECTED_RUNTIME_HEAD = bytes.fromhex(
    "C5 D5 E5 B7 28 04 00 00 00 AF E0 E0"
)
EXPECTED_DISPATCH_HEAD = bytes.fromhex(
    "06 05 FA 80 D8 D6 03 FE 06 38 10"
)
EXPECTED_FFE0_SCENE_CONSUMER = bytes.fromhex(
    "F5 F0 E0 EA 80 D8 F1 C9"
)
EXPECTED_INSTALLER = bytes.fromhex(
    "C5 D5 E5 "
    "21 00 7B 11 00 DA 01 5D 00 CD B3 09 "
    "21 B2 7B 11 60 DA 01 2E 00 CD B3 09 "
    "21 4D 7C 11 8E DA 01 72 00 CD B3 09 "
    "21 3A 56 11 80 DB 01 23 00 CD B3 09 "
    "C3 5C 57"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if bank == 0:
        return address
    return bank * BANK_SIZE + address - 0x4000


def xor_key(raw: bytes, samples: tuple[int, ...]) -> int:
    value = 0
    for offset in samples:
        value ^= raw[offset]
    return value


def stage4_plane(raw: bytes) -> bytes:
    """Reproduce the production Stage 4 semantic LUT for the trace."""
    lut = bytearray(256)
    for tile in range(0x01, 0x09):
        lut[tile] = 4
    lut[0x2D] = 2
    lut[0x2E] = 2
    return bytes(lut[tile] for tile in raw)


def parse_stage4_corpus(path: Path) -> list[tuple[int, bytes, bytes]]:
    records = set()
    for number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) < 14:
            continue
        raw = bytes.fromhex(fields[-1])
        if len(raw) != RAW_SIZE:
            raise AssertionError(
                f"{path}:{number}: expected {RAW_SIZE} raw bytes, got {len(raw)}"
            )
        room = int(fields[1], 16)
        records.add((room, raw, stage4_plane(raw)))
    if not records:
        raise AssertionError(f"no Stage 4 records in {path}")
    return sorted(records)


def key_metrics(
    records: list[tuple[int, bytes, bytes]],
    samples_a: tuple[int, ...],
    samples_b: tuple[int, ...],
) -> dict[str, object]:
    semantics_by_key: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
    keys_by_semantic: dict[tuple[int, bytes], set[tuple[int, int, int]]] = (
        defaultdict(set)
    )
    raws_by_key: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
    for room, raw, semantic in records:
        key = (room, xor_key(raw, samples_a), xor_key(raw, samples_b))
        semantics_by_key[key].add(semantic)
        keys_by_semantic[(room, semantic)].add(key)
        raws_by_key[key].add(raw)

    collisions = sum(len(values) - 1 for values in semantics_by_key.values())
    false_variants = sum(len(values) - 1 for values in keys_by_semantic.values())
    examples = []
    for key, semantics in sorted(semantics_by_key.items()):
        if len(semantics) < 2:
            continue
        examples.append(
            {
                "room": f"${key[0]:02X}",
                "signature_a": f"${key[1]:02X}",
                "signature_b": f"${key[2]:02X}",
                "semantic_sha256": sorted(sha256(value) for value in semantics),
                "raw_sha256": sorted(sha256(value) for value in raws_by_key[key]),
            }
        )
    return {
        "samples_a": list(samples_a),
        "samples_b": list(samples_b),
        "collisions": collisions,
        "false_variants": false_variants,
        "collision_examples": examples,
    }


def load_speed_row(path: Path) -> tuple[dict[str, object], dict[str, object]]:
    manifest = json.loads(path.read_text())
    if manifest.get("dx_rom_md5") != R264_MD5:
        raise AssertionError("strict speed receipt is not bound to exact r264")
    rows = [row for row in manifest.get("rows", []) if row.get("stage") == 4]
    if len(rows) != 1:
        raise AssertionError("strict speed receipt lacks one Stage 4 row")
    row = rows[0]
    original = row["original"]
    dx = row["dx"]
    return manifest, {
        "receipt": str(path.relative_to(ROOT)),
        "receipt_sha256": sha256(path.read_bytes()),
        "ratio": row["ratio"],
        "original_main_loop_hits": original["main_loop_hits"],
        "dx_main_loop_hits": dx["main_loop_hits"],
        "minimum_hits_for_0_99": (99 * original["main_loop_hits"] + 99) // 100,
        "loops_needed": (
            (99 * original["main_loop_hits"] + 99) // 100
            - dx["main_loop_hits"]
        ),
        "original_scroll_changes": original["scroll_changes"],
        "dx_scroll_changes": dx["scroll_changes"],
        "deterministic_replay": row["deterministic_replay"],
    }


def audit(base: bytes, corpus_path: Path, speed_path: Path) -> dict[str, object]:
    digest = sha256(base)
    if digest != R264_SHA256:
        raise AssertionError(f"wrong r264 base: {digest}")
    if hashlib.md5(base).hexdigest() != R264_MD5:
        raise AssertionError("r264 MD5 preimage changed")

    source_a = base[
        bank_offset(13, SOURCE_A):bank_offset(13, SOURCE_A_END)
    ]
    source_b = base[
        bank_offset(13, SOURCE_B):bank_offset(13, SOURCE_B_END)
    ]
    runtime = source_a + source_b
    if len(runtime) != 160 or sha256(runtime) != RUNTIME_SHA256:
        raise AssertionError("DA60 runtime source preimage changed")
    if runtime[:len(EXPECTED_RUNTIME_HEAD)] != EXPECTED_RUNTIME_HEAD:
        raise AssertionError("DA60 hot-path header preimage changed")
    dispatch_offset = DISPATCH - RUNTIME
    if runtime[
        dispatch_offset:dispatch_offset + len(EXPECTED_DISPATCH_HEAD)
    ] != EXPECTED_DISPATCH_HEAD:
        raise AssertionError("DAB9 scene dispatcher preimage changed")
    if runtime[dispatch_offset - 1] != 0:
        raise AssertionError("expected one-byte DA60/dispatcher pad is occupied")

    installer_off = bank_offset(13, 0x7CBF)
    installer = base[installer_off:installer_off + len(EXPECTED_INSTALLER)]
    if installer != EXPECTED_INSTALLER:
        raise AssertionError("WRAM installer preimage changed")

    ffe0_consumer_off = 0x7CDA
    if base[
        ffe0_consumer_off:ffe0_consumer_off + len(EXPECTED_FFE0_SCENE_CONSUMER)
    ] != EXPECTED_FFE0_SCENE_CONSUMER:
        raise AssertionError("bank1 FFE0-to-D880 consumer preimage changed")

    records = parse_stage4_corpus(corpus_path)
    current = key_metrics(records, CURRENT_A, CURRENT_B)
    proposed = key_metrics(records, STAGE4_A, STAGE4_B)
    if proposed["collisions"] != 0 or proposed["false_variants"] != 0:
        raise AssertionError("Stage 4 two-sample key is no longer corpus-safe")

    _, speed = load_speed_row(speed_path)
    if speed["loops_needed"] != 1:
        raise AssertionError("Stage 4 no longer has the expected one-loop deficit")

    return {
        "schema": "penta-stage4-decider-static-audit-r264-v1",
        "status": "NO-STATIC-SAFE-CANDIDATE",
        "emulator_invoked": False,
        "candidate_written": False,
        "base": {
            "sha256": digest,
            "md5": hashlib.md5(base).hexdigest(),
        },
        "speed_evidence": speed,
        "corpus": {
            "path": str(corpus_path.relative_to(ROOT)),
            "sha256": sha256(corpus_path.read_bytes()),
            "unique_records": len(records),
            "current_key": current,
            "stage4_two_sample_key": proposed,
            "claim_scope": "archived deterministic 8,000-frame Stage 4 corpus",
        },
        "runtime_preimage": {
            "source_fragments": [
                "bank13:$7BB2-$7BDF -> WRAM $DA60-$DA8D",
                "bank13:$7C4D-$7CBE -> WRAM $DA8E-$DAFF",
            ],
            "runtime_sha256": sha256(runtime),
            "runtime_bytes": len(runtime),
            "decider_to_dispatch_padding_bytes": 1,
            "compare_entry": f"${COMPARE:04X}",
            "installer_first_copy_length": "$005D",
            "installer_leaves_da5d_da5f_uninitialized": True,
            "ffe0_scene_consumer": {
                "address": "bank1:$7CDA-$7CE1",
                "bytes": EXPECTED_FFE0_SCENE_CONSUMER.hex(" ").upper(),
                "behavior": "PUSH AF; A=FFE0; D880=A; POP AF; RET",
            },
        },
        "fast_path_opportunity": {
            "stage4_samples": ["$C1A1", "$C305"],
            "existing_metadata_retained": ["physical-map record", "FFBD room"],
            "minimal_external_helper_bytes": 20,
            "minimal_external_helper_t_cycles_to_compare": 96,
            "current_header_metadata_signature_t_cycles_to_compare": 224,
            "estimated_net_saving_with_near_JP_trampoline_t_cycles": 72,
            "interpretation": (
                "The receipt-bounded key has ample static headroom to recover "
                "one loop, but throughput remains phase-sensitive and must be measured."
            ),
        },
        "rejected_routes": [
            {
                "route": "replace non-Stage2 NOP/NOP/NOP/XOR with CP 2/JR Z",
                "why_rejected": (
                    "It is cycle-equal for non-target stages only by omitting XOR. "
                    "Cache hits then leave normalized stage identity in FFE0. "
                    "Bank1:$7CDA is an exact live FFE0-to-D880 consumer, so this "
                    "changes shared scene state rather than merely scratch telemetry."
                ),
            },
            {
                "route": "retain XOR after CP 2/JR Z",
                "why_rejected": (
                    "It adds 4 T-cycles to Stages 3/5/6/7 on every decision, "
                    "violating Stage2/5/7 containment and the receipt-qualified phase."
                ),
            },
            {
                "route": "compensate with reordered generic signature loads",
                "why_rejected": (
                    "Although XOR is commutative, reordering interruptible C1A0 "
                    "reads changes snapshot boundaries for every dungeon and Crystal. "
                    "That is not a Stage-4-only static proof."
                ),
            },
            {
                "route": "install a Stage4 runtime on transition and restore later",
                "why_rejected": (
                    "Self-modifying scene overlays add reset, savestate, and transition "
                    "restoration obligations not covered by the static corpus."
                ),
            },
            {
                "route": "revive r232 OAM helper",
                "why_rejected": "explicitly prohibited; visually failed lineage",
            },
        ],
        "required_trace_before_candidate": {
            "rom_sha256": R264_SHA256,
            "scenes": [
                "Stage 2 ($03)",
                "Stage 4 ($05)",
                "Stage 5 ($06)",
                "Stage 7 ($08)",
                "Crystal Dragon ($0E)",
            ],
            "breakpoints": [
                {
                    "address": "$42A7",
                    "record": "caller return, destination H, SP, D880, FFE0",
                },
                {
                    "address": "$DA60",
                    "record": "A/F/BC/DE/HL/SP and top three return words",
                },
                {
                    "address": "$DA92",
                    "record": (
                        "B/C, DE cache record, FFBD, C1A1, C305, FFE0, "
                        "decision index"
                    ),
                },
                {
                    "address": "$42FC",
                    "record": "dirty compiler entry and FFE0",
                },
                {
                    "address": "$7CDA",
                    "record": (
                        "all hits plus the most recent DA60 decision index; prove "
                        "whether an unchanged decision's FFE0 lifetime overlaps it"
                    ),
                },
            ],
            "acceptance": [
                "two deterministic replays per scene have identical trace SHA256",
                "identify a Stage4-exclusive caller/entry or a proven-dead scratch lifetime",
                "Stages 2/5/7 and Crystal retain byte-for-byte decision outputs and exact cycles",
                "Stage 4 reaches at least 757/764 main-loop hits with scroll 14/14",
                "Stage 4 semantic soak retains zero missed desired-plane transitions",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        type=Path,
        default=ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb",
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=(
            ROOT
            / "tmp/stage2-isolated-entry-r263/stage346-semantic-soak-8000/"
            "stage4.layout-events.tsv"
        ),
    )
    parser.add_argument(
        "--speed",
        type=Path,
        default=(
            ROOT
            / "tmp/stage1-menu-hidden-repair-r264/"
            "stage2-stage4-speed-strict99-r1/manifest.json"
        ),
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=ROOT / "tmp/stage4-decider-static-audit-r264/receipt.json",
    )
    args = parser.parse_args()

    receipt = audit(args.base.read_bytes(), args.corpus, args.speed)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
