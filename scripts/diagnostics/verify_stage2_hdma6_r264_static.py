#!/usr/bin/env python3
"""Fail-closed static qualification for the Stage-2 HDMA path in r264.

This does not build or mutate a ROM.  It proves that exact r264 is the
deterministic r258 -> r260 -> r263 -> r264 build chain, that the Stage-2-only
six-row publisher survived the visual repair byte-for-byte, and that the
historical Stage-2 layout corpus fits the published semantic envelope.

Live emulator and hardware qualification remains mandatory.  In particular,
this verifier cannot prove HBlank timing or active-map atomicity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_stage1_menu_hidden_repair_r264 as r264_build  # noqa: E402
import build_stage2_isolated_entry_r263 as r263_build  # noqa: E402
import build_stage2_runtime_hdma6_r260 as r260_build  # noqa: E402


R264_SHA256 = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
R263_SHA256 = r264_build.BASE_SHA256
R260_SHA256 = r263_build.BASE_SHA256
R258_SHA256 = r260_build.BASE_SHA256
RARE_IDS = frozenset((0xAE, 0xAF, 0xBE, 0xBF, 0xC6, 0xC7, 0xD6, 0xD7))
SEMANTIC_ROWS = range(6)
SEMANTIC_ENVELOPE = frozenset(
    row * 24 + column for row in SEMANTIC_ROWS for column in range(24)
)
SIGNATURE_A = (15, 83, 230)
SIGNATURE_B = (250, 337, 433)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
        if physical not in (0x98, 0x9C) or len(source) != 576:
            raise AssertionError(f"{path}:{line_number}: invalid map record")
        records.append((physical, room, source))
    if not records:
        raise AssertionError(f"no 24x24 records in {path}")
    return records


def desired(source: bytes) -> bytearray:
    # Stage 2's rare-pickup LUT is the only non-neutral BG semantic class.
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
    """Model first-full-per-map followed by exact six-row publications."""
    planes: dict[int, bytearray] = {}
    keys: dict[int, tuple[int, int, int]] = {}
    full = sparse = pure = changes = 0
    for index, (physical, room, source) in enumerate(records):
        wanted = desired(source)
        current_key = key(room, source)
        dirty = keys.get(physical) != current_key
        if physical not in planes:
            full += 1
            planes[physical] = wanted.copy()
            keys[physical] = current_key
        elif dirty:
            changes += 1
            sparse += 1
            for offset in SEMANTIC_ENVELOPE:
                planes[physical][offset] = wanted[offset]
            keys[physical] = current_key
        else:
            pure += 1
        if planes[physical] != wanted:
            raise AssertionError(
                f"semantic trail/equality failure at record {index}, "
                f"map ${physical:02X}00 room ${room:02X}"
            )
    if set(planes) != {0x98, 0x9C}:
        raise AssertionError("corpus did not exercise both physical maps")
    return {"full": full, "sparse": sparse, "pure": pure, "changes": changes}


def exact_slice(rom: bytes, bank: int, address: int, payload: bytes, name: str) -> None:
    offset = r260_build.bank_offset(bank, address)
    actual = rom[offset:offset + len(payload)]
    if actual != payload:
        raise AssertionError(f"{name} differs at bank{bank}:${address:04X}")


def mutate_and_expect_failure(check) -> bool:
    try:
        check()
    except AssertionError:
        return True
    raise AssertionError("negative control was not rejected")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate", type=Path,
        default=Path("tmp/stage1-menu-hidden-repair-r264/candidate.gb"),
    )
    parser.add_argument(
        "--r258", type=Path,
        default=Path("tmp/stage2-runtime-unrolled-abi-r258/candidate.gb"),
    )
    parser.add_argument(
        "--r263", type=Path,
        default=Path("tmp/stage2-isolated-entry-r263/candidate.gb"),
    )
    parser.add_argument(
        "--corpus-index", type=Path,
        default=Path("tmp/stage2-sparse-pickup-r113/static-receipt.json"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage2-hdma6-r264/static-receipt.json"),
    )
    args = parser.parse_args()

    candidate = args.candidate.read_bytes()
    r258 = args.r258.read_bytes()
    r263_file = args.r263.read_bytes()
    if sha256(candidate) != R264_SHA256:
        raise AssertionError(f"wrong r264 candidate: {sha256(candidate)}")
    if sha256(r258) != R258_SHA256:
        raise AssertionError(f"wrong r258 chain base: {sha256(r258)}")
    if sha256(r263_file) != R263_SHA256:
        raise AssertionError(f"wrong r263 lineage ROM: {sha256(r263_file)}")

    # Re-run every strict installer.  This re-proves the r260 publisher cave
    # preimage, r263 generated-record ownership, and r264 menu-tail preimage.
    rebuilt_r260, r260_receipt = r260_build.install(r258)
    if sha256(rebuilt_r260) != R260_SHA256:
        raise AssertionError("deterministic r260 rebuild changed")
    rebuilt_r263, r263_receipt = r263_build.install(rebuilt_r260)
    if rebuilt_r263 != r263_file:
        raise AssertionError("deterministic r263 rebuild differs from lineage ROM")
    rebuilt_r264, r264_receipt = r264_build.install(rebuilt_r263)
    if rebuilt_r264 != candidate:
        raise AssertionError("r264 is not the deterministic qualified chain")

    runtime_length = len(r260_build.r258_runtime_copy())
    runtime_active = r260_build.build_runtime()
    runtime = runtime_active + bytes(runtime_length - len(runtime_active))
    publisher = r260_build.build_publisher()
    old_entry_length = len(r263_build.build_rare_entry(runtime_length))
    entry_active = r263_build.build_stage2_entry(runtime_length)
    entry = entry_active + bytes(old_entry_length - len(entry_active))
    trampoline_asm = r263_build.Asm(r263_build.TRAMPOLINE)
    r263_build.map_jump(
        trampoline_asm, r263_build.BANK, r263_build.RARE_ENTRY
    )
    trampoline = trampoline_asm.finish()

    exact_slice(candidate, r260_build.BANK, r260_build.SPECIAL_BLOB,
                runtime, "Stage2 runtime")
    exact_slice(candidate, r260_build.BANK, r260_build.PUBLISH_ENTRY,
                publisher, "six-row publisher")
    exact_slice(candidate, r263_build.BANK, r263_build.RARE_ENTRY,
                entry, "Stage2-only entry")
    exact_slice(candidate, 13, 0x5422, r263_build.ORIGINAL_RARE,
                "Stage5/7 original rare helper")
    exact_slice(candidate, 13, r263_build.STAGE2_BRANCH,
                bytes.fromhex("CA 5D 55"), "Stage2 dispatcher")
    exact_slice(candidate, 13, r263_build.TRAMPOLINE, trampoline,
                "Stage2 mapper trampoline")
    if candidate[r264_build.MENU_CLOSE_TAIL:r264_build.MENU_CLOSE_TAIL + 4] \
            != r264_build.NATIVE_HIDDEN_HANDOFF:
        raise AssertionError("r264 hidden-map menu repair is absent")

    # r264 may differ from visually qualified r263 only at the named menu
    # handoff and checksums.  In particular, banks 13/21 and all Stage2 code
    # must be byte-identical.
    lineage_diffs = [
        index for index, pair in enumerate(zip(r263_file, candidate))
        if pair[0] != pair[1]
    ]
    expected_lineage_diffs = [0x14E, 0x14F, 0x77A8, 0x77A9, 0x77AA]
    if lineage_diffs != expected_lineage_diffs:
        raise AssertionError(f"unexpected r263->r264 changes: {lineage_diffs}")

    # Structural semantics: 24 compiler calls count down to 18, the first
    # full publication is tracked independently per physical map, and the
    # publisher owns one 12-block HBlank transfer to exact FFA5&FE.
    structural_patterns = {
        "stage_gate": bytes.fromhex("F0 BA FE 01"),
        "ready_state_read": bytes.fromhex("FA 7F D4 4F"),
        "physical_map_bit": bytes.fromhex("F0 A5 CB 57"),
        "six_row_boundary": bytes.fromhex("F0 E0 FE 12"),
        "publisher_map": bytes.fromhex("01 00 58 C5 3E 15 C3 61 00"),
        "publisher_source": bytes.fromhex("3E D0 E0 51 AF E0 52"),
        "exact_destination": bytes.fromhex("F0 A5 E6 FE E0 53"),
        "hblank_12_blocks": bytes.fromhex("3E 8B E0 55"),
        "hdma_completion_wait": bytes.fromhex("F0 55 CB 7F 28"),
        "restore_vbk_svbk": bytes.fromhex("AF E0 4F 3E 01 E0 70"),
    }
    for name, pattern in structural_patterns.items():
        owner = runtime if name in {
            "stage_gate", "ready_state_read", "physical_map_bit",
            "six_row_boundary", "publisher_map",
        } else publisher
        if pattern not in owner:
            raise AssertionError(f"missing {name} contract")

    corpus_index = json.loads(args.corpus_index.read_text())
    corpus_files = corpus_index["corpus"]["files"]
    corpus_stats: dict[str, dict[str, int]] = {}
    corpus_hashes: dict[str, str] = {}
    unique_layouts: set[bytes] = set()
    record_count = 0
    for name, expected_hash in corpus_files.items():
        path = Path(name)
        actual_hash = sha256(path.read_bytes())
        if actual_hash != expected_hash:
            raise AssertionError(f"corpus changed: {path}")
        records = trace_records(path)
        corpus_stats[name] = simulate(records)
        corpus_hashes[name] = actual_hash
        record_count += len(records)
        unique_layouts.update(source for _, _, source in records)

    semantic_cells = 0
    for source in unique_layouts:
        positions = {i for i, tile in enumerate(source) if tile in RARE_IDS}
        if not positions:
            raise AssertionError("Stage2 corpus layout has no rare family")
        if not positions <= SEMANTIC_ENVELOPE:
            raise AssertionError("Stage2 semantic cell escapes rows 0..5")
        semantic_cells += len(positions)

    # Negative controls exercise the verifier, not the ROM.  A semantic tile
    # in row 6 must escape the six-row overwrite, while moved/deleted cells
    # inside the envelope must erase cleanly.  Byte mutations must also break
    # the exact architecture and menu containment checks.
    exemplar = bytearray(next(iter(unique_layouts)))
    escaped = exemplar.copy()
    escaped[6 * 24] = 0xAE
    shadow = desired(exemplar)
    for offset in SEMANTIC_ENVELOPE:
        shadow[offset] = desired(escaped)[offset]
    if shadow == desired(escaped):
        raise AssertionError("row-6 semantic escape negative control failed")

    old_positions = {i for i, tile in enumerate(exemplar) if tile in RARE_IDS}
    moved = next(
        source for source in unique_layouts
        if {i for i, tile in enumerate(source) if tile in RARE_IDS}
        != old_positions
    )
    shadow = desired(exemplar)
    moved_wanted = desired(moved)
    for offset in SEMANTIC_ENVELOPE:
        shadow[offset] = moved_wanted[offset]
    if shadow != moved_wanted:
        raise AssertionError("six-row overwrite leaves a semantic trail")

    publisher_offset = r260_build.bank_offset(
        r260_build.BANK, r260_build.PUBLISH_ENTRY
    )
    command_index = publisher.index(bytes.fromhex("3E 8B E0 55")) + 1
    bad_dma = bytearray(candidate)
    bad_dma[publisher_offset + command_index] = 0x0B
    dma_control = mutate_and_expect_failure(
        lambda: exact_slice(bytes(bad_dma), r260_build.BANK,
                            r260_build.PUBLISH_ENTRY, publisher,
                            "mutated DMA command")
    )
    bad_menu = bytearray(candidate)
    bad_menu[r264_build.MENU_CLOSE_TAIL:r264_build.MENU_CLOSE_TAIL + 4] \
        = r264_build.FORCED_VISIBLE_REPAIR
    menu_control = mutate_and_expect_failure(
        lambda: (_ for _ in ()).throw(AssertionError("old menu tail"))
        if bytes(bad_menu[r264_build.MENU_CLOSE_TAIL:
                          r264_build.MENU_CLOSE_TAIL + 4])
        != r264_build.NATIVE_HIDDEN_HANDOFF else None
    )

    prior_speed = json.loads(Path(
        "tmp/stage2-isolated-entry-r263/stage2-speed-qualified/manifest.json"
    ).read_text())["rows"][0]
    r264_speed = json.loads(Path(
        "tmp/stage1-menu-hidden-repair-r264/stage12-speed/manifest.json"
    ).read_text())["rows"][1]
    promoted_baseline = json.loads(Path(
        "tmp/agent-stage-speed/stage2-promoted-repro-r1/manifest.json"
    ).read_text())["rows"][0]

    receipt = {
        "schema": "penta-stage2-hdma6-r264-static-v1",
        "status": "static-pass-live-qualification-required",
        "candidate_sha256": sha256(candidate),
        "candidate_is_exact_r264_no_rom_changes": True,
        "deterministic_chain": {
            "r258": R258_SHA256,
            "r260": R260_SHA256,
            "r263": R263_SHA256,
            "r264": R264_SHA256,
            "r260_build": r260_receipt,
            "r263_build": r263_receipt,
            "r264_build": r264_receipt,
        },
        "architecture": {
            "scope": "Stage2 only",
            "first_publication": "one full 24x24 attr plane per physical map",
            "steady_publication": "packed rows 0..5, all 24 cells",
            "staging": "SVBK3:$D000-$D0BF",
            "publisher": "bank21:$5800-$582D",
            "dma": "$8B HBlank (12 blocks / 192 bytes)",
            "destination": "$FFA5 & $FE -> $9800/$9C00",
            "other_stage_fallback": "restore the preexisting runtime entry",
            "stage5_stage7_helper_byte_exact": True,
            "r264_menu_hidden_map_fix_byte_exact": True,
            "runtime_active_bytes": len(runtime_active),
            "runtime_copy_bytes": runtime_length,
            "stage2_entry_active_bytes": len(entry_active),
            "stage2_entry_copy_bytes": len(entry),
            "publisher_bytes": len(publisher),
            "trampoline_bytes": len(trampoline),
            "patterns": {name: pattern.hex(" ").upper()
                         for name, pattern in structural_patterns.items()},
        },
        "cave_and_preimage_proof": {
            "r260_installer_replayed": True,
            "publisher_base_was_all_ff": True,
            "r263_generated_record_preimage_replayed": True,
            "r263_trampoline_preexisting_refs":
                r263_receipt["trampoline_preexisting_absolute_refs"],
            "r263_to_r264_changed_offsets":
                [f"0x{offset:05X}" for offset in lineage_diffs],
            "banks13_and21_unchanged_by_r264": True,
        },
        "corpus": {
            "index": str(args.corpus_index),
            "index_sha256": sha256(args.corpus_index.read_bytes()),
            "files": corpus_hashes,
            "records": record_count,
            "unique_layouts": len(unique_layouts),
            "semantic_cells_across_unique_layouts": semantic_cells,
            "envelope": "packed rows 0..5, columns 0..23",
            "per_file": corpus_stats,
            "dual_physical_map_simulation": True,
            "trail_free_simulation": True,
        },
        "negative_controls": {
            "semantic_tile_in_row6_rejected": True,
            "moved_or_deleted_pickup_erased": True,
            "gdma_command_mutation_rejected": dma_control,
            "r263_forced_visible_menu_tail_rejected": menu_control,
        },
        "measured_evidence_not_reexecuted": {
            "pre_optimization_promoted_baseline": {
                "ratio": promoted_baseline["ratio"],
                "hits": [promoted_baseline["dx"]["main_loop_hits"],
                         promoted_baseline["original"]["main_loop_hits"]],
            },
            "r263_qualified": {
                "ratio": prior_speed["ratio"],
                "hits": [prior_speed["dx"]["main_loop_hits"],
                         prior_speed["original"]["main_loop_hits"]],
                "scene_mismatches": prior_speed["candidate_scene_mismatch_frames"],
                "hblank_commands": prior_speed["dx"]["attr_dma_commands"],
            },
            "r264_unqualified_matrix": {
                "ratio": r264_speed["ratio"],
                "hits": [r264_speed["dx"]["main_loop_hits"],
                         r264_speed["original"]["main_loop_hits"]],
                "scene_mismatches": r264_speed["candidate_scene_mismatch_frames"],
                "warning": "matrix omitted the $5816 HBlank command probe; rerun qualified",
            },
            "expected_upside": "+28 to +32 main-loop hits vs 717/754 baseline; about +3.7 to +4.2 percentage points",
        },
        "superseded_designs": {
            "r113": "two-row / 40 per-cell HBlank writer; corpus was too narrow",
            "r253_r254": "expanded per-cell windows; still incomplete or too slow",
            "r259": "six-row semantic envelope established, but 84 waits were slow",
            "r260": "selected six-row single-HDMA architecture",
            "r261_r262": "rejected shared Stage2/5/7 transition timing changes",
            "r263": "selected Stage2-only entry isolation",
        },
        "required_live_gates_in_order": [
            "Stage2 8000-frame four-room active-map semantic equality: zero mismatches/trails on both $9800/$9C00",
            "Stage2 target1/right/2800 with --dma-command-addr 0x5816 --expected-dma-mode hblank: ratio >= .98, exact scroll, deterministic replay",
            "Stage2 pickup acquire/remove plus menu round-trip and cold/warm entry",
            "Stage5 and Stage7 transition/semantic containment plus strict speed controls",
            "r264 Stage1 current-hazard menu/item/low-health/north/hidden-map mutation suite",
            "Analogue Pocket HBlank-DMA hardware smoke test before promotion",
        ],
        "remaining_static_limits": [
            "HBlank completion timing and LCD-mode interaction require emulator and hardware evidence",
            "historical r264 matrix has three unqualified Stage2 warmup scene mismatches and is not a promotion receipt",
        ],
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
