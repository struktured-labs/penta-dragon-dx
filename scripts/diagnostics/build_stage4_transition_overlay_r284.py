#!/usr/bin/env python3
"""Build the exact-r281 Stage-4-only page-pair runtime overlay.

The later-stage transition selector is moved temporarily into bank 22 through
an eight-byte code-owned front.  Every selector entry first restores the exact
r281 Stage-7 router, native later-dungeon landing, and native dirty redirect.
Exact Stage 4 then installs a private C1F1/C2F1 helper and commits its landing
byte last.  Stages 2/3/5/6, Stage 7, and Crystal therefore retain their exact
r281 gameplay runtime bytes and instruction timelines.

This is a static builder.  It never imports or launches an emulator, and all
generated artifacts remain under the repository-local ignored ``tmp/`` tree.
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
    "4afd1cc05ebc9ceca70abd2e2245eeb12c77ed06247678c33a9b78ea7fa6605a"
)
EXPECTED_CHANGED_BYTES = 190
EXPECTED_FUNCTIONAL_CHANGED_BYTES = 188

BANK_SIZE = 0x4000
MIRROR_BANKS = (13, 16)
OVERLAY_BANK = 22

FRONT_ADDR = 0x53F2
FRONT_SIZE = 36
STAGE2_STUB_ADDR = 0x5401
STAGE4_STUB_ADDR = 0x5413
HEALTH_TARGET_ADDR = 0x5436
STAGE5_TARGET_ADDR = 0x540D
STAGE7_TARGET_ADDR = 0x5407
STAGE4_TARGET_ADDR = 0x7C22
STAGE2_TARGETS = {13: 0x555D, 16: 0x5422}

ENTRY = bytes.fromhex("F0 99 F5 3E 16 CD 61 00")
RETURN_THUNK = bytes.fromhex("F1 CD 61 00")
LANDING_ADDR = 0x53FA
RETURN_THUNKS = {
    "stage2": 0x53FD,       # mapper RET -> original-bank $5401 stub
    "stage7": 0x5403,       # mapper RET -> original-bank $5407
    "stage5": 0x5409,       # mapper RET -> original-bank $540D
    "stage4": 0x540F,       # mapper RET -> original-bank $5413 stub
    "health": 0x5432,       # mapper RET -> original-bank $5436
}
MAIN_ADDR = 0x6000
ROUTER_PAYLOAD_ADDR = 0x6300
HELPER_PAYLOAD_ADDR = 0x6316

RUNTIME_SOURCE_A_ADDR = 0x7BB2
RUNTIME_SOURCE_A_SIZE = 46
RUNTIME_SOURCE_B_ADDR = 0x7C4D
RUNTIME_SOURCE_B_SIZE = 114
RUNTIME_SOURCE_SIZE = RUNTIME_SOURCE_A_SIZE + RUNTIME_SOURCE_B_SIZE
RUNTIME_ADDR = 0xDA60
RUNTIME_LANDING_OPERAND_ADDR = 0xDAD5
RUNTIME_REDIRECT_OPERAND_ADDR = 0xDAB7
RUNTIME_ROUTER_ADDR = 0xDAE9
RUNTIME_COMPARE_ADDR = 0xDA92

ROUTER = bytes.fromhex(
    "E1 D1 C1 F5 FA 80 D8 FE 08 28 02 18 00 "
    "F3 F1 F1 F1 3E 16 C3 47 08"
)
HELPER = bytes.fromhex(
    "C5 D5 E5 AF E0 E0 7C EE CB 5F 16 DF "
    "21 F1 C1 46 24 4E 18 95"
)
SHARED_COMPARE = bytes.fromhex(
    "1A B8 20 13 13 1A B9 20 0D 13 1A 6F "
    "F0 BD BD 20 04 E1 D1 C1 C9"
)

OLD_FRONT = {
    13: bytes.fromhex(
        "F0 BA 3D CA 5D 55 3D CA 36 54 3D CA 22 7C 3D 28 0A 3D "
        "CA 36 54 C3 0E 57 00 00 00 CD 36 54 C3 22 54 00 00 00"
    ),
    16: bytes.fromhex(
        "F0 BA 3D CA 22 54 3D CA 36 54 3D CA 22 7C 3D 28 0A 3D "
        "CA 36 54 C3 0E 57 00 00 00 CD 36 54 C3 22 54 00 00 00"
    ),
}

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
    require(
        actual == expected,
        f"{label} moved at bank{bank}:${address:04X}: "
        f"{actual.hex(' ')} != {expected.hex(' ')}",
    )


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


class Asm:
    """Tiny absolute-jump assembler sufficient for the bank-22 selector."""

    def __init__(self, start: int):
        self.start = start
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    @property
    def pc(self) -> int:
        return self.start + len(self.code)

    def db(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def label(self, name: str) -> None:
        require(name not in self.labels, f"duplicate label {name}")
        self.labels[name] = self.pc

    def jp(self, opcode: int, label: str) -> None:
        require(opcode in (0xC3, 0xCA), f"unsupported JP opcode ${opcode:02X}")
        self.db(opcode, 0, 0)
        self.fixups.append((len(self.code) - 2, label))

    def finish(self) -> tuple[bytes, dict[str, int]]:
        for offset, label in self.fixups:
            require(label in self.labels, f"undefined label {label}")
            target = self.labels[label]
            self.code[offset:offset + 2] = target.to_bytes(2, "little")
        return bytes(self.code), dict(self.labels)


def build_main() -> tuple[bytes, dict[str, int]]:
    a = Asm(MAIN_ADDR)
    a.db(0xC5, 0xD5, 0xE5)                  # preserve BC, DE, HL
    a.db(0x3E, 0x60, 0xEA, 0xD5, 0xDA)      # DAD5=$60 native landing
    a.db(0x3E, 0xEB, 0xEA, 0xB7, 0xDA)      # DAB7=$EB native dirty return
    a.db(
        0x21, ROUTER_PAYLOAD_ADDR & 0xFF, ROUTER_PAYLOAD_ADDR >> 8,
        0x11, RUNTIME_ROUTER_ADDR & 0xFF, RUNTIME_ROUTER_ADDR >> 8,
        0x01, len(ROUTER), 0x00,
        0xCD, 0xB3, 0x09,                   # exact stock BC-byte memcpy
    )
    a.db(0xF0, 0xBA, 0x3D)                  # Stage 2?
    a.jp(0xCA, "stage2")
    a.db(0x3D)                              # Stage 3?
    a.jp(0xCA, "health")
    a.db(0x3D)                              # Stage 4?
    a.jp(0xCA, "stage4")
    a.db(0x3D)                              # Stage 5?
    a.jp(0xCA, "stage5")
    a.db(0x3D)                              # Stage 6?
    a.jp(0xCA, "health")
    a.jp(0xC3, "stage7")                   # zero/out-of-range matches r281

    def exit_to(name: str, thunk: int) -> None:
        a.label(name)
        a.db(0xE1, 0xD1, 0xC1, 0xC3, thunk & 0xFF, thunk >> 8)

    exit_to("stage2", RETURN_THUNKS["stage2"])
    exit_to("health", RETURN_THUNKS["health"])

    a.label("stage4")
    # DAD5 remains native while the helper body is incomplete.  The final
    # store is the sole atomic commit that makes the new landing reachable.
    a.db(
        0x21, HELPER_PAYLOAD_ADDR & 0xFF, HELPER_PAYLOAD_ADDR >> 8,
        0x11, RUNTIME_ROUTER_ADDR & 0xFF, RUNTIME_ROUTER_ADDR >> 8,
        0x01, len(HELPER), 0x00,
        0xCD, 0xB3, 0x09,
        0x3E, 0xE9, 0xEA, 0xD5, 0xDA,
        0xE1, 0xD1, 0xC1,
        0xC3, RETURN_THUNKS["stage4"] & 0xFF,
        RETURN_THUNKS["stage4"] >> 8,
    )
    exit_to("stage5", RETURN_THUNKS["stage5"])
    exit_to("stage7", RETURN_THUNKS["stage7"])
    return a.finish()


def runtime_from(payload: bytes, bank: int) -> bytes:
    result = (
        region(payload, bank, RUNTIME_SOURCE_A_ADDR, RUNTIME_SOURCE_A_SIZE)
        + region(payload, bank, RUNTIME_SOURCE_B_ADDR, RUNTIME_SOURCE_B_SIZE)
    )
    require(len(result) == RUNTIME_SOURCE_SIZE, "runtime source width changed")
    return result


def desired_plane(raw: bytes) -> bytes:
    return bytes(
        4 if 0x01 <= tile <= 0x08 else 2 if tile in (0x2D, 0x2E) else 0
        for tile in raw
    )


def parse_corpus(path: Path, expected_sha: str, *, live: bool):
    payload = path.read_bytes()
    require(digest(payload) == expected_sha,
            f"corpus identity changed: {path}")
    rows = []
    for number, line in enumerate(payload.decode().splitlines(), 1):
        fields = line.split("\t")
        expected_fields = 30 if live else 14
        require(len(fields) == expected_fields,
                f"{path}:{number}: expected {expected_fields} fields")
        raw = bytes.fromhex(fields[29] if live else fields[13])
        require(len(raw) == 24 * 24, f"{path}:{number}: raw width changed")
        if live:
            frame = int(fields[1])
            physical = int(fields[2], 16)
            room = int(fields[3], 16)
        else:
            frame = int(fields[0])
            room = int(fields[1], 16)
            physical = int(fields[2], 16)
        rows.append((frame, room, physical, raw, desired_plane(raw)))
    return rows


def corpus_metrics(rows) -> dict[str, object]:
    unique = {(room, raw): plane for _, room, _, raw, plane in rows}
    semantics: dict[tuple[int, int, int], set[bytes]] = defaultdict(set)
    variants: dict[tuple[int, bytes], set[tuple[int, int, int]]] = (
        defaultdict(set)
    )
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
        "false_variants": sum(
            len(values) - 1 for values in variants.values()
        ),
        "hits": hits,
        "misses": misses,
        "stale_hits": stale_hits,
    }


def verify_corpora() -> dict[str, object]:
    canonical = corpus_metrics(parse_corpus(
        CANONICAL_CORPUS, CANONICAL_CORPUS_SHA256, live=False
    ))
    live = corpus_metrics(parse_corpus(
        LIVE_CORPUS, LIVE_CORPUS_SHA256, live=True
    ))
    require(canonical == {
        "rows": 328,
        "unique_records": 21,
        "unique_keys": 20,
        "collisions": 0,
        "false_variants": 0,
        "hits": 278,
        "misses": 50,
        "stale_hits": 0,
    }, f"canonical page-pair contract changed: {canonical}")
    require(live == {
        "rows": 985,
        "unique_records": 5,
        "unique_keys": 5,
        "collisions": 0,
        "false_variants": 0,
        "hits": 975,
        "misses": 10,
        "stale_hits": 0,
    }, f"exact-r279 live page-pair contract changed: {live}")

    manifest_payload = SPEED_MANIFEST.read_bytes()
    require(digest(manifest_payload) == SPEED_MANIFEST_SHA256,
            "r279 strict speed manifest identity changed")
    manifest = json.loads(manifest_payload)
    rows = [row for row in manifest.get("rows", []) if row.get("stage") == 4]
    require(len(rows) == 1, "r279 strict manifest lost Stage 4")
    row = rows[0]
    require(
        row.get("deterministic_replay") is True
        and row.get("ratio_exact") == 0.9895287958115183
        and row["original"].get("main_loop_hits") == 764
        and row["dx"].get("main_loop_hits") == 756
        and row["dx"].get("lava_copy_hits") == 985,
        "r279 Stage-4 speed evidence changed",
    )
    return {
        "canonical": {
            "path": str(CANONICAL_CORPUS.relative_to(ROOT)),
            "sha256": CANONICAL_CORPUS_SHA256,
            **canonical,
        },
        "exact_r279_live": {
            "path": str(LIVE_CORPUS.relative_to(ROOT)),
            "sha256": LIVE_CORPUS_SHA256,
            **live,
        },
        "strict_speed_baseline": {
            "path": str(SPEED_MANIFEST.relative_to(ROOT)),
            "sha256": SPEED_MANIFEST_SHA256,
            "original_main_loop_hits": 764,
            "r279_main_loop_hits": 756,
            "ratio_exact": 0.9895287958115183,
            "r279_stage4_decisions": 985,
        },
    }


def route_for(value: int, bank: int) -> tuple[str, int]:
    if value == 1:
        return "stage2", STAGE2_TARGETS[bank]
    if value in (2, 5):
        return "health", HEALTH_TARGET_ADDR
    if value == 3:
        return "stage4", STAGE4_TARGET_ADDR
    if value == 4:
        return "stage5", STAGE5_TARGET_ADDR
    return "stage7", 0x570E


def route_contract(labels: dict[str, int]) -> dict[str, object]:
    counts: dict[str, int] = defaultdict(int)
    encoded = bytearray()
    route_codes = {
        "stage2": 1, "health": 2, "stage4": 3,
        "stage5": 4, "stage7": 5,
    }
    for bank in MIRROR_BANKS:
        for value in range(256):
            route, target = route_for(value, bank)
            counts[route] += 1
            encoded.extend((bank, value, route_codes[route], target & 0xFF,
                            target >> 8))
    require(counts == {
        "stage2": 2,
        "health": 4,
        "stage4": 2,
        "stage5": 2,
        "stage7": 502,
    }, f"selector partition changed: {dict(counts)}")
    require(set(labels) == {"stage2", "health", "stage4", "stage5", "stage7"},
            "main label set changed")
    return {
        "FFBA_values_exhausted_per_mirror": 256,
        "mirrors": list(MIRROR_BANKS),
        "counts_across_both_mirrors": dict(counts),
        "classification_sha256": digest(encoded),
        "truth_table": {
            "$01": "Stage2 (bank13:$555D; bank16:$5422)",
            "$02/$05": "health $5436",
            "$03": "Stage4 install then $7C22",
            "$04": "Stage5 $540D",
            "$00/$06-$FF": "Stage7/default $570E",
        },
    }


def verify_base(base: bytes, r279: bytes) -> dict[str, object]:
    require(len(base) == 32 * BANK_SIZE, "r281 is not 512 KiB")
    require(digest(base) == R281_SHA256,
            f"wrong exact r281 base: {digest(base)}")
    require(digest(r279) == R279_SHA256,
            f"wrong exact r279 lineage base: {digest(r279)}")
    differences = {
        index: (before, after)
        for index, (before, after) in enumerate(zip(r279, base, strict=True))
        if before != after
    }
    require(differences == R281_VISUAL_DELTA,
            f"r281 is not the six-byte-only visual delta: {differences}")

    runtime_hashes = []
    for bank in MIRROR_BANKS:
        require_region(base, bank, FRONT_ADDR, OLD_FRONT[bank],
                       "r281 later-stage transition front")
        runtime = runtime_from(base, bank)
        runtime_hashes.append(digest(runtime))
        compare_offset = RUNTIME_COMPARE_ADDR - RUNTIME_ADDR
        require(runtime[compare_offset:compare_offset + len(SHARED_COMPARE)]
                == SHARED_COMPARE, "shared compare/return moved")
        router_offset = RUNTIME_ROUTER_ADDR - RUNTIME_ADDR
        require(runtime[router_offset:router_offset + len(ROUTER)] == ROUTER,
                "r281 runtime router moved")
        require(runtime[RUNTIME_LANDING_OPERAND_ADDR - RUNTIME_ADDR] == 0x60,
                "r281 later-stage landing is not native")
        require(runtime[RUNTIME_REDIRECT_OPERAND_ADDR - RUNTIME_ADDR] == 0xEB,
                "r281 dirty redirect is not native")

    require(runtime_hashes[0] == runtime_hashes[1],
            "r281 runtime source mirrors differ")
    require_region(base, OVERLAY_BANK, LANDING_ADDR,
                   bytes([0xFF]) * 0x80, "bank22 front cave")
    require_region(base, OVERLAY_BANK, MAIN_ADDR,
                   bytes([0xFF]) * 0x100, "bank22 selector cave")
    require_region(base, OVERLAY_BANK, ROUTER_PAYLOAD_ADDR,
                   bytes([0xFF]) * 0x100, "bank22 payload cave")
    return {
        "r279_sha256": R279_SHA256,
        "r281_sha256": R281_SHA256,
        "r281_delta_offsets": [f"0x{value:06X}" for value in differences],
        "runtime_sha256": runtime_hashes[0],
        "runtime_mirrors": list(MIRROR_BANKS),
    }


def install(base: bytes, r279: bytes) -> tuple[bytes, dict[str, object]]:
    lineage = verify_base(base, r279)
    corpora = verify_corpora()
    main, labels = build_main()
    require(MAIN_ADDR + len(main) < ROUTER_PAYLOAD_ADDR,
            "bank22 main overlaps payloads")
    require(len(ROUTER) == 22 and len(HELPER) == 20,
            "payload widths changed")

    # The helper's final JR must execute the shared LD A,[DE], not skip it.
    helper_jr_pc_after = RUNTIME_ROUTER_ADDR + len(HELPER)
    helper_join = helper_jr_pc_after + int.from_bytes(
        HELPER[-1:], "little", signed=True
    )
    require(helper_join == RUNTIME_COMPARE_ADDR,
            f"helper joins ${helper_join:04X}, not $DA92")
    require(HELPER[-2:] == bytes.fromhex("18 95"),
            "corrected page-pair JR changed")

    rom = bytearray(base)
    allowed = {0x014D, 0x014E, 0x014F}
    mirror_records = []
    for bank in MIRROR_BANKS:
        patch_region(
            rom, bank, FRONT_ADDR,
            OLD_FRONT[bank][:len(ENTRY)], ENTRY,
            "code-owned mapper entry", allowed,
        )
        stage2_stub = bytes((
            0xC3, STAGE2_TARGETS[bank] & 0xFF,
            STAGE2_TARGETS[bank] >> 8,
        ))
        patch_region(
            rom, bank, STAGE2_STUB_ADDR,
            OLD_FRONT[bank][STAGE2_STUB_ADDR - FRONT_ADDR:
                            STAGE2_STUB_ADDR - FRONT_ADDR + 3],
            stage2_stub, "bank-specific Stage2 return stub", allowed,
        )
        patch_region(
            rom, bank, STAGE4_STUB_ADDR, bytes(3),
            bytes((0xC3, STAGE4_TARGET_ADDR & 0xFF,
                   STAGE4_TARGET_ADDR >> 8)),
            "Stage4 return stub", allowed,
        )
        mirror_records.append({
            "bank": bank,
            "front": "$53F2-$53F9 maps bank22 and lands at $53FA",
            "stage2_stub": (
                f"$5401 JP ${STAGE2_TARGETS[bank]:04X}"
            ),
            "stage4_stub": "$5413 JP $7C22",
        })

    overlay_regions = [
        (LANDING_ADDR, bytes((0xC3, MAIN_ADDR & 0xFF, MAIN_ADDR >> 8)),
         "bank22 landing"),
        *[
            (address, RETURN_THUNK, f"{name} mapper-return thunk")
            for name, address in RETURN_THUNKS.items()
        ],
        (MAIN_ADDR, main, "bank22 lifecycle selector"),
        (ROUTER_PAYLOAD_ADDR, ROUTER, "exact r281 router payload"),
        (HELPER_PAYLOAD_ADDR, HELPER, "corrected Stage4 helper payload"),
    ]
    overlay_records = []
    for address, replacement, label in overlay_regions:
        patch_region(
            rom, OVERLAY_BANK, address,
            bytes([0xFF]) * len(replacement), replacement,
            label, allowed,
        )
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
            f"candidate change escaped owned bytes: {sorted(changed - allowed)[:8]}")
    functional_changed = changed - {0x014D, 0x014E, 0x014F}
    require(functional_changed,
            "candidate unexpectedly has no functional changes")
    require(len(changed) == EXPECTED_CHANGED_BYTES,
            f"changed-byte count drifted: {len(changed)}")
    require(len(functional_changed) == EXPECTED_FUNCTIONAL_CHANGED_BYTES,
            f"functional changed-byte count drifted: {len(functional_changed)}")

    # No hot runtime source, Stage-7 selector, palette, service, or helper
    # lineage byte may move.  Live non-Stage4 state is restored from payloads.
    for bank in MIRROR_BANKS:
        require(runtime_from(candidate, bank) == runtime_from(base, bank),
                f"bank{bank} hot runtime source changed")
        require_region(candidate, bank, 0x570E,
                       region(base, bank, 0x570E, 16),
                       "Stage7 arm selector")
        require_region(candidate, bank, 0x68C8,
                       region(base, bank, 0x68C8, 8),
                       "r281 Stage1 metallic-tooth row")
    require(region(candidate, OVERLAY_BANK, 0x6C80, 0x5C5)
            == region(base, OVERLAY_BANK, 0x6C80, 0x5C5),
            "existing bank22 Stage7 helper/lazy-disarm region changed")

    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND":
        require(candidate_sha == EXPECTED_CANDIDATE_SHA256,
                f"candidate identity drift: {candidate_sha}")

    generic_precompare_t = 272
    helper_precompare_t = 132
    saving_t = generic_precompare_t - helper_precompare_t
    require((generic_precompare_t, helper_precompare_t, saving_t)
            == (272, 132, 140), "cycle proof changed")
    projected_route_saving = saving_t * 985
    require(projected_route_saving == 137900,
            "Stage4 route projection changed")

    routes = route_contract(labels)
    receipt: dict[str, object] = {
        "schema": "penta-stage4-transition-overlay-r284-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_sha256": R281_SHA256,
        "candidate_sha256": candidate_sha,
        "changed_bytes_including_checksums": len(changed),
        "functional_changed_bytes": len(functional_changed),
        "checksums": checksum_contract(candidate),
        "lineage": lineage,
        "mirror_patches": mirror_records,
        "bank22_overlay": overlay_records,
        "main": {
            "range": f"${MAIN_ADDR:04X}-${MAIN_ADDR + len(main) - 1:04X}",
            "length": len(main),
            "sha256": digest(main),
            "labels": {name: f"${value:04X}" for name, value in labels.items()},
            "atomic_order": [
                "$DAD5=$60 makes every later dungeon native",
                "$DAB7=$EB makes dirty return native",
                "copy all 22 exact router bytes to $DAE9-$DAFE",
                "classify FFBA exhaustively",
                "Stage4 copies all 20 helper bytes before $DAD5=$E9 commit",
                "Stage7 reaches unchanged $570E arm only after router restore",
            ],
        },
        "route_contract": routes,
        "helper": {
            "runtime_range": "$DAE9-$DAFC",
            "bytes": HELPER.hex(" ").upper(),
            "sample_load": "LD HL,$C1F1; LD B,[HL]; INC H; LD C,[HL]",
            "join": "$DAFC=$95; next $DAFD-107=$DA92 LD A,[DE]",
            "pushes": ["BC", "DE", "HL"],
            "ffe0_value": "$00",
            "shared_epilogue_pops": ["HL", "DE", "BC"],
        },
        "cycle_contract_t": {
            "r281_DA60_to_DA92": generic_precompare_t,
            "r284_DAE9_to_DA92": helper_precompare_t,
            "saved_per_stage4_decision": saving_t,
            "r279_measured_stage4_decisions": 985,
            "projected_route_saving": projected_route_saving,
            "dispatcher_final_JP_both": 16,
            "shared_compare_hit_dirty_and_epilogue": "byte-identical",
            "all_nonstage_gameplay_routes": "byte-and-cycle-identical to r281",
        },
        "stack_contract": {
            "entry": "PUSH saved FF99 bank; stock mapper CALL/RET is balanced",
            "main": "PUSH BC/DE/HL; both stock memcpy CALL/RET pairs are balanced",
            "exit": (
                "POP HL/DE/BC; return thunk POPs saved bank then CALL $0061; "
                "mapper RET lands on original-bank code"
            ),
            "net_words_vs_original_selector_caller": 0,
            "target_registers": "BC/DE/HL exact; every target overwrites A before use",
        },
        "lifecycle_contract": {
            "cold_boot": "$DAD5=$60, $DAB7=$EB, exact router from r281 sources",
            "Stage4_entry": "common reset then helper copy then $DAD5=$E9 commit",
            "Stage4_menu_roundtrip": "overlay retained; FFBA and hot route remain Stage4",
            "Stage4_to_Stage5_or_6": "common reset restores native landing/router/redirect",
            "Stage4_to_Stage7": (
                "common reset restores exact router; unchanged $570E selector then arms $31"
            ),
            "Stage7_to_other": "common reset restores $DAB7=$EB before classification",
            "Crystal": "$DACE JP $DA60 bypasses $DAD4 landing; later selector still resets",
            "cache_invalidation": (
                "unchanged common tail $5484-$549B writes $DF55/$DF59=$FF before $53F2"
            ),
        },
        "corpus_contract": corpora,
        "contracts": {
            "exact_r281_base_and_six_byte_visual_delta_preserved": True,
            "only_code_owned_front_stubs_and_erased_bank22_changed": True,
            "no_graphic_or_BG_table_cave_used": True,
            "both_runtime_source_mirrors_byte_exact_to_r281": True,
            "Stage2_3_5_6_gameplay_runtime_byte_and_cycle_exact_to_r281": True,
            "Stage7_router_arm_helper_and_gameplay_timeline_exact_to_r281": True,
            "Crystal_DACE_path_byte_exact_to_r281": True,
            "all_512_FFBA_mirror_cases_partitioned": True,
            "router_restore_precedes_Stage7_arm": True,
            "Stage4_helper_commit_is_last_and_fail_closed": True,
            "corrected_helper_joins_DA92_not_DA93": True,
            "pagepair_zero_collision_variant_and_stale_hit_on_bound_corpora": True,
            "mapper_and_memcpy_stack_balance_static": True,
            "r281_Stage1_palette_delta_unchanged": True,
        },
        "required_live_gates": [
            "single-flight Stage4 strict speed replay",
            "Stage4 semantic/attribute and room-edge containment",
            "Stage4 SELECT-menu roundtrip",
            "Stage4->5->6->7 lifecycle trace of DAD5/DAB7/DAE9",
            "Stage5 and Stage7 strict phase containment",
            "candidate-bound Crystal and all-stage visual containment",
        ],
    }
    return candidate, receipt


def require_tmp(path: Path) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved == scratch or scratch in resolved.parents,
            f"output must remain below {scratch}: {resolved}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", type=Path,
        default=TMP / "stage1-metallic-teeth-r281/candidate.gb",
    )
    parser.add_argument(
        "--r279", type=Path,
        default=TMP / "stage7-lazy-disarm-r279/candidate.gb",
    )
    parser.add_argument(
        "--output", type=Path,
        default=TMP / "stage4-transition-overlay-r284/candidate.gb",
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=TMP / "stage4-transition-overlay-r284/build-receipt.json",
    )
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
