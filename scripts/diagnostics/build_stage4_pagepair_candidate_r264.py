#!/usr/bin/env python3
"""Build the default-off Stage-4 C1F1/C2F1 refinement on exact 5bdde7.

This is an isolated diagnostic, not a release builder.  ROM emission requires
``--emit-candidate``.  The script is static-only and confines every output to
the repository-local ignored ``tmp/`` tree.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
DEFAULT_BASE = TMP / "stage4-key11-r264-candidate/candidate.gb"
DEFAULT_CORPUS = (
    TMP
    / "stage2-isolated-entry-r263/stage346-semantic-soak-8000/"
    "stage4.layout-events.tsv"
)
DEFAULT_LIVE_TRACE = (
    TMP
    / "stage4-key11-r264-candidate/stage4-speed-strict/"
    "stage4-dx-a-right/attr-events.tsv"
)
DEFAULT_LIVE_MANIFEST = (
    TMP / "stage4-key11-r264-candidate/stage4-speed-strict/manifest.json"
)
DEFAULT_OUT = TMP / "stage4-pagepair-r264-candidate"

BASE_SHA256 = "5bdde7cdf14f2600c97fefd5f400cdb6d17c6bc730d84da9b7449becf7d96e7e"
BASE_MD5 = "81b5df2955b4f74cc4c55640da6b82b2"
CANDIDATE_SHA256 = "555988114a24571402911e758853f24d07adc8411e85efb4d027712c95ce55bc"
CANDIDATE_MD5 = "387c311a4f903486c4ed6c182b07a3d6"
CORPUS_SHA256 = "54becf276a33dc9f51cce123d39c8ce80f58be04f4b186a534c34ae2a672c90a"
LIVE_TRACE_SHA256 = "84cf504702d0d8e9fe8a990dfcfa14665abf5e3e78fbf3fd610155b1783df32f"
LIVE_MANIFEST_SHA256 = "e90ee5f80af481c6effadb73c0fd3450f3cc7e079e9da6e5457955821c32db85"

BANK_SIZE = 0x4000
BANKS = (13, 16)
SOURCE_A = 0x7BB2
SOURCE_A_SIZE = 46
SOURCE_B = 0x7C4D
SOURCE_B_SIZE = 114
INSTALLER = 0x7CBF
RUNTIME_ADDRESS = 0xDA60
RUNTIME_SIZE = 160

BASE_RUNTIME_SHA256 = "c6feb9acd86779de5571e2e033209c1650dcd5d86f93e8ab14c6f92404836ef7"
BASE_SOURCE_A_SHA256 = "8c668be4a80c7f077ccee60a93582ec3cbed6a2ba3d3c18ba171b47e6354790f"
BASE_SOURCE_B_SHA256 = "b7210e3a16f625543516060ac494de889c8804ae3fea85b6809626b7aae9add6"
NEW_RUNTIME_SHA256 = "44f12eb75c4bd408475c92c563250f132594710fa90c0d0df0a6b65a8ccde913"
NEW_SOURCE_B_SHA256 = "5bd398eccf6cf6228d839592fcdded46380606922ca128cab519aebe1db912ca"

INSTALLER_BYTES = bytes.fromhex(
    "C5 D5 E5 "
    "21 00 7B 11 00 DA 01 5D 00 CD B3 09 "
    "21 B2 7B 11 60 DA 01 2E 00 CD B3 09 "
    "21 4D 7C 11 8E DA 01 72 00 CD B3 09 "
    "21 3A 56 11 80 DB 01 23 00 CD B3 09 "
    "C3 5C 57"
)
OLD_HELPER = bytes.fromhex(
    "E0 E0 7C EE CB 5F 16 DF FA A1 C1 47 FA 05 C3 18 98"
)
NEW_HELPER = bytes.fromhex(
    "E0 E0 7C EE CB 5F 16 DF 21 F1 C1 46 24 4E 18 9A"
)
SHARED_COMPARE = bytes.fromhex(
    "1A B8 20 13 13 1A B9 20 0D 13 1A 6F F0 BD BD 20 04 E1 D1 C1 C9 1B"
)

RAW_SIZE = 24 * 24
OLD_KEY_A = (444, 149, 19, 251)
OLD_KEY_B = (0, 59, 333, 201)
PAGE_KEY_A = (81,)   # $C1F1
PAGE_KEY_B = (337,)  # $C2F1
COLLISION_RAW_SHA256 = sorted([
    "16617ed35129ce24f6757899080481203a955db9dea045e1cab3b8c7b10706d6",
    "fe09ce2e85f1e7ed8352b6a0112c725c9620e9f0f8afcfc59516142559024a82",
])
COLLISION_PLANE_SHA256 = sorted([
    "155fb16e076c9198dbac15bfb701ecd0dbdc268a29464edef5dd02df7a343dd9",
    "9ea6c09fdcd274b0b12624fac854734fcaa869eccb131449c10b49298436517b",
])


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    return bank * BANK_SIZE + address - 0x4000


def require_tmp(path: Path) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    if resolved != scratch and scratch not in resolved.parents:
        raise AssertionError(f"output must remain under {scratch}: {resolved}")
    return resolved


def plane(raw: bytes) -> bytes:
    return bytes(
        4 if 0x01 <= tile <= 0x08 else 2 if tile in (0x2D, 0x2E) else 0
        for tile in raw
    )


def xor_key(raw: bytes, offsets: tuple[int, ...]) -> int:
    value = 0
    for offset in offsets:
        value ^= raw[offset]
    return value


def metrics(
    rows: list[tuple[int, int, bytes, bytes]],
    offsets_a: tuple[int, ...],
    offsets_b: tuple[int, ...],
) -> dict[str, object]:
    unique = {(room, raw): wanted for _, room, raw, wanted in rows}
    semantics: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
    variants: dict[tuple[int, bytes], set[tuple[int, int, int]]] = defaultdict(set)
    raws: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
    for (room, raw), wanted in unique.items():
        key = (room, xor_key(raw, offsets_a), xor_key(raw, offsets_b))
        semantics[key].add(wanted)
        variants[(room, wanted)].add(key)
        raws[key].add(raw)
    collision_records = []
    for key, values in sorted(semantics.items()):
        if len(values) > 1:
            collision_records.append({
                "key": list(key),
                "raw_sha256": sorted(digest(raw) for raw in raws[key]),
                "plane_sha256": sorted(digest(value) for value in values),
            })
    return {
        "samples": [list(offsets_a), list(offsets_b)],
        "unique_records": len(unique),
        "unique_keys": len(semantics),
        "collisions": sum(len(value) - 1 for value in semantics.values()),
        "false_variants": sum(len(value) - 1 for value in variants.values()),
        "collision_records": collision_records,
    }


def parse_canonical(path: Path) -> list[tuple[int, int, bytes, bytes]]:
    payload = path.read_bytes()
    if digest(payload) != CORPUS_SHA256:
        raise AssertionError("canonical Stage 4 corpus preimage changed")
    rows = []
    for number, line in enumerate(payload.decode().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) != 14:
            raise AssertionError(f"canonical line {number} has {len(fields)} fields")
        raw = bytes.fromhex(fields[13])
        if len(raw) != RAW_SIZE:
            raise AssertionError(f"canonical line {number} raw length changed")
        if int(fields[3], 16) != xor_key(raw, OLD_KEY_A):
            raise AssertionError(f"canonical line {number} old signature A changed")
        if int(fields[4], 16) != xor_key(raw, OLD_KEY_B):
            raise AssertionError(f"canonical line {number} old signature B changed")
        rows.append((int(fields[0]), int(fields[1], 16), raw, plane(raw)))
    if len(rows) != 328:
        raise AssertionError(f"expected 328 canonical rows, got {len(rows)}")
    return rows


def parse_live(path: Path) -> tuple[list[tuple[int, int, bytes, bytes]], int]:
    payload = path.read_bytes()
    if digest(payload) != LIVE_TRACE_SHA256:
        raise AssertionError("live Stage 4 trace preimage changed")
    rows = []
    old_signature_mismatches = 0
    for number, line in enumerate(payload.decode().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) != 30:
            raise AssertionError(f"live line {number} has {len(fields)} fields")
        raw = bytes.fromhex(fields[29])
        if len(raw) != RAW_SIZE:
            raise AssertionError(f"live line {number} raw length changed")
        map_hi = int(fields[2], 16)
        if map_hi not in (0x98, 0x9C):
            raise AssertionError(f"live line {number} map high byte changed")
        cache_fields = (12, 13) if map_hi == 0x98 else (16, 17)
        cached = tuple(int(fields[index], 16) for index in cache_fields)
        if cached != (raw[1], raw[357]):
            old_signature_mismatches += 1
        rows.append((int(fields[0]), int(fields[3], 16), raw, plane(raw)))
    if len(rows) != 987 or old_signature_mismatches != 6:
        raise AssertionError(
            "live cadence/pre-publication transition count changed: "
            f"{len(rows)} rows, {old_signature_mismatches} transitions"
        )
    return rows, old_signature_mismatches


def verify_keys(
    canonical: list[tuple[int, int, bytes, bytes]],
    live: list[tuple[int, int, bytes, bytes]],
    live_transition_misses: int,
) -> dict[str, object]:
    old = metrics(canonical, OLD_KEY_A, OLD_KEY_B)
    expected_collision = [{
        "key": [0x01, 0x01, 0x40],
        "raw_sha256": COLLISION_RAW_SHA256,
        "plane_sha256": COLLISION_PLANE_SHA256,
    }]
    if (
        old["unique_records"] != 21
        or old["collisions"] != 1
        or old["false_variants"] != 0
        or old["collision_records"] != expected_collision
    ):
        raise AssertionError("mandatory old-key collision negative control failed")

    canonical_page = metrics(canonical, PAGE_KEY_A, PAGE_KEY_B)
    live_page = metrics(live, PAGE_KEY_A, PAGE_KEY_B)
    for name, result, unique_records in (
        ("canonical", canonical_page, 21),
        ("live", live_page, 5),
    ):
        if (
            result["unique_records"] != unique_records
            or result["collisions"] != 0
            or result["false_variants"] != 0
            or result["collision_records"]
        ):
            raise AssertionError(f"C1F1/C2F1 is not exact over {name} corpus")

    collision_raws: dict[str, bytes] = {}
    for _, _, raw, _ in canonical:
        raw_hash = digest(raw)
        if raw_hash in COLLISION_RAW_SHA256:
            collision_raws[raw_hash] = raw
    first, second = (collision_raws[value] for value in COLLISION_RAW_SHA256)
    pair_samples = [[first[81], second[81]], [first[337], second[337]]]
    if pair_samples != [[0x04, 0x04], [0x02, 0x21]]:
        # COLLISION_RAW_SHA256 is sorted, so bind the unordered pair instead.
        if sorted(pair_samples[1]) != [0x02, 0x21] or pair_samples[0] != [4, 4]:
            raise AssertionError("collision pair C1F1/C2F1 values changed")

    return {
        "mandatory_old_key_negative_control": old,
        "C1F1_C2F1": {
            "addresses": ["$C1F1", "$C2F1"],
            "page_separation": "$0100",
            "canonical": canonical_page,
            "live_strict_gate": live_page,
            "collision_pair_samples_unordered": [[4, 4], [2, 33]],
            "all_corpus_rows_semantically_exact": True,
        },
        "live_rows": len(live),
        "live_cached_C1A1_C305_matches": len(live) - live_transition_misses,
        "live_expected_transition_misses": live_transition_misses,
    }


def runtime_from(rom: bytes, bank: int) -> bytes:
    a = bank_offset(bank, SOURCE_A)
    b = bank_offset(bank, SOURCE_B)
    return rom[a:a + SOURCE_A_SIZE] + rom[b:b + SOURCE_B_SIZE]


def verify_base(rom: bytes) -> bytes:
    if len(rom) != 32 * BANK_SIZE:
        raise AssertionError("base is not a 512 KiB image")
    if digest(rom) != BASE_SHA256 or hashlib.md5(rom).hexdigest() != BASE_MD5:
        raise AssertionError("base is not exact Stage4 key11 candidate 5bdde7")
    runtimes = []
    for bank in BANKS:
        runtime = runtime_from(rom, bank)
        if digest(runtime) != BASE_RUNTIME_SHA256:
            raise AssertionError(f"bank {bank} runtime preimage changed")
        if digest(runtime[:SOURCE_A_SIZE]) != BASE_SOURCE_A_SHA256:
            raise AssertionError(f"bank {bank} source-A preimage changed")
        if digest(runtime[SOURCE_A_SIZE:]) != BASE_SOURCE_B_SHA256:
            raise AssertionError(f"bank {bank} source-B preimage changed")
        if runtime[0x89:0x9A] != OLD_HELPER:
            raise AssertionError(f"bank {bank} Stage4 helper preimage changed")
        installer = bank_offset(bank, INSTALLER)
        if rom[installer:installer + len(INSTALLER_BYTES)] != INSTALLER_BYTES:
            raise AssertionError(f"bank {bank} installer preimage changed")
        runtimes.append(runtime)
    if runtimes[0] != runtimes[1]:
        raise AssertionError("base runtime mirrors diverged")
    return runtimes[0]


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom) - rom[0x014E] - rom[0x014F]) & 0xFFFF
    rom[0x014E] = total >> 8
    rom[0x014F] = total & 0xFF


def construct(base: bytes, old_runtime: bytes) -> tuple[bytes, dict[str, object]]:
    runtime = bytearray(old_runtime)
    runtime[0x89:0x9A] = NEW_HELPER + b"\x00"
    runtime = bytes(runtime)
    if digest(runtime) != NEW_RUNTIME_SHA256:
        raise AssertionError("constructed page-paired runtime hash changed")
    if digest(runtime[:SOURCE_A_SIZE]) != BASE_SOURCE_A_SHA256:
        raise AssertionError("page-pair unexpectedly changed source A")
    if digest(runtime[SOURCE_A_SIZE:]) != NEW_SOURCE_B_SHA256:
        raise AssertionError("page-pair source-B output hash changed")
    if runtime[:0x89] != old_runtime[:0x89] or runtime[0x9A:] != old_runtime[0x9A:]:
        raise AssertionError("runtime change escaped DAE9-DAF9")
    if runtime[0x33:0x49] != SHARED_COMPARE:
        raise AssertionError("shared compare/return sequence changed")

    rom = bytearray(base)
    functional = set()
    for bank in BANKS:
        a = bank_offset(bank, SOURCE_A)
        b = bank_offset(bank, SOURCE_B)
        old_a = bytes(rom[a:a + SOURCE_A_SIZE])
        old_b = bytes(rom[b:b + SOURCE_B_SIZE])
        new_a, new_b = runtime[:SOURCE_A_SIZE], runtime[SOURCE_A_SIZE:]
        functional.update(a + i for i, pair in enumerate(zip(old_a, new_a)) if pair[0] != pair[1])
        functional.update(b + i for i, pair in enumerate(zip(old_b, new_b)) if pair[0] != pair[1])
        rom[a:a + SOURCE_A_SIZE] = new_a
        rom[b:b + SOURCE_B_SIZE] = new_b
    update_checksums(rom)
    candidate = bytes(rom)
    if digest(candidate) != CANDIDATE_SHA256:
        raise AssertionError("candidate SHA256 differs from reviewed construction")
    if hashlib.md5(candidate).hexdigest() != CANDIDATE_MD5:
        raise AssertionError("candidate MD5 differs from reviewed construction")
    changed = {i for i, pair in enumerate(zip(base, candidate)) if pair[0] != pair[1]}
    allowed = functional | {0x014D, 0x014E, 0x014F}
    if not changed <= allowed or len(functional) != 16 or len(changed) != 18:
        raise AssertionError("strict diff allowlist/count changed")
    return candidate, {
        "functional_bytes_changed": len(functional),
        "total_bytes_changed": len(changed),
        "changed_by_bank": {str(bank): 8 for bank in BANKS},
        "only_runtime_range_changed": "$DAE9-$DAF9",
        "checksum_offsets_allowed": ["$014D", "$014E", "$014F"],
    }


def verify_live_manifest(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if digest(payload) != LIVE_MANIFEST_SHA256:
        raise AssertionError("strict Stage 4 manifest preimage changed")
    report = json.loads(payload)
    if report.get("dx_rom_md5") != BASE_MD5:
        raise AssertionError("strict manifest is not bound to exact 5bdde7")
    rows = report.get("rows", [])
    if len(rows) != 1 or rows[0].get("stage") != 4:
        raise AssertionError("strict manifest no longer has one Stage 4 row")
    row = rows[0]
    original, dx = row["original"], row["dx"]
    exact = (
        row.get("ratio_exact"), original.get("main_loop_hits"),
        dx.get("main_loop_hits"), dx.get("tile_copy_hits"),
        dx.get("postcopy_decisions"), dx.get("postcopy_dirty_decisions"),
        dx.get("compiler_tile_copy_indices"), dx.get("attr_map_changes"),
        dx.get("attr_map_unchanged"),
    )
    expected = (0.9895287958115183, 764, 756, 987, 2299, 857, [4, 5, 6, 8, 12, 13, 17, 19], 4, 983)
    if exact != expected or row.get("deterministic_replay") is not True:
        raise AssertionError(f"strict Stage 4 evidence changed: {exact}")
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": LIVE_MANIFEST_SHA256,
        "base_candidate_sha256": BASE_SHA256,
        "ratio_exact": row["ratio_exact"],
        "main_loop_hits_original_dx": [764, 756],
        "minimum_dx_hits_for_0_99": 757,
        "tile_copy_hits": 987,
        "compiler_invocations": 8,
        "desired_plane_changes": 4,
        "unchanged_plane_copies": 983,
        "deterministic_replay": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--live-trace", type=Path, default=DEFAULT_LIVE_TRACE)
    parser.add_argument("--live-manifest", type=Path, default=DEFAULT_LIVE_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--emit-candidate", action="store_true")
    args = parser.parse_args()
    out_dir = require_tmp(args.out_dir)

    base = args.base.read_bytes()
    old_runtime = verify_base(base)
    canonical = parse_canonical(args.corpus)
    live, live_misses = parse_live(args.live_trace)
    key_contract = verify_keys(canonical, live, live_misses)
    strict_gate = verify_live_manifest(args.live_manifest)
    candidate, diff = construct(base, old_runtime)

    report: dict[str, object] = {
        "schema": "penta-stage4-pagepair-r264-candidate-v1",
        "status": "STATIC_QUALIFIED_DEFAULT_OFF",
        "promotable": False,
        "default_off": True,
        "emulator_invoked": False,
        "emit_candidate_requested": args.emit_candidate,
        "base": {
            "path": str(args.base.resolve().relative_to(ROOT)),
            "sha256": BASE_SHA256,
            "md5": BASE_MD5,
            "lineage": "exact static 1+1 Stage4 candidate atop r264 aa4c1560",
        },
        "runtime": {
            "old_sha256": BASE_RUNTIME_SHA256,
            "new_sha256": NEW_RUNTIME_SHA256,
            "source_a_unchanged_sha256": BASE_SOURCE_A_SHA256,
            "source_b_sha256": NEW_SOURCE_B_SHA256,
            "old_helper": OLD_HELPER.hex(" ").upper(),
            "new_helper": NEW_HELPER.hex(" ").upper(),
            "decoded_join": "$DAF9 + signed($9A) = $DA93",
            "stage4_additional_saving_t_per_helper": 8,
            "measured_987_helper_upper_bound_t": 7896,
            "other_stage_cycle_delta_vs_5bdde7": {
                "stage2": 0, "stage3": 0, "stage5": 0,
                "stage6": 0, "stage7": 0, "crystal": 0,
            },
            "ffe0_contract": (
                "The first Stage4 instruction remains LDH [$FFE0],A with A=0; "
                "all bytes outside DAE9-DAF9, including every other cache-hit "
                "route and the dirty-tail value-one writer, are byte-identical."
            ),
        },
        "key_contract": key_contract,
        "strict_gate_preimage": strict_gate,
        "additional_150k_audit": {
            "target_t_cycles": 150000,
            "minimum_saving_per_987_tile_copies_t": 152,
            "pagepair_total_t_upper_bound": 7896,
            "compiler_invocations": 8,
            "minimum_saving_per_compiler_t": 18750,
            "static_safe_candidate_found": False,
            "blocker": (
                "The page-pair exhausts the only byte-local Stage4 helper win. "
                "A further 152T on every copy exceeds the remaining private "
                "helper work; the stock-cadence copier is shared. The only "
                "large Stage4-local budget is the eight semantically required "
                "compiler/publication events, and replacing them needs a trace-"
                "qualified complete-plane algorithm. The 21-record corpus is "
                "not a proof that mutable layouts may be replaced by ROM planes."
            ),
            "required_trace": (
                "Cycle-bound each Stage4 compiler entry/exit and record raw input, "
                "complete desired plane, physical destination, room, and mutation "
                "state across the full semantic soak before specializing publication."
            ),
        },
        "required_next_gate": (
            "None for this 8T-only diagnostic: do not spend another emulator "
            "run or integrate it into production. Exact r264 remains the release "
            "baseline and further Stage4 work waits behind Stage7."
        ),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    if args.emit_candidate:
        path = out_dir / "candidate.gb"
        path.write_bytes(candidate)
        report["status"] = "PASS_STATIC_DIAGNOSTIC_ONLY"
        report["candidate"] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": CANDIDATE_SHA256,
            "md5": CANDIDATE_MD5,
            **diff,
        }
    else:
        report["candidate"] = {
            "written": False,
            "reviewed_sha256": CANDIDATE_SHA256,
            "reason": "default-off; rerun with --emit-candidate",
        }

    receipt = out_dir / ("build-receipt.json" if args.emit_candidate else "audit-receipt.json")
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
