#!/usr/bin/env python3
"""Independently verify the exact-r264 Stage 4 1+1-key candidate.

This is a static, fail-closed verifier.  It reconstructs the only permitted
ROM delta, decodes every new branch target, proves the FFE0 cache-hit writes,
replays C1A1/C305 semantics over the complete archived Stage 4 corpus, and
quantifies the shared +4T risk against the pinned all-stage speed receipt.

It never launches an emulator and writes only a JSON receipt below repo tmp/.
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
DEFAULT_CANDIDATE = TMP_ROOT / "stage4-key11-r264-candidate/candidate.gb"
DEFAULT_TRACE = (
    TMP_ROOT
    / "stage2-isolated-entry-r263/stage346-semantic-soak-8000/"
    "stage4.layout-events.tsv"
)
DEFAULT_SPEED = (
    TMP_ROOT
    / "stage1-menu-hidden-repair-r264/all-stage-speed-right-r1/manifest.json"
)
DEFAULT_RECEIPT = (
    TMP_ROOT / "stage4-key11-r264-candidate/static-verification.json"
)

BASE_SHA256 = (
    "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
)
BASE_MD5 = "cd025fd5c3ccdf49ac5a9ebebceff8e5"
CANDIDATE_SHA256 = (
    "5bdde7cdf14f2600c97fefd5f400cdb6d17c6bc730d84da9b7449becf7d96e7e"
)
CANDIDATE_MD5 = "81b5df2955b4f74cc4c55640da6b82b2"
TRACE_SHA256 = (
    "54becf276a33dc9f51cce123d39c8ce80f58be04f4b186a534c34ae2a672c90a"
)
SPEED_SHA256 = (
    "7b32a6d44db7f11370747930896377cbfad1ed7b21b7b482cb3fb73c4525ac49"
)

BANK_SIZE = 0x4000
BANKS = (13, 16)
SOURCE_A = 0x7BB2
SOURCE_A_SIZE = 46
SOURCE_B = 0x7C4D
SOURCE_B_SIZE = 114
INSTALLER = 0x7CBF
RUNTIME_ADDR = 0xDA60
RUNTIME_SIZE = 160

OLD_RUNTIME_SHA256 = (
    "765d22df24f270dd5210500f05ae101278edab35ee0c8707bed26738f90c8b5a"
)
NEW_RUNTIME_SHA256 = (
    "c6feb9acd86779de5571e2e033209c1650dcd5d86f93e8ab14c6f92404836ef7"
)
NEW_SOURCE_A_SHA256 = (
    "8c668be4a80c7f077ccee60a93582ec3cbed6a2ba3d3c18ba171b47e6354790f"
)
NEW_SOURCE_B_SHA256 = (
    "b7210e3a16f625543516060ac494de889c8804ae3fea85b6809626b7aae9add6"
)
EXPECTED_INSTALLER = bytes.fromhex(
    "C5 D5 E5 "
    "21 00 7B 11 00 DA 01 5D 00 CD B3 09 "
    "21 B2 7B 11 60 DA 01 2E 00 CD B3 09 "
    "21 4D 7C 11 8E DA 01 72 00 CD B3 09 "
    "21 3A 56 11 80 DB 01 23 00 CD B3 09 "
    "C3 5C 57"
)
HEADER = bytes.fromhex("B7 28 05 D6 02 28 7F AF E0 E0")
DISPATCHER = bytes.fromhex(
    "06 05 FA 80 D8 D6 03 FE 06 38 10 D6 09 FE 09 38 02 AF C9 "
    "FE 02 2F 28 8F C3 A4 DB C3 60 DA"
)
ARENA_PREFIX = bytes.fromhex(
    "FA 80 D8 E6 F7 FE 02 C2 B9 DA 3E 15 CD 61 00 C3 00 41"
)
STAGE4_HELPER = bytes.fromhex(
    "E0 E0 7C EE CB 5F 16 DF FA A1 C1 47 FA 05 C3 18 98"
)

RAW_SIZE = 24 * 24
OLD_A = (444, 149, 19, 251)
OLD_B = (0, 59, 333, 201)
NEW_A = (1,)
NEW_B = (357,)
RAW_A_SHA256 = (
    "16617ed35129ce24f6757899080481203a955db9dea045e1cab3b8c7b10706d6"
)
RAW_B_SHA256 = (
    "fe09ce2e85f1e7ed8352b6a0112c725c9620e9f0f8afcfc59516142559024a82"
)
PLANE_A_SHA256 = (
    "155fb16e076c9198dbac15bfb701ecd0dbdc268a29464edef5dd02df7a343dd9"
)
PLANE_B_SHA256 = (
    "9ea6c09fdcd274b0b12624fac854734fcaa869eccb131449c10b49298436517b"
)

EXPECTED_SPEED = {
    3: (0.9943, 699, 695, 953, 14, 14),
    4: (0.9895, 764, 756, 985, 14, 14),
    5: (0.9924, 790, 784, 1227, 18, 18),
    6: (0.9947, 756, 752, 851, 14, 14),
    7: (0.9801, 806, 790, 903, 110, 70),
}


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    return bank * BANK_SIZE + address - 0x4000 if bank else address


def signed8(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def require_tmp(path: Path) -> Path:
    resolved = path.resolve()
    tmp = TMP_ROOT.resolve()
    if resolved != tmp and tmp not in resolved.parents:
        raise AssertionError(f"receipt must stay under {tmp}: {resolved}")
    return resolved


def header_checksum(rom: bytes) -> int:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def global_checksum(rom: bytes) -> int:
    return (sum(rom) - rom[0x014E] - rom[0x014F]) & 0xFFFF


def update_checksums(rom: bytearray) -> None:
    rom[0x014D] = header_checksum(rom)
    total = global_checksum(rom)
    rom[0x014E] = total >> 8
    rom[0x014F] = total & 0xFF


def runtime_from(rom: bytes, bank: int) -> bytes:
    a = bank_offset(bank, SOURCE_A)
    b = bank_offset(bank, SOURCE_B)
    return rom[a:a + SOURCE_A_SIZE] + rom[b:b + SOURCE_B_SIZE]


def reconstruct_expected(base: bytes) -> tuple[bytes, bytes]:
    old = runtime_from(base, 13)
    if len(old) != RUNTIME_SIZE or sha256(old) != OLD_RUNTIME_SHA256:
        raise AssertionError("old DA60 runtime preimage changed")
    new = bytearray(old)
    new[3:13] = HEADER
    new[13:0x59] = old[12:0x58]
    new[0x59:0x77] = DISPATCHER
    new[0x89:0x9A] = STAGE4_HELPER
    if new[0x9A:0xA0] != bytes(6):
        raise AssertionError("expected DAFA-DAFF zero metadata changed")
    expected_runtime = bytes(new)
    if sha256(expected_runtime) != NEW_RUNTIME_SHA256:
        raise AssertionError("independent runtime reconstruction hash changed")

    expected_rom = bytearray(base)
    for bank in BANKS:
        a = bank_offset(bank, SOURCE_A)
        b = bank_offset(bank, SOURCE_B)
        expected_rom[a:a + SOURCE_A_SIZE] = expected_runtime[:SOURCE_A_SIZE]
        expected_rom[b:b + SOURCE_B_SIZE] = expected_runtime[SOURCE_A_SIZE:]
    update_checksums(expected_rom)
    return expected_runtime, bytes(expected_rom)


def verify_rom(base: bytes, candidate: bytes) -> tuple[bytes, dict[str, object]]:
    if len(base) != len(candidate) or len(base) != 32 * BANK_SIZE:
        raise AssertionError("base/candidate are not equal 512 KiB images")
    if sha256(base) != BASE_SHA256 or hashlib.md5(base).hexdigest() != BASE_MD5:
        raise AssertionError("base is not exact r264 aa4c1560")
    if (
        sha256(candidate) != CANDIDATE_SHA256
        or hashlib.md5(candidate).hexdigest() != CANDIDATE_MD5
    ):
        raise AssertionError("candidate digest is not the reviewed build")

    expected_runtime, expected_candidate = reconstruct_expected(base)
    if candidate != expected_candidate:
        mismatch = next(
            index
            for index, pair in enumerate(zip(candidate, expected_candidate))
            if pair[0] != pair[1]
        )
        raise AssertionError(f"candidate escaped exact reconstruction at ${mismatch:06X}")

    changed = [
        index for index, pair in enumerate(zip(base, candidate))
        if pair[0] != pair[1]
    ]
    functional_ranges = []
    for bank in BANKS:
        functional_ranges.extend(
            [
                range(
                    bank_offset(bank, SOURCE_A),
                    bank_offset(bank, SOURCE_A) + SOURCE_A_SIZE,
                ),
                range(
                    bank_offset(bank, SOURCE_B),
                    bank_offset(bank, SOURCE_B) + SOURCE_B_SIZE,
                ),
            ]
        )
    allowed = {0x014D, 0x014E, 0x014F}
    for addresses in functional_ranges:
        allowed.update(addresses)
    if not set(changed) <= allowed:
        raise AssertionError("candidate diff escaped source/checksum allowlist")
    functional_changed = [index for index in changed if index > 0x014F]
    if len(functional_changed) != 198 or len(changed) != 200:
        raise AssertionError("candidate changed-byte counts moved")

    runtimes = []
    for bank in BANKS:
        runtime = runtime_from(candidate, bank)
        if runtime != expected_runtime:
            raise AssertionError(f"bank {bank} runtime mirror differs")
        if sha256(runtime[:SOURCE_A_SIZE]) != NEW_SOURCE_A_SHA256:
            raise AssertionError(f"bank {bank} source-A output hash changed")
        if sha256(runtime[SOURCE_A_SIZE:]) != NEW_SOURCE_B_SHA256:
            raise AssertionError(f"bank {bank} source-B output hash changed")
        installer_offset = bank_offset(bank, INSTALLER)
        if (
            base[installer_offset:installer_offset + len(EXPECTED_INSTALLER)]
            != EXPECTED_INSTALLER
            or candidate[
                installer_offset:installer_offset + len(EXPECTED_INSTALLER)
            ]
            != EXPECTED_INSTALLER
        ):
            raise AssertionError(f"bank {bank} installer changed")
        runtimes.append(runtime)
    if runtimes[0] != runtimes[1]:
        raise AssertionError("candidate runtime mirrors are not byte-identical")

    if candidate[0x014D] != header_checksum(candidate):
        raise AssertionError("header checksum is invalid")
    stored_global = (candidate[0x014E] << 8) | candidate[0x014F]
    if stored_global != global_checksum(candidate):
        raise AssertionError("global checksum is invalid")

    return expected_runtime, {
        "base_sha256": BASE_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "candidate_md5": CANDIDATE_MD5,
        "candidate_exact_independent_reconstruction": True,
        "runtime_mirror_banks": list(BANKS),
        "runtime_sha256": NEW_RUNTIME_SHA256,
        "functional_bytes_changed": len(functional_changed),
        "total_bytes_changed": len(changed),
        "diff_allowlist_exact": True,
        "installers_unchanged": True,
        "checksums_valid": True,
    }


def verify_routes(runtime: bytes) -> dict[str, object]:
    if runtime[3:13] != HEADER:
        raise AssertionError("new DA63 header bytes changed")
    if runtime[0x59:0x77] != DISPATCHER:
        raise AssertionError("new DAB9 dispatcher bytes changed")
    if runtime[0x77:0x89] != ARENA_PREFIX:
        raise AssertionError("DAD7 arena input-kill prefix changed")
    if runtime[0x89:0x9A] != STAGE4_HELPER:
        raise AssertionError("DAE9 Stage 4 helper bytes changed")

    stage2_target = 0xDA66 + signed8(runtime[5])
    stage4_target = 0xDA6A + signed8(runtime[9])
    helper_join = 0xDAFA + signed8(runtime[0x99])
    crystal_target = 0xDAD1 + signed8(runtime[0x70])
    expected_targets = {
        "stage2_zero": 0xDA6B,
        "stage4_helper": 0xDAE9,
        "stage4_join": 0xDA92,
        "crystal_to_header": 0xDA60,
    }
    actual_targets = {
        "stage2_zero": stage2_target,
        "stage4_helper": stage4_target,
        "stage4_join": helper_join,
        "crystal_to_header": crystal_target,
    }
    if actual_targets != expected_targets:
        raise AssertionError(f"decoded branch targets changed: {actual_targets}")
    if runtime[0x32] != 0x4F:
        raise AssertionError("Stage 4 helper no longer joins at LD C,A")
    if bytes.fromhex("FA A1 C1") not in STAGE4_HELPER:
        raise AssertionError("helper lost exact C1A1 load")
    if bytes.fromhex("FA 05 C3") not in STAGE4_HELPER:
        raise AssertionError("helper lost exact C305 load")
    if runtime[0x33:0x49] != bytes.fromhex(
        "1A B8 20 13 13 1A B9 20 0D 13 1A 6F F0 BD BD 20 04 E1 D1 C1 C9 1B"
    ):
        raise AssertionError("shared cache-hit compare/return sequence changed")

    ffe0_writes = [
        RUNTIME_ADDR + offset
        for offset in range(len(runtime) - 1)
        if runtime[offset:offset + 2] == bytes.fromhex("E0 E0")
    ]
    if ffe0_writes != [0xDA6B, 0xDAB5, 0xDAE9]:
        raise AssertionError(f"unexpected FFE0 writers: {ffe0_writes}")
    if runtime[0x53:0x57] != bytes.fromhex("3E 01 E0 E0"):
        raise AssertionError("dirty-tail FFE0=1 writer changed")
    if runtime[0x0A:0x0D] != bytes.fromhex("AF E0 E0"):
        raise AssertionError("generic FFE0=0 writer changed")
    if runtime[0x89:0x8B] != bytes.fromhex("E0 E0"):
        raise AssertionError("Stage 4 helper does not publish FFE0=0 first")

    # Model only the new header's A/branch behavior.  Stage identity 0 is the
    # Stage 2 fast route; 2 is Stage 4; all other normalized identities clear
    # A explicitly before the shared store.
    def header_route(value: int) -> tuple[str, int]:
        value &= 0xFF
        if value == 0:
            return "stage2", value
        value = (value - 2) & 0xFF
        if value == 0:
            return "stage4", value
        value ^= value
        return "generic", value

    modeled = {str(value): header_route(value) for value in range(6)}
    if any(final != 0 for _, final in modeled.values()):
        raise AssertionError("a dungeon cache-hit route can leak nonzero FFE0")
    crystal_after_cpl = (~2) & 0xFF
    crystal_route = header_route(crystal_after_cpl)
    if crystal_route != ("generic", 0):
        raise AssertionError("Crystal route does not clear FFE0")

    # CP 2 sets Z for Crystal, CPL preserves flags, and the conditional JR has
    # the same timing as the replaced conditional JP.  For every other arena,
    # DAD7 overwrites A and the following AND overwrites flags before CP/JR.
    if runtime[0x6C:0x71] != bytes.fromhex("FE 02 2F 28 8F"):
        raise AssertionError("cycle-equal Crystal discriminator changed")
    if runtime[0x77:0x7C] != bytes.fromhex("FA 80 D8 E6 F7"):
        raise AssertionError("arena route no longer kills complemented A/flags")

    old_stage2_header = 4 + 12 + 12
    new_stage2_header = 4 + 12 + 12
    old_generic_header = 4 + 8 + 12 + 4 + 12
    new_generic_header = 4 + 8 + 8 + 8 + 4 + 12
    generic_body_to_compare = 40 + 144
    stage4_helper_to_compare = 12 + 4 + 8 + 4 + 8 + 16 + 4 + 16 + 12 + 4
    old_stage4_precompare = old_generic_header + generic_body_to_compare
    new_stage4_precompare = 4 + 8 + 8 + 12 + stage4_helper_to_compare
    if (
        old_stage2_header != new_stage2_header
        or new_generic_header - old_generic_header != 4
        or old_stage4_precompare - new_stage4_precompare != 104
    ):
        raise AssertionError("static cycle proof changed")
    if (8 + 16, 8 + 4 + 12, 8 + 12, 8 + 4 + 8) != (24, 24, 20, 20):
        raise AssertionError("dispatcher CP/JP to CP/CPL/JR timing is not equal")

    return {
        "decoded_branch_targets": {
            name: f"${address:04X}" for name, address in actual_targets.items()
        },
        "cache_hit_ffe0_zero": {
            "stage2": True,
            "stage4": True,
            "generic_stages_3_5_6_7": True,
            "crystal": True,
        },
        "ffe0_write_addresses": [f"${address:04X}" for address in ffe0_writes],
        "dirty_tail_only_value_one_writer": "$DAB5",
        "arena_complement_input_dead_before_branch": True,
        "cycle_proof": {
            "stage2_header_old_new": [old_stage2_header, new_stage2_header],
            "generic_header_old_new": [old_generic_header, new_generic_header],
            "stage4_precompare_old_new": [
                old_stage4_precompare,
                new_stage4_precompare,
            ],
            "stage4_saving_t_cycles": 104,
            "generic_cost_t_cycles": 4,
            "crystal_dispatch_taken_old_new": [24, 24],
            "arena_dispatch_not_taken_old_new": [20, 20],
        },
    }


def xor_key(raw: bytes, offsets: tuple[int, ...]) -> int:
    value = 0
    for offset in offsets:
        value ^= raw[offset]
    return value


def desired_plane(raw: bytes) -> bytes:
    lut = bytearray(256)
    for tile in range(1, 9):
        lut[tile] = 4
    lut[0x2D] = lut[0x2E] = 2
    return bytes(lut[tile] for tile in raw)


def verify_corpus(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if sha256(payload) != TRACE_SHA256:
        raise AssertionError("Stage 4 corpus preimage changed")
    rows = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) != 14:
            raise AssertionError(f"trace line {line_number} is malformed")
        raw = bytes.fromhex(fields[13])
        if len(raw) != RAW_SIZE:
            raise AssertionError(f"trace line {line_number} raw size changed")
        if int(fields[3], 16) != xor_key(raw, OLD_A):
            raise AssertionError(f"trace line {line_number} old A mismatch")
        if int(fields[4], 16) != xor_key(raw, OLD_B):
            raise AssertionError(f"trace line {line_number} old B mismatch")
        rows.append(
            (
                int(fields[0]),
                int(fields[1], 16),
                int(fields[2], 16),
                raw,
                desired_plane(raw),
            )
        )
    if len(rows) != 328:
        raise AssertionError(f"expected 328 Stage 4 rows, got {len(rows)}")

    unique = {(room, raw): plane for _, room, _, raw, plane in rows}
    if len(unique) != 21:
        raise AssertionError(f"expected 21 unique records, got {len(unique)}")

    def metrics(samples_a: tuple[int, ...], samples_b: tuple[int, ...]):
        semantics: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
        keys: dict[tuple[int, bytes], set[tuple[int, int, int]]] = defaultdict(set)
        raws: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
        for (room, raw), plane in unique.items():
            key = (room, xor_key(raw, samples_a), xor_key(raw, samples_b))
            semantics[key].add(plane)
            keys[(room, plane)].add(key)
            raws[key].add(raw)
        collisions = sum(len(value) - 1 for value in semantics.values())
        variants = sum(len(value) - 1 for value in keys.values())
        collision_detail = []
        for key, planes in semantics.items():
            if len(planes) > 1:
                collision_detail.append(
                    (
                        key,
                        sorted(sha256(raw) for raw in raws[key]),
                        sorted(sha256(plane) for plane in planes),
                    )
                )
        return collisions, variants, sorted(collision_detail)

    old = metrics(OLD_A, OLD_B)
    expected_old = [
        (
            (0x01, 0x01, 0x40),
            sorted([RAW_A_SHA256, RAW_B_SHA256]),
            sorted([PLANE_A_SHA256, PLANE_B_SHA256]),
        )
    ]
    if old != (1, 0, expected_old):
        raise AssertionError("mandatory old collision negative control failed")
    new = metrics(NEW_A, NEW_B)
    if new != (0, 0, []):
        raise AssertionError("C1A1/C305 key is not exact over unique corpus")

    collision_raws = {
        sha256(raw): raw
        for _, _, _, raw, _ in rows
        if sha256(raw) in (RAW_A_SHA256, RAW_B_SHA256)
    }
    raw_a = collision_raws[RAW_A_SHA256]
    raw_b = collision_raws[RAW_B_SHA256]
    if (raw_a[1], raw_b[1], raw_a[357], raw_b[357]) != (
        0x43,
        0x43,
        0x32,
        0x43,
    ):
        raise AssertionError("collision pair's exact 1+1 samples changed")

    # Synthetic per-physical-map replay is an intentionally strict negative
    # control: the old key aliases the consecutive frame-131/132 layouts,
    # while the new key never returns a stale desired plane on any row.
    def replay(samples_a: tuple[int, ...], samples_b: tuple[int, ...]):
        cache: dict[int, tuple[tuple[int, int, int], bytes]] = {}
        hits = misses = stale_hits = 0
        stale_frames = []
        for frame, room, active_map, raw, plane in rows:
            key = (room, xor_key(raw, samples_a), xor_key(raw, samples_b))
            previous = cache.get(active_map)
            if previous is not None and previous[0] == key:
                hits += 1
                if previous[1] != plane:
                    stale_hits += 1
                    stale_frames.append(frame)
            else:
                misses += 1
                cache[active_map] = (key, plane)
        return hits, misses, stale_hits, stale_frames

    old_replay = replay(OLD_A, OLD_B)
    new_replay = replay(NEW_A, NEW_B)
    if old_replay[2] < 1 or 132 not in old_replay[3]:
        raise AssertionError("old-key sequential negative control disappeared")
    if new_replay[2] != 0:
        raise AssertionError("new key returns stale semantics in corpus replay")

    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": TRACE_SHA256,
        "rows": len(rows),
        "unique_room_raw_records": len(unique),
        "mandatory_old_negative_control": {
            "collisions": old[0],
            "false_variants": old[1],
            "sequential_stale_hits": old_replay[2],
            "stale_frames": old_replay[3],
        },
        "C1A1_C305": {
            "addresses": ["$C1A1", "$C305"],
            "samples": [[raw_a[1], raw_b[1]], [raw_a[357], raw_b[357]]],
            "collisions": new[0],
            "false_variants": new[1],
            "sequential_cache_hits": new_replay[0],
            "sequential_cache_misses": new_replay[1],
            "sequential_stale_hits": new_replay[2],
            "all_328_rows_exact": True,
        },
    }


def verify_speed(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    if sha256(payload) != SPEED_SHA256:
        raise AssertionError("speed receipt preimage changed")
    manifest = json.loads(payload)
    if manifest.get("dx_rom_md5") != BASE_MD5:
        raise AssertionError("speed receipt is not exact-r264 evidence")
    rows = {int(row["stage"]): row for row in manifest["rows"]}
    result = {}
    for stage, expected in EXPECTED_SPEED.items():
        row = rows[stage]
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
            raise AssertionError(f"Stage {stage} pinned speed row changed")
        minimum = (99 * original["main_loop_hits"] + 99) // 100
        headroom = dx["main_loop_hits"] - minimum
        delta = -104 if stage == 4 else 4
        aggregate = delta * dx["tile_copy_hits"]
        result[str(stage)] = {
            "baseline_ratio": row["ratio"],
            "baseline_hits": [
                original["main_loop_hits"],
                dx["main_loop_hits"],
            ],
            "minimum_dx_hits_for_0_99": minimum,
            "baseline_headroom_loops": headroom,
            "decisions": dx["tile_copy_hits"],
            "candidate_delta_t_per_decision": delta,
            "candidate_aggregate_t": aggregate,
            "absolute_delta_t_per_baseline_dx_loop": round(
                abs(aggregate) / dx["main_loop_hits"], 4
            ),
        }
    if (
        result["3"]["baseline_headroom_loops"] != 2
        or result["4"]["baseline_headroom_loops"] != -1
        or result["5"]["baseline_headroom_loops"] != 1
        or result["6"]["baseline_headroom_loops"] != 3
        or result["7"]["baseline_headroom_loops"] != -8
    ):
        raise AssertionError("measured headroom interpretation changed")
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": SPEED_SHA256,
        "stages": result,
        "conclusion": (
            "The shared cost is exactly +4T/decision: +3812T in Stage 3, "
            "+4908T in Stage 5, +3404T in Stage 6, and +3612T in separately "
            "handled Stage 7. Stage 5's one-loop headroom is the promotion "
            "risk. Stage 4 statically saves 102440T across 985 decisions."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--trace", type=Path, default=DEFAULT_TRACE)
    parser.add_argument("--speed", type=Path, default=DEFAULT_SPEED)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    receipt_path = require_tmp(args.receipt)

    runtime, rom_contract = verify_rom(
        args.base.read_bytes(), args.candidate.read_bytes()
    )
    routes = verify_routes(runtime)
    corpus = verify_corpus(args.trace)
    speed = verify_speed(args.speed)
    report = {
        "schema": "penta-stage4-key11-r264-static-verification-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "rom_contract": rom_contract,
        "route_contract": routes,
        "corpus_contract": corpus,
        "speed_risk": speed,
        "next_gate": (
            "Run the project single-flight Stage 3-6 speed matrix, then the "
            "Stage 4 semantic/visual soak. Do not promote on static evidence."
        ),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
