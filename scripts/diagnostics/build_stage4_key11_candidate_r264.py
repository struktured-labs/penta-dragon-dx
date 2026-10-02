#!/usr/bin/env python3
"""Build the default-off exact-r264 Stage 4 1+1-key diagnostic.

The candidate gives Stage 4 a private C1A1/C305 cache key in the already
copied DA60-DAFF runtime.  It is deliberately not a release builder: ROM
emission requires ``--emit-candidate``, every input is receipt-pinned, and the
result remains non-promotable until emulator-backed speed and visual gates run.

This script never launches an emulator.  All outputs are restricted to the
repository-local ignored ``tmp/`` directory.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tmp"
DEFAULT_BASE = TMP_ROOT / "stage1-menu-hidden-repair-r264/candidate.gb"
DEFAULT_TRACE = (
    TMP_ROOT
    / "stage2-isolated-entry-r263/stage346-semantic-soak-8000/"
    "stage4.layout-events.tsv"
)
DEFAULT_SPEED = (
    TMP_ROOT
    / "stage1-menu-hidden-repair-r264/all-stage-speed-right-r1/manifest.json"
)
DEFAULT_OUT = TMP_ROOT / "stage4-key11-r264-candidate"

R264_SHA256 = (
    "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
)
R264_MD5 = "cd025fd5c3ccdf49ac5a9ebebceff8e5"
TRACE_SHA256 = (
    "54becf276a33dc9f51cce123d39c8ce80f58be04f4b186a534c34ae2a672c90a"
)
SPEED_SHA256 = (
    "7b32a6d44db7f11370747930896377cbfad1ed7b21b7b482cb3fb73c4525ac49"
)

BANK_SIZE = 0x4000
MIRROR_BANKS = (13, 16)
SOURCE_A = 0x7BB2
SOURCE_A_SIZE = 46
SOURCE_B = 0x7C4D
SOURCE_B_SIZE = 114
INSTALLER = 0x7CBF
RUNTIME_ADDR = 0xDA60
RUNTIME_SIZE = SOURCE_A_SIZE + SOURCE_B_SIZE

SOURCE_A_SHA256 = (
    "cf20fc43bbab456a503f5fa589149b7a876316a236252cfe469413bb5c3f4cb7"
)
SOURCE_B_SHA256 = (
    "c1db01bd90c3bfe80d173eda949fea06ffdacf5b2e61e275e2c6b7e077d5163d"
)
RUNTIME_SHA256 = (
    "765d22df24f270dd5210500f05ae101278edab35ee0c8707bed26738f90c8b5a"
)
EXPECTED_INSTALLER = bytes.fromhex(
    "C5 D5 E5 "
    "21 00 7B 11 00 DA 01 5D 00 CD B3 09 "
    "21 B2 7B 11 60 DA 01 2E 00 CD B3 09 "
    "21 4D 7C 11 8E DA 01 72 00 CD B3 09 "
    "21 3A 56 11 80 DB 01 23 00 CD B3 09 "
    "C3 5C 57"
)
EXPECTED_HEADER = bytes.fromhex("B7 28 04 00 00 00 AF E0 E0")
EXPECTED_DISPATCHER = bytes.fromhex(
    "06 05 FA 80 D8 D6 03 FE 06 38 10 D6 09 FE 09 38 02 AF C9 "
    "FE 02 CA 60 DA C3 A4 DB C3 60 DA"
)
EXPECTED_ARENA_PREFIX = bytes.fromhex(
    "FA 80 D8 E6 F7 FE 02 C2 B9 DA 3E 15 CD 61 00 C3 00 41"
)

NEW_HEADER = bytes.fromhex("B7 28 05 D6 02 28 7F AF E0 E0")
NEW_DISPATCHER = bytes.fromhex(
    "06 05 FA 80 D8 D6 03 FE 06 38 10 D6 09 FE 09 38 02 AF C9 "
    "FE 02 2F 28 8F C3 A4 DB C3 60 DA"
)
STAGE4_HELPER = bytes.fromhex(
    "E0 E0 7C EE CB 5F 16 DF FA A1 C1 47 FA 05 C3 18 98"
)
NEW_SOURCE_A_SHA256 = (
    "8c668be4a80c7f077ccee60a93582ec3cbed6a2ba3d3c18ba171b47e6354790f"
)
NEW_SOURCE_B_SHA256 = (
    "b7210e3a16f625543516060ac494de889c8804ae3fea85b6809626b7aae9add6"
)
NEW_RUNTIME_SHA256 = (
    "c6feb9acd86779de5571e2e033209c1650dcd5d86f93e8ab14c6f92404836ef7"
)
NEW_DISPATCHER_SHA256 = (
    "52df9f8acb39a1062bb77f2d43e6bef98f3b8f0ee3300e0c47e4c66eab8abd34"
)

RAW_SIZE = 24 * 24
CURRENT_A = (444, 149, 19, 251)
CURRENT_B = (0, 59, 333, 201)
STAGE4_A = (1,)
STAGE4_B = (357,)
COLLISION_RAW_A_SHA256 = (
    "16617ed35129ce24f6757899080481203a955db9dea045e1cab3b8c7b10706d6"
)
COLLISION_RAW_B_SHA256 = (
    "fe09ce2e85f1e7ed8352b6a0112c725c9620e9f0f8afcfc59516142559024a82"
)
COLLISION_PLANE_A_SHA256 = (
    "155fb16e076c9198dbac15bfb701ecd0dbdc268a29464edef5dd02df7a343dd9"
)
COLLISION_PLANE_B_SHA256 = (
    "9ea6c09fdcd274b0b12624fac854734fcaa869eccb131449c10b49298436517b"
)

EXPECTED_SPEED_ROWS = {
    3: (0.9943, 699, 695, 953, 14, 14),
    4: (0.9895, 764, 756, 985, 14, 14),
    5: (0.9924, 790, 784, 1227, 18, 18),
    6: (0.9947, 756, 752, 851, 14, 14),
    7: (0.9801, 806, 790, 903, 110, 70),
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if bank == 0:
        return address
    return bank * BANK_SIZE + address - 0x4000


def require_tmp(path: Path) -> Path:
    resolved = path.resolve()
    tmp = TMP_ROOT.resolve()
    if resolved != tmp and tmp not in resolved.parents:
        raise AssertionError(f"scratch output must stay under {tmp}: {resolved}")
    return resolved


def xor_key(raw: bytes, offsets: tuple[int, ...]) -> int:
    result = 0
    for offset in offsets:
        result ^= raw[offset]
    return result


def stage4_plane(raw: bytes) -> bytes:
    lut = bytearray(256)
    for tile in range(0x01, 0x09):
        lut[tile] = 4
    lut[0x2D] = lut[0x2E] = 2
    return bytes(lut[tile] for tile in raw)


def parse_corpus(path: Path) -> list[dict[str, object]]:
    if sha256(path.read_bytes()) != TRACE_SHA256:
        raise AssertionError("canonical Stage 4 trace preimage changed")
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) != 14:
            raise AssertionError(
                f"{path}:{line_number}: expected 14 fields, got {len(fields)}"
            )
        raw = bytes.fromhex(fields[13])
        if len(raw) != RAW_SIZE:
            raise AssertionError(
                f"{path}:{line_number}: expected {RAW_SIZE} raw bytes"
            )
        row = {
            "line": line_number,
            "frame": int(fields[0]),
            "room": int(fields[1], 16),
            "active_map": int(fields[2], 16),
            "recorded_a": int(fields[3], 16),
            "recorded_b": int(fields[4], 16),
            "raw": raw,
            "raw_sha256": sha256(raw),
            "plane": stage4_plane(raw),
        }
        if row["recorded_a"] != xor_key(raw, CURRENT_A):
            raise AssertionError(f"line {line_number}: recorded signature A moved")
        if row["recorded_b"] != xor_key(raw, CURRENT_B):
            raise AssertionError(f"line {line_number}: recorded signature B moved")
        rows.append(row)
    if len(rows) != 328:
        raise AssertionError(f"expected 328 corpus rows, got {len(rows)}")
    return rows


def key_metrics(
    rows: list[dict[str, object]],
    samples_a: tuple[int, ...],
    samples_b: tuple[int, ...],
) -> dict[str, object]:
    unique: dict[tuple[int, bytes], bytes] = {}
    for row in rows:
        unique[(int(row["room"]), bytes(row["raw"]))] = bytes(row["plane"])
    semantics_by_key: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
    keys_by_semantic: dict[tuple[int, bytes], set[tuple[int, int, int]]] = (
        defaultdict(set)
    )
    raws_by_key: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
    for (room, raw), plane in unique.items():
        key = (room, xor_key(raw, samples_a), xor_key(raw, samples_b))
        semantics_by_key[key].add(plane)
        keys_by_semantic[(room, plane)].add(key)
        raws_by_key[key].add(raw)
    collisions = sum(len(values) - 1 for values in semantics_by_key.values())
    variants = sum(len(values) - 1 for values in keys_by_semantic.values())
    collision_records = []
    for key, semantics in sorted(semantics_by_key.items()):
        if len(semantics) <= 1:
            continue
        collision_records.append(
            {
                "key": [key[0], key[1], key[2]],
                "raw_sha256": sorted(sha256(raw) for raw in raws_by_key[key]),
                "plane_sha256": sorted(sha256(plane) for plane in semantics),
            }
        )
    return {
        "samples_a": list(samples_a),
        "samples_b": list(samples_b),
        "unique_records": len(unique),
        "unique_keys": len(semantics_by_key),
        "collisions": collisions,
        "false_variants": variants,
        "collision_records": collision_records,
    }


def verify_corpus(rows: list[dict[str, object]]) -> dict[str, object]:
    old = key_metrics(rows, CURRENT_A, CURRENT_B)
    new = key_metrics(rows, STAGE4_A, STAGE4_B)
    expected_negative = {
        "key": [0x01, 0x01, 0x40],
        "raw_sha256": sorted(
            [COLLISION_RAW_A_SHA256, COLLISION_RAW_B_SHA256]
        ),
        "plane_sha256": sorted(
            [COLLISION_PLANE_A_SHA256, COLLISION_PLANE_B_SHA256]
        ),
    }
    if (
        old["unique_records"] != 21
        or old["collisions"] != 1
        or old["false_variants"] != 0
        or old["collision_records"] != [expected_negative]
    ):
        raise AssertionError("mandatory old-key collision negative control failed")
    if (
        new["unique_records"] != 21
        or new["collisions"] != 0
        or new["false_variants"] != 0
        or new["collision_records"]
    ):
        raise AssertionError("Stage 4 C1A1/C305 key is not exact over corpus")

    collision_rows = {
        str(row["raw_sha256"]): row
        for row in rows
        if row["raw_sha256"]
        in (COLLISION_RAW_A_SHA256, COLLISION_RAW_B_SHA256)
    }
    if set(collision_rows) != {
        COLLISION_RAW_A_SHA256,
        COLLISION_RAW_B_SHA256,
    }:
        raise AssertionError("collision pair disappeared from canonical corpus")
    raw_a = bytes(collision_rows[COLLISION_RAW_A_SHA256]["raw"])
    raw_b = bytes(collision_rows[COLLISION_RAW_B_SHA256]["raw"])
    if (raw_a[1], raw_b[1], raw_a[357], raw_b[357]) != (
        0x43,
        0x43,
        0x32,
        0x43,
    ):
        raise AssertionError("exact C1A1/C305 collision-pair semantics changed")

    # Validate the actual helper loads on every archived row, not merely the
    # 21 de-duplicated records used for collision accounting.
    row_keys = []
    semantic_for_key: dict[tuple[int, int, int], bytes] = {}
    for row in rows:
        raw = bytes(row["raw"])
        key = (int(row["room"]), raw[1], raw[357])
        plane = bytes(row["plane"])
        previous = semantic_for_key.setdefault(key, plane)
        if previous != plane:
            raise AssertionError(
                f"line {row['line']}: 1+1 key selected stale semantics"
            )
        row_keys.append(key)
    if len(row_keys) != 328:
        raise AssertionError("not every corpus row received an exact 1+1 key")

    return {
        "trace_rows_checked": len(rows),
        "old_key_negative_control": old,
        "stage4_key_1_plus_1": new,
        "collision_pair_samples": {
            "C1A1": [raw_a[1], raw_b[1]],
            "C305": [raw_a[357], raw_b[357]],
        },
        "all_row_semantics_exact": True,
    }


def verify_speed(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if sha256(payload) != SPEED_SHA256:
        raise AssertionError("all-stage speed receipt preimage changed")
    manifest = json.loads(payload)
    if manifest.get("dx_rom_md5") != R264_MD5:
        raise AssertionError("speed receipt is not bound to exact r264")
    rows = {int(row["stage"]): row for row in manifest.get("rows", [])}
    result: dict[str, object] = {}
    for stage, expected in EXPECTED_SPEED_ROWS.items():
        row = rows.get(stage)
        if row is None:
            raise AssertionError(f"speed receipt is missing Stage {stage}")
        original = row["original"]
        dx = row["dx"]
        actual = (
            row["ratio"],
            original["main_loop_hits"],
            dx["main_loop_hits"],
            dx["tile_copy_hits"],
            original["scroll_changes"],
            dx["scroll_changes"],
        )
        if actual != expected or row.get("deterministic_replay") is not True:
            raise AssertionError(f"Stage {stage} speed row changed: {actual}")
        minimum = (99 * original["main_loop_hits"] + 99) // 100
        headroom = dx["main_loop_hits"] - minimum
        if stage == 4:
            delta_per_decision = -104
        elif stage in (3, 5, 6, 7):
            delta_per_decision = 4
        else:
            delta_per_decision = 0
        aggregate = delta_per_decision * dx["tile_copy_hits"]
        result[str(stage)] = {
            "ratio": row["ratio"],
            "original_main_loop_hits": original["main_loop_hits"],
            "dx_main_loop_hits": dx["main_loop_hits"],
            "minimum_hits_for_0_99": minimum,
            "measured_headroom_loops": headroom,
            "tile_copy_decisions": dx["tile_copy_hits"],
            "candidate_delta_t_cycles_per_decision": delta_per_decision,
            "candidate_aggregate_t_cycles_over_recorded_decisions": aggregate,
            "absolute_delta_t_cycles_per_current_dx_loop": round(
                abs(aggregate) / dx["main_loop_hits"], 4
            ),
            "scroll_changes": [
                original["scroll_changes"],
                dx["scroll_changes"],
            ],
        }
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": SPEED_SHA256,
        "stages": result,
        "risk": (
            "Stage 5 has only one measured loop of >=.99 headroom; Stage 3 "
            "has two and Stage 6 has three. The exact +4T/decision is static, "
            "but phase-sensitive loop loss must be measured in an emulator."
        ),
        "stage7_scope": "recorded only; its separate route remains below .99",
    }


def update_checksums(rom: bytearray) -> None:
    checksum = 0
    for value in rom[0x0134:0x014D]:
        checksum = (checksum - value - 1) & 0xFF
    rom[0x014D] = checksum
    total = (sum(rom) - rom[0x014E] - rom[0x014F]) & 0xFFFF
    rom[0x014E] = total >> 8
    rom[0x014F] = total & 0xFF


def verify_base(source: bytes) -> bytes:
    if len(source) != 32 * BANK_SIZE:
        raise AssertionError(f"expected 512 KiB r264, got {len(source)} bytes")
    if sha256(source) != R264_SHA256:
        raise AssertionError("base is not exact r264 aa4c1560")
    if hashlib.md5(source).hexdigest() != R264_MD5:
        raise AssertionError("r264 MD5 preimage changed")

    fragments: list[bytes] = []
    for bank in MIRROR_BANKS:
        a_off = bank_offset(bank, SOURCE_A)
        b_off = bank_offset(bank, SOURCE_B)
        source_a = source[a_off:a_off + SOURCE_A_SIZE]
        source_b = source[b_off:b_off + SOURCE_B_SIZE]
        if sha256(source_a) != SOURCE_A_SHA256:
            raise AssertionError(f"bank {bank} source-A preimage changed")
        if sha256(source_b) != SOURCE_B_SHA256:
            raise AssertionError(f"bank {bank} source-B preimage changed")
        runtime = source_a + source_b
        if sha256(runtime) != RUNTIME_SHA256:
            raise AssertionError(f"bank {bank} DA60 runtime preimage changed")
        if source[
            bank_offset(bank, INSTALLER):
            bank_offset(bank, INSTALLER) + len(EXPECTED_INSTALLER)
        ] != EXPECTED_INSTALLER:
            raise AssertionError(f"bank {bank} installer preimage changed")
        fragments.append(runtime)
    if fragments[0] != fragments[1]:
        raise AssertionError("bank13/bank16 DA60 source mirrors diverged")

    runtime = fragments[0]
    if runtime[3:12] != EXPECTED_HEADER:
        raise AssertionError("DA63 header preimage changed")
    if runtime[0x59:0x59 + len(EXPECTED_DISPATCHER)] != EXPECTED_DISPATCHER:
        raise AssertionError("DAB9 dispatcher preimage changed")
    if runtime[0x58] != 0:
        raise AssertionError("DAB8 shift byte is no longer free")
    if runtime[0x77:0x77 + len(EXPECTED_ARENA_PREFIX)] != EXPECTED_ARENA_PREFIX:
        raise AssertionError("DAD7 arena input-kill prefix changed")
    if runtime[0x89:0xA0] != bytes(0x17):
        raise AssertionError("DAE9-DAFF helper/metadata tail is no longer zero")
    return runtime


def build_runtime(old: bytes) -> bytes:
    if len(old) != RUNTIME_SIZE or sha256(old) != RUNTIME_SHA256:
        raise AssertionError("unexpected runtime passed to builder")
    new = bytearray(old)
    new[3:13] = NEW_HEADER
    # Move only the exact generic metadata/signature/compare body.  DAB8 is
    # the one receipt-proven pad; DAB9 stays the dispatcher boundary.
    new[13:0x59] = old[12:0x58]
    new[0x59:0x77] = NEW_DISPATCHER
    new[0x89:0x89 + len(STAGE4_HELPER)] = STAGE4_HELPER
    if new[0x9A:0xA0] != bytes(6):
        raise AssertionError("DAFA-DAFF cache metadata changed")
    result = bytes(new)
    if sha256(result) != NEW_RUNTIME_SHA256:
        raise AssertionError("constructed runtime does not match reviewed design")
    if sha256(result[0x59:0x77]) != NEW_DISPATCHER_SHA256:
        raise AssertionError("constructed dispatcher hash changed")
    if sha256(result[:SOURCE_A_SIZE]) != NEW_SOURCE_A_SHA256:
        raise AssertionError("constructed source-A hash changed")
    if sha256(result[SOURCE_A_SIZE:]) != NEW_SOURCE_B_SHA256:
        raise AssertionError("constructed source-B hash changed")
    return result


def build_candidate(source: bytes, old_runtime: bytes) -> tuple[bytes, dict[str, object]]:
    runtime = build_runtime(old_runtime)
    rom = bytearray(source)
    functional_allowlist: set[int] = set()
    for bank in MIRROR_BANKS:
        a_off = bank_offset(bank, SOURCE_A)
        b_off = bank_offset(bank, SOURCE_B)
        old_fragment = bytes(rom[a_off:a_off + SOURCE_A_SIZE])
        new_fragment = runtime[:SOURCE_A_SIZE]
        for index, (before, after) in enumerate(zip(old_fragment, new_fragment)):
            if before != after:
                functional_allowlist.add(a_off + index)
        rom[a_off:a_off + SOURCE_A_SIZE] = new_fragment

        old_fragment = bytes(rom[b_off:b_off + SOURCE_B_SIZE])
        new_fragment = runtime[SOURCE_A_SIZE:]
        for index, (before, after) in enumerate(zip(old_fragment, new_fragment)):
            if before != after:
                functional_allowlist.add(b_off + index)
        rom[b_off:b_off + SOURCE_B_SIZE] = new_fragment

    update_checksums(rom)
    candidate = bytes(rom)
    changed = {index for index, pair in enumerate(zip(source, candidate)) if pair[0] != pair[1]}
    checksum_bytes = {0x014D, 0x014E, 0x014F}
    expected_changed = functional_allowlist | {
        index for index in checksum_bytes if source[index] != candidate[index]
    }
    if changed != expected_changed:
        unexpected = sorted(changed ^ expected_changed)
        raise AssertionError(f"candidate diff escaped strict allowlist: {unexpected[:16]}")
    if not changed <= functional_allowlist | checksum_bytes:
        raise AssertionError("candidate modified bytes outside source mirrors/checksums")
    return candidate, {
        "functional_bytes_changed": len(functional_allowlist),
        "total_bytes_changed": len(changed),
        "changed_by_bank": {
            str(bank): sum(
                bank * BANK_SIZE <= offset < (bank + 1) * BANK_SIZE
                for offset in functional_allowlist
            )
            for bank in MIRROR_BANKS
        },
        "checksum_offsets_allowed": ["$014D", "$014E", "$014F"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--speed", type=Path, default=DEFAULT_SPEED)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--emit-candidate",
        action="store_true",
        help="write the non-promotable diagnostic ROM after all static gates",
    )
    args = parser.parse_args()
    out_dir = require_tmp(args.out_dir)

    source = args.base.read_bytes()
    old_runtime = verify_base(source)
    corpus = verify_corpus(parse_corpus(args.trace))
    speed = verify_speed(args.speed)
    new_runtime = build_runtime(old_runtime)

    report: dict[str, object] = {
        "schema": "penta-stage4-key11-r264-candidate-v1",
        "status": "STATIC_QUALIFIED_DEFAULT_OFF",
        "promotable": False,
        "emulator_invoked": False,
        "default_off": True,
        "emit_candidate_requested": args.emit_candidate,
        "base": {
            "path": str(args.base.resolve().relative_to(ROOT)),
            "sha256": R264_SHA256,
            "md5": R264_MD5,
        },
        "runtime": {
            "source_mirror_banks": list(MIRROR_BANKS),
            "old_sha256": RUNTIME_SHA256,
            "new_sha256": sha256(new_runtime),
            "source_a_sha256": sha256(new_runtime[:SOURCE_A_SIZE]),
            "source_b_sha256": sha256(new_runtime[SOURCE_A_SIZE:]),
            "dispatcher_sha256": sha256(new_runtime[0x59:0x77]),
            "stage2_precompare_delta_t_cycles": 0,
            "stage4_precompare_delta_t_cycles": -104,
            "generic_later_stage_precompare_delta_t_cycles": 4,
            "crystal_dispatch_delta_t_cycles": 0,
            "crystal_generic_header_delta_t_cycles": 4,
            "ffe0_contract": (
                "Stage2, Stage4, generic, and Crystal cache-hit routes all "
                "write zero; the existing dirty tail alone writes one."
            ),
            "arena_input_safety": (
                "The cycle-equal CP 2/CPL/JR Z dispatcher complement is dead "
                "on non-Crystal arenas because DAD7 immediately reloads A "
                "from D880 and AND $F7 replaces flags before any branch."
            ),
        },
        "corpus": corpus,
        "speed_evidence": speed,
        "qualification": {
            "static_only": True,
            "visual_semantics_claim": (
                "C1A1/C305 is collision-free and variant-free only over the "
                "exact archived 8,000-frame Stage 4 corpus."
            ),
            "stage4_outlook": (
                "104T saved across each of 985 recorded decisions is 102440T "
                "total, plausibly enough for the one missing loop; measurement required."
            ),
            "other_stage_risk": (
                "The +4T shared-header cost is exact. Stage 5 is the fragile "
                "one-loop-headroom case; Stage 7 is handled separately."
            ),
            "required_next_gate": (
                "single-flight emulator speed replay plus Stage 4 semantic/visual soak"
            ),
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    if args.emit_candidate:
        candidate, diff = build_candidate(source, old_runtime)
        candidate_path = out_dir / "candidate.gb"
        candidate_path.write_bytes(candidate)
        report["status"] = "PASS_STATIC_CANDIDATE_EMULATOR_REQUIRED"
        report["candidate"] = {
            "path": str(candidate_path.relative_to(ROOT)),
            "sha256": sha256(candidate),
            "md5": hashlib.md5(candidate).hexdigest(),
            **diff,
        }
    else:
        report["candidate"] = {
            "written": False,
            "reason": "default-off; rerun with --emit-candidate",
        }

    receipt_path = out_dir / (
        "build-receipt.json" if args.emit_candidate else "audit-receipt.json"
    )
    receipt_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
