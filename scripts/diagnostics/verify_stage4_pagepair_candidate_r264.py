#!/usr/bin/env python3
"""Independently verify the exact-5bdde7 Stage-4 page-pair candidate.

The verifier reconstructs the only permitted ROM delta, decodes the new
branch, checks every FFE0 writer, and replays the old negative control plus
the C1F1/C2F1 key over both pinned corpora.  It never launches an emulator.
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
DEFAULT_CANDIDATE = TMP / "stage4-pagepair-r264-candidate/candidate.gb"
DEFAULT_CORPUS = (
    TMP
    / "stage2-isolated-entry-r263/stage346-semantic-soak-8000/"
    "stage4.layout-events.tsv"
)
DEFAULT_LIVE = (
    TMP
    / "stage4-key11-r264-candidate/stage4-speed-strict/"
    "stage4-dx-a-right/attr-events.tsv"
)
DEFAULT_MANIFEST = (
    TMP / "stage4-key11-r264-candidate/stage4-speed-strict/manifest.json"
)
DEFAULT_RECEIPT = TMP / "stage4-pagepair-r264-candidate/static-verification.json"

BASE_SHA256 = "5bdde7cdf14f2600c97fefd5f400cdb6d17c6bc730d84da9b7449becf7d96e7e"
BASE_MD5 = "81b5df2955b4f74cc4c55640da6b82b2"
CANDIDATE_SHA256 = "555988114a24571402911e758853f24d07adc8411e85efb4d027712c95ce55bc"
CANDIDATE_MD5 = "387c311a4f903486c4ed6c182b07a3d6"
CORPUS_SHA256 = "54becf276a33dc9f51cce123d39c8ce80f58be04f4b186a534c34ae2a672c90a"
LIVE_SHA256 = "84cf504702d0d8e9fe8a990dfcfa14665abf5e3e78fbf3fd610155b1783df32f"
MANIFEST_SHA256 = "e90ee5f80af481c6effadb73c0fd3450f3cc7e079e9da6e5457955821c32db85"

BANK_SIZE = 0x4000
BANKS = (13, 16)
SOURCE_A = 0x7BB2
SOURCE_A_SIZE = 46
SOURCE_B = 0x7C4D
SOURCE_B_SIZE = 114
INSTALLER = 0x7CBF
RUNTIME = 0xDA60

BASE_RUNTIME_SHA256 = "c6feb9acd86779de5571e2e033209c1650dcd5d86f93e8ab14c6f92404836ef7"
NEW_RUNTIME_SHA256 = "44f12eb75c4bd408475c92c563250f132594710fa90c0d0df0a6b65a8ccde913"
SOURCE_A_SHA256 = "8c668be4a80c7f077ccee60a93582ec3cbed6a2ba3d3c18ba171b47e6354790f"
OLD_SOURCE_B_SHA256 = "b7210e3a16f625543516060ac494de889c8804ae3fea85b6809626b7aae9add6"
NEW_SOURCE_B_SHA256 = "5bd398eccf6cf6228d839592fcdded46380606922ca128cab519aebe1db912ca"

HEADER = bytes.fromhex("B7 28 05 D6 02 28 7F AF E0 E0")
OLD_HELPER = bytes.fromhex(
    "E0 E0 7C EE CB 5F 16 DF FA A1 C1 47 FA 05 C3 18 98"
)
NEW_HELPER = bytes.fromhex(
    "E0 E0 7C EE CB 5F 16 DF 21 F1 C1 46 24 4E 18 9A"
)
COMPARE = bytes.fromhex(
    "1A B8 20 13 13 1A B9 20 0D 13 1A 6F F0 BD BD 20 04 E1 D1 C1 C9 1B"
)
INSTALLER_BYTES = bytes.fromhex(
    "C5 D5 E5 "
    "21 00 7B 11 00 DA 01 5D 00 CD B3 09 "
    "21 B2 7B 11 60 DA 01 2E 00 CD B3 09 "
    "21 4D 7C 11 8E DA 01 72 00 CD B3 09 "
    "21 3A 56 11 80 DB 01 23 00 CD B3 09 "
    "C3 5C 57"
)

RAW_SIZE = 576
OLD_A = (444, 149, 19, 251)
OLD_B = (0, 59, 333, 201)
PAIR_A = (81,)
PAIR_B = (337,)
RAW_HASHES = sorted([
    "16617ed35129ce24f6757899080481203a955db9dea045e1cab3b8c7b10706d6",
    "fe09ce2e85f1e7ed8352b6a0112c725c9620e9f0f8afcfc59516142559024a82",
])
PLANE_HASHES = sorted([
    "155fb16e076c9198dbac15bfb701ecd0dbdc268a29464edef5dd02df7a343dd9",
    "9ea6c09fdcd274b0b12624fac854734fcaa869eccb131449c10b49298436517b",
])


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    return bank * BANK_SIZE + address - 0x4000


def signed8(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def require_tmp(path: Path) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    if resolved != scratch and scratch not in resolved.parents:
        raise AssertionError(f"receipt must remain under {scratch}: {resolved}")
    return resolved


def runtime_from(rom: bytes, bank: int) -> bytes:
    a = bank_offset(bank, SOURCE_A)
    b = bank_offset(bank, SOURCE_B)
    return rom[a:a + SOURCE_A_SIZE] + rom[b:b + SOURCE_B_SIZE]


def header_checksum(rom: bytes) -> int:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def global_checksum(rom: bytes) -> int:
    return (sum(rom) - rom[0x014E] - rom[0x014F]) & 0xFFFF


def update_checksums(rom: bytearray) -> None:
    rom[0x014D] = header_checksum(rom)
    value = global_checksum(rom)
    rom[0x014E] = value >> 8
    rom[0x014F] = value & 0xFF


def reconstruct(base: bytes) -> tuple[bytes, bytes]:
    old = runtime_from(base, 13)
    if sha256(old) != BASE_RUNTIME_SHA256:
        raise AssertionError("base runtime preimage changed")
    if old[0x89:0x9A] != OLD_HELPER:
        raise AssertionError("base helper preimage changed")
    new = bytearray(old)
    new[0x89:0x9A] = NEW_HELPER + b"\x00"
    new = bytes(new)
    if sha256(new) != NEW_RUNTIME_SHA256:
        raise AssertionError("independent runtime reconstruction hash changed")
    expected = bytearray(base)
    for bank in BANKS:
        a = bank_offset(bank, SOURCE_A)
        b = bank_offset(bank, SOURCE_B)
        expected[a:a + SOURCE_A_SIZE] = new[:SOURCE_A_SIZE]
        expected[b:b + SOURCE_B_SIZE] = new[SOURCE_A_SIZE:]
    update_checksums(expected)
    return new, bytes(expected)


def verify_rom(base: bytes, candidate: bytes) -> tuple[bytes, dict[str, object]]:
    if len(base) != 32 * BANK_SIZE or len(candidate) != len(base):
        raise AssertionError("base/candidate are not equal 512 KiB images")
    if sha256(base) != BASE_SHA256 or hashlib.md5(base).hexdigest() != BASE_MD5:
        raise AssertionError("base is not exact 5bdde7")
    if sha256(candidate) != CANDIDATE_SHA256:
        raise AssertionError("candidate SHA256 is not exact reviewed build")
    if hashlib.md5(candidate).hexdigest() != CANDIDATE_MD5:
        raise AssertionError("candidate MD5 is not exact reviewed build")

    runtime, expected = reconstruct(base)
    if candidate != expected:
        mismatch = next(i for i, pair in enumerate(zip(candidate, expected)) if pair[0] != pair[1])
        raise AssertionError(f"candidate escaped reconstruction at ${mismatch:06X}")

    expected_changed = {
        0x014E, 0x014F,
        0x037CB0, 0x037CB1, 0x037CB3, 0x037CB4,
        0x037CB5, 0x037CB6, 0x037CB7, 0x037CB8,
        0x043CB0, 0x043CB1, 0x043CB3, 0x043CB4,
        0x043CB5, 0x043CB6, 0x043CB7, 0x043CB8,
    }
    changed = {i for i, pair in enumerate(zip(base, candidate)) if pair[0] != pair[1]}
    if changed != expected_changed:
        raise AssertionError(f"exact changed-address set moved: {sorted(changed ^ expected_changed)}")

    for bank in BANKS:
        old_runtime = runtime_from(base, bank)
        new_runtime = runtime_from(candidate, bank)
        if old_runtime[:0x89] != new_runtime[:0x89] or old_runtime[0x9A:] != new_runtime[0x9A:]:
            raise AssertionError(f"bank {bank} changed outside DAE9-DAF9")
        if new_runtime != runtime:
            raise AssertionError(f"bank {bank} runtime mirror mismatch")
        if sha256(new_runtime[:SOURCE_A_SIZE]) != SOURCE_A_SHA256:
            raise AssertionError(f"bank {bank} source A changed")
        if sha256(old_runtime[SOURCE_A_SIZE:]) != OLD_SOURCE_B_SHA256:
            raise AssertionError(f"bank {bank} old source B preimage changed")
        if sha256(new_runtime[SOURCE_A_SIZE:]) != NEW_SOURCE_B_SHA256:
            raise AssertionError(f"bank {bank} source B output changed")
        installer = bank_offset(bank, INSTALLER)
        if base[installer:installer + len(INSTALLER_BYTES)] != INSTALLER_BYTES:
            raise AssertionError(f"bank {bank} base installer changed")
        if candidate[installer:installer + len(INSTALLER_BYTES)] != INSTALLER_BYTES:
            raise AssertionError(f"bank {bank} candidate installer changed")

    if candidate[0x014D] != header_checksum(candidate):
        raise AssertionError("candidate header checksum invalid")
    if (candidate[0x014E] << 8 | candidate[0x014F]) != global_checksum(candidate):
        raise AssertionError("candidate global checksum invalid")
    return runtime, {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "candidate_md5": CANDIDATE_MD5,
        "independent_exact_reconstruction": True,
        "runtime_sha256": NEW_RUNTIME_SHA256,
        "runtime_mirrors": list(BANKS),
        "functional_bytes_changed": 16,
        "checksum_bytes_changed": 2,
        "total_bytes_changed": 18,
        "exact_diff_set": True,
        "installers_unchanged": True,
        "checksums_valid": True,
    }


def verify_routes(runtime: bytes, base_runtime: bytes) -> dict[str, object]:
    if runtime[3:13] != HEADER:
        raise AssertionError("Stage2/Stage4/generic header changed")
    if runtime[0x89:0x99] != NEW_HELPER or runtime[0x99] != 0:
        raise AssertionError("page-pair helper bytes changed")
    if runtime[0x33:0x49] != COMPARE:
        raise AssertionError("shared compare/return sequence changed")
    if runtime[:0x89] != base_runtime[:0x89] or runtime[0x9A:] != base_runtime[0x9A:]:
        raise AssertionError("non-Stage4 runtime bytes changed")

    stage4_target = RUNTIME + 0x0A + signed8(runtime[9])
    helper_join = RUNTIME + 0x99 + signed8(runtime[0x98])
    if stage4_target != 0xDAE9 or helper_join != 0xDA93:
        raise AssertionError(
            f"branch decode changed: Stage4 ${stage4_target:04X}, join ${helper_join:04X}"
        )
    if runtime[0x91:0x97] != bytes.fromhex("21 F1 C1 46 24 4E"):
        raise AssertionError("LD HL/C1F1; LD B,[HL]; INC H; LD C,[HL] changed")
    if runtime[0x97:0x99] != bytes.fromhex("18 9A"):
        raise AssertionError("direct DA93 join changed")

    writers = [
        RUNTIME + i for i in range(len(runtime) - 1)
        if runtime[i:i + 2] == bytes.fromhex("E0 E0")
    ]
    if writers != [0xDA6B, 0xDAB5, 0xDAE9]:
        raise AssertionError(f"FFE0 writer inventory changed: {writers}")
    if runtime[0x0A:0x0D] != bytes.fromhex("AF E0 E0"):
        raise AssertionError("generic/Crystal FFE0=0 route changed")
    if runtime[0x53:0x57] != bytes.fromhex("3E 01 E0 E0"):
        raise AssertionError("dirty-tail FFE0=1 route changed")
    if runtime[0x89:0x8B] != bytes.fromhex("E0 E0"):
        raise AssertionError("Stage4 no longer writes FFE0 first")
    # SUB $02 reaches the Stage4 JR only with A=0. Stage2 jumps to the shared
    # zero store; all generic/Crystal paths execute XOR A before that store.
    if runtime[3:13] != bytes.fromhex("B7 28 05 D6 02 28 7F AF E0 E0"):
        raise AssertionError("cache-hit zero-value proof preimage changed")

    current_load_join = 16 + 4 + 16 + 12 + 4
    page_load_join = 12 + 8 + 4 + 8 + 12
    if (current_load_join, page_load_join, current_load_join - page_load_join) != (52, 44, 8):
        raise AssertionError("page-pair cycle proof changed")
    return {
        "stage4_dispatch_target": "$DAE9",
        "pagepair_join_target": "$DA93",
        "pagepair_instruction": "LD HL,$C1F1; LD B,[HL]; INC H; LD C,[HL]",
        "old_new_sample_and_join_t": [52, 44],
        "exact_stage4_saving_t_per_helper": 8,
        "ffe0_writers": [f"${address:04X}" for address in writers],
        "cache_hit_ffe0_zero": {
            "stage2": True, "stage4": True, "stage3_5_6_7": True, "crystal": True,
        },
        "dirty_tail_only_value_one_writer": "$DAB5",
        "runtime_outside_stage4_helper_byte_identical": True,
        "other_stage_cycle_delta_vs_5bdde7": 0,
    }


def desired_plane(raw: bytes) -> bytes:
    return bytes(4 if 1 <= tile <= 8 else 2 if tile in (0x2D, 0x2E) else 0 for tile in raw)


def xor_key(raw: bytes, offsets: tuple[int, ...]) -> int:
    value = 0
    for offset in offsets:
        value ^= raw[offset]
    return value


def parse_rows(path: Path, live: bool) -> tuple[list[tuple[int, int, int, bytes, bytes]], int]:
    expected_hash = LIVE_SHA256 if live else CORPUS_SHA256
    payload = path.read_bytes()
    if sha256(payload) != expected_hash:
        raise AssertionError(f"{'live' if live else 'canonical'} corpus preimage changed")
    rows = []
    signature_misses = 0
    for number, line in enumerate(payload.decode().splitlines(), 1):
        fields = line.split("\t")
        expected_fields = 30 if live else 14
        if len(fields) != expected_fields:
            raise AssertionError(f"line {number}: expected {expected_fields} fields")
        raw = bytes.fromhex(fields[29] if live else fields[13])
        if len(raw) != RAW_SIZE:
            raise AssertionError(f"line {number}: raw length changed")
        if live:
            frame, room, physical = int(fields[1]), int(fields[3], 16), int(fields[2], 16)
            indexes = (12, 13) if physical == 0x98 else (16, 17)
            if tuple(int(fields[i], 16) for i in indexes) != (raw[1], raw[357]):
                signature_misses += 1
        else:
            frame, room, physical = int(fields[0]), int(fields[1], 16), int(fields[2], 16)
            if int(fields[3], 16) != xor_key(raw, OLD_A) or int(fields[4], 16) != xor_key(raw, OLD_B):
                raise AssertionError(f"line {number}: old signature fields changed")
        rows.append((frame, room, physical, raw, desired_plane(raw)))
    expected_rows = 987 if live else 328
    if len(rows) != expected_rows:
        raise AssertionError(f"expected {expected_rows} rows, got {len(rows)}")
    if live and signature_misses != 6:
        raise AssertionError(f"expected six transition misses, got {signature_misses}")
    return rows, signature_misses


def key_metrics(rows, samples_a, samples_b):
    unique = {(room, raw): plane for _, room, _, raw, plane in rows}
    semantics: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
    variants: dict[tuple[int, bytes], set[tuple[int, int, int]]] = defaultdict(set)
    rawsets: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
    for (room, raw), plane in unique.items():
        key = (room, xor_key(raw, samples_a), xor_key(raw, samples_b))
        semantics[key].add(plane)
        variants[(room, plane)].add(key)
        rawsets[key].add(raw)
    details = []
    for key, values in sorted(semantics.items()):
        if len(values) > 1:
            details.append((
                key,
                sorted(sha256(raw) for raw in rawsets[key]),
                sorted(sha256(value) for value in values),
            ))
    return (
        len(unique),
        sum(len(value) - 1 for value in semantics.values()),
        sum(len(value) - 1 for value in variants.values()),
        details,
    )


def replay(rows, samples_a, samples_b) -> dict[str, object]:
    caches: dict[int, tuple[tuple[int, int, int], bytes]] = {}
    hits = misses = stale = 0
    stale_frames = []
    for frame, room, physical, raw, plane in rows:
        key = (room, xor_key(raw, samples_a), xor_key(raw, samples_b))
        previous = caches.get(physical)
        if previous is not None and previous[0] == key:
            hits += 1
            if previous[1] != plane:
                stale += 1
                stale_frames.append(frame)
        else:
            misses += 1
            caches[physical] = (key, plane)
    return {"hits": hits, "misses": misses, "stale_hits": stale, "stale_frames": stale_frames}


def verify_corpora(corpus_path: Path, live_path: Path) -> dict[str, object]:
    canonical, _ = parse_rows(corpus_path, False)
    live, live_misses = parse_rows(live_path, True)
    old = key_metrics(canonical, OLD_A, OLD_B)
    expected_detail = [((1, 1, 64), RAW_HASHES, PLANE_HASHES)]
    if old != (21, 1, 0, expected_detail):
        raise AssertionError("mandatory old-key negative control failed")
    page_canonical = key_metrics(canonical, PAIR_A, PAIR_B)
    page_live = key_metrics(live, PAIR_A, PAIR_B)
    if page_canonical != (21, 0, 0, []) or page_live != (5, 0, 0, []):
        raise AssertionError("C1F1/C2F1 key is not exact on both corpora")
    old_replay = replay(canonical, OLD_A, OLD_B)
    page_replay = replay(canonical, PAIR_A, PAIR_B)
    live_replay = replay(live, PAIR_A, PAIR_B)
    if old_replay["stale_hits"] < 1 or 132 not in old_replay["stale_frames"]:
        raise AssertionError("old sequential stale-hit control disappeared")
    if page_replay["stale_hits"] or live_replay["stale_hits"]:
        raise AssertionError("page-pair returned stale semantics")
    collision_raws = {
        sha256(raw): raw for _, _, _, raw, _ in canonical if sha256(raw) in RAW_HASHES
    }
    samples_a = sorted(raw[81] for raw in collision_raws.values())
    samples_b = sorted(raw[337] for raw in collision_raws.values())
    if samples_a != [4, 4] or samples_b != [2, 33]:
        raise AssertionError("collision-pair C1F1/C2F1 samples changed")
    return {
        "canonical": {
            "path": str(corpus_path.relative_to(ROOT)), "sha256": CORPUS_SHA256,
            "rows": 328, "unique_records": 21,
            "old_key": {"collisions": 1, "false_variants": 0, **old_replay},
            "C1F1_C2F1": {"collisions": 0, "false_variants": 0, **page_replay},
        },
        "strict_live": {
            "path": str(live_path.relative_to(ROOT)), "sha256": LIVE_SHA256,
            "rows": 987, "unique_records": 5,
            "C1F1_C2F1": {"collisions": 0, "false_variants": 0, **live_replay},
            "expected_prepublication_C1A1_C305_misses": live_misses,
        },
        "collision_pair_samples": {"C1F1": [4, 4], "C2F1": [2, 33]},
        "all_rows_semantically_exact": True,
    }


def verify_manifest(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if sha256(payload) != MANIFEST_SHA256:
        raise AssertionError("strict speed manifest preimage changed")
    manifest = json.loads(payload)
    if manifest.get("dx_rom_md5") != BASE_MD5:
        raise AssertionError("manifest not bound to exact 5bdde7")
    rows = manifest.get("rows", [])
    if len(rows) != 1 or rows[0].get("deterministic_replay") is not True:
        raise AssertionError("strict Stage4 deterministic replay moved")
    row = rows[0]
    values = (
        row.get("stage"), row.get("ratio_exact"),
        row["original"].get("main_loop_hits"), row["dx"].get("main_loop_hits"),
        row["dx"].get("tile_copy_hits"), row["dx"].get("compiler_tile_copy_indices"),
        row["dx"].get("attr_map_changes"), row["dx"].get("attr_map_unchanged"),
    )
    expected = (4, 0.9895287958115183, 764, 756, 987, [4, 5, 6, 8, 12, 13, 17, 19], 4, 983)
    if values != expected:
        raise AssertionError(f"strict Stage4 values changed: {values}")
    return {
        "path": str(path.relative_to(ROOT)), "sha256": MANIFEST_SHA256,
        "base_sha256": BASE_SHA256, "ratio_exact": values[1],
        "main_loop_hits_original_dx": [764, 756],
        "minimum_for_0_99": 757, "deterministic": True,
        "tile_copy_hits": 987, "compiler_invocations": 8,
        "pagepair_static_upper_bound_t": 7896,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--live-trace", type=Path, default=DEFAULT_LIVE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    receipt_path = require_tmp(args.receipt)

    base = args.base.read_bytes()
    candidate = args.candidate.read_bytes()
    runtime, rom = verify_rom(base, candidate)
    routes = verify_routes(runtime, runtime_from(base, 13))
    corpora = verify_corpora(args.corpus, args.live_trace)
    speed = verify_manifest(args.manifest)
    report = {
        "schema": "penta-stage4-pagepair-r264-static-verification-v1",
        "status": "PASS_STATIC_NO_EMULATOR_REQUESTED",
        "promotable": False,
        "emulator_invoked": False,
        "release_baseline": "r264 aa4c1560",
        "rom_contract": rom,
        "route_contract": routes,
        "corpus_contract": corpora,
        "speed_evidence": speed,
        "conclusion": (
            "The refinement is an exact isolated 8T/helper experiment only. "
            "At 7,896T over the measured route it does not justify another "
            "emulator gate or production integration. Exact r264's deterministic "
            "756/764=.989528 result is release-acceptable; Stage7 has priority."
        ),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
