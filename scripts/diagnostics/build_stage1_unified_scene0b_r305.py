#!/usr/bin/env python3
"""Build r305: unified, relocatable Stage-1 scene-$0B repair on exact r303.

r303 proved that the native scene-$0B publishers reach the split-key gateway,
but exposed three independent omissions.  The copied WRAM gateway contained a
bank-relative CALL that executed the wrong physical routine and clobbered live
HL, the room-context wall hook did not invalidate both physical-map semantic
keys, and menu close left those same keys valid.

r305 routes the gateway's slow path through an audited fixed-bank bridge and
one erased bank-31 multiplexer, preserves live HL so stock DA13 publishes the
odd exact-destination FFA5 tag, installs r298's atomic wall helper byte-exact,
and folds the reviewed menu-close invalidator into the same bridge.  Normal
scene $02/$0A keeps r303's exact 44T gateway; no emulator is invoked here.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import build_stage1_fast_scene0b_gates_r303 as r303
import build_stage1_room01_atomic_wall_r298 as r298
import build_stage1_scene0b_menu_close_r304 as r304


ROOT = r304.ROOT
TMP = r304.TMP
BASE = r304.BASE
BASE_RECEIPT = r304.BASE_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-unified-scene0b-r305/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-unified-scene0b-r305/build-receipt.json"

BASE_SHA256 = r304.BASE_SHA256
BASE_RECEIPT_SHA256 = r304.BASE_RECEIPT_SHA256
BASE_SCHEMA = r304.BASE_SCHEMA
REJECTED_LIVE_RECEIPT = (
    TMP / "stage1-fast-scene0b-gates-r303/live-scene0b-dcbb40/receipt.json"
)
REJECTED_LIVE_RECEIPT_SHA256 = (
    "5ffb3c24a0f3ae150970081df4cd581136e3dc399221312722f31e41d816dd6c"
)
EXPECTED_CANDIDATE_SHA256 = (
    "9c83a6937a1b71f2b4d0a6628fa3022d8f46f89e46c7aafa23a61a8d9166ce13"
)

FIXED_STUB_ADDR = r304.FIXED_STUB_ADDR
OLD_FIXED_STUB = r304.OLD_FIXED_STUB
NEW_FIXED_STUB = r304.NEW_FIXED_STUB
SHARED_TAIL_ADDR = r304.SHARED_TAIL_ADDR
OLD_SHARED_TAIL = r304.OLD_SHARED_TAIL
NEW_SHARED_TAIL = r304.NEW_SHARED_TAIL

ATTR_BANKS = r303.MIRROR_BANKS
ATTR_GATEWAY_ADDR = r303.r297.ATTR_GATEWAY_ADDR
OLD_GATEWAYS = {
    bank: (
        r303.r297.OLD_ATTR_GATEWAY[:7]
        + bytes((0xC4, helper & 0xFF, helper >> 8))
    )
    for bank, helper in r303.r297.ATTR_HELPER_BY_BANK.items()
}
NEW_ATTR_GATEWAY = (
    r303.r297.OLD_ATTR_GATEWAY[:7]
    + bytes.fromhex("C4 13 00")
)
RUNTIME_LENGTH = 41
RUNTIME_RELOCATED_ADDR = 0xDAD7
ATTR_OUTER_RETURN = 0xDAE1
ATTR_REJECT_ADDR = 0xDAB9
ATTR_ACCEPT_ADDR = 0xDAE1
ATTR_CONTINUATION = bytes.fromhex("3E 15 CD 61 00 C3 00 41")
ATTR_REJECT_SOURCE_ADDR = ATTR_GATEWAY_ADDR - (
    RUNTIME_RELOCATED_ADDR - ATTR_REJECT_ADDR
)
ATTR_REJECT_PREIMAGE = bytes.fromhex("06 05 FA 80 D8")

BANK31 = r304.BANK31
BANK31_START = r304.BANK31_START
BANK31_END = r304.BANK31_END
MUX_ADDR = r304.HELPER_ADDR

WALL_BANK = r303.r297.EXPANSION_BANK
WALL_ADDR = r303.r297.WALL_HELPER_ADDR
OLD_WALL_HELPER = r303.r297.WALL_HELPER + bytes([0xFF]) * 8
NEW_WALL_HELPER = r298.WALL_HELPER

# Exact stock tagged-destination chain retained by r305.  The rejected r303
# wrong-bank helper changed H=$98/$9C to $55, so DA13 visibly wrote even $56.
# The new mux preserves HL; DA13 therefore writes $99/$9D and mapdone's bit-0
# test reaches the native dirty compiler/postcopy path.
PRIVATE_DIRTY_TAIL_OFFSET = r304.bank_offset(21, 0x4139)
PRIVATE_DIRTY_TAIL = bytes.fromhex("3E 01 B7 C3 61 00")
ATOMIC_SOURCE_OFFSET = r304.bank_offset(13, 0x7B13)
ATOMIC_SOURCE = bytes.fromhex("7C 3C E0 A5 F0 FF EA 5A DF E6 04 E0 FF C9")
MAP_ENTRY_ADDR = 0x42A7
MAP_ENTRY = bytes.fromhex("2E 00 7C E0 A5 16 FF CD 85 34")
MAPDONE_ADDR = 0x42ED
MAPDONE = bytes.fromhex("F0 A5 1F 38 0A")
COMPILER_DEST_ADDR = 0x4328
COMPILER_DEST = bytes.fromhex("F0 A5 3D 67 E0 53")
POSTCOPY_OFFSET = r304.bank_offset(19, 0x6CCE)
POSTCOPY = bytes.fromhex("F0 A5 E6 FE 67 C3 A7 6B")

CACHE_ADDRS = r304.CACHE_ADDRS
CHECKSUM_OFFSETS = r304.CHECKSUM_OFFSETS


class Asm:
    def __init__(self, origin: int) -> None:
        self.origin = origin
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    @property
    def pc(self) -> int:
        return self.origin + len(self.code)

    def db(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def label(self, name: str) -> None:
        r304.require(name not in self.labels, f"duplicate label {name}")
        self.labels[name] = self.pc

    def jr(self, opcode: int, label: str) -> None:
        self.db(opcode, 0)
        self.fixups.append((len(self.code) - 1, label))

    def finish(self) -> bytes:
        for operand, label in self.fixups:
            after = self.origin + operand + 1
            displacement = self.labels[label] - after
            r304.require(-128 <= displacement <= 127,
                         f"JR {label} out of range: {displacement}")
            self.code[operand] = displacement & 0xFF
        return bytes(self.code)


def build_mux() -> bytes:
    """Build the bank-31 menu/relocated-attribute multiplexer."""
    a = Asm(MUX_ADDR)
    # Stack at entry: [084D][outer return][real caller...].  Save the caller's
    # HL and inspect the outer return in place without consuming either frame.
    a.db(0xE5, 0xF8, 0x04, 0x7E)       # PUSH HL; LD HL,SP+4; LD A,[HL]
    a.db(0xFE, ATTR_OUTER_RETURN & 0xFF)
    a.jr(0x28, "attr_high")
    a.db(0xFE, r304.TAIL_RETURN_ADDR & 0xFF)
    a.jr(0x20, "unknown")
    a.db(0x23, 0x7E, 0xFE, r304.TAIL_RETURN_ADDR >> 8)
    a.jr(0x28, "menu")
    a.jr(0x18, "unknown")

    a.label("attr_high")
    a.db(0x23, 0x7E, 0xFE, ATTR_OUTER_RETURN >> 8)
    a.jr(0x28, "attr")

    a.label("unknown")
    # Fail closed while still restoring the coherent bank-1 mapper contract.
    a.db(0xE1, 0x3E, 0x01, 0xB7, 0xC9)  # POP HL; LD A,1; OR A; RET

    a.label("attr")
    # D880 and the stack both live in switchable WRAM bank 1.  Reject before
    # reading/writing either semantic state if SVBK's low three bits differ.
    a.db(0xF0, 0x70, 0xE6, 0x07, 0xFE, 0x01)
    a.jr(0x20, "attr_reject")
    # The native F7/CP02 fast path already handled $02/$0A.  Its only newly
    # reachable slow case is masked $03 plus the authoritative Stage-1 $02.
    a.db(0xFA, 0x80, 0xD8, 0xE6, 0xF7, 0xFE, 0x03)
    a.jr(0x20, "attr_reject")
    a.db(0xF0, 0xB7, 0xFE, 0x02)
    a.jr(0x20, "attr_reject")
    # Z from CP $02 is the private decider's accepted gateway ABI.  LD A,d8,
    # POP and RET preserve it; fixed:$084D restores bank 1 before $DAE1.
    a.db(0xE1, 0x3E, 0x01, 0xC9)

    a.label("attr_reject")
    # HL still points at the high byte of outer $DAE1.  Rewrite it in place to
    # native $DAB9, restore caller HL, and return through $084D's bank-1 map.
    a.db(0x2B, 0x36, ATTR_REJECT_ADDR & 0xFF, 0x23)
    a.db(0x36, ATTR_REJECT_ADDR >> 8, 0xE1, 0x3E, 0x01, 0xB7, 0xC9)

    a.label("menu")
    # Menu always reproduces the native common-tail result.  Cache writes are
    # additionally fail-closed on SVBK1, exact scene $0B and Stage 1 marker.
    a.db(0xF0, 0x70, 0xE6, 0x07, 0xFE, 0x01)
    a.jr(0x20, "menu_exit")
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x0B)
    a.jr(0x20, "menu_exit")
    a.db(0xF0, 0xB7, 0xFE, 0x02)
    a.jr(0x20, "menu_exit")
    a.db(0x3E, 0xFF, 0xEA, 0x53, 0xDF, 0xEA, 0x57, 0xDF)

    a.label("menu_exit")
    # Restore HL, discard synthetic $084D, clear FFE4/A/Z as native, then use
    # the stock AF-preserving mapper thunk.  $77AB performs the final RET.
    a.db(0xE1, 0xF1, 0xAF, 0xE0, 0xE4, 0xC3, 0x9A, 0x09)
    return a.finish()


MUX = build_mux()


def byte_range(bank: int, address: int, width: int) -> set[int]:
    start = r304.bank_offset(bank, address)
    return set(range(start, start + width))


def owned_ranges() -> set[int]:
    result = set(range(FIXED_STUB_ADDR, FIXED_STUB_ADDR + 5))
    result |= set(range(SHARED_TAIL_ADDR, SHARED_TAIL_ADDR + 4))
    result |= byte_range(BANK31, MUX_ADDR, len(MUX))
    result |= byte_range(WALL_BANK, WALL_ADDR, len(NEW_WALL_HELPER))
    for bank in ATTR_BANKS:
        result |= byte_range(bank, ATTR_GATEWAY_ADDR, len(NEW_ATTR_GATEWAY))
    return result


def attr_accepts(scene: int, ffb7: int, svbk: int) -> bool:
    masked = scene & 0xF7
    if masked == 0x02:
        return True
    return ((svbk & 7) == 1 and masked == 0x03 and ffb7 == 0x02)


def source_semantic_contract() -> dict[str, Any]:
    cases = 0
    newly_accepted: set[tuple[int, int]] = set()
    for ffb7 in range(256):
        for dd06 in range(4):
            for ffbf in range(4):
                scene = r303.r297.reachable_scene(
                    ffb7, dd06=dd06, ffbf=ffbf
                )
                for svbk in range(8):
                    accepted = attr_accepts(scene, ffb7, svbk)
                    old = r303.r297.old_attr_accepts(scene)
                    if accepted and not old:
                        r304.require(
                            scene == 0x0B and ffb7 == 0x02 and svbk == 1,
                            "relocated attr mux admitted an unsafe state",
                        )
                        newly_accepted.add((scene, ffb7))
                    cases += 1
    r304.require(newly_accepted == {(0x0B, 0x02)},
                 "Stage-1 scene0B is not the sole reachable new state")
    r304.require(not attr_accepts(0x18, 0x02, 1), "splash admitted")
    r304.require(not attr_accepts(0x03, 0x03, 1), "Stage2 admitted")

    # Exact stock tagged-destination algebra after the mux preserves HL.
    latch_rows = []
    for destination in (0x98, 0x9C):
        da13_tag = (destination + 1) & 0xFF
        carry = da13_tag & 1
        compiler_h = (da13_tag - 1) & 0xFF
        r304.require(carry == 1 and compiler_h == destination,
                     "stock tagged destination no longer round-trips")
        latch_rows.append({
            "destination_h": f"{destination:02X}",
            "mux_preserved_h": f"{destination:02X}",
            "DA13_FFA5": f"{da13_tag:02X}",
            "mapdone_carry": carry,
            "compiler_h": f"{compiler_h:02X}",
        })
    return {
        "reachable_attr_states_exhausted": cases,
        "only_new_reachable_attr_state": "SVBK1,FFB7=02,D880=0B",
        "splash18_rejected": True,
        "stage2_scene03_rejected": True,
        "dirty_latch_truth_table": latch_rows,
        "stock_tag_chain_retained_byte_exact": True,
    }


def exhaustive_contract() -> dict[str, Any]:
    return {
        **source_semantic_contract(),
        "r303_observed_bad_tag": "56 (proves H was clobbered to 55)",
    }


def stack_contract() -> dict[str, Any]:
    outer = [0x34, 0x12, 0x78, 0x56]
    attr_entry = [0x4D, 0x08, 0xE1, 0xDA] + outer
    saved_hl = [0xCD, 0xAB]
    frame = saved_hl + attr_entry
    # accept: POP HL, RET $084D, mapper RET $DAE1
    r304.require(frame[2:4] == [0x4D, 0x08]
                 and frame[4:6] == [0xE1, 0xDA], "attr stack moved")
    # reject mutates only the outer gateway return.
    rejected = list(frame)
    rejected[4:6] = [0xB9, 0xDA]
    r304.require(rejected[:4] == frame[:4] and rejected[6:] == frame[6:],
                 "reject rewrite escaped its return frame")

    menu_entry = saved_hl + [0x4D, 0x08, 0xAB, 0x77] + outer
    after_restore_and_discard = menu_entry[4:]
    r304.require(after_restore_and_discard[:2] == [0xAB, 0x77],
                 "menu did not discard only synthetic $084D")
    r304.require(after_restore_and_discard[2:] == outer,
                 "menu real outer frame changed")
    return {
        "attr_entry": "[084D,DAE1,outer]",
        "attr_accept": "restore HL; preserve Z; RET 084D -> map1 -> DAE1",
        "attr_reject": "rewrite DAE1->DAB9; restore HL; map1; outer SP exact",
        "attr_abi": "BC/DE/HL/outer-SP preserved; A=01; accept Z preserved",
        "menu_entry": "[084D,77AB,outer]",
        "menu_exit": "restore HL; discard 084D; native $099A/$77AB tail",
        "required_entry_state": "SVBK=FF99=DC09=01",
    }


def source_preimages(source: bytes) -> dict[str, Any]:
    """Validate the fixed recipe without claiming a historical live audit."""
    r304.require(r304.digest(source) == BASE_SHA256, "wrong exact r303 base")
    r304.validate_preimages(source)
    for bank in ATTR_BANKS:
        offset = r304.bank_offset(bank, ATTR_GATEWAY_ADDR)
        r304.require(source[offset:offset + 10] == OLD_GATEWAYS[bank],
                     f"bank{bank} r303 attr gateway changed")
        r304.require(source[offset + 10:offset + 18] == ATTR_CONTINUATION,
                     f"bank{bank} accepted continuation changed")
        r304.require(source[offset:offset + RUNTIME_LENGTH][-1] == 0,
                     f"bank{bank} runtime payload width changed")
        reject = r304.bank_offset(bank, ATTR_REJECT_SOURCE_ADDR)
        r304.require(source[reject:reject + 5] == ATTR_REJECT_PREIMAGE,
                     f"bank{bank} native DAB9 reject ABI changed")

    wall = r304.bank_offset(WALL_BANK, WALL_ADDR)
    r304.require(source[wall:wall + len(OLD_WALL_HELPER)] == OLD_WALL_HELPER,
                 "r303/r297 wall helper preimage changed")
    r304.require(source[PRIVATE_DIRTY_TAIL_OFFSET:
                        PRIVATE_DIRTY_TAIL_OFFSET + len(PRIVATE_DIRTY_TAIL)]
                 == PRIVATE_DIRTY_TAIL,
                 "bank1-restoring private dirty tail changed")
    r304.require(source[ATOMIC_SOURCE_OFFSET:
                        ATOMIC_SOURCE_OFFSET + len(ATOMIC_SOURCE)]
                 == ATOMIC_SOURCE, "tagged DA13 cold source changed")
    r304.require(source[MAP_ENTRY_ADDR:MAP_ENTRY_ADDR + len(MAP_ENTRY)]
                 == MAP_ENTRY, "map-entry exact destination changed")
    r304.require(source[MAPDONE_ADDR:MAPDONE_ADDR + len(MAPDONE)]
                 == MAPDONE, "mapdone tagged decision changed")
    r304.require(source[COMPILER_DEST_ADDR:
                        COMPILER_DEST_ADDR + len(COMPILER_DEST)]
                 == COMPILER_DEST, "compiler tag normalization changed")
    r304.require(source[POSTCOPY_OFFSET:POSTCOPY_OFFSET + len(POSTCOPY)]
                 == POSTCOPY, "postcopy tag normalization changed")

    return {
        "runtime_payload": "bank13/16:$7C96 copied byte-exact to SVBK1:$DAD7",
        "runtime_entry": "$DAD7",
        "accepted_continuation": "$DAE1",
        "rejected_continuation": "$DAB9",
        "source_gateway_direct_execution": False,
        "wall_preimage": "exact r297 52 bytes plus eight erased bytes",
        "latch_preimage": "entry/DA13/mapdone/compiler/postcopy byte exact",
    }


def validate_preimages(source: bytes, rejected_receipt_bytes: bytes | None = None
                       ) -> dict[str, Any]:
    contract = source_preimages(source)
    if rejected_receipt_bytes is None:
        rejected_receipt_bytes = REJECTED_LIVE_RECEIPT.read_bytes()
    r304.require(r304.digest(rejected_receipt_bytes)
                 == REJECTED_LIVE_RECEIPT_SHA256,
                 "rejected r303 live receipt identity changed")
    rejected = json.loads(rejected_receipt_bytes)
    r304.require(rejected.get("rom_sha256") == BASE_SHA256,
                 "rejected live receipt was not bound to r303")
    return {
        "r303_live_rejection_receipt_sha256": REJECTED_LIVE_RECEIPT_SHA256,
        "r303_live_rejection_rom_sha256": rejected["rom_sha256"],
        **contract,
    }


def patch_exact(
    rom: bytearray, source: bytes, offset: int, old: bytes, new: bytes,
    allowed: set[int], label: str,
) -> None:
    r304.patch_exact(rom, source, offset, old, new, allowed, label)


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    r304.require(len(candidate) == len(source) == r304.ROM_SIZE,
                 "candidate size changed")
    changed = r304.delta(source, candidate)
    functional = r304.delta(source, candidate, functional=True)
    allowed = owned_ranges() | CHECKSUM_OFFSETS
    r304.require(changed <= allowed,
                 f"r305 escaped ownership: {sorted(changed - allowed)[:8]}")
    expected = {offset for offset in owned_ranges()
                if source[offset] != candidate[offset]}
    r304.require(functional == expected,
                 "functional delta is not exactly the reviewed patch")

    helper = r304.bank_offset(BANK31, MUX_ADDR)
    r304.require(candidate[helper:helper + len(MUX)] == MUX,
                 "bank31 mux changed")
    r304.require(candidate[BANK31_START:helper]
                 == bytes([0xFF]) * (helper - BANK31_START),
                 "bank31 prefix changed")
    r304.require(candidate[helper + len(MUX):BANK31_END]
                 == bytes([0xFF]) * (BANK31_END - helper - len(MUX)),
                 "bank31 suffix changed")

    # The fixed cave has exactly three executable entries: the shared menu
    # tail and the two copied-runtime source mirrors.  Keep the reviewed bank15
    # graphics-data false mention as the sole fourth raw mention.
    mentions = r304.absolute_cave_mentions(candidate)
    expected_mentions = {
        r304.CAVE_DATA_FALSE_MENTION,
        (SHARED_TAIL_ADDR, 0xCD, FIXED_STUB_ADDR),
        *{
            (r304.bank_offset(bank, ATTR_GATEWAY_ADDR) + 7,
             0xC4, FIXED_STUB_ADDR)
            for bank in ATTR_BANKS
        },
    }
    r304.require(set(mentions) == expected_mentions,
                 f"fixed cave entry set changed: {mentions}")
    r304.require(not r304.relative_fixed_cave_mentions(candidate),
                 "fixed cave gained a relative entry")

    # Exact r303 pieces not superseded here remain immutable.
    for bank in ATTR_BANKS:
        offset = r304.bank_offset(bank, ATTR_GATEWAY_ADDR)
        r304.require(candidate[offset + 10:offset + RUNTIME_LENGTH]
                     == source[offset + 10:offset + RUNTIME_LENGTH],
                     f"bank{bank} runtime continuation changed")
    r304.require(candidate[r304.SHARED_ROUTINE_ADDR:SHARED_TAIL_ADDR]
                 == source[r304.SHARED_ROUTINE_ADDR:SHARED_TAIL_ADDR],
                 "shared menu body changed")
    return {
        "functional_changed_bytes": len(functional),
        "changed_offsets": [f"0x{offset:06X}" for offset in sorted(functional)],
        "owned_ranges": [
            "fixed:$0013-$0017", "bank1:$77A8-$77AB",
            "bank13/16:$7C96-$7C9F", "bank21:$6C80-$6CBB",
            f"bank31:$6C80-${MUX_ADDR + len(MUX)-1:04X}",
        ],
        "fixed_cave_executable_entries": 3,
        "fixed_cave_reviewed_data_mentions": 1,
        "escaped_bytes": 0,
    }


def timing_contract() -> dict[str, Any]:
    return {
        "attr_scene02_0A": {"r303": 44, "r305": 44, "delta": 0},
        "stock_tagged_destination_chain": {"delta": 0},
        "attr_scene0B": {
            "classification": "slow bank31 bridge only",
            "delta": "live speed gate required",
        },
        "attr_rejected_scenes": {
            "classification": "diagnostic bank31 bridge",
            "delta": "must be optimized after live ownership proof if hot",
        },
        "wall_hook": "room-write lifecycle only; renderer +0T",
        "menu_tail": "user-action lifecycle only; renderer +0T",
    }


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    """Emit exact r305; historical observations are not construction inputs."""
    preimages = source_preimages(source)
    semantic = source_semantic_contract()
    abi = stack_contract()

    rom = bytearray(source)
    allowed: set[int] = set()
    patch_exact(rom, source, FIXED_STUB_ADDR, OLD_FIXED_STUB, NEW_FIXED_STUB,
                allowed, "fixed bank31 bridge")
    patch_exact(rom, source, SHARED_TAIL_ADDR, OLD_SHARED_TAIL, NEW_SHARED_TAIL,
                allowed, "shared menu-close tail")
    for bank in ATTR_BANKS:
        patch_exact(
            rom, source, r304.bank_offset(bank, ATTR_GATEWAY_ADDR),
            OLD_GATEWAYS[bank], NEW_ATTR_GATEWAY, allowed,
            f"bank{bank} relocatable attr gateway",
        )
    patch_exact(
        rom, source, r304.bank_offset(WALL_BANK, WALL_ADDR),
        OLD_WALL_HELPER, NEW_WALL_HELPER, allowed,
        "exact r298 atomic wall/cache helper",
    )
    patch_exact(
        rom, source, r304.bank_offset(BANK31, MUX_ADDR),
        bytes([0xFF]) * len(MUX), MUX, allowed,
        "bank31 attr/menu multiplexer",
    )
    r304.require(allowed == owned_ranges(), "constructed ownership drifted")
    r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    candidate_sha256 = r304.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r304.require(candidate_sha256 == EXPECTED_CANDIDATE_SHA256,
                     f"candidate identity drift: {candidate_sha256}")

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-unified-scene0b-r305-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "base": {
            "revision": "r303",
            "candidate_sha256": BASE_SHA256,
        },
        "candidate_sha256": candidate_sha256,
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "root_causes": {
            "relocation": "WRAM payload called mirror-bank-local ROM helpers",
            "dirty_latch": (
                "preserve H across the attr mux so tagged DA13 produces "
                "an odd destination tag consumed by dirty mapdone"
            ),
            "wall_cache": "r297 C600 writes omitted DF53/DF57 invalidation",
            "menu_close": "native shared close tail omitted scene0B invalidation",
        },
        "patch": {
            "fixed_bridge": NEW_FIXED_STUB.hex(" ").upper(),
            "gateway": NEW_ATTR_GATEWAY.hex(" ").upper(),
            "tagged_destination_chain": "byte-exact stock/r303; HL preserved",
            "wall_helper": NEW_WALL_HELPER.hex(" ").upper(),
            "mux_range": f"bank31:$6C80-${MUX_ADDR + len(MUX)-1:04X}",
            "mux_bytes": MUX.hex(" ").upper(),
            "menu_tail": NEW_SHARED_TAIL.hex(" ").upper(),
        },
        "preimage_contract": preimages,
        "offline_contract": {
            "semantic": semantic,
            "abi": abi,
            "timing_t_cycles": timing_contract(),
            "wall": r298.room_hook_model(
                {tile: 0 for tile in r303.r297.TARGET_TILES},
                {0xDF53: 0, 0xDF57: 0}, stage=0, room=1,
            )[1],
        },
        "ownership": ownership,
        "composition": {
            "r303_art_BG7_row_transition": "byte-exact retained",
            "r300_bank20_semantic_row": "byte-exact retained",
            "r298_wall_helper": "byte-exact installed",
            "r304_menu_design": "folded into bank31 mux",
            "r301_open_hook": "omitted",
            "cache_semantics": (
                "wall lifecycle and menu close both idempotently write only "
                "DF53/DF57=FF; dirty decider then consumes the same sentinels"
            ),
        },
        "required_live_gates": [
            "scene0B decider dirty must produce dirty postcopy (not pure)",
            "zero unsafe wall/edge attrs in room01 low-health route",
            "menu open/hold/close red-green and palette continuity",
            "hazard trail/gray-spike rendered continuity",
            "blank-SRAM Stage1 handoff has no cyan/white flash",
            "release speed matrix: Stage1 >=95%, Stages2-7 strict 99%",
        ],
        "decision": "CONSTRUCTION_ONLY_LIVE_GATES_REQUIRED",
    }
    return candidate, receipt


def build(source: bytes, base_receipt_bytes: bytes, *, rejected_receipt_bytes: bytes | None = None
          ) -> tuple[bytes, dict[str, Any]]:
    r304.require(r304.digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
                 "r303 build receipt identity changed")
    base_receipt = json.loads(base_receipt_bytes)
    r304.require(base_receipt.get("schema") == BASE_SCHEMA,
                 "r303 schema changed")
    r304.require(base_receipt.get("candidate_sha256") == BASE_SHA256,
                 "r303 receipt names another ROM")
    preimages = validate_preimages(source, rejected_receipt_bytes)
    semantic = exhaustive_contract()
    candidate, receipt = construct(source)
    receipt.update({
        "schema": "penta-stage1-unified-scene0b-r305-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "base": {
            "revision": "r303-rejected", "candidate_sha256": BASE_SHA256,
            "build_receipt_sha256": BASE_RECEIPT_SHA256,
            "live_rejection_receipt_sha256": REJECTED_LIVE_RECEIPT_SHA256,
        },
        "preimage_contract": preimages,
        "decision": "STATIC_DIAGNOSTIC_ONLY_LIVE_GATES_REQUIRED",
    })
    receipt["offline_contract"]["semantic"] = semantic
    receipt["root_causes"]["dirty_latch"] = (
        "wrong-bank r303 attr helper clobbered live H to 55; tagged "
        "DA13 consequently wrote even FFA5=56 and mapdone went pure"
    )
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r304.checked_output(args.output, "candidate output")
    receipt_path = r304.checked_output(args.receipt, "receipt output")
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_bytes(r304.receipt_bytes(receipt))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
