#!/usr/bin/env python3
"""Build the exact-r281 Stage-4 page-pair fast path with lazy departure.

Only the Stage-4-owned material helper maps bank 22 and installs the fast
WRAM path.  The original later-stage transition selector, exact DAE9 router,
and every non-Stage-4 transition remain byte-for-byte unchanged.  The first
subsequent non-Stage-4 DAD4 call restores DAD5=$60 and tail-enters the exact
native DA60 decider; all later calls are therefore instruction-exact r281.

This is a static builder.  It never imports or launches an emulator, and all
generated artifacts remain below the repository-local ignored ``tmp/`` tree.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"

R279_SHA256 = "649dab3b8895e680ff9e64005641de89b3ac1f66bcb417d6a1c42ce98bc30a9d"
R281_SHA256 = "6b2bb22129011d06a1d5f5eb07a34c04f5dc09c35d9df65afa4a000546a8cf49"
EXPECTED_CANDIDATE_SHA256 = (
    "f93cbfd20760ec88363b039c47373422e90453116a841a872e22ef293d29ce75"
)
EXPECTED_CHANGED_BYTES = 143
EXPECTED_FUNCTIONAL_CHANGED_BYTES = 141

BANK_SIZE = 0x4000
MIRROR_BANKS = (13, 16)
OVERLAY_BANK = 22

STAGE4_ENTRY_ADDR = 0x7C22
STAGE4_ENTRY_OLD = bytes.fromhex("21 01 C6 3E 04 06 08 C3")
STAGE4_ENTRY_NEW = bytes.fromhex("F0 99 F5 3E 16 CD 61 00")
STAGE4_A_STUB_ADDR = 0x5413
STAGE4_A_STUB = bytes.fromhex("3E 04 C9")
STAGE4_MATERIAL_CONT_ADDR = 0x7C44
STAGE4_MATERIAL_CONT = bytes.fromhex("22 05 20 FC C3 F5 7C")
STAGE4_MATERIAL_TAIL_ADDR = 0x7CF5
STAGE4_MATERIAL_TAIL = bytes.fromhex("2E 2D 3E 02 22 77 C9")
STAGE4_BANK22_LANDING_ADDR = 0x7C2A
INSTALLER_ADDR = 0x6000
WRAM_PAYLOAD_ADDR = 0x6300
TRAMPOLINE_PAYLOAD_ADDR = 0x633C

RUNTIME_SOURCE_A_ADDR = 0x7BB2
RUNTIME_SOURCE_A_SIZE = 46
RUNTIME_SOURCE_B_ADDR = 0x7C4D
RUNTIME_SOURCE_B_SIZE = 114
RUNTIME_ADDR = 0xDA60
RUNTIME_SIZE = RUNTIME_SOURCE_A_SIZE + RUNTIME_SOURCE_B_SIZE
RUNTIME_LANDING_JP_ADDR = 0xDAD4
RUNTIME_LANDING_OPERAND_ADDR = 0xDAD5
RUNTIME_REDIRECT_OPERAND_ADDR = 0xDAB7
RUNTIME_COMPARE_ADDR = 0xDA92
RUNTIME_ROUTER_ADDR = 0xDAE9
RUNTIME_DISPATCH_ADDR = 0xDAB9
TRAMPOLINE_ADDR = 0xDA5D
WRAM_BLOCK_ADDR = 0xDB00
WRAM_BLOCK_SIZE = 0x3C
GUARD_ADDR = 0xDB20
HELPER_ADDR = 0xDB26

TRAMPOLINE = bytes.fromhex("C3 20 DB")
RESTORER = bytes.fromhex(
    "3E 60 EA D5 DA "                     # restore DAD5 first
    "FA 80 D8 D6 03 "                     # exact normalized dispatcher A
    "C3 60 DA"                            # service current call natively
)
GUARD = bytes.fromhex("F0 BA FE 03 20 DA")
HELPER = bytes.fromhex(
    "C5 D5 E5 AF E0 E0 7C EE CB 5F 16 DF "
    "21 F1 C1 46 24 4E C3 92 DA"
)
RUNTIME_INSTALLER_ADDR = 0x7CC2
RUNTIME_INSTALLER_PREFIX = bytes.fromhex(
    "21 00 7B 11 00 DA 01 5D 00 CD B3 09 "
    "21 B2 7B 11 60 DA 01 2E 00 CD B3 09 "
    "21 4D 7C 11 8E DA"
)
ROUTER = bytes.fromhex(
    "E1 D1 C1 F5 FA 80 D8 FE 08 28 02 18 00 "
    "F3 F1 F1 F1 3E 16 C3 47 08"
)
SHARED_COMPARE = bytes.fromhex(
    "1A B8 20 13 13 1A B9 20 0D 13 1A 6F "
    "F0 BD BD 20 04 E1 D1 C1 C9"
)
DISPATCH_NORMALIZE_AND_DAD4_BRANCH = bytes.fromhex(
    "06 05 FA 80 D8 D6 03 FE 06 38 10"
)

R281_VISUAL_DELTA = {
    0x014E: (0x7E, 0x7D),
    0x014F: (0xFD, 0xDF),
    0x0368CC: (0xFF, 0x4A),
    0x0368CD: (0x03, 0x29),
    0x0428CC: (0xFF, 0x4A),
    0x0428CD: (0x03, 0x29),
}

CANONICAL_CORPUS = (
    TMP / "stage2-isolated-entry-r263/stage346-semantic-soak-8000/"
    "stage4.layout-events.tsv"
)
CANONICAL_CORPUS_SHA256 = (
    "54becf276a33dc9f51cce123d39c8ce80f58be04f4b186a534c34ae2a672c90a"
)
LIVE_CORPUS = (
    TMP / "stage7-lazy-disarm-r279/stages134567-speed-right-strict99-r1/"
    "stage4-dx-a-right/attr-events.tsv"
)
LIVE_CORPUS_SHA256 = (
    "d23a6cb7699a82bc6c7f0fe99c189fa6a34d9dd019a2b1389257e72de8af18fb"
)
SPEED_MANIFEST = (
    TMP / "stage7-lazy-disarm-r279/stages134567-speed-right-strict99-r1/"
    "manifest.json"
)
SPEED_MANIFEST_SHA256 = (
    "c644b20b24f71dd28cdf1268a18c9adad9ed44b75d56c540b01925fb662db8a9"
)

WRAM_OWNERSHIP_ROOT = TMP / "r285-wram-ownership-r281"
WRAM_OWNERSHIP_SHA256 = (
    "38723a2e5e8a17aa7950dc008209944e898f69a7bd10a23c839d341e935fd5ca"
)
WRAM_META = {
    2: "frame=612 target=1 expected_scene=03 D880=03 FFC1=01 FF91=09 DF02=5A DF0D=03 FFBA=01",
    3: "frame=613 target=2 expected_scene=04 D880=04 FFC1=01 FF91=0E DF02=5A DF0D=04 FFBA=02",
    4: "frame=613 target=3 expected_scene=05 D880=05 FFC1=01 FF91=0F DF02=5A DF0D=05 FFBA=03",
    5: "frame=613 target=4 expected_scene=06 D880=06 FFC1=01 FF91=0C DF02=5A DF0D=06 FFBA=04",
    6: "frame=613 target=5 expected_scene=07 D880=07 FFC1=01 FF91=0D DF02=5A DF0D=07 FFBA=05",
    7: "frame=613 target=6 expected_scene=08 D880=08 FFC1=01 FF91=02 DF02=5A DF0D=08 FFBA=06",
}


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address < 0x8000,
            f"bad banked address bank{bank}:${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def region(payload: bytes | bytearray, bank: int, address: int,
           size: int) -> bytes:
    offset = bank_offset(bank, address)
    return bytes(payload[offset:offset + size])


def require_region(payload: bytes | bytearray, bank: int, address: int,
                   expected: bytes, label: str) -> None:
    actual = region(payload, bank, address, len(expected))
    require(actual == expected,
            f"{label} moved at bank{bank}:${address:04X}: "
            f"{actual.hex(' ')} != {expected.hex(' ')}")


def patch_region(rom: bytearray, bank: int, address: int, expected: bytes,
                 replacement: bytes, label: str,
                 allowed: set[int]) -> None:
    require(len(expected) == len(replacement), f"{label} width changed")
    require_region(rom, bank, address, expected, f"{label} preimage")
    offset = bank_offset(bank, address)
    rom[offset:offset + len(replacement)] = replacement
    allowed.update(range(offset, offset + len(replacement)))


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def checksum_contract(payload: bytes) -> dict[str, str]:
    header = 0
    for value in payload[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    require(payload[0x014D] == header, "header checksum is invalid")
    total = (sum(payload[:0x014E]) + sum(payload[0x0150:])) & 0xFFFF
    require(int.from_bytes(payload[0x014E:0x0150], "big") == total,
            "global checksum is invalid")
    return {"header": f"${header:02X}", "global": f"${total:04X}"}


def build_wram_block() -> bytes:
    block = bytearray(WRAM_BLOCK_SIZE)
    block[0:len(RESTORER)] = RESTORER
    guard_offset = GUARD_ADDR - WRAM_BLOCK_ADDR
    helper_offset = HELPER_ADDR - WRAM_BLOCK_ADDR
    block[guard_offset:guard_offset + len(GUARD)] = GUARD
    block[helper_offset:helper_offset + len(HELPER)] = HELPER
    require(GUARD_ADDR + len(GUARD) == HELPER_ADDR,
            "Stage4 guard no longer falls through to helper")
    require(GUARD_ADDR + len(GUARD) + int.from_bytes(
        GUARD[-1:], "little", signed=True
    ) == WRAM_BLOCK_ADDR, "non-Stage4 guard no longer reaches restorer")
    require(HELPER[-3:] == bytes.fromhex("C3 92 DA"),
            "page-pair helper no longer joins shared compare at DA92")
    return bytes(block)


def build_installer() -> bytes:
    """Install private WRAM code, then enter the exact material continuation."""
    code = bytearray([
        0xC5, 0xD5,                         # preserve BC (especially C), DE
        0x21, WRAM_PAYLOAD_ADDR & 0xFF, WRAM_PAYLOAD_ADDR >> 8,
        0x11, WRAM_BLOCK_ADDR & 0xFF, WRAM_BLOCK_ADDR >> 8,
        0x01, WRAM_BLOCK_SIZE, 0x00,
        0xCD, 0xB3, 0x09,                   # copy DB00-DB3B
        0x21, TRAMPOLINE_PAYLOAD_ADDR & 0xFF,
        TRAMPOLINE_PAYLOAD_ADDR >> 8,
        0x11, TRAMPOLINE_ADDR & 0xFF, TRAMPOLINE_ADDR >> 8,
        0x01, len(TRAMPOLINE), 0x00,
        0xCD, 0xB3, 0x09,                   # copy DA5D-DA5F
        0x3E, 0xEB,
        0xEA, RUNTIME_REDIRECT_OPERAND_ADDR & 0xFF,
        RUNTIME_REDIRECT_OPERAND_ADDR >> 8, # native dirty redirect
        0x3E, TRAMPOLINE_ADDR & 0xFF,
        0xEA, RUNTIME_LANDING_OPERAND_ADDR & 0xFF,
        RUNTIME_LANDING_OPERAND_ADDR >> 8, # atomic final DAD5=$5D commit
        0xD1, 0xC1,                         # restore DE, BC
        0xF1,                               # saved original bank and DEC flags
        0x21, STAGE4_MATERIAL_CONT_ADDR & 0xFF,
        STAGE4_MATERIAL_CONT_ADDR >> 8,
        0xE5,                               # synthetic RET after A=$04 stub
        0x21, STAGE4_A_STUB_ADDR & 0xFF, STAGE4_A_STUB_ADDR >> 8,
        0xE5,                               # mapper RET -> original-bank stub
        0x21, 0x01, 0xC6,
        0x06, 0x08,                         # exact continuation inputs
        0xC3, 0x61, 0x00,                   # map back; RET -> $5413 -> $7C44
    ])
    return bytes(code)


def runtime_from(payload: bytes, bank: int) -> bytes:
    result = (
        region(payload, bank, RUNTIME_SOURCE_A_ADDR, RUNTIME_SOURCE_A_SIZE)
        + region(payload, bank, RUNTIME_SOURCE_B_ADDR, RUNTIME_SOURCE_B_SIZE)
    )
    require(len(result) == RUNTIME_SIZE, "runtime source width changed")
    return result


def absolute_control_refs(payload: bytes, bank: int, target: int) -> list[int]:
    """Return byte-aligned absolute JP/CALL references in one switch bank."""
    data = region(payload, bank, 0x4000, 0x4000)
    opcodes = {0xC2, 0xC3, 0xC4, 0xCA, 0xCC, 0xCD, 0xD2, 0xD4, 0xDA, 0xDC}
    refs = []
    for offset in range(len(data) - 2):
        if (data[offset] in opcodes
                and int.from_bytes(data[offset + 1:offset + 3], "little") == target):
            refs.append(0x4000 + offset)
    return refs


def desired_plane(raw: bytes) -> bytes:
    return bytes(
        4 if 0x01 <= tile <= 0x08 else 2 if tile in (0x2D, 0x2E) else 0
        for tile in raw
    )


def evidence_bytes(path: Path, evidence: dict[str, bytes] | None = None) -> bytes:
    """Read a historical input, or require its explicitly supplied bytes."""
    if evidence is None:
        return path.read_bytes()
    key = str(path.relative_to(ROOT))
    require(key in evidence, f"missing explicit historical input: {key}")
    return evidence[key]


def parse_corpus(path: Path, expected_sha: str, *, live: bool,
                 evidence: dict[str, bytes] | None = None):
    payload = evidence_bytes(path, evidence)
    require(digest(payload) == expected_sha, f"corpus identity changed: {path}")
    rows = []
    for number, line in enumerate(payload.decode().splitlines(), 1):
        fields = line.split("\t")
        require(len(fields) == (30 if live else 14),
                f"{path}:{number}: field count changed")
        raw = bytes.fromhex(fields[29] if live else fields[13])
        require(len(raw) == 24 * 24, f"{path}:{number}: raw width changed")
        if live:
            frame, physical, room = (
                int(fields[1]), int(fields[2], 16), int(fields[3], 16)
            )
        else:
            frame, room, physical = (
                int(fields[0]), int(fields[1], 16), int(fields[2], 16)
            )
        rows.append((frame, room, physical, raw, desired_plane(raw)))
    return rows


def corpus_metrics(rows) -> dict[str, int]:
    unique = {(room, raw): plane for _, room, _, raw, plane in rows}
    semantics: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
    variants: dict[tuple[int, bytes], set[tuple[int, int, int]]] = defaultdict(set)
    for (room, raw), plane in unique.items():
        key = (room, raw[81], raw[337])
        semantics[key].add(plane)
        variants[(room, plane)].add(key)
    caches: dict[int, tuple[tuple[int, int, int], bytes]] = {}
    hits = misses = stale_hits = 0
    for _frame, room, physical, raw, plane in rows:
        key = (room, raw[81], raw[337])
        previous = caches.get(physical)
        if previous is not None and previous[0] == key:
            hits += 1
            stale_hits += int(previous[1] != plane)
        else:
            misses += 1
            caches[physical] = (key, plane)
    return {
        "rows": len(rows),
        "unique_records": len(unique),
        "unique_keys": len(semantics),
        "collisions": sum(len(values) - 1 for values in semantics.values()),
        "false_variants": sum(len(values) - 1 for values in variants.values()),
        "hits": hits,
        "misses": misses,
        "stale_hits": stale_hits,
    }


def verify_corpora(evidence: dict[str, bytes] | None = None) -> dict[str, object]:
    canonical = corpus_metrics(parse_corpus(
        CANONICAL_CORPUS, CANONICAL_CORPUS_SHA256, live=False, evidence=evidence
    ))
    live = corpus_metrics(parse_corpus(
        LIVE_CORPUS, LIVE_CORPUS_SHA256, live=True, evidence=evidence
    ))
    require(canonical == {
        "rows": 328, "unique_records": 21, "unique_keys": 20,
        "collisions": 0, "false_variants": 0,
        "hits": 278, "misses": 50, "stale_hits": 0,
    }, f"canonical page-pair contract changed: {canonical}")
    require(live == {
        "rows": 985, "unique_records": 5, "unique_keys": 5,
        "collisions": 0, "false_variants": 0,
        "hits": 975, "misses": 10, "stale_hits": 0,
    }, f"exact-r279 live page-pair contract changed: {live}")
    speed_payload = evidence_bytes(SPEED_MANIFEST, evidence)
    require(digest(speed_payload) == SPEED_MANIFEST_SHA256,
            "r279 strict speed manifest identity changed")
    speed = json.loads(speed_payload)
    rows = [row for row in speed.get("rows", []) if row.get("stage") == 4]
    require(len(rows) == 1, "r279 strict manifest lost Stage4")
    row = rows[0]
    require(
        row.get("deterministic_replay") is True
        and row.get("ratio_exact") == 0.9895287958115183
        and row["original"].get("main_loop_hits") == 764
        and row["dx"].get("main_loop_hits") == 756
        and row["dx"].get("lava_copy_hits") == 985,
        "r279 Stage4 speed evidence changed",
    )
    return {
        "canonical": {"path": str(CANONICAL_CORPUS.relative_to(ROOT)),
                      "sha256": CANONICAL_CORPUS_SHA256, **canonical},
        "exact_r279_live": {"path": str(LIVE_CORPUS.relative_to(ROOT)),
                            "sha256": LIVE_CORPUS_SHA256, **live},
        "strict_speed_baseline": {
            "path": str(SPEED_MANIFEST.relative_to(ROOT)),
            "sha256": SPEED_MANIFEST_SHA256,
            "original_main_loop_hits": 764,
            "r279_main_loop_hits": 756,
            "ratio_exact": 0.9895287958115183,
            "r279_stage4_decisions": 985,
        },
    }


def verify_wram_ownership(evidence: dict[str, bytes] | None = None) -> dict[str, object]:
    records = []
    for stage, meta_prefix in WRAM_META.items():
        dump = WRAM_OWNERSHIP_ROOT / f"stage{stage}.wram1-db.bin"
        meta = WRAM_OWNERSHIP_ROOT / f"stage{stage}.meta"
        payload = evidence_bytes(dump, evidence)
        meta_text = evidence_bytes(meta, evidence).decode()
        require(len(payload) == 0x80, f"Stage{stage} DB00-DB7F width changed")
        require(payload == bytes(0x80), f"Stage{stage} DB00-DB7F is not zero")
        require(digest(payload) == WRAM_OWNERSHIP_SHA256,
                f"Stage{stage} DB00-DB7F hash changed")
        require(meta_text.startswith(meta_prefix),
                f"Stage{stage} ownership metadata changed")
        records.append({
            "stage": stage,
            "range": "$DB00-$DB7F",
            "path": str(dump.relative_to(ROOT)),
            "sha256": WRAM_OWNERSHIP_SHA256,
            "all_zero": True,
            "capture_meta": meta_text.splitlines()[0],
        })
    return {
        "current_r281_checked_stages": records,
        "owned_subrange": "$DB00-$DB3B",
        "owned_subrange_size": WRAM_BLOCK_SIZE,
    }


def verify_base(base: bytes, r279: bytes) -> dict[str, object]:
    require(len(base) == 32 * BANK_SIZE, "r281 is not 512 KiB")
    require(digest(base) == R281_SHA256, f"wrong exact r281 base: {digest(base)}")
    require(digest(r279) == R279_SHA256, f"wrong exact r279 base: {digest(r279)}")
    differences = {
        index: (before, after)
        for index, (before, after) in enumerate(zip(r279, base, strict=True))
        if before != after
    }
    require(differences == R281_VISUAL_DELTA,
            f"r281 is not the six-byte-only visual delta: {differences}")

    runtime_hashes = []
    for bank in MIRROR_BANKS:
        require_region(base, bank, STAGE4_ENTRY_ADDR, STAGE4_ENTRY_OLD,
                       "Stage4 material entry")
        require_region(base, bank, STAGE4_A_STUB_ADDR, bytes(3),
                       "Stage4 A-load return stub")
        require_region(base, bank, STAGE4_MATERIAL_CONT_ADDR,
                       STAGE4_MATERIAL_CONT, "Stage4 material continuation")
        require_region(base, bank, STAGE4_MATERIAL_TAIL_ADDR,
                       STAGE4_MATERIAL_TAIL, "Stage4 material tail")
        require(absolute_control_refs(base, bank, STAGE4_ENTRY_ADDR) == [0x53FD],
                f"bank{bank} Stage4 entry is not sole control target")
        require(absolute_control_refs(base, bank, STAGE4_A_STUB_ADDR) == [],
                f"bank{bank} dead Stage4 return stub gained a base caller")
        require_region(base, bank, RUNTIME_INSTALLER_ADDR,
                       RUNTIME_INSTALLER_PREFIX,
                       "DA00/DA60 split runtime installer")
        runtime = runtime_from(base, bank)
        runtime_hashes.append(digest(runtime))
        require(runtime[RUNTIME_LANDING_OPERAND_ADDR - RUNTIME_ADDR] == 0x60,
                "native DAD5 is not $60")
        require(runtime[RUNTIME_REDIRECT_OPERAND_ADDR - RUNTIME_ADDR] == 0xEB,
                "native DAB7 is not $EB")
        compare = RUNTIME_COMPARE_ADDR - RUNTIME_ADDR
        router = RUNTIME_ROUTER_ADDR - RUNTIME_ADDR
        dispatch = RUNTIME_DISPATCH_ADDR - RUNTIME_ADDR
        require(runtime[compare:compare + len(SHARED_COMPARE)] == SHARED_COMPARE,
                "shared compare moved")
        require(runtime[router:router + len(ROUTER)] == ROUTER,
                "exact DAE9 router moved")
        require(
            runtime[dispatch:dispatch + len(DISPATCH_NORMALIZE_AND_DAD4_BRANCH)]
            == DISPATCH_NORMALIZE_AND_DAD4_BRANCH,
            "DAD4 dispatcher no longer supplies A=[D880]-$03",
        )
        branch_pc_after = RUNTIME_DISPATCH_ADDR + 11
        require(branch_pc_after + int.from_bytes(
            DISPATCH_NORMALIZE_AND_DAD4_BRANCH[-1:], "little", signed=True
        ) == RUNTIME_LANDING_JP_ADDR,
                "normalized-A dispatcher branch no longer lands at DAD4")
        require_region(base, bank, 0x53F2,
                       region(r279, bank, 0x53F2, 33),
                       "exact r281 executed transition selector/front")
        require_region(base, bank, 0x570E,
                       region(r279, bank, 0x570E, 16),
                       "exact Stage7 arm selector")
    require(runtime_hashes[0] == runtime_hashes[1],
            "runtime source mirrors differ")

    # Bank22 ownership is exact erased ROM.  These regions do not intersect
    # the existing r279 Stage7 helper/lazy-disarm code at $6C80-$7244.
    for address, size, label in (
        (STAGE4_BANK22_LANDING_ADDR, 3, "Stage4 bank22 landing"),
        (INSTALLER_ADDR, 0x100, "bank22 installer cave"),
        (WRAM_PAYLOAD_ADDR, 0x100, "bank22 WRAM payload cave"),
    ):
        require_region(base, OVERLAY_BANK, address, bytes([0xFF]) * size,
                       label)
    return {
        "r279_sha256": R279_SHA256,
        "r281_sha256": R281_SHA256,
        "r281_delta_offsets": [f"0x{value:06X}" for value in differences],
        "runtime_sha256": runtime_hashes[0],
    }


def construct(base: bytes, r279: bytes) -> tuple[bytes, dict[str, object]]:
    """Emit the fixed source recipe without claiming corpus/WRAM observations."""
    lineage = verify_base(base, r279)
    block = build_wram_block()
    installer = build_installer()
    require(len(block) == WRAM_BLOCK_SIZE, "WRAM block width changed")
    require(INSTALLER_ADDR + len(installer) < WRAM_PAYLOAD_ADDR,
            "installer overlaps payload")
    require(TRAMPOLINE_PAYLOAD_ADDR == WRAM_PAYLOAD_ADDR + len(block),
            "trampoline payload no longer follows WRAM block")

    rom = bytearray(base)
    allowed = {0x014D, 0x014E, 0x014F}
    for bank in MIRROR_BANKS:
        patch_region(rom, bank, STAGE4_ENTRY_ADDR,
                     STAGE4_ENTRY_OLD, STAGE4_ENTRY_NEW,
                     "Stage4-only mapper entry", allowed)
        patch_region(rom, bank, STAGE4_A_STUB_ADDR,
                     bytes(3), STAGE4_A_STUB,
                     "Stage4-only exact-A return stub", allowed)

    overlay_regions = (
        (STAGE4_BANK22_LANDING_ADDR,
         bytes((0xC3, INSTALLER_ADDR & 0xFF, INSTALLER_ADDR >> 8)),
         "bank22 Stage4 landing"),
        (INSTALLER_ADDR, installer, "bank22 Stage4 installer/material helper"),
        (WRAM_PAYLOAD_ADDR, block, "DB00-DB3B payload"),
        (TRAMPOLINE_PAYLOAD_ADDR, TRAMPOLINE, "DA5D trampoline payload"),
    )
    overlay_records = []
    for address, replacement, label in overlay_regions:
        patch_region(rom, OVERLAY_BANK, address,
                     bytes([0xFF]) * len(replacement), replacement,
                     label, allowed)
        overlay_records.append({
            "label": label,
            "range": f"${address:04X}-${address + len(replacement) - 1:04X}",
            "length": len(replacement),
            "sha256": digest(replacement),
        })

    update_checksums(rom)
    candidate = bytes(rom)
    changed = {
        index for index, (before, after) in enumerate(zip(base, candidate))
        if before != after
    }
    require(changed <= allowed,
            f"candidate escaped owned bytes: {sorted(changed - allowed)[:8]}")
    functional_changed = changed - {0x014D, 0x014E, 0x014F}
    require(len(changed) == EXPECTED_CHANGED_BYTES,
            f"changed-byte count drifted: {len(changed)}")
    require(len(functional_changed) == EXPECTED_FUNCTIONAL_CHANGED_BYTES,
            f"functional changed-byte count drifted: {len(functional_changed)}")

    # The rejected shared-overlay experiment's critical contract: nothing in
    # any non-Stage-4 transition or hot runtime source is allowed to move.
    for bank in MIRROR_BANKS:
        require_region(candidate, bank, 0x53F2,
                       region(base, bank, 0x53F2, 33),
                       "non-Stage4 executed transition selector/front")
        require(runtime_from(candidate, bank) == runtime_from(base, bank),
                f"bank{bank} runtime source changed")
        require_region(candidate, bank, 0x570E,
                       region(base, bank, 0x570E, 16),
                       "Stage7 arm selector")
        require_region(candidate, bank, 0x68C8,
                       region(base, bank, 0x68C8, 8),
                       "r281 Stage1 metallic-tooth row")
    require(region(candidate, OVERLAY_BANK, 0x6C80, 0x5C5)
            == region(base, OVERLAY_BANK, 0x6C80, 0x5C5),
            "existing Stage7 helper/lazy-disarm changed")

    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {candidate_sha}")

    # Exact SM83 T-cycle accounting to the shared DA92 compare.  Stage4's
    # captured D880=$05 makes native A=$02, selecting the 276T nonzero path.
    native_nonzero_t = 276
    optimized_t = 16 + 28 + 140  # DA5D JP + FFBA guard + helper/JP
    saved_t = native_nonzero_t - optimized_t
    require((optimized_t, saved_t) == (184, 92), "cycle proof changed")
    first_departure_t = 16 + 32 + 64 + native_nonzero_t
    departure_overhead_t = first_departure_t - native_nonzero_t
    require((first_departure_t, departure_overhead_t) == (388, 112),
            "lazy departure cycle proof changed")

    receipt: dict[str, object] = {
        "schema": "penta-stage4-lazy-departure-r285-construction-v1",
        "status": "construction-only",
        "promotable": False,
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "emulator_invoked": False,
        "base_sha256": R281_SHA256,
        "candidate_sha256": candidate_sha,
        "changed_bytes_including_checksums": len(changed),
        "functional_changed_bytes": len(functional_changed),
        "checksums": checksum_contract(candidate),
        "lineage": lineage,
        "mirror_patches": [
            {
                "bank": bank,
                "range": "$7C22-$7C29",
                "old": STAGE4_ENTRY_OLD.hex(" ").upper(),
                "new": STAGE4_ENTRY_NEW.hex(" ").upper(),
                "contract": "sole Stage4 CA $7C22 target; mapper RET lands bank22:$7C2A",
            }
            for bank in MIRROR_BANKS
        ],
        "stage4_A_return_stubs": [
            {
                "bank": bank,
                "range": "$5413-$5415",
                "old": "00 00 00",
                "new": STAGE4_A_STUB.hex(" ").upper(),
                "contract": (
                    "synthetic mapper RET only; LD A,$04; RET to exact $7C44"
                ),
            }
            for bank in MIRROR_BANKS
        ],
        "bank22_overlay": overlay_records,
        "runtime_contract": {
            "atomic_install_order": [
                "copy complete DB00-DB3B block while DAD5 remains $60",
                "copy complete JP $DB20 trampoline to unused DA5D-DA5F",
                "write DAB7=$EB native dirty redirect",
                "commit DAD5=$5D last",
            ],
            "Stage4": (
                "$DAD4 -> $DA5D -> $DB20; FFBA=$03 falls through to "
                "C1F1/C2F1 helper, then JP $DA92"
            ),
            "first_nonstage_call": (
                "$DB20 FFBA!=$03 -> $DB00; write DAD5=$60; recompute "
                "A=[D880]-$03; JP $DA60 to service the current call natively"
            ),
            "later_nonstage_calls": "$DAD4 -> exact r281 $DA60",
            "Stage7": (
                "unchanged transition $570E arms DAB7=$31; first call only "
                "restores DAD5, preserving the exact DAE9 router/redirect"
            ),
            "Crystal": "$DACE JP $DA60 remains exact and bypasses DAD5",
            "DAE9_router": "never modified; exact r281 bytes for full lifecycle",
        },
        "helper": {
            "runtime_range": "$DB26-$DB3A",
            "bytes": HELPER.hex(" ").upper(),
            "key": "room + raw C1F1/C2F1 page pair",
            "join": "$DB38 JP $DA92 (shared LD A,[DE])",
            "pushes": ["BC", "DE", "HL"],
            "shared_epilogue_pops": ["HL", "DE", "BC"],
        },
        "cycle_contract_t": {
            "native_DA60_to_DA92_nonzero_D880_minus_3": native_nonzero_t,
            "r285_DA5D_to_DA92": optimized_t,
            "saved_per_bound_Stage4_decision": saved_t,
            "first_nonstage_call_total_to_DA92": first_departure_t,
            "one_time_departure_overhead": departure_overhead_t,
            "all_subsequent_nonstage_calls": "byte-and-cycle exact r281",
            "common_DAD4_JP_excluded_both": 16,
        },
        "stack_register_contract": {
            "entry": "PUSH saved FF99 bank; stock mapper CALL/RET balanced",
            "installer": "PUSH BC/DE around copies; restores DE/C; then sets HL=$C601 and B=$08",
            "return": (
                "POP saved bank; push synthetic $7C44 then $5413; JP $0061; "
                "mapper RET->$5413 loads A=$04; RET->$7C44 exact material loop; "
                "stock $7CF5 tail RET consumes original outer return"
            ),
            "lazy_path": "no stack mutation beyond helper's exact push/shared-pop contract",
            "material_return_registers": (
                "exact stock A=$02, B=$00, C preserved, DE preserved, HL=$C62E; "
                "DEC-loop flags exact"
            ),
        },
        "contracts": {
            "exact_r281_base_and_six_byte_visual_delta_preserved": True,
            "only_Stage4_owned_entry_dead_stub_and_erased_bank22_changed": True,
            "original_53F2_5412_executed_transition_front_exact": True,
            "all_nonstage_transition_timing_exact": True,
            "both_runtime_source_mirrors_exact": True,
            "DAE9_router_exact_and_never_overwritten": True,
            "Stage7_arm_and_existing_helper_exact": True,
            "lazy_departure_services_first_call_after_restoring_DAD5": True,
            "lazy_departure_recomputes_exact_normalized_A": True,
            "material_continuation_register_and_stack_ABI_exact": True,
            "r281_Stage1_palette_delta_unchanged": True,
        },
        "required_live_gates": [
            "single-flight Stage4 strict speed replay",
            "Stage4 semantic/attribute and room-edge containment",
            "Stage4 SELECT-menu roundtrip",
            "Stage4->5->6->7 DAD5/DAB7/DAE9 lazy lifecycle trace",
            "Stage5 and Stage7 strict phase containment",
            "candidate-bound Crystal and all-stage visual containment",
        ],
    }
    return candidate, receipt


def install(base: bytes, r279: bytes, *, evidence: dict[str, bytes] | None = None
            ) -> tuple[bytes, dict[str, object]]:
    # Historical qualification stays mandatory here; no synthetic observations
    # are passed to the source-only emitter.
    verify_base(base, r279)
    corpora = verify_corpora(evidence)
    ownership = verify_wram_ownership(evidence)
    candidate, construction = construct(base, r279)
    receipt = {}
    for key, value in construction.items():
        if key in ("historical_evidence_consumed", "fresh_live_qualification"):
            continue
        if key == "schema":
            value = "penta-stage4-lazy-departure-r285-build-v1"
        elif key == "status":
            value = "STATIC_PASS_LIVE_GATES_REQUIRED"
        elif key == "runtime_contract":
            receipt["wram_ownership"] = ownership
        elif key == "cycle_contract_t":
            value = dict(value)
            historical_cycles = {}
            for name, metric in value.items():
                historical_cycles[name] = metric
                if name == "saved_per_bound_Stage4_decision":
                    historical_cycles["r279_measured_stage4_decisions"] = 985
                    historical_cycles["projected_route_saving"] = metric * 985
            value = historical_cycles
        elif key == "contracts":
            receipt["corpus_contract"] = corpora
            historical_contracts = {}
            for name, contract in value.items():
                historical_contracts[name] = contract
                if name == "Stage7_arm_and_existing_helper_exact":
                    historical_contracts["DB00_DB3B_zero_in_bound_current_r281_Stages2_through_7"] = True
                    historical_contracts["helper_pagepair_zero_collision_variant_and_stale_hit"] = True
            value = historical_contracts
        receipt[key] = value
    return candidate, receipt


def require_tmp(path: Path) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved == scratch or scratch in resolved.parents,
            f"output must remain below {scratch}: {resolved}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path,
                        default=TMP / "stage1-metallic-teeth-r281/candidate.gb")
    parser.add_argument("--r279", type=Path,
                        default=TMP / "stage7-lazy-disarm-r279/candidate.gb")
    parser.add_argument("--output", type=Path,
                        default=TMP / "stage4-lazy-departure-r285/candidate.gb")
    parser.add_argument("--receipt", type=Path,
                        default=TMP / "stage4-lazy-departure-r285/build-receipt.json")
    args = parser.parse_args()
    output = require_tmp(args.output)
    receipt_path = require_tmp(args.receipt)
    candidate, receipt = install(args.base.read_bytes(), args.r279.read_bytes())
    for path, payload in (
        (output, candidate),
        (receipt_path, json.dumps(receipt, indent=2).encode() + b"\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
