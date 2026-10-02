#!/usr/bin/env python3
"""Build r320: publish Stage-1 scroll and BG page as one critical commit.

The r318 north trace exposed one real presentation tear at gameplay frame
1040.  The completed $9800 page became live while SCY still described the
old $9C00 page; fixed ``$12E0-$1302`` writes LCDC at $12EC but does not write
SCY until $1300.  A service/frame boundary in that interval presented 101
wrong viewport cells for one frame.

This exact-width overlay rewrites the 35-byte fixed publisher so it disables
interrupts, writes SCX/SCY first, selects LCDC with the original zero/nonzero
DC0B semantics, writes LCDC last, and restores IME before returning.  r314's
private Scene-$0B repair commit formerly published LCDC itself and continued
at $12EE.  Two in-place changes instead make it acknowledge under DI and
continue at $12E0, so both success and abort use the same atomic publisher.

No emulator is invoked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import build_stage1_effective_row_context_r319 as r319


ROOT = r319.ROOT
TMP = r319.TMP
BASE = r319.DEFAULT_OUTPUT
BASE_RECEIPT = r319.DEFAULT_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-atomic-presentation-commit-r320/candidate.gb"
DEFAULT_RECEIPT = (
    TMP / "stage1-atomic-presentation-commit-r320/build-receipt.json"
)

BASE_SHA256 = (
    "2afaa7c87b1cb84f00c25a0f9d6edc8b811144b31ef64430fa0fa9d9d8bcc2db"
)
BASE_RECEIPT_SHA256 = (
    "ccf15f3f8d927f8d512329a1428190263e84b1f05c570a7d14fa9e9cd03b0d00"
)
BASE_SCHEMA = "penta-stage1-effective-row-context-r319-build-v1"
EXPECTED_CANDIDATE_SHA256 = (
    "1bbe2d1d3950b1a6f1a194de42fbf5b5e31b26671b037635c42cbd3013d35ae7"
)

PRIMARY_ADDR = 0x12E0
PRIMARY_END = 0x1303
OLD_PRIMARY = bytes.fromhex(
    "FA 0B DC B7 28 04 3E 8B 18 02 3E 83 E0 40 "
    "F0 97 FE 02 28 07 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 C9"
)
NEW_PRIMARY = bytes.fromhex(
    "F3 "                              # DI
    "F0 97 FE 02 28 07 "               # preserve native FF97 SCX gate
    "FA 00 DC E6 0F E0 43 "            # SCX = DC00 & $0F
    "FA 02 DC E6 0F E0 42 "            # SCY = DC02 & $0F
    "FA 0B DC B7 3E 83 28 02 CB DF "   # DC0B==0 ? $83 : $8B
    "E0 40 FB C9"                       # LCDC last; EI; RET
)

# r314 private commit, bank 31.  The low byte inside the reconstructed stack
# continuation changes $12EE->$12E0.  The old LCDC store becomes DI/NOP; the
# following DADE acknowledgment and mapper return remain byte exact.
SCENE0B_BANK = 31
SCENE0B_CONTINUATION_ADDR = 0x6E11
SCENE0B_CONTINUATION_OLD = 0xEE
SCENE0B_CONTINUATION_NEW = 0xE0
SCENE0B_FLIP_ADDR = 0x6E23
SCENE0B_FLIP_OLD = bytes.fromhex("E0 40")
SCENE0B_FLIP_NEW = bytes.fromhex("F3 00")
SCENE0B_ACK_ADDR = 0x6E25
SCENE0B_ACK = bytes.fromhex("3E C4 EA DE DA")
SCENE0B_TAIL_ADDR = 0x6E2A
SCENE0B_TAIL = bytes.fromhex("E1 3E 01 C3 61 00")
SCENE0B_ABORT_ADDR = 0x6E30
SCENE0B_ABORT_CONTINUATION = bytes.fromhex(
    "F8 00 7E F8 02 77 F8 01 7E F8 03 77 "
    "F8 04 36 E0 23 36 12 E8 02"
)

SCENE0B_SUCCESS_START_ADDR = 0x6E0E
SCENE0B_SUCCESS_OLD = bytes.fromhex(
    "F8 04 36 EE 23 36 12 E8 02 "
    "FA 0B DC B7 28 04 3E 8B 18 02 3E 83 E0 40 "
    "3E C4 EA DE DA E1 3E 01 C3 61 00"
)
SCENE0B_SUCCESS_NEW = bytes.fromhex(
    "F8 04 36 E0 23 36 12 E8 02 "
    "FA 0B DC B7 28 04 3E 8B 18 02 3E 83 F3 00 "
    "3E C4 EA DE DA E1 3E 01 C3 61 00"
)

# $12E0-$1302 is the tail of the sole fixed:$12A0 publisher.  RET does not
# fall through to $1303: fixed:$01ED CALLs $12A0, so the real return is $01F0.
# Its first three instructions overwrite A and all flags before testing them.
PUBLISHER_ENTRY_ADDR = 0x12A0
PUBLISHER_ENTRY_PREFIX = bytes.fromhex(
    "B7 CA 03 13 4F CD 3F 42 CD 50 42 D5 E5 45 4B C5 CD 22 13"
)
PUBLISHER_CALL_ADDR = 0x01ED
PUBLISHER_CALL = bytes.fromhex("CD A0 12")
PUBLISHER_RETURN_ADDR = 0x01F0
PUBLISHER_RETURN_CONTINUATION = bytes.fromhex(
    "F0 CC 3C E6 01 E0 CC C8 F0 CD 3C E6 03 E0 CD C3 78 0B"
)
ABSOLUTE_TRANSFER_OPCODES = frozenset({
    0xC2, 0xC3, 0xC4, 0xCA, 0xCC, 0xCD, 0xD2, 0xD4, 0xDA, 0xDC,
})

# Four copies use the same zero-branch LCDC selector.  Two are already safe
# because this exact DD87/DD85 SCY/SCX publisher prefix immediately precedes
# them; the fixed primary and Scene0B private clone have no such prefix.  A
# fifth no-scroll publisher uses JR NZ ($20) and is intentionally unchanged.
LCDC_SELECTOR_ZERO_BRANCH = bytes.fromhex(
    "FA 0B DC B7 28 04 3E 8B 18 02 3E 83 E0 40"
)
SCROLL_FIRST_PREFIX = bytes.fromhex(
    "FA 87 DD E6 1F E0 42 FA 85 DD E6 1F E0 43"
)
NO_SCROLL_SELECTOR = bytes.fromhex(
    "FA 0B DC B7 20 04 3E 8B 18 02 3E 83 E0 40"
)
BASE_SELECTOR_OFFSETS = (0x0012E0, 0x003089, 0x00818E, 0x07EE17)
SAFE_SELECTOR_OFFSETS = (0x003089, 0x00818E)
UNSAFE_SELECTOR_OFFSETS = (0x0012E0, 0x07EE17)
NO_SCROLL_SELECTOR_OFFSETS = (0x00B990,)

MAPPER_ENTRY_ADDR = 0x0061
MAPPER_ENTRY = bytes.fromhex("EA 09 DC C3 BE 09")
MAPPER_BODY_ADDR = 0x09BE
MAPPER_BODY = bytes.fromhex("E0 99 EA 00 21 C9")
CHECKSUM_OFFSETS = r319.CHECKSUM_OFFSETS


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    r319.require(condition, message)


def bank_offset(bank: int, address: int) -> int:
    return r319.bank_offset(bank, address)


def primary_changed_offsets() -> set[int]:
    return {
        PRIMARY_ADDR + index
        for index, (before, after) in enumerate(
            zip(OLD_PRIMARY, NEW_PRIMARY, strict=True)
        )
        if before != after
    }


def scene0b_changed_offsets() -> set[int]:
    flip = bank_offset(SCENE0B_BANK, SCENE0B_FLIP_ADDR)
    return {
        bank_offset(SCENE0B_BANK, SCENE0B_CONTINUATION_ADDR),
        flip,
        flip + 1,
    }


def owned_ranges() -> set[int]:
    return primary_changed_offsets() | scene0b_changed_offsets()


def jr_target(address: int, operand: int) -> int:
    displacement = operand if operand < 0x80 else operand - 0x100
    return (address + 2 + displacement) & 0xFFFF


def fixed_target_census(
    payload: bytes, target: int,
) -> list[tuple[int, int]]:
    """Return every raw fixed-bank absolute CALL/JP targeting ``target``."""
    require(0 <= target <= 0xFFFF, "absolute target is not a word")
    low, high = target & 0xFF, target >> 8
    fixed = payload[:0x4000]
    return [
        (offset, fixed[offset])
        for offset in range(len(fixed) - 2)
        if fixed[offset] in ABSOLUTE_TRANSFER_OPCODES
        and fixed[offset + 1] == low
        and fixed[offset + 2] == high
    ]


def sequence_census(payload: bytes, pattern: bytes) -> list[int]:
    """Return every overlapping whole-ROM occurrence of an exact pattern."""
    require(pattern, "cannot census an empty byte pattern")
    offsets: list[int] = []
    start = 0
    while (offset := payload.find(pattern, start)) >= 0:
        offsets.append(offset)
        start = offset + 1
    return offsets


def unsafe_selector_census(payload: bytes) -> list[int]:
    """Classify selector copies not immediately preceded by scroll writes."""
    unsafe: list[int] = []
    for offset in sequence_census(payload, LCDC_SELECTOR_ZERO_BRANCH):
        prefix_start = offset - len(SCROLL_FIRST_PREFIX)
        scroll_first = (
            prefix_start >= 0
            and payload[prefix_start:offset] == SCROLL_FIRST_PREFIX
        )
        if not scroll_first:
            unsafe.append(offset)
    return unsafe


def selector_clone_contract(
    source: bytes, candidate: bytes,
) -> dict[str, Any]:
    """Prove every native LCDC selector clone is classified fail-closed."""
    base_all = sequence_census(source, LCDC_SELECTOR_ZERO_BRANCH)
    base_unsafe = unsafe_selector_census(source)
    candidate_all = sequence_census(candidate, LCDC_SELECTOR_ZERO_BRANCH)
    candidate_unsafe = unsafe_selector_census(candidate)
    no_scroll_base = sequence_census(source, NO_SCROLL_SELECTOR)
    no_scroll_candidate = sequence_census(candidate, NO_SCROLL_SELECTOR)
    require(base_all == list(BASE_SELECTOR_OFFSETS),
            "r319 whole-ROM LCDC selector census changed")
    require(base_unsafe == list(UNSAFE_SELECTOR_OFFSETS),
            "r319 unsafe LCDC-first selector census changed")
    require(candidate_all == list(SAFE_SELECTOR_OFFSETS),
            "r320 changed or retained an unexpected selector clone")
    require(candidate_unsafe == [],
            "r320 retained an unsafe LCDC-first selector clone")
    require(no_scroll_base == no_scroll_candidate
            == list(NO_SCROLL_SELECTOR_OFFSETS),
            "r320 changed the separate no-scroll LCDC publisher")
    return {
        "r319_zero_branch_selector_offsets": [
            f"0x{offset:06X}" for offset in base_all
        ],
        "r319_scroll_first_offsets": [
            f"0x{offset:06X}" for offset in SAFE_SELECTOR_OFFSETS
        ],
        "r319_unsafe_LCDC_first_offsets": [
            f"0x{offset:06X}" for offset in base_unsafe
        ],
        "r320_zero_branch_selector_offsets": [
            f"0x{offset:06X}" for offset in candidate_all
        ],
        "r320_unsafe_LCDC_first_offsets": [],
        "unchanged_no_scroll_selector_offsets": [
            f"0x{offset:06X}" for offset in no_scroll_candidate
        ],
    }


def lcdc_from_dc0b(dc0b: int) -> int:
    """Retain native $12E0 semantics: zero selects $9800, any nonzero $9C00."""
    require(0 <= dc0b <= 0xFF, "DC0B is not a byte")
    return 0x83 if dc0b == 0 else 0x8B


def primary_publisher_model(
    *, ff97: int, dc00: int, dc02: int, dc0b: int, incoming_scx: int,
) -> dict[str, Any]:
    """Model the complete r320 leaf including write order and IME state."""
    for name, value in (
        ("FF97", ff97), ("DC00", dc00), ("DC02", dc02),
        ("DC0B", dc0b), ("incoming_scx", incoming_scx),
    ):
        require(0 <= value <= 0xFF, f"{name} is not a byte")
    writes: list[tuple[str, int, bool]] = []
    scx = incoming_scx
    if ff97 != 0x02:
        scx = dc00 & 0x0F
        writes.append(("FF43", scx, False))
    scy = dc02 & 0x0F
    writes.append(("FF42", scy, False))
    lcdc = lcdc_from_dc0b(dc0b)
    writes.append(("FF40", lcdc, False))
    cycles = (
        144 if ff97 == 0x02 and dc0b == 0
        else 148 if ff97 == 0x02
        else 176 if dc0b == 0
        else 180
    )
    return {
        "writes": writes,
        "scx": scx,
        "scy": scy,
        "lcdc": lcdc,
        "final_a": lcdc,
        "final_f": 0x80 if dc0b == 0 else 0x00,
        "final_ime": True,
        "return": PUBLISHER_RETURN_ADDR,
        "t_cycles": cycles,
    }


def primary_static_contract(code: bytes = NEW_PRIMARY) -> dict[str, Any]:
    """Pin instruction layout, branch targets, and presentation write order."""
    require(len(OLD_PRIMARY) == len(code) == PRIMARY_END - PRIMARY_ADDR == 35,
            "primary publisher is not exactly 35 bytes")
    require(code == NEW_PRIMARY, "primary publisher target bytes changed")
    require(code[0] == 0xF3, "primary publisher no longer begins with DI")
    require(code[-2:] == bytes.fromhex("FB C9"),
            "primary publisher no longer ends EI/RET")
    require(jr_target(PRIMARY_ADDR + 5, code[6]) == 0x12EE,
            "FF97 SCX-skip branch target changed")
    require(jr_target(PRIMARY_ADDR + 27, code[28]) == 0x12FF,
            "DC0B zero-selector branch target changed")

    writes = {
        "SCX": PRIMARY_ADDR + code.index(bytes.fromhex("E0 43")),
        "SCY": PRIMARY_ADDR + code.index(bytes.fromhex("E0 42")),
        "LCDC": PRIMARY_ADDR + code.index(bytes.fromhex("E0 40")),
    }
    require(writes == {"SCX": 0x12EC, "SCY": 0x12F3, "LCDC": 0x12FF},
            "primary presentation write addresses changed")
    require(writes["SCX"] < writes["SCY"] < writes["LCDC"],
            "LCDC is not the final presentation write")
    require(code.count(bytes.fromhex("E0 40")) == 1,
            "primary publisher has an ambiguous LCDC store")
    require(code.count(bytes((0xF3,))) == 1
            and code.count(bytes((0xFB,))) == 1,
            "primary critical-section delimiters changed")
    return {
        "range": "$12E0-$1302",
        "bytes": len(code),
        "DI": "$12E0",
        "SCX_write": "$12EC",
        "SCY_write": "$12F3",
        "LCDC_write": "$12FF",
        "EI": "$1301",
        "RET": "$1302",
        "write_order": ["FF43 optional", "FF42", "FF40"],
        "all_presentation_writes_IME_disabled": True,
        "selector": "DC0B == 00 ? LCDC 83 : LCDC 8B",
    }


def scene0b_static_contract(payload: bytes) -> dict[str, Any]:
    """Prove success/abort ordering and the shared matching EI boundary."""
    start = bank_offset(SCENE0B_BANK, SCENE0B_SUCCESS_START_ADDR)
    stream = payload[start:start + len(SCENE0B_SUCCESS_NEW)]
    require(stream == SCENE0B_SUCCESS_NEW,
            "Scene0B success stream changed")
    require(len(SCENE0B_SUCCESS_OLD) == len(SCENE0B_SUCCESS_NEW),
            "Scene0B in-place stream width changed")

    # Both DC0B selector arms converge at the old private FF40 site, which is
    # now DI/NOP.  There is no display write before or after the DADE ack in
    # bank31; mapper RET consumes the reconstructed $12E0 continuation.
    require(jr_target(0x6E1B, stream[0x6E1C - 0x6E0E]) == 0x6E21,
            "Scene0B zero-selector target changed")
    require(jr_target(0x6E1F, stream[0x6E20 - 0x6E0E]) == 0x6E23,
            "Scene0B nonzero-selector target changed")
    require(stream[0x6E23 - 0x6E0E:0x6E25 - 0x6E0E]
            == bytes.fromhex("F3 00"),
            "Scene0B selector arms do not converge on DI/NOP")
    require(bytes.fromhex("E0 40") not in stream,
            "Scene0B success still has a private LCDC write")
    require(stream[0x6E11 - 0x6E0E] == 0xE0
            and stream[0x6E14 - 0x6E0E] == 0x12,
            "Scene0B success continuation is not $12E0")
    require(stream[0x6E25 - 0x6E0E:0x6E2A - 0x6E0E]
            == SCENE0B_ACK,
            "Scene0B acknowledgment moved outside the DI region")
    require(0xFB not in stream,
            "Scene0B success re-enables IME before fixed publisher")

    require(payload[MAPPER_ENTRY_ADDR:
                    MAPPER_ENTRY_ADDR + len(MAPPER_ENTRY)] == MAPPER_ENTRY,
            "fixed mapper entry changed")
    require(payload[MAPPER_BODY_ADDR:
                    MAPPER_BODY_ADDR + len(MAPPER_BODY)] == MAPPER_BODY,
            "fixed mapper RET body changed")
    abort = bank_offset(SCENE0B_BANK, SCENE0B_ABORT_ADDR)
    require(
        payload[abort:abort + len(SCENE0B_ABORT_CONTINUATION)]
        == SCENE0B_ABORT_CONTINUATION,
        "Scene0B abort no longer reconstructs $12E0",
    )
    require(payload[PRIMARY_ADDR:PRIMARY_END] == NEW_PRIMARY,
            "Scene0B convergence target is not the atomic publisher")

    success_events = [
        "DI bank31:$6E23",
        "DADE=$C4 bank31:$6E25",
        "mapper fixed:$0061->$09BE RET",
        "continuation fixed:$12E0 DI",
        "SCX fixed:$12EC (optional)",
        "SCY fixed:$12F3",
        "LCDC fixed:$12FF",
        "matching EI fixed:$1301",
        "RET fixed:$1302 -> caller:$01F0",
    ]
    ordinary_events = [
        "DI fixed:$12E0",
        "SCX fixed:$12EC (optional)",
        "SCY fixed:$12F3",
        "LCDC fixed:$12FF",
        "matching EI fixed:$1301",
        "RET fixed:$1302 -> caller:$01F0",
    ]
    abort_events = [
        "no owned write in bank31 abort",
        "mapper fixed:$0061->$09BE RET",
        "continuation fixed:$12E0 DI",
        "SCX fixed:$12EC (optional)",
        "SCY fixed:$12F3",
        "LCDC fixed:$12FF",
        "matching EI fixed:$1301",
        "RET fixed:$1302 -> caller:$01F0",
    ]
    return {
        "success_stream": "$6E0E-$6E2F exact",
        "selector_zero_target": "$6E21 -> $6E23 DI",
        "selector_nonzero_target": "$6E23 DI",
        "private_FF40_writes": 0,
        "success_stack_continuation": "$12E0",
        "abort_stack_continuation": "$12E0",
        "mapper": "$0061->$09BE RET exact",
        "success_order": success_events,
        "ordinary_order": ordinary_events,
        "abort_order": abort_events,
        "success_ack_interrupt_closed": True,
        "all_presentation_paths_reach_fixed_EI_1301": True,
        "no_interrupt_visible_write_before_path_DI": True,
    }


def exhaustive_contract() -> dict[str, Any]:
    """Exhaust each independent byte domain of the publisher state."""
    selector_cases = 0
    selector_counts = {"83": 0, "8B": 0}
    for dc0b in range(0x100):
        for ff97 in (0x00, 0x02, 0xFF):
            result = primary_publisher_model(
                ff97=ff97, dc00=0xA5, dc02=0x5A,
                dc0b=dc0b, incoming_scx=0xC3,
            )
            expected = 0x83 if dc0b == 0 else 0x8B
            require(result["lcdc"] == expected,
                    "zero/nonzero DC0B selector drifted")
            require(result["writes"][-1] == ("FF40", expected, False),
                    "LCDC is not the final interrupt-closed write")
            require(result["final_ime"] is True,
                    "publisher failed to restore IME")
            selector_counts[f"{expected:02X}"] += 1
            selector_cases += 1

    scx_cases = 0
    for ff97 in range(0x100):
        for dc00 in range(0x100):
            result = primary_publisher_model(
                ff97=ff97, dc00=dc00, dc02=0xAC,
                dc0b=0, incoming_scx=0x5E,
            )
            expected_scx = 0x5E if ff97 == 2 else dc00 & 0x0F
            require(result["scx"] == expected_scx,
                    "FF97/DC00 SCX model drifted")
            expected_writes = 2 if ff97 == 2 else 3
            require(len(result["writes"]) == expected_writes,
                    "SCX write gate changed")
            scx_cases += 1

    scy_cases = 0
    for dc02 in range(0x100):
        for dc0b in (0x00, 0x01, 0x80, 0xFF):
            result = primary_publisher_model(
                ff97=2, dc00=0x00, dc02=dc02,
                dc0b=dc0b, incoming_scx=0x0C,
            )
            require(result["scy"] == dc02 & 0x0F,
                    "DC02 SCY model drifted")
            require(result["writes"][0] == (
                "FF42", dc02 & 0x0F, False
            ), "SCY is not first on the SCX-suppressed path")
            scy_cases += 1

    timing = {
        "FF97_02_DC0B_00_t": 144,
        "FF97_02_DC0B_nonzero_t": 148,
        "FF97_other_DC0B_00_t": 176,
        "FF97_other_DC0B_nonzero_t": 180,
        "delta_from_r319_t": {
            "DC0B_00": 8,
            "DC0B_nonzero": 4,
        },
    }
    for ff97, dc0b, key in (
        (2, 0, "FF97_02_DC0B_00_t"),
        (2, 1, "FF97_02_DC0B_nonzero_t"),
        (0, 0, "FF97_other_DC0B_00_t"),
        (0, 1, "FF97_other_DC0B_nonzero_t"),
    ):
        result = primary_publisher_model(
            ff97=ff97, dc00=0, dc02=0, dc0b=dc0b,
            incoming_scx=0,
        )
        require(result["t_cycles"] == timing[key],
                "publisher timing model drifted")

    return {
        "selector_cases_exhausted": selector_cases,
        "selector_counts": selector_counts,
        "FF97_DC00_cases_exhausted": scx_cases,
        "DC02_selector_controls_exhausted": scy_cases,
        "all_writes_interrupt_closed": True,
        "LCDC_is_final_write": True,
        "timing": timing,
    }


def source_preimages(source: bytes) -> dict[str, Any]:
    require(len(source) == r319.r318.r317.r305.r304.ROM_SIZE,
            "r320 base is not exactly 512 KiB")
    require(BASE_SHA256 == r319.EXPECTED_CANDIDATE_SHA256,
            "pinned r319 module identity changed")
    require(digest(source) == BASE_SHA256,
            f"wrong exact r319 base: {digest(source)}")

    require(source[PRIMARY_ADDR:PRIMARY_END] == OLD_PRIMARY,
            "fixed $12E0-$1302 publisher preimage changed")
    require(
        source[
            PUBLISHER_ENTRY_ADDR:
            PUBLISHER_ENTRY_ADDR + len(PUBLISHER_ENTRY_PREFIX)
        ] == PUBLISHER_ENTRY_PREFIX,
        "fixed $12A0 publisher entry changed",
    )
    require(source[PUBLISHER_CALL_ADDR:
                   PUBLISHER_CALL_ADDR + len(PUBLISHER_CALL)]
            == PUBLISHER_CALL,
            "fixed $01ED publisher CALL changed")
    caller_census = fixed_target_census(source, PUBLISHER_ENTRY_ADDR)
    require(caller_census == [(PUBLISHER_CALL_ADDR, 0xCD)],
            "fixed $12A0 CALL/JP target census changed")
    require(
        source[
            PUBLISHER_RETURN_ADDR:
            PUBLISHER_RETURN_ADDR + len(PUBLISHER_RETURN_CONTINUATION)
        ] == PUBLISHER_RETURN_CONTINUATION,
        "fixed $01F0 publisher return continuation changed",
    )
    continuation = bank_offset(
        SCENE0B_BANK, SCENE0B_CONTINUATION_ADDR
    )
    require(source[continuation] == SCENE0B_CONTINUATION_OLD,
            "r314 private continuation preimage changed")
    flip = bank_offset(SCENE0B_BANK, SCENE0B_FLIP_ADDR)
    require(source[flip:flip + 2] == SCENE0B_FLIP_OLD,
            "r314 private LCDC preimage changed")
    success = bank_offset(SCENE0B_BANK, SCENE0B_SUCCESS_START_ADDR)
    require(
        source[success:success + len(SCENE0B_SUCCESS_OLD)]
        == SCENE0B_SUCCESS_OLD,
        "r314 complete Scene0B success stream changed",
    )
    ack = bank_offset(SCENE0B_BANK, SCENE0B_ACK_ADDR)
    require(source[ack:ack + len(SCENE0B_ACK)] == SCENE0B_ACK,
            "r314 DADE acknowledgment preimage changed")
    tail = bank_offset(SCENE0B_BANK, SCENE0B_TAIL_ADDR)
    require(source[tail:tail + len(SCENE0B_TAIL)] == SCENE0B_TAIL,
            "r314 mapper tail preimage changed")
    abort = bank_offset(SCENE0B_BANK, SCENE0B_ABORT_ADDR)
    require(
        source[abort:abort + len(SCENE0B_ABORT_CONTINUATION)]
        == SCENE0B_ABORT_CONTINUATION,
        "r314 abort $12E0 continuation changed",
    )
    require(source[MAPPER_ENTRY_ADDR:
                   MAPPER_ENTRY_ADDR + len(MAPPER_ENTRY)] == MAPPER_ENTRY,
            "fixed mapper entry preimage changed")
    require(source[MAPPER_BODY_ADDR:
                   MAPPER_BODY_ADDR + len(MAPPER_BODY)] == MAPPER_BODY,
            "fixed mapper body preimage changed")
    require(sequence_census(source, LCDC_SELECTOR_ZERO_BRANCH)
            == list(BASE_SELECTOR_OFFSETS),
            "r319 whole-ROM LCDC selector census changed")
    require(unsafe_selector_census(source)
            == list(UNSAFE_SELECTOR_OFFSETS),
            "r319 unsafe LCDC-first selector census changed")
    require(sequence_census(source, NO_SCROLL_SELECTOR)
            == list(NO_SCROLL_SELECTOR_OFFSETS),
            "r319 no-scroll selector census changed")
    require(source[r319.r318.r317.r316.CGB_FLAG_OFFSET]
            == r319.r318.r317.r316.CGB_ONLY_FLAG,
            "r319 CGB-only header changed")
    checksummed = bytearray(source)
    r319.r318.r317.r305.r304.update_checksums(checksummed)
    require(bytes(checksummed) == source,
            "r319 source checksums are not canonical")

    return {
        "candidate_sha256": BASE_SHA256,
        "primary_preimage": OLD_PRIMARY.hex(" ").upper(),
        "scene0B_continuation": "bank31:$6E11 $EE ($12EE)",
        "scene0B_private_flip": "bank31:$6E23 E0 40",
        "scene0B_ack": "bank31:$6E25 3E C4 EA DE DA",
        "scene0B_abort_continuation": "$12E0 exact",
        "publisher_entry": "fixed:$12A0 exact",
        "publisher_target_census": ["fixed:$01ED CALL $12A0"],
        "publisher_return": "fixed:$01F0 exact",
        "publisher_return_AF": (
            "FFCC load, INC, and AND $01 overwrite A/F before use"
        ),
        "mapper": "fixed:$0061->$09BE RET exact",
        "unsafe_selector_census": ["file:$0012E0", "file:$07EE17"],
        "r319_effective_row_context": "exact",
        "cgb_only_header": "exact",
    }


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    require(len(candidate) == len(source), "r320 changed ROM size")
    require(candidate[PRIMARY_ADDR:PRIMARY_END] == NEW_PRIMARY,
            "r320 primary atomic publisher changed")
    primary_static_contract(candidate[PRIMARY_ADDR:PRIMARY_END])
    require(
        candidate[
            PUBLISHER_ENTRY_ADDR:
            PUBLISHER_ENTRY_ADDR + len(PUBLISHER_ENTRY_PREFIX)
        ] == PUBLISHER_ENTRY_PREFIX,
        "r320 changed fixed $12A0 publisher entry",
    )
    require(fixed_target_census(candidate, PUBLISHER_ENTRY_ADDR)
            == [(PUBLISHER_CALL_ADDR, 0xCD)],
            "r320 changed fixed $12A0 caller census")
    require(candidate[PUBLISHER_CALL_ADDR:
                      PUBLISHER_CALL_ADDR + len(PUBLISHER_CALL)]
            == PUBLISHER_CALL,
            "r320 changed fixed publisher CALL")
    require(candidate[PUBLISHER_RETURN_ADDR:
                      PUBLISHER_RETURN_ADDR
                      + len(PUBLISHER_RETURN_CONTINUATION)]
            == PUBLISHER_RETURN_CONTINUATION,
            "r320 changed fixed publisher return continuation")

    continuation = bank_offset(
        SCENE0B_BANK, SCENE0B_CONTINUATION_ADDR
    )
    require(candidate[continuation] == SCENE0B_CONTINUATION_NEW,
            "r320 Scene0B continuation is not $12E0")
    flip = bank_offset(SCENE0B_BANK, SCENE0B_FLIP_ADDR)
    require(candidate[flip:flip + 2] == SCENE0B_FLIP_NEW,
            "r320 Scene0B private flip is not DI/NOP")
    ack = bank_offset(SCENE0B_BANK, SCENE0B_ACK_ADDR)
    require(candidate[ack:ack + len(SCENE0B_ACK)] == SCENE0B_ACK,
            "r320 changed the Scene0B DADE acknowledgment")
    tail = bank_offset(SCENE0B_BANK, SCENE0B_TAIL_ADDR)
    require(candidate[tail:tail + len(SCENE0B_TAIL)] == SCENE0B_TAIL,
            "r320 changed the Scene0B mapper tail")
    abort = bank_offset(SCENE0B_BANK, SCENE0B_ABORT_ADDR)
    require(
        candidate[abort:abort + len(SCENE0B_ABORT_CONTINUATION)]
        == SCENE0B_ABORT_CONTINUATION,
        "r320 changed the Scene0B abort continuation",
    )
    scene0b_static_contract(candidate)
    selector_clone_contract(source, candidate)

    changed = {
        offset
        for offset, (before, after) in enumerate(
            zip(source, candidate, strict=True)
        )
        if before != after
    }
    functional = changed - CHECKSUM_OFFSETS
    require(functional == owned_ranges(),
            "r320 functional delta escaped exact publisher ownership")
    require(changed <= owned_ranges() | CHECKSUM_OFFSETS,
            "r320 changed bytes outside publishers/checksums")
    require(candidate[r319.r318.r317.r316.CGB_FLAG_OFFSET]
            == r319.r318.r317.r316.CGB_ONLY_FLAG,
            "r320 lost the CGB-only header")
    checksummed = bytearray(candidate)
    r319.r318.r317.r305.r304.update_checksums(checksummed)
    require(bytes(checksummed) == candidate,
            "r320 candidate checksums are not canonical")
    return {
        "functional_changed_bytes_from_r319": len(functional),
        "primary_changed_bytes": len(primary_changed_offsets()),
        "scene0B_changed_bytes": len(scene0b_changed_offsets()),
        "changed_file_offsets_from_r319": [
            f"0x{offset:06X}" for offset in sorted(functional)
        ],
        "checksum_changed_offsets": [
            f"0x{offset:04X}"
            for offset in sorted(changed & CHECKSUM_OFFSETS)
        ],
        "escaped_bytes": 0,
        "rom_size_delta_bytes": 0,
        "primary_exact_width": True,
        "scene0B_in_place": True,
        "r319_effective_row_context_exact": True,
        "cgb_only_header_retained": True,
    }


def mutation_contract(source: bytes, candidate: bytes) -> dict[str, Any]:
    """Prove every owned target byte and both boundaries fail closed."""
    rejected = 0
    for offset in sorted(owned_ranges()):
        mutant = bytearray(candidate)
        mutant[offset] ^= 0x01
        try:
            validate_candidate(source, bytes(mutant))
        except AssertionError:
            rejected += 1
        else:
            raise AssertionError(
                f"owned-byte mutation survived at file offset {offset:#x}"
            )
    boundary_offsets = {
        PRIMARY_ADDR - 1,
        PRIMARY_END,
        bank_offset(SCENE0B_BANK, SCENE0B_CONTINUATION_ADDR) - 1,
        bank_offset(SCENE0B_BANK, SCENE0B_CONTINUATION_ADDR) + 1,
        bank_offset(SCENE0B_BANK, SCENE0B_FLIP_ADDR) - 1,
        bank_offset(SCENE0B_BANK, SCENE0B_FLIP_ADDR) + 2,
    }
    boundary_rejected = 0
    for offset in sorted(boundary_offsets):
        mutant = bytearray(candidate)
        mutant[offset] ^= 0x01
        try:
            validate_candidate(source, bytes(mutant))
        except AssertionError:
            boundary_rejected += 1
        else:
            raise AssertionError(
                f"boundary mutation survived at file offset {offset:#x}"
            )
    return {
        "owned_byte_mutations": len(owned_ranges()),
        "owned_byte_mutations_rejected": rejected,
        "boundary_mutations": len(boundary_offsets),
        "boundary_mutations_rejected": boundary_rejected,
    }


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    preimages = source_preimages(source)
    static = primary_static_contract()
    exhaustive = exhaustive_contract()

    rom = bytearray(source)
    rom[PRIMARY_ADDR:PRIMARY_END] = NEW_PRIMARY
    continuation = bank_offset(
        SCENE0B_BANK, SCENE0B_CONTINUATION_ADDR
    )
    rom[continuation] = SCENE0B_CONTINUATION_NEW
    flip = bank_offset(SCENE0B_BANK, SCENE0B_FLIP_ADDR)
    rom[flip:flip + 2] = SCENE0B_FLIP_NEW
    r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    scene0b = scene0b_static_contract(candidate)
    selector_clones = selector_clone_contract(source, candidate)
    mutations = mutation_contract(source, candidate)
    sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        require(sha == EXPECTED_CANDIDATE_SHA256,
                f"r320 candidate identity drift: {sha}")

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-atomic-presentation-commit-r320-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "base": preimages,
        "root_cause": (
            "fixed:$12E0 published LCDC before SCY; scroll and physical-map "
            "selection must commit within one interrupt-closed transaction"
        ),
        "patch": {
            "primary": {
                "range": "$12E0-$1302",
                "old": OLD_PRIMARY.hex(" ").upper(),
                "new": NEW_PRIMARY.hex(" ").upper(),
                "change": "exact-width scroll-first interrupt-closed commit",
            },
            "scene0B": {
                "continuation": "bank31:$6E11 EE->E0 ($12EE->$12E0)",
                "private_flip": "bank31:$6E23 E0 40->F3 00 (DI/NOP)",
                "ack": "bank31:$6E25 unchanged under DI",
                "abort": "existing $12E0 continuation unchanged",
            },
        },
        "offline_contract": {
            "primary_static": static,
            "scene0B_static": scene0b,
            "selector_clone_census": selector_clones,
            "exhaustive": exhaustive,
            "mutation": mutations,
            "ABI": {
                "BC_DE_HL_SP": "preserved",
                "AF": (
                    "caller-clobbered; sole fixed:$01ED CALL $12A0 returns "
                    "to $01F0, whose FFCC load/INC/AND overwrite A/F before "
                    "the first conditional consumer"
                ),
                "publisher_target_census": ["fixed:$01ED CALL $12A0"],
                "entry_IME": (
                    "primary $4295 completion restores IME before $12E0"
                ),
                "exit_IME": "enabled after EI/RET",
                "post_publish_PC": "$01F0",
            },
        },
        "ownership": ownership,
        "required_live_gates": [
            "north every-frame route has zero viewport tile differences",
            "north attributes use FFE5 physical-page ownership and are exact",
            "scene0B menu repair commit remains exact without a half-state",
            "reported hazards/menu/wall-edge visual contract is clean",
            "Stage1 release speed remains at least 95%",
            "cold CHR writer remains canonical",
            "Analogue Pocket visual round-trip before promotion",
        ],
        "decision": "CONSTRUCTION_ONLY_LIVE_GATES_REQUIRED",
    }
    return candidate, receipt


def validate_preimages(source: bytes, base_receipt_bytes: bytes) -> dict[str, Any]:
    contract = source_preimages(source)
    require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
            "r319 base receipt identity changed")
    receipt = json.loads(base_receipt_bytes)
    require(receipt.get("schema") == BASE_SCHEMA,
            "r319 base receipt schema changed")
    require(receipt.get("candidate_sha256") == BASE_SHA256,
            "r319 base receipt names another ROM")
    require(receipt.get("emulator_invoked") is False,
            "r319 base build receipt unexpectedly invoked an emulator")
    return {**contract, "build_receipt_sha256": BASE_RECEIPT_SHA256, "schema": BASE_SCHEMA}


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    preimages = validate_preimages(source, base_receipt_bytes)
    candidate, receipt = construct(source)
    receipt.update({
        "schema": "penta-stage1-atomic-presentation-commit-r320-build-v1",
        "status": "STATIC_PASS_R320_LIVE_GATES_REQUIRED",
        "base": preimages,
        "root_cause": (
            "fixed:$12E0 published LCDC before SCY; the r318 north route "
            "exposed that pre-existing service/frame-boundary race as "
            "LCDC=$83 with stale SCY=$00 for one 101-cell-corrupt room01 "
            "frame at camera $042C"
        ),
        "evidence": {
            "candidate": BASE_SHA256,
            "bad_frame": "g1040 room01 camera042C LCDC83 SCX0C SCY00",
            "previous": "g1038/g1039 LCDC8B SCX0C SCY00 exact",
            "recovered": "g1041 LCDC83 SCX0C SCY0C exact",
            "r317_control": (
                "same route g1038 service; first LCDC83 frame g1039 already "
                "SCY0C; g1040 remains exact"
            ),
            "r318_repeat": (
                "candidate replay repeats service g1039, torn g1040, and "
                "repaired g1041 exactly"
            ),
            "stock": "equivalent g820 commits LCDC83 and SCY0C together",
            "raw_bad_vs_r317_coherent_differences": {"tiles": 234, "attributes": 43},
            "reviewed_terrain_tile_differences": 101,
        },
        "decision": "STATIC_ATOMIC_PRESENTATION_FIX_LIVE_GATES_REQUIRED",
    })
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r319.r318.r317.r305.r304.checked_output(
        args.output, "candidate output"
    )
    receipt_path = r319.r318.r317.r305.r304.checked_output(
        args.receipt, "receipt output"
    )
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_bytes(
        r319.r318.r317.r305.r304.receipt_bytes(receipt)
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
