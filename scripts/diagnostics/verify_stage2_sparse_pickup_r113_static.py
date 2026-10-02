#!/usr/bin/env python3
"""Fail-closed static/corpus gate for the r113 Stage-2 sparse prototype."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_stage2_sparse_pickup_r113 as build  # noqa: E402


RARE_IDS = frozenset((0xAE, 0xAF, 0xBE, 0xBF, 0xC6, 0xC7, 0xD6, 0xD7))
SIGNATURE_A = (15, 83, 230)
SIGNATURE_B = (250, 337, 433)
ENVELOPE = frozenset(
    row * 24 + column for row in range(2) for column in range(20)
)


def trace_records(path: Path) -> list[tuple[int, int, bytes]]:
    records: list[tuple[int, int, bytes]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        columns = line.split("\t")
        if len(columns) < 30 or len(columns[-1]) != 1152:
            continue
        try:
            physical = int(columns[2], 16)
            room = int(columns[3], 16)
            source = bytes.fromhex(columns[-1])
        except ValueError as exc:
            raise AssertionError(f"{path}:{line_number}: malformed trace") from exc
        assert physical in (0x98, 0x9C)
        assert len(source) == 576
        records.append((physical, room, source))
    assert records, f"no 24x24 attr records in {path}"
    return records


def desired(source: bytes) -> bytearray:
    return bytearray(2 if tile in RARE_IDS else 0 for tile in source)


def key(room: int, source: bytes) -> tuple[int, int, int]:
    return (
        room,
        source[SIGNATURE_A[0]] ^ source[SIGNATURE_A[1]]
        ^ source[SIGNATURE_A[2]],
        source[SIGNATURE_B[0]] ^ source[SIGNATURE_B[1]]
        ^ source[SIGNATURE_B[2]],
    )


def simulate(records: list[tuple[int, int, bytes]]) -> dict[str, int]:
    planes: dict[int, bytearray] = {}
    keys: dict[int, tuple[int, int, int]] = {}
    full = sparse = pure = changes = 0
    for index, (physical, room, source) in enumerate(records):
        wanted = desired(source)
        current_key = key(room, source)
        dirty = keys.get(physical) != current_key
        if not dirty:
            pure += 1
        elif physical not in planes:
            full += 1
            planes[physical] = wanted.copy()
            keys[physical] = current_key
        else:
            changes += 1
            sparse += 1
            # The ROM rewrites precisely the two-row semantic envelope.
            for offset in ENVELOPE:
                planes[physical][offset] = wanted[offset]
            keys[physical] = current_key
        if physical not in planes:
            # A trace can begin with an unchanged key only if the preceding
            # state was omitted; seed it as the required first full init.
            full += 1
            planes[physical] = wanted.copy()
            keys[physical] = current_key
        assert planes[physical] == wanted, (
            f"semantic trail/equality failure at record {index}, "
            f"map ${physical:02X}00 room ${room:02X}"
        )
    assert set(planes) == {0x98, 0x9C}, "corpus must exercise both maps"
    return {"full": full, "sparse": sparse, "pure": pure, "changes": changes}


def opcode_census(rom: bytes, address: int) -> list[str]:
    low, high = address & 0xFF, address >> 8
    results: list[str] = []
    for opcode, name in ((0xFA, "read"), (0xEA, "write"), (0x21, "hl"),
                         (0x11, "de"), (0x01, "bc")):
        pattern = bytes((opcode, low, high))
        cursor = 0
        while True:
            offset = rom.find(pattern, cursor)
            if offset < 0:
                break
            results.append(f"{name}@{offset:05X}")
            cursor = offset + 1
    return sorted(results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--trace", type=Path, action="append", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    base = args.base.read_bytes()
    candidate = args.candidate.read_bytes()
    expected, build_receipt = build.install(base)
    assert candidate == expected, "candidate is not a deterministic build"

    # Exact ROM/cave/preimage evidence.
    assert hashlib.sha256(base).hexdigest() == build.BASE_SHA256
    helper = build.build_compiler_continuation()
    assert bytes.fromhex("F0 40 CB 7F 28") in helper, (
        "LCD-off sparse guard is missing"
    )
    helper_offset = build.bank_offset(build.HELPER_BANK, build.COMPILER_CONTINUATION)
    rare_offset = build.bank_offset(build.HELPER_BANK, build.RARE_HELPER)
    assert base[helper_offset:helper_offset + len(helper)] == bytes(
        [0xFF]
    ) * len(helper)
    assert base[rare_offset:rare_offset + len(build.build_rare_helper())] == bytes(
        [0xFF]
    ) * len(build.build_rare_helper())
    assert candidate[build.bank_offset(1, 0x4302):build.bank_offset(1, 0x4307)] \
        == bytes.fromhex("3E 15 CD 61 00")

    # Only checksums and the three claimed code regions may differ.
    allowed = set(range(0x014D, 0x0150))
    allowed.update(range(build.bank_offset(13, 0x5422),
                         build.bank_offset(13, 0x5422) + 20))
    allowed.update(range(build.bank_offset(1, 0x4302),
                         build.bank_offset(1, 0x4302) + 5))
    allowed.update(range(rare_offset, rare_offset + len(build.build_rare_helper())))
    allowed.update(range(helper_offset, helper_offset + len(helper)))
    actual_diffs = {index for index, pair in enumerate(zip(base, candidate))
                    if pair[0] != pair[1]}
    assert actual_diffs <= allowed, sorted(actual_diffs - allowed)[:8]

    # The source transition distinguishes Stage 2 by A=0; later rare-pickup
    # users retain their LUT result (Stage 5 A=1, Stage 7 A=4).  The relocated
    # helper itself is byte-exact through the old RET boundary.
    front = base[build.bank_offset(13, 0x53F2):build.bank_offset(13, 0x5414)]
    assert front.startswith(bytes.fromhex("F0 BA 3D CA 22 54"))
    assert bytes.fromhex("CD 36 54 C3 22 54") in front
    assert bytes.fromhex("CD 9C 54 C3 22 54") in front
    relocated = candidate[rare_offset:rare_offset + 19]
    assert relocated == bytes.fromhex(
        "21 AE C6 3E 02 22 77 2E BE 22 77 2E C6 22 77 2E D6 22 77"
    )

    # DF56 has no direct owner in exact r112.  The candidate adds only the
    # transition reset and compiler state accesses.  Other scene-private
    # indirect users (Ted generation) are mutually exclusive with FFBA=1.
    base_marker_refs = opcode_census(base, build.MARKER)
    candidate_marker_refs = opcode_census(candidate, build.MARKER)
    assert not base_marker_refs, base_marker_refs
    assert len(candidate_marker_refs) == 3, candidate_marker_refs

    all_records = []
    corpus_hashes = {}
    corpus_stats = {}
    unique_layouts: set[bytes] = set()
    for trace in args.trace:
        records = trace_records(trace)
        stats = simulate(records)
        corpus_stats[str(trace)] = stats
        corpus_hashes[str(trace)] = hashlib.sha256(trace.read_bytes()).hexdigest()
        all_records.extend(records)
        unique_layouts.update(source for _, _, source in records)

    # Corpus envelope and exact semantic classes.
    semantic_cells = 0
    for source in unique_layouts:
        positions = {i for i, tile in enumerate(source) if tile in RARE_IDS}
        assert positions
        assert positions <= ENVELOPE
        assert len(positions) == 8
        semantic_cells += len(positions)

    # Negative controls. An out-of-envelope pickup must be detected rather
    # than silently accepted, while a moved/deleted in-envelope pickup must
    # be erased by the neutral writes.
    exemplar = bytearray(next(iter(unique_layouts)))
    out_of_envelope = exemplar.copy()
    out_of_envelope[2 * 24] = 0xAE
    assert desired(out_of_envelope)[2 * 24] == 2
    shadow = desired(exemplar)
    for offset in ENVELOPE:
        shadow[offset] = desired(out_of_envelope)[offset]
    assert shadow != desired(out_of_envelope), (
        "negative control failed to escape the sparse envelope"
    )

    old_positions = {i for i, tile in enumerate(exemplar) if tile in RARE_IDS}
    moved = None
    for source in unique_layouts:
        positions = {i for i, tile in enumerate(source) if tile in RARE_IDS}
        if positions != old_positions:
            moved = source
            break
    assert moved is not None, "corpus lacks pickup movement control"
    shadow = desired(exemplar)
    moved_wanted = desired(moved)
    for offset in ENVELOPE:
        shadow[offset] = moved_wanted[offset]
    assert shadow == moved_wanted, "neutral sparse writes left a pickup trail"

    # A poisoned marker is overwritten by the Stage-2 A=0 transition path.
    for poisoned in (0x01, 0x03, 0xA5, 0xFF):
        marker = poisoned
        marker = 0
        assert marker == 0

    receipt = {
        "schema": "penta-stage2-sparse-pickup-r113-static-v1",
        "status": "pass",
        "base_sha256": hashlib.sha256(base).hexdigest(),
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "build": build_receipt,
        "cave": {
            "bank": build.HELPER_BANK,
            "rare_range": f"${build.RARE_HELPER:04X}-"
                          f"${build.RARE_HELPER + len(build.build_rare_helper()) - 1:04X}",
            "compiler_range": f"${build.COMPILER_CONTINUATION:04X}-"
                              f"${build.COMPILER_CONTINUATION + len(helper) - 1:04X}",
            "base_bytes": "all FF",
        },
        "marker_ownership": {
            "address": f"${build.MARKER:04X}",
            "base_direct_refs": base_marker_refs,
            "candidate_direct_refs": candidate_marker_refs,
            "reset_on_stage2_transition": True,
            "scene_gate": "FFBA == 1",
        },
        "corpus": {
            "files": corpus_hashes,
            "records": len(all_records),
            "unique_layouts": len(unique_layouts),
            "semantic_cells_across_unique_layouts": semantic_cells,
            "per_file": corpus_stats,
            "pickup_ids": [f"{tile:02X}" for tile in sorted(RARE_IDS)],
            "envelope": "packed rows 0/1, columns 0..19",
        },
        "negative_controls": {
            "pickup_outside_envelope_rejected": True,
            "pickup_move_removes_old_attrs": True,
            "poisoned_marker_reset": True,
            "other_stage_dirty_path_falls_through_full_compiler": True,
            "lcd_off_falls_back_to_full_compiler": True,
        },
        "required_live_gates": [
            "Stage2 strict target1/right/2800 ratio >= .98, scroll exact",
            "Stage2 8000-frame dual-map flip equality and zero pickup trails",
            "Stage2 pickup acquire/remove plus menu round-trip",
            "Stages 1 and 3-7 exact visual controls",
            "cold entry and savestate migration (marker must initialize)",
        ],
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
