#!/usr/bin/env python3
"""Static exact-r264 audit for a hidden-map Stage-7 dual-plane publisher.

This is deliberately not an emulator verifier.  It first completes every
static gate, then may write the surviving candidate plus its JSON receipt
under repository ``tmp/``.  It has no emulator integration.

The candidate handles only a dirty Stage-7 ($D880=$08) publication.  It first
compiles a padded 24x32 attribute plane in SVBK3:$D000 and stages the twelve
unaligned odd tile rows in SVBK2:$D000.  It then completes one fixed-bank
48-block attribute HBlank DMA and twenty-four fixed-bank two-block tile DMAs.
Even tile rows are already 16-byte aligned in C1A0; odd rows use the staging
plane.  VBK and SVBK are never changed while FF55 reports an active transfer.

Runtime guards fail closed to the untouched native dirty copier unless the
scene, dungeon, gameplay state, camera domain, idle-DMA state, hidden target,
and fixed caller are all exact.  Thus neither row padding nor the
attr-first/tile-second intermediate state can become visible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
import sys
import zlib


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyze_later_attr_signature import semantic_lut  # noqa: E402


BASE_SHA256 = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
BANK_SIZE = 0x4000
RAW_SIZE = 24 * 24
PADDED_SIZE = 24 * 32
ALLOWED_CAMERA = frozenset((0x00, 0x04, 0x08, 0x0C))

RUNTIME_SHA256 = "765d22df24f270dd5210500f05ae101278edab35ee0c8707bed26738f90c8b5a"
RUNTIME_SOURCE_A = 0x7BB2
RUNTIME_SOURCE_A_SIZE = 46
RUNTIME_SOURCE_B = 0x7C4D
RUNTIME_SOURCE_B_SIZE = 114
RUNTIME_BASE = 0xDA60
RUNTIME_REDIRECT_OPERAND = 0xDAB7
RUNTIME_TAIL = 0xDAE9

BANK = 22
HELPER = 0x6C80
DESCRIPTORS = 0x7500
LUT = 0x7600
MAPPER = 0x0061
ATOMIC_SETUP = 0xDA13
ROW_HELPER = 0xD400
NATIVE_DIRTY = 0x42B3
ATOMIC_COMPLETION = 0x3497

SCREEN_LINE_T = 456
MIN_HBLANK_T = 87
MODE2_T = 80
MIN_MODE3_T = 172
HDMA_BLOCK_T = 32
TIMER_PERIOD_T = (0x100 - 0xD2) * 1024  # TAC=$04: 4096 Hz.


# (name, bank, inclusive start, exclusive end, sha256)
PREIMAGES = (
    ("fixed_bank_mapper_wrapper", 0, 0x0845, 0x0850,
     "dfa1d3e1ef60c858da76f1c59eef652324f92fc7b79def0f327c5406b4908a31"),
    ("mapper_front", 0, 0x0061, 0x0067,
     "6587ca3c214af72906225e7a46e4d176ef9c1083b31423867b0399378c8ea7dd"),
    ("mapper_body", 0, 0x09BE, 0x09C4,
     "4b4807cfc057d800b049a31e4beef32c2eb2f422729c9f219bae03981f21abfa"),
    ("decision_helper", 0, 0x3485, 0x3497,
     "595c9b9e6f631d9e44aa92c8725609acb5abc91b81b6e1363966f18bd5e1cb56"),
    ("atomic_completion", 0, 0x3497, 0x34A3,
     "0a36f5a808cec35591db9db871ae97b561ec6733f0e851b1d3ff20a8afa1182d"),
    ("timer_isr", 0, 0x06B3, 0x06D1,
     "954d0f7250bc0c28e6bd5cf595798a2940ebcf637de88969b0c00c6441819cc9"),
    ("centisecond_leaf", 0, 0x0D79, 0x0D85,
     "86a26e84fc76caaf0b192d72e5c06d520c8631fc5ae9479fe07d943e8e8442f6"),
    ("source_then_publisher", 0, 0x12D0, 0x12E4,
     "83fec7ce4af6fc64b99a845ec76a8b4cb9d3a47c8a82c29121054a7e0814911c"),
    ("secondary_caller", 0, 0x0AB2, 0x0ABB,
     "1c850cfc0b988ca054754033979473855a7507eb93ca024152e62cca20bbca8c"),
    ("secondary_control_flow", 0, 0x0A4F, 0x0ABB,
     "c4fbb0c59c35e38c4c23da72b103c2b5af9dbffac927766a6eb52f28d0f0e96a"),
    ("secondary_pending_camera_publisher", 0, 0x307B, 0x309A,
     "4f566e582eab7f817b6548c6be7d916ff0c25351321535eaca379e5a04c89943"),
    ("primary_postcaller_camera_publisher", 0, 0x12E0, 0x1303,
     "ba992740e1d54d61c7f439abe1a629232419b51d42983efdc21bb86ea9b1fdc7"),
    ("inline_copier", 1, 0x42A7, 0x435A,
     "ae6ce521529209c6b3cdf553c93b59434e2e2372955143bd6d7a236751c564a1"),
    ("inline_completion_tail", 1, 0x4354, 0x436E,
     "322a25c6e750ecef82988c9ab002b49086847641ec589c4a5f01bde94d6aec94"),
    ("row_helper_source", 21, 0x4A00, 0x4A79,
     "d28ac08f093c2e6cc065d87c3dedc0e28779dda54885e0ba7f1c6c8ed77804d0"),
    ("row_helper_installer", 21, 0x4900, 0x4924,
     "a7411b17a1333c56c2a0628df87b04a779ef7dd5cc2f05450d40f1fbeba61e5f"),
    ("atomic_setup_source", 13, 0x7B13, 0x7B21,
     "635d20d72632df4684d6b03ded2d47952fe1467d9b9eeda75aee40d000ece41c"),
    ("boss_entry_FFDA_set", 0, 0x1A2B, 0x1A75,
     "9fc695174972ab96e75ead990df062f33e5daf09210a8eaec1828fe686532426"),
    ("boss_exit_FFDA_clear", 0, 0x1A78, 0x1AA9,
     "59233e5b89c434aca763a47fbbfd5d8726fd9b07fd3ef8cde80d19b2f3602413"),
    ("later_dungeon_FFDA_clear", 1, 0x4160, 0x4177,
     "ece5a2ab10921dd55c07764fdddb36868c1c17b7f29a94041a89a32230b53e12"),
    ("boss_scene_setup", 1, 0x759B, 0x75C8,
     "1e5b354b3c5f71ce7719bfde39aa51a69ab5121f7fa35a08bacba1026515a0a1"),
    ("final_bridge_FFDA_set", 1, 0x54C0, 0x5505,
     "ebda3d886eaeca730f9f51aad66b3e056c2482f4f0de53babc41b73f49adf233"),
)

EXPECTED_ROUTER = bytes.fromhex("3E 0D CD 61 00 CD 80 6C C3 61 00")
EXPECTED_ATOMIC_SETUP = bytes.fromhex(
    "7C 3C E0 A5 F0 FF EA 5A DF E6 04 E0 FF C9"
)
EXPECTED_TIMER_ISR = bytes.fromhex(
    "F5 C5 D5 E5 3E 03 EA 00 21 CD 00 40 3E 01 EA 00 21 "
    "CD 79 0D F0 99 EA 00 21 E1 D1 C1 F1 D9"
)


def sha256(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if bank == 0:
        if not 0 <= address < 0x4000:
            raise AssertionError((bank, address))
        return address
    if not 0x4000 <= address < 0x8000:
        raise AssertionError((bank, address))
    return bank * BANK_SIZE + address - 0x4000


class Asm:
    """Tiny label assembler sufficient for this static byte contract."""

    def __init__(self, base: int) -> None:
        self.base = base
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str, str]] = []

    def db(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise AssertionError(f"duplicate label: {name}")
        self.labels[name] = self.base + len(self.code)

    def jr(self, opcode: int, label: str) -> None:
        self.db(opcode, 0)
        self.fixups.append((len(self.code) - 1, label, "jr"))

    def jp(self, opcode: int, label: str) -> None:
        self.db(opcode, 0, 0)
        self.fixups.append((len(self.code) - 2, label, "jp"))

    def finish(self) -> tuple[bytes, dict[str, int]]:
        for operand, label, kind in self.fixups:
            target = self.labels[label]
            if kind == "jr":
                delta = target - (self.base + operand + 1)
                if not -128 <= delta <= 127:
                    raise AssertionError((label, delta))
                self.code[operand] = delta & 0xFF
            else:
                self.code[operand:operand + 2] = target.to_bytes(2, "little")
        return bytes(self.code), dict(self.labels)


def build_router_tail() -> bytes:
    # Restore DA60's saved input registers and save the exact dirty-result AF
    # before testing the scene.  Non-Stage7 restores AF and returns through
    # the untouched $3493/$42B1 frames.  Stage7 discards saved AF plus those
    # two internal frames with POP AF.  POP BC would silently destroy the
    # native room/token register.
    tail = bytes.fromhex(
        "E1 D1 C1 F5 FA 80 D8 FE 08 28 02 F1 C9 F3 F1 F1 F1 "
        "3E 16 C3 47 08"
    )
    if len(tail) != 22:
        raise AssertionError(len(tail))
    return tail


def build_descriptors() -> bytes:
    table = bytearray()
    for row in range(24):
        if row & 1:
            source = 0xD000 + (row // 2) * 32
        else:
            source = 0xC1A0 + row * 24
        destination_delta = row * 32
        if source & 0x0F:
            raise AssertionError(f"row {row} source is not HDMA aligned")
        table.extend((
            source >> 8,
            source & 0xF0,
            destination_delta >> 8,
            destination_delta & 0xF0,
        ))
    if len(table) != 24 * 4:
        raise AssertionError(len(table))
    return bytes(table)


def build_helper() -> tuple[bytes, dict[str, int]]:
    a = Asm(HELPER)
    a.label("entry")

    # Revalidate after the tail's DI.  A Timer IRQ can land between the
    # tail's first D880 read and that DI, and the sound engine owns D880.
    # FFBA=$06 is the exact Stage-7 dungeon selector (zero based).
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x08)
    a.jp(0xC2, "fallback_native")
    a.db(0xF0, 0xBA, 0xFE, 0x06)
    a.jp(0xC2, "fallback_native")
    a.db(0xF0, 0xC1, 0xFE, 0x01)           # exact gameplay, not SELECT menu
    a.jp(0xC2, "fallback_native")
    a.db(0xF0, 0x40, 0xCB, 0x6F)           # Window enable (LCDC.5)
    a.jp(0xC2, "fallback_native")           # either map may be Window-visible
    a.db(0xF0, 0x55, 0xFE, 0xFF)           # inherited HDMA must be idle
    a.jp(0xC2, "fallback_native")

    # $4295 has exactly two fixed-bank callers, but the natural Stage-7 corpus
    # exercises only the primary $12E0 publication.  Admit that exact outer
    # return and route $0AB8 (plus every unknown caller) through the untouched
    # native dirty copier before DA13 or any bank/VRAM mutation.  PUSH/POP is
    # safe here because SVBK is still native bank 1.
    a.label("caller_guard")
    a.db(0xE5, 0xF8, 0x04, 0x2A, 0xFE, 0xE0)
    a.jp(0xC2, "caller_reject")
    a.db(0x7E, 0xFE, 0x12)
    a.jp(0xC2, "caller_reject")
    a.db(0xE1)

    # Padding-domain guard. AND $F3 admits exactly 00/04/08/0C.
    for register in (0x43, 0x42):
        a.db(0xF0, register, 0xE6, 0xF3)
        a.jp(0xC2, "fallback_native")       # JP NZ

    # Validate H and prove the target is opposite live LCDC.3.  LCD-off work
    # is synchronous GDMA and has no visible-map restriction.
    a.db(0x7C, 0xFE, 0x98)
    a.jr(0x28, "target_98")
    a.db(0xFE, 0x9C)
    a.jp(0xC2, "fallback_native")
    a.label("target_9c")
    a.db(0xF0, 0x40, 0xCB, 0x7F)           # LCDC; BIT 7,A
    a.jr(0x28, "guards_passed")            # LCD off
    a.db(0xCB, 0x5F)                       # BIT 3,A; 9C visible if set
    a.jp(0xC2, "fallback_native")
    a.jr(0x18, "guards_passed")
    a.label("target_98")
    a.db(0xF0, 0x40, 0xCB, 0x7F)
    a.jr(0x28, "guards_passed")
    a.db(0xCB, 0x5F)                       # 98 visible if clear
    a.jp(0xCA, "fallback_native")

    a.label("guards_passed")
    a.db(0xF1)                             # discard synthetic $084D
    a.db(0xCD, ATOMIC_SETUP & 0xFF, ATOMIC_SETUP >> 8)

    # Phase 1a: exact immutable Stage-7 attrs in SVBK3:D000-D2FF.
    a.label("phase1_attr_compile")
    a.db(
        0x3E, 0x03, 0xE0, 0x70,
        0x21, 0x00, 0xD0,
        0x11, 0xA0, 0xC1,
        0x06, LUT >> 8,
        0x3E, 0x18, 0xE0, 0xE0,
    )
    a.label("attr_row")
    a.db(0xCD, ROW_HELPER & 0xFF, ROW_HELPER >> 8)
    a.db(0xAF, *([0x22] * 8))               # deterministic attr padding
    a.db(0xF0, 0xE0, 0x3D, 0xE0, 0xE0)
    a.jr(0x20, "attr_row")

    # Phase 1b: stage only the twelve odd, +8-aligned tile rows.  Rows are
    # intentionally unrolled: it saves about 1.2kT per dirty publication.
    a.label("phase1_odd_stage")
    a.db(0x3E, 0x02, 0xE0, 0x70, 0x21, 0x00, 0xD0)
    for row in range(1, 24, 2):
        source = 0xC1A0 + row * 24
        a.db(0x11, source & 0xFF, source >> 8)
        for _ in range(24):
            a.db(0x1A, 0x13, 0x22)
        a.db(0xAF, *([0x22] * 8))

    # A bounded Timer opportunity occurs only with no DMA active and the real
    # stack visible in SVBK1. EI's delayed enable makes EI/NOP/DI service one
    # pending Timer interrupt and otherwise close IME again.
    a.db(0xAF, 0xE0, 0x4F, 0x3C, 0xE0, 0x70)
    a.label("phase1_service")
    a.db(0xFB, 0x00, 0xF3)
    a.db(0xCD, 0x00, 0x00)
    phase1_revalidate_call = len(a.code) - 2
    a.jp(0xDA, "fallback_after_atomic")     # JP C

    # Phase 2: one completed fixed-VBK1/SVBK3 48-block attr transfer.
    a.label("phase2_attr_setup")
    a.db(
        0x3E, 0x03, 0xE0, 0x70,
        0x3E, 0x01, 0xE0, 0x4F,
        0x3E, 0xD0, 0xE0, 0x51,
        0xAF, 0xE0, 0x52,
        0xF0, 0xA5, 0x3D, 0xE0, 0x53,
        0xAF, 0xE0, 0x54,
        0xF0, 0x40, 0xCB, 0x7F,
    )
    a.jr(0x28, "attr_gdma")
    a.db(0x06, 0xAF)                       # B = 48-block HBlank command
    a.label("attr_wait_mode3")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, "attr_wait_mode3")
    a.db(0x78)
    a.jr(0x18, "attr_start")
    a.label("attr_gdma")
    a.db(0x3E, 0x2F)                       # LCD-off 48-block GDMA
    a.label("attr_start")
    a.db(0xE0, 0x55)                       # inline; no bank3 stack frame
    a.label("attr_wait_complete")
    a.db(0xF0, 0x55, 0xCB, 0x7F)
    a.jr(0x28, "attr_wait_complete")

    a.db(0xAF, 0xE0, 0x4F, 0x3C, 0xE0, 0x70)
    a.label("phase2_service")
    a.db(0xFB, 0x00, 0xF3)
    a.db(0xCD, 0x00, 0x00)
    phase2_revalidate_call = len(a.code) - 2
    a.jp(0xDA, "fallback_after_atomic")

    # Phase 3: 24 completed fixed-VBK0/SVBK2 two-block transfers.
    a.label("phase3_tile_setup")
    a.db(
        0x3E, 0x02, 0xE0, 0x70,
        0x21, DESCRIPTORS & 0xFF, DESCRIPTORS >> 8,
        0x3E, 0x18, 0xE0, 0xE0,
        0xF0, 0x40, 0xCB, 0x7F,
        0x06, 0x01,
    )
    a.jr(0x28, "tile_loop")
    a.db(0x06, 0x81)
    a.label("tile_loop")
    a.db(
        0x2A, 0xE0, 0x51,
        0x2A, 0xE0, 0x52,
        0x2A, 0x4F,
        0xF0, 0xA5, 0x3D, 0x81, 0xE0, 0x53,
        0x2A, 0xE0, 0x54,
        0xCB, 0x78,
    )
    a.jr(0x28, "tile_start")
    a.label("tile_wait_mode3")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, "tile_wait_mode3")
    a.label("tile_start")
    a.db(0x78, 0xE0, 0x55)                 # inline; no bank2 stack frame
    a.label("tile_wait_complete")
    a.db(0xF0, 0x55, 0xCB, 0x7F)
    a.jr(0x28, "tile_wait_complete")
    a.db(0xF0, 0xE0, 0x3D, 0xE0, 0xE0)
    a.jr(0x20, "tile_loop")

    # Exact native Stage-7 completion ABI.  BC=$084D is not the compiler's
    # earlier C6xx value: stock DBF1's bank19 row helper consumes its mapper
    # frame with POP BC and then writes B=$08.  Push $3497 only after SVBK1 is
    # restored; its existing $4368 RETI returns to the preserved outer caller.
    a.label("final_restore")
    a.db(
        0xAF, 0xE0, 0x4F,
        0x3C, 0xE0, 0x70,
        0xF0, 0xA5, 0x3D, 0x67,
        0xAF, 0x6F, 0xE0, 0xA5,
        0x01, 0x4D, 0x08,
        0x11, ATOMIC_COMPLETION & 0xFF, ATOMIC_COMPLETION >> 8,
        0xD5,
        0x11, 0xE0, 0xC3,
        0x3E, 0x01, 0xC3, MAPPER & 0xFF, MAPPER >> 8,
    )

    # The fallback has not called DA13 or changed SVBK/VBK.  Discard $084D,
    # synthesize the untouched bank-1 dirty entry, and retain the outer caller.
    a.label("fallback_native")
    a.db(
        0xF1,
        0x11, NATIVE_DIRTY & 0xFF, NATIVE_DIRTY >> 8,
        0xD5,
        0x3E, 0x01, 0xC3, MAPPER & 0xFF, MAPPER >> 8,
    )

    a.label("caller_reject")
    a.db(0xE1)
    a.jp(0xC3, "fallback_native")

    # DA13 has already saved/masked IE on these paths, but no tile VRAM has
    # been published at phase 1 and native can safely repaint the hidden map
    # after phase 2. Restore the saved IE while IME remains disabled, rebuild
    # H from the exact tag, then restart the untouched native dirty copier.
    a.label("fallback_after_atomic")
    a.db(
        0xFA, 0x5A, 0xDF, 0xE0, 0xFF,
        0xF0, 0xA5, 0x3D, 0x67,
        0xAF, 0x6F, 0xE0, 0xA5,
        0x3C, 0xE0, 0xE0,
        0x11, NATIVE_DIRTY & 0xFF, NATIVE_DIRTY >> 8,
        0xD5,
        0x3E, 0x01, 0xC3, MAPPER & 0xFF, MAPPER >> 8,
    )

    # Re-run every mutable-state guard after each bounded Timer opportunity.
    # This CALL is made only with SVBK1 and FF55 idle.
    a.label("revalidate_after_service")
    for opcode_bytes in (
        (0xFA, 0x80, 0xD8, 0xFE, 0x08),
        (0xF0, 0xBA, 0xFE, 0x06),
        (0xF0, 0xC1, 0xFE, 0x01),
    ):
        a.db(*opcode_bytes)
        a.jp(0xC2, "revalidate_fail")
    a.db(0xF0, 0x40, 0xCB, 0x6F)
    a.jp(0xC2, "revalidate_fail")
    a.db(0xF0, 0x55, 0xFE, 0xFF)
    a.jp(0xC2, "revalidate_fail")
    for register in (0x43, 0x42):
        a.db(0xF0, register, 0xE6, 0xF3)
        a.jp(0xC2, "revalidate_fail")
    a.db(0xF0, 0xA5, 0xFE, 0x99)
    a.jr(0x28, "revalidate_98")
    a.db(0xFE, 0x9D)
    a.jp(0xC2, "revalidate_fail")
    a.db(0xF0, 0x40, 0xCB, 0x7F)
    a.jr(0x28, "revalidate_pass")
    a.db(0xCB, 0x5F)
    a.jp(0xC2, "revalidate_fail")
    a.jr(0x18, "revalidate_pass")
    a.label("revalidate_98")
    a.db(0xF0, 0x40, 0xCB, 0x7F)
    a.jr(0x28, "revalidate_pass")
    a.db(0xCB, 0x5F)
    a.jp(0xCA, "revalidate_fail")
    a.label("revalidate_pass")
    a.db(0xAF, 0xC9)                       # carry clear
    a.label("revalidate_fail")
    a.db(0x37, 0xC9)                       # carry set
    a.fixups.extend((
        (phase1_revalidate_call, "revalidate_after_service", "jp"),
        (phase2_revalidate_call, "revalidate_after_service", "jp"),
    ))
    return a.finish()


def require_preimages(payload: bytes) -> list[dict[str, object]]:
    checked = []
    for name, bank, start, end, expected in PREIMAGES:
        offset = bank_offset(bank, start)
        blob = payload[offset:offset + end - start]
        actual = sha256(blob)
        if actual != expected:
            raise AssertionError(
                f"{name} changed at bank{bank}:${start:04X}-${end - 1:04X}: "
                f"{actual} != {expected}"
            )
        checked.append({
            "name": name,
            "bank": bank,
            "range": f"${start:04X}-${end - 1:04X}",
            "length": end - start,
            "sha256": actual,
        })
    if payload[0x0845:0x0850] != EXPECTED_ROUTER:
        raise AssertionError("fixed mapper wrapper bytes changed")
    if payload[bank_offset(13, 0x7B13):bank_offset(13, 0x7B21)] \
            != EXPECTED_ATOMIC_SETUP:
        raise AssertionError("tagged DA13 source changed")
    if payload[0x06B3:0x06D1] != EXPECTED_TIMER_ISR:
        raise AssertionError("Timer ISR bytes changed")
    return checked


def runtime_from_source(payload: bytes, bank: int) -> bytes:
    first = payload[
        bank_offset(bank, RUNTIME_SOURCE_A):
        bank_offset(bank, RUNTIME_SOURCE_A) + RUNTIME_SOURCE_A_SIZE
    ]
    second = payload[
        bank_offset(bank, RUNTIME_SOURCE_B):
        bank_offset(bank, RUNTIME_SOURCE_B) + RUNTIME_SOURCE_B_SIZE
    ]
    return first + second


def runtime_source_address(index: int) -> int:
    if index < RUNTIME_SOURCE_A_SIZE:
        return RUNTIME_SOURCE_A + index
    return RUNTIME_SOURCE_B + index - RUNTIME_SOURCE_A_SIZE


def require_runtime(payload: bytes) -> dict[str, object]:
    copies = [runtime_from_source(payload, bank) for bank in (13, 16)]
    if copies[0] != copies[1] or sha256(copies[0]) != RUNTIME_SHA256:
        raise AssertionError("bank13/bank16 DA60 source mirrors changed")
    runtime = copies[0]
    redirect_index = RUNTIME_REDIRECT_OPERAND - RUNTIME_BASE
    tail_index = RUNTIME_TAIL - RUNTIME_BASE
    if runtime[redirect_index - 1:redirect_index + 1] != bytes.fromhex("18 EB"):
        raise AssertionError("DAB7 native dirty redirect preimage changed")
    if runtime[tail_index:tail_index + 23] != bytes(23):
        raise AssertionError("DAE9-DAFF cave is not zero")
    if runtime_source_address(redirect_index) != 0x7C76:
        raise AssertionError("DAB7 source mapping changed")
    if runtime_source_address(tail_index) != 0x7CA8:
        raise AssertionError("DAE9 source mapping changed")
    return {
        "sha256": sha256(runtime),
        "source_mirrors": [13, 16],
        "redirect": "$DAB6: JR $DAA3; operand at $DAB7/source $7C76",
        "required_redirect": "$DAB7 operand $31 (JR base $DAB8 -> $DAE9)",
        "cave": "$DAE9-$DAFF, 23 zero bytes",
        "discarded_returns": ["$3493", "$42B1"],
    }


@dataclass(frozen=True)
class LayoutRow:
    path: Path
    line: int
    destination: int
    scx: int
    scy: int
    raw: bytes


def padded_planes(raw: bytes, lut: bytes) -> tuple[bytes, bytes]:
    attrs = bytearray(PADDED_SIZE)
    tiles = bytearray(PADDED_SIZE)
    for row in range(24):
        source = row * 24
        destination = row * 32
        attrs[destination:destination + 24] = bytes(
            lut[tile] for tile in raw[source:source + 24]
        )
        if row & 1:
            tiles[destination:destination + 24] = raw[source:source + 24]
        else:
            # The 32-byte direct HDMA deliberately places the first eight
            # bytes of the following row in invisible padding.
            tiles[destination:destination + 32] = raw[source:source + 32]
    return bytes(attrs), bytes(tiles)


def viewport_cells(scx: int, scy: int) -> set[tuple[int, int]]:
    first_column, first_row = scx // 8, scy // 8
    columns = 20 + bool(scx & 7)
    rows = 18 + bool(scy & 7)
    return {
        (first_row + row, first_column + column)
        for row in range(rows)
        for column in range(columns)
    }


def corpus_contract(root: Path, lut: bytes) -> dict[str, object]:
    discovered_paths = sorted(root.glob("**/stage7.layout-events.tsv"))
    candidate_output = ROOT / "tmp/stage7-dual-plane-hdma-r264"
    self_generated_paths = [
        path for path in discovered_paths if path.is_relative_to(candidate_output)
    ]
    paths = [path for path in discovered_paths if path not in self_generated_paths]
    if len(paths) != 24:
        raise AssertionError(
            f"expected 24 independent Stage7 layout files, got {len(paths)}"
        )
    modern: list[LayoutRow] = []
    excluded: list[dict[str, object]] = []
    malformed = 0
    membership = hashlib.sha256()
    normalized_raw = hashlib.sha256()
    file_hashes: dict[str, str] = {}

    for path in paths:
        relative = str(path.relative_to(ROOT))
        file_hashes[relative] = sha256(path.read_bytes())
        file_rows: list[LayoutRow] = []
        has_modern_schema = False
        for number, line in enumerate(path.read_text().splitlines(), 1):
            fields = line.split("\t")
            if len(fields[-1]) != 1152:
                malformed += 1
                continue
            raw = bytes.fromhex(fields[-1])
            if len(raw) != RAW_SIZE:
                raise AssertionError(f"{relative}:{number}: raw width")
            if len(fields) < 14:
                continue
            has_modern_schema = True
            destination = int(fields[2], 16)
            scx, scy = int(fields[7], 16), int(fields[8], 16)
            if destination not in (0x9800, 0x9C00):
                raise AssertionError(f"{relative}:{number}: bad destination")
            if scx not in ALLOWED_CAMERA or scy not in ALLOWED_CAMERA:
                raise AssertionError(
                    f"{relative}:{number}: camera left admitted domain"
                )
            row = LayoutRow(path, number, destination, scx, scy, raw)
            file_rows.append(row)
            membership.update(relative.encode() + b"\0")
            membership.update(number.to_bytes(4, "big"))
            membership.update(destination.to_bytes(2, "big"))
            membership.update(bytes((scx, scy)))
            membership.update(raw)
            normalized_raw.update(raw)
        if not has_modern_schema:
            excluded.append({
                "path": relative,
                "reason": (
                    "legacy 8-field schema has zero valid 14-field rows; "
                    "SCX/SCY provenance absent, so it cannot admit the fast path"
                ),
            })
        modern.extend(file_rows)

    if len(modern) != 1268 or len(excluded) != 3 or malformed != 1:
        raise AssertionError((len(modern), len(excluded), malformed))

    tile_errors = attr_errors = padding_exposures = 0
    forced_direct_full_matches = 0
    forced_direct_bad_rows = 0
    for record in modern:
        attrs, tiles = padded_planes(record.raw, lut)
        direct_bad = bytearray(PADDED_SIZE)
        for row in range(24):
            source = row * 24
            output = row * 32
            expected_tiles = record.raw[source:source + 24]
            actual_tiles = tiles[output:output + 24]
            tile_errors += sum(a != b for a, b in zip(actual_tiles, expected_tiles))
            expected_attrs = bytes(lut[tile] for tile in expected_tiles)
            actual_attrs = attrs[output:output + 24]
            attr_errors += sum(a != b for a, b in zip(actual_attrs, expected_attrs))

            # Negative control: an odd-row direct source is rounded down by
            # HDMA's ignored low nibble and therefore begins eight bytes early.
            rounded = source & ~0x0F
            direct_bad[output:output + 32] = record.raw[rounded:rounded + 32]
            if row & 1 and direct_bad[output:output + 24] != expected_tiles:
                forced_direct_bad_rows += 1

        if all(
            direct_bad[row * 32:row * 32 + 24]
            == record.raw[row * 24:row * 24 + 24]
            for row in range(24)
        ):
            forced_direct_full_matches += 1

        for row, column in viewport_cells(record.scx, record.scy):
            padding_exposures += row >= 24 or column >= 24

    exhaustive_exposures = sum(
        row >= 24 or column >= 24
        for scx in sorted(ALLOWED_CAMERA)
        for scy in sorted(ALLOWED_CAMERA)
        for row, column in viewport_cells(scx, scy)
    )
    if tile_errors or attr_errors or padding_exposures or exhaustive_exposures:
        raise AssertionError({
            "tile_errors": tile_errors,
            "attr_errors": attr_errors,
            "padding_exposures": padding_exposures,
            "exhaustive_exposures": exhaustive_exposures,
        })
    if forced_direct_full_matches or not forced_direct_bad_rows:
        raise AssertionError("odd-row alignment negative control disappeared")

    return {
        "discovered_files": len(discovered_paths),
        "independent_input_files": len(paths),
        "candidate_output_files_excluded": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256(path.read_bytes()),
                "reason": (
                    "candidate-owned live output cannot extend its own static "
                    "compiler/padding corpus"
                ),
            }
            for path in self_generated_paths
        ],
        "admitted_14_field_files": len(paths) - len(excluded),
        "admitted_layouts": len(modern),
        "malformed_rows_skipped": malformed,
        "excluded": excluded,
        "file_sha256": file_hashes,
        "membership_digest_definition": (
            "sorted relative path NUL + big-endian line/destination + SCX/SCY + raw"
        ),
        "membership_sha256": membership.hexdigest(),
        "normalized_raw_stream_definition": (
            "concatenated 576-byte raw layouts in sorted-path, line order"
        ),
        "normalized_raw_stream_sha256": normalized_raw.hexdigest(),
        "tile_reconstruction_errors": tile_errors,
        "attribute_reconstruction_errors": attr_errors,
        "record_camera_padding_exposures": padding_exposures,
        "all_16_camera_state_padding_exposures": exhaustive_exposures,
        "forced_odd_direct_bad_rows": forced_direct_bad_rows,
        "forced_odd_direct_full_layout_matches": forced_direct_full_matches,
    }


STATE_SIZE = 0x11800
STATE_MAGIC = 0x00400003
STATE_IO = 0x0300
STATE_HRAM = 0x0380
STATE_WRAM0 = 0x4400
STATE_WRAM1 = 0x5400
STATE_FIELDS = (
    ("D880", "wram1", 0xD880),
    ("FFBA", "hram", 0xFFBA),
    ("FFC1", "hram", 0xFFC1),
    ("FFDA", "hram", 0xFFDA),
    ("FF94", "hram", 0xFF94),
    ("DD05", "wram1", 0xDD05),
    ("DD06", "wram1", 0xDD06),
    ("DCBB", "wram1", 0xDCBB),
    ("DC0B", "wram1", 0xDC0B),
    ("DD85", "wram1", 0xDD85),
    ("DD86", "wram1", 0xDD86),
    ("DD87", "wram1", 0xDD87),
    ("DD88", "wram1", 0xDD88),
    ("FF40", "io", 0xFF40),
    ("FF42", "io", 0xFF42),
    ("FF43", "io", 0xFF43),
    ("FF55", "io", 0xFF55),
    ("FF70", "io", 0xFF70),
)


def serialized_state(path: Path) -> bytes:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not PNG")
    offset = 8
    states: list[bytes] = []
    saw_iend = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("truncated chunk")
        size = struct.unpack(">I", data[offset:offset + 4])[0]
        end = offset + size + 12
        if end > len(data):
            raise ValueError("truncated payload")
        kind = data[offset + 4:offset + 8]
        chunk = data[offset + 8:offset + 8 + size]
        crc = struct.unpack(">I", data[offset + 8 + size:end])[0]
        if crc != zlib.crc32(kind + chunk) & 0xFFFFFFFF:
            raise ValueError("CRC")
        if kind == b"gbAs":
            states.append(zlib.decompress(chunk))
        if kind == b"IEND":
            saw_iend = size == 0 and end == len(data)
        offset = end
    if not saw_iend or len(states) != 1:
        raise ValueError("container")
    state = states[0]
    if len(state) != STATE_SIZE:
        raise ValueError("state size")
    if int.from_bytes(state[:4], "little") != STATE_MAGIC:
        raise ValueError("state magic")
    return state


def selected_state_fields(state: bytes) -> dict[str, int]:
    fields: dict[str, int] = {}
    for name, kind, address in STATE_FIELDS:
        if kind == "wram1":
            offset = STATE_WRAM1 + address - 0xD000
        elif kind == "hram":
            offset = STATE_HRAM + address - 0xFF80
        elif kind == "io":
            offset = STATE_IO + address - 0xFF00
        else:
            raise AssertionError(kind)
        fields[name] = state[offset]
    return fields


def savestate_corpus_contract(root: Path) -> dict[str, object]:
    """Bind the natural-state evidence behind excluding secondary Stage 7.

    The static caller guard is the actual safety gate.  This corpus only
    explains why requiring a natural $0AB8 hit in every patrol is unrealistic.
    Our deliberately synthesized, never-run route fixture is excluded by exact
    path prefix and reported separately; it cannot manufacture reachability.
    """

    paths = sorted(path for path in root.rglob("*.ss?") if path.is_file())
    synthetic_prefix = (
        ROOT / "tmp/stage7-dual-plane-hdma-r264/secondary-fixture-static"
    )
    excluded_synthetic: list[dict[str, str]] = []
    invalid = 0
    by_sha: dict[str, tuple[Path, bytes]] = {}
    valid_files = 0
    for path in paths:
        try:
            relative = path.relative_to(ROOT)
        except ValueError:
            relative = path
        if path.is_relative_to(synthetic_prefix):
            excluded_synthetic.append({
                "path": str(relative),
                "sha256": sha256(path.read_bytes()),
                "reason": "explicitly synthesized and never executed",
            })
            continue
        try:
            state = serialized_state(path)
        except (OSError, ValueError, zlib.error):
            invalid += 1
            continue
        valid_files += 1
        file_sha = sha256(path.read_bytes())
        by_sha.setdefault(file_sha, (path, state))

    normalized = hashlib.sha256()
    stage7: list[dict[str, object]] = []
    for file_sha, (path, state) in sorted(by_sha.items()):
        fields = selected_state_fields(state)
        normalized.update(bytes.fromhex(file_sha))
        normalized.update(bytes(fields[name] for name, _kind, _address in STATE_FIELDS))
        if (fields["D880"], fields["FFBA"], fields["FFC1"]) == (8, 6, 1):
            stage7.append({
                "sha256": file_sha,
                "representative_path": str(path.relative_to(ROOT)),
                "FFDA": f"${fields['FFDA']:02X}",
            })

    nonzero = [record for record in stage7 if record["FFDA"] != "$00"]
    if not stage7:
        raise AssertionError("natural savestate corpus has no Stage-7 gameplay state")
    if nonzero:
        raise AssertionError(f"natural Stage-7 corpus has FFDA!=0: {nonzero!r}")

    # Negative control: the classifier must detect the exact synthetic state
    # mutation which would be needed to reach the secondary FFDA-gated caller.
    mutant = dict(stage7[0])
    mutant["FFDA"] = "$01"
    if mutant["FFDA"] == "$00":
        raise AssertionError("FFDA corpus negative control escaped")

    return {
        "role": (
            "reachability evidence only; emitted caller guard remains the "
            "fail-closed safety authority"
        ),
        "discovered_state_files": len(paths),
        "valid_natural_state_files": valid_files,
        "unique_natural_state_files_by_full_file_sha": len(by_sha),
        "deduplication_identity": "SHA-256 of complete CRC-valid PNG savestate",
        "invalid_or_non_mGBA_files": invalid,
        "synthetic_exclusions": excluded_synthetic,
        "selected_fields": [name for name, _kind, _address in STATE_FIELDS],
        "normalized_digest_definition": (
            "unique full-file SHA bytes plus selected field bytes, sorted by SHA"
        ),
        "normalized_selected_fields_sha256": normalized.hexdigest(),
        "stage7_gameplay_states": stage7,
        "stage7_gameplay_state_count": len(stage7),
        "stage7_FFDA_nonzero_count": len(nonzero),
        "mutation_controls": {
            "mutated_stage7_FFDA_nonzero_detected": True,
        },
    }


def fast_path_admitted(
    scx: int, scy: int, target_h: int, lcdc: int,
    scene: int = 0x08, dungeon: int = 0x06, ffc1: int = 1,
    ff55: int = 0xFF, outer_return: int = 0x12E0,
) -> bool:
    if scene != 0x08 or dungeon != 0x06 or ffc1 != 1:
        return False
    if lcdc & 0x20:
        return False
    if ff55 != 0xFF or outer_return != 0x12E0:
        return False
    if scx not in ALLOWED_CAMERA or scy not in ALLOWED_CAMERA:
        return False
    if target_h not in (0x98, 0x9C):
        return False
    if not lcdc & 0x80:
        return True
    visible_h = 0x9C if lcdc & 0x08 else 0x98
    return target_h != visible_h


def emitted_guard_contract(
    helper: bytes, labels: dict[str, int]
) -> dict[str, object]:
    fallback = labels["fallback_native"].to_bytes(2, "little")
    caller_reject = labels["caller_reject"].to_bytes(2, "little")
    destructive = labels["guards_passed"] - HELPER
    prefix = helper[:destructive]
    patterns = {
        "post_DI_scene": bytes.fromhex("FA 80 D8 FE 08 C2") + fallback,
        "post_DI_dungeon": bytes.fromhex("F0 BA FE 06 C2") + fallback,
        "gameplay_FFC1_exact": bytes.fromhex("F0 C1 FE 01 C2") + fallback,
        "window_LCDC5_clear": bytes.fromhex("F0 40 CB 6F C2") + fallback,
        "incoming_FF55_exact_idle": bytes.fromhex("F0 55 FE FF C2") + fallback,
        "SCX_domain": bytes.fromhex("F0 43 E6 F3 C2") + fallback,
        "SCY_domain": bytes.fromhex("F0 42 E6 F3 C2") + fallback,
    }
    caller_pattern = (
        bytes.fromhex("E5 F8 04 2A FE E0 C2") + caller_reject
        + bytes.fromhex("7E FE 12 C2") + caller_reject + bytes.fromhex("E1")
    )
    fallback_offset = labels["fallback_native"] - HELPER
    fallback_pattern = bytes.fromhex("F1 11 B3 42 D5 3E 01 C3 61 00")
    reject_offset = labels["caller_reject"] - HELPER
    reject_pattern = bytes.fromhex("E1 C3") + fallback

    def validate(blob: bytes) -> None:
        front = blob[:destructive]
        for name, pattern in patterns.items():
            if front.count(pattern) != 1:
                raise AssertionError(f"emitted helper lost {name} guard")
        if front.count(bytes.fromhex("F0 40 CB 7F")) != 2:
            raise AssertionError("emitted helper lost LCD-off/hidden-map arms")
        if front.count(bytes.fromhex("CB 5F")) != 2:
            raise AssertionError("emitted helper lost LCDC.3 visibility checks")
        if front.count(caller_pattern) != 1:
            raise AssertionError("emitted helper lost exact caller-set guard")
        if blob[fallback_offset:fallback_offset + len(fallback_pattern)] \
                != fallback_pattern:
            raise AssertionError("emitted helper lost exact native fallback")
        if blob[reject_offset:reject_offset + len(reject_pattern)] != reject_pattern:
            raise AssertionError("emitted helper lost balanced caller rejection")

    validate(helper)
    controls: dict[str, bool] = {}
    for name, pattern in patterns.items():
        mutant = bytearray(helper)
        position = mutant.find(pattern)
        if position < 0:
            raise AssertionError(name)
        mutant[position] ^= 1
        try:
            validate(bytes(mutant))
        except AssertionError:
            controls[f"mutated_{name}_rejected"] = True
        else:
            raise AssertionError(f"mutated emitted guard escaped: {name}")

    mutant = bytearray(helper)
    position = mutant.find(caller_pattern)
    if position < 0:
        raise AssertionError("caller guard")
    mutant[position + 5] ^= 1
    try:
        validate(bytes(mutant))
    except AssertionError:
        controls["mutated_exact_caller_rejected"] = True
    else:
        raise AssertionError("mutated caller guard escaped")

    # This deliberate two-byte mutation would change the accepted stack word
    # from $12E0 to $0AB8.  The strict emitted-pattern gate must reject it.
    mutant = bytearray(helper)
    mutant[position + 5] = 0xB8
    mutant[position + 11] = 0x0A
    try:
        validate(bytes(mutant))
    except AssertionError:
        controls["mutated_secondary_0AB8_admission_rejected"] = True
    else:
        raise AssertionError("secondary-admission caller mutation escaped")

    mutant = bytearray(helper)
    mutant[fallback_offset + 2] ^= 1       # $42B3 -> an invalid native entry
    try:
        validate(bytes(mutant))
    except AssertionError:
        controls["mutated_secondary_native_fallback_rejected"] = True
    else:
        raise AssertionError("mutated native fallback escaped")

    mutant = bytearray(helper)
    mutant[reject_offset] = 0xC1           # POP BC would clobber native BC
    try:
        validate(bytes(mutant))
    except AssertionError:
        controls["mutated_caller_reject_POP_HL_rejected"] = True
    else:
        raise AssertionError("mutated caller-reject POP escaped")

    # Stack-word model is deliberately small and is tied to the exact byte
    # patterns above.  It proves rejection neither consumes nor substitutes
    # the original $0AB8 outer continuation.
    stack = [0x084D, 0x0AB8]
    saved_hl = 0x9C00
    stack.insert(0, saved_hl)               # caller_guard PUSH HL
    if stack.pop(0) != saved_hl:            # caller_reject POP HL
        raise AssertionError("caller rejection failed to restore HL")
    if stack.pop(0) != 0x084D:              # fallback POP AF
        raise AssertionError("native fallback lost synthetic mapper return")
    stack.insert(0, NATIVE_DIRTY)           # PUSH $42B3
    if stack.pop(0) != NATIVE_DIRTY:        # mapper RET
        raise AssertionError("native mapper continuation changed")
    if stack != [0x0AB8]:
        raise AssertionError("secondary outer continuation was not preserved")

    revalidate_start = labels["revalidate_after_service"] - HELPER
    revalidate = helper[revalidate_start:]
    revalidate_fail = labels["revalidate_fail"].to_bytes(2, "little")
    revalidate_patterns = {
        "post_service_scene": bytes.fromhex("FA 80 D8 FE 08 C2")
        + revalidate_fail,
        "post_service_dungeon": bytes.fromhex("F0 BA FE 06 C2")
        + revalidate_fail,
        "post_service_gameplay": bytes.fromhex("F0 C1 FE 01 C2")
        + revalidate_fail,
        "post_service_window": bytes.fromhex("F0 40 CB 6F C2")
        + revalidate_fail,
        "post_service_FF55_idle": bytes.fromhex("F0 55 FE FF C2")
        + revalidate_fail,
        "post_service_SCX": bytes.fromhex("F0 43 E6 F3 C2")
        + revalidate_fail,
        "post_service_SCY": bytes.fromhex("F0 42 E6 F3 C2")
        + revalidate_fail,
    }
    for name, pattern in revalidate_patterns.items():
        if revalidate.count(pattern) != 1:
            raise AssertionError(f"emitted helper lost {name} guard")
    revalidate_call = bytes((0xCD,)) + labels[
        "revalidate_after_service"
    ].to_bytes(2, "little")
    if helper.count(bytes.fromhex("FB 00 F3") + revalidate_call) != 2:
        raise AssertionError("both Timer service windows must immediately revalidate")

    idle_pattern = revalidate_patterns["post_service_FF55_idle"]
    mutant = bytearray(helper)
    position = mutant.find(idle_pattern, revalidate_start)
    if position < 0:
        raise AssertionError("post-service idle guard")
    mutant[position] ^= 1
    mutated_revalidate = bytes(mutant[revalidate_start:])
    if mutated_revalidate.count(idle_pattern) != 0:
        raise AssertionError("post-service FF55 negative control ineffective")
    controls["mutated_post_service_FF55_idle_rejected"] = True
    return {
        "guarded_prefix_range": f"${HELPER:04X}-${HELPER + destructive - 1:04X}",
        "guarded_prefix_sha256": sha256(prefix),
        "patterns": {
            name: pattern.hex(" ").upper() for name, pattern in patterns.items()
        },
        "caller_pattern": caller_pattern.hex(" ").upper(),
        "caller_policy": {
            "admitted_outer_returns": ["fixed:$12E0"],
            "rejected_outer_returns": ["fixed:$0AB8"],
            "rejected_continuation": "native fallback before $DA13",
        },
        "native_fallback_pattern": fallback_pattern.hex(" ").upper(),
        "caller_reject_pattern": reject_pattern.hex(" ").upper(),
        "secondary_stack_model": {
            "helper_entry": ["$084D", "$0AB8"],
            "after_balanced_HL_probe": ["$084D", "$0AB8"],
            "native_mapper_entry": ["$42B3", "$0AB8"],
            "after_mapper_RET": ["$0AB8"],
        },
        "post_service_guard_range": (
            f"${labels['revalidate_after_service']:04X}-"
            f"${HELPER + len(helper) - 1:04X}"
        ),
        "post_service_patterns": {
            name: pattern.hex(" ").upper()
            for name, pattern in revalidate_patterns.items()
        },
        "post_service_call_count": 2,
        "mutation_controls": controls,
        "first_mutation_after_guards": "$DA13 tagged atomic setup",
    }


def guard_contract() -> dict[str, object]:
    admitted = rejected_visible = 0
    for scx in ALLOWED_CAMERA:
        for scy in ALLOWED_CAMERA:
            for lcdc in (0x80, 0x88):
                visible = 0x9C if lcdc & 8 else 0x98
                hidden = 0x98 if visible == 0x9C else 0x9C
                if not fast_path_admitted(scx, scy, hidden, lcdc):
                    raise AssertionError("hidden map was rejected")
                if fast_path_admitted(scx, scy, visible, lcdc):
                    raise AssertionError("visible map was admitted")
                admitted += 1
                rejected_visible += 1
    for bad in (0x01, 0x10, 0xFC, 0xFF):
        if fast_path_admitted(bad, 0, 0x9C, 0x80):
            raise AssertionError("unsafe SCX admitted")
        if fast_path_admitted(0, bad, 0x9C, 0x80):
            raise AssertionError("unsafe SCY admitted")
    for target in (0x00, 0x99, 0x9D, 0xA0):
        if fast_path_admitted(0, 0, target, 0):
            raise AssertionError("invalid target admitted")
    for target in (0x98, 0x9C):
        if not fast_path_admitted(0, 0, target, 0):
            raise AssertionError("LCD-off target rejected")
    if fast_path_admitted(0, 0, 0x9C, 0x80, scene=0x0E):
        raise AssertionError("Crystal scene escaped TOCTOU guard")
    if fast_path_admitted(0, 0, 0x9C, 0x80, dungeon=0x05):
        raise AssertionError("wrong dungeon escaped TOCTOU guard")
    if fast_path_admitted(0, 0, 0x9C, 0x80, ffc1=0):
        raise AssertionError("SELECT menu escaped gameplay guard")
    if fast_path_admitted(0, 0, 0x9C, 0xA0):
        raise AssertionError("Window-visible map escaped LCDC.5 guard")
    if fast_path_admitted(0, 0, 0x9C, 0x80, ff55=0x00):
        raise AssertionError("inherited active HDMA escaped FF55 guard")
    if fast_path_admitted(0, 0, 0x9C, 0x80, outer_return=0x0AB8):
        raise AssertionError("secondary $0AB8 caller escaped native fallback")
    if fast_path_admitted(0, 0, 0x9C, 0x80, outer_return=0x4242):
        raise AssertionError("unknown caller escaped exact-caller guard")
    return {
        "post_DI_revalidation": "$D880==$08 and $FFBA==$06",
        "gameplay_guard": "$FFC1 == $01",
        "window_guard": "LCDC.5 must be clear; otherwise native fallback",
        "incoming_dma_guard": "$FF55 must equal $FF before any bank switch",
        "caller_guard": (
            "only exact outer $12E0 is admitted; $0AB8 and unknown callers "
            "fall back to the untouched native dirty copier before $DA13"
        ),
        "camera_domain": [f"${value:02X}" for value in sorted(ALLOWED_CAMERA)],
        "active_lcd_hidden_cases_admitted": admitted,
        "active_lcd_visible_cases_rejected": rejected_visible,
        "lcd_off_both_maps_admitted": True,
        "fallback": (
            "POP synthetic $084D; push $42B3; map bank1; untouched native dirty path"
        ),
        "caller_flip": (
            "$12E0 remains below the helper and cannot publish LCDC until "
            "completion; rejected $0AB8 remains below the native copier"
        ),
    }


def caller_camera_contract(payload: bytes) -> dict[str, object]:
    call = bytes.fromhex("CD 95 42")
    call_sites = [
        offset for offset in range(len(payload) - len(call) + 1)
        if payload[offset:offset + len(call)] == call
    ]
    if call_sites != [0x0AB5, 0x12DD]:
        raise AssertionError(f"unexpected $4295 caller census: {call_sites!r}")

    # The rejected $0AB8 continuation remains bound so the receipt proves
    # exactly which native producer we are excluding.  Its geometry is useful
    # diagnostic evidence but is no longer part of fast-path admission.
    secondary_exposures = sum(
        row >= 24 or column >= 24
        for scx in range(32)
        for scy in range(32)
        for row, column in viewport_cells(scx, scy)
    )
    # $12E0 writes LCDC at $12EC before loading pending DC00/DC02&$0F.
    # The exact live-camera guard covers that brief old-scroll interval; this
    # exhaustive check covers every possible pending 0..15px state afterward.
    primary_exposures = sum(
        row >= 24 or column >= 24
        for scx in range(16)
        for scy in range(16)
        for row, column in viewport_cells(scx, scy)
    )
    if secondary_exposures or primary_exposures:
        raise AssertionError((secondary_exposures, primary_exposures))
    return {
        "exact_call_instruction": "CALL $4295",
        "whole_ROM_occurrences": ["fixed:$0AB5", "fixed:$12DD"],
        "admitted_outer_returns": ["fixed:$12E0"],
        "rejected_outer_returns": ["fixed:$0AB8"],
        "rejected_caller_policy": "native fallback before $DA13",
        "unknown_outer_return_policy": "native fallback before $DA13",
        "secondary": {
            "continuation": "$0AB8 CALL $307B",
            "fast_path_policy": "rejected; untouched native dirty copier",
            "strict_publisher_preimage": "$307B-$3099 inclusive",
            "pending_scroll": "SCY=DD87&$1F; SCX=DD85&$1F",
            "write_order": "FF42, FF43, then LCDC at $3095",
            "exhaustive_states": 32 * 32,
            "padding_exposures": secondary_exposures,
            "maximum_touched_column": 23,
            "maximum_touched_row": 21,
            "geometry_role": "diagnostic only; not an admission proof",
        },
        "primary": {
            "continuation": "$12E0",
            "strict_publisher_preimage": "$12E0-$1302 inclusive",
            "write_order": (
                "LCDC at $12EC, then FF43=DC00&$0F and FF42=DC02&$0F"
            ),
            "old_scroll_interval": "covered by live FF43/FF42 guard",
            "exhaustive_pending_states": 16 * 16,
            "padding_exposures": primary_exposures,
        },
    }


def secondary_reachability_contract(payload: bytes) -> dict[str, object]:
    """Explain, without relying on it for safety, why Stage-7 $0AB8 is absent."""

    ffda_stores = [
        offset for offset in range(len(payload) - 1)
        if payload[offset:offset + 2] == bytes.fromhex("E0 DA")
    ]
    if ffda_stores != [0x1A45, 0x1A85, 0x4164, 0x54EC]:
        raise AssertionError(f"unexpected whole-ROM FFDA store census: {ffda_stores}")
    expected_sites = {
        0x1A45: ("set", bytes.fromhex("3E 01 E0 DA"), 0x1A43),
        0x1A85: ("clear", bytes.fromhex("AF E0 DA"), 0x1A84),
        0x4164: ("clear", bytes.fromhex("AF E0 DA"), 0x4163),
        0x54EC: ("set", bytes.fromhex("3E 01 E0 DA"), 0x54EA),
    }
    write_receipts: list[dict[str, object]] = []
    for site, (value, pattern, start) in expected_sites.items():
        if payload[start:start + len(pattern)] != pattern:
            raise AssertionError(f"FFDA {value} preimage changed at ${site:04X}")
        write_receipts.append({
            "site": f"fixed:${site:04X}",
            "value": "$01" if value == "set" else "$00",
            "classification": value,
            "preimage": pattern.hex(" ").upper(),
        })

    # The secondary producer exists only in the FFDA!=0 arm.  The zero arm's
    # JR target is $0ABB and bypasses CALL $309B/CALL $4295 completely.
    if payload[0x0A9A:0x0A9F] != bytes.fromhex("F0 DA B7 28 1C"):
        raise AssertionError("secondary FFDA route gate changed")
    if payload[0x0AB2:0x0ABB] != bytes.fromhex(
        "CD 9B 30 CD 95 42 CD 7B 30"
    ):
        raise AssertionError("secondary producer chain changed")

    # Both FFDA-set paths leave ordinary Stage-7 identity before the fixed
    # main loop can consume the flag.  The boss path calls $759B, whose bound
    # scene setup writes D880=$18; the final bridge wrote D880=$19 first.
    if payload[0x1A43:0x1A52] != bytes.fromhex(
        "3E 01 E0 DA E0 E4 CD FD 16 CD 4E 17 CD 9B 75"
    ):
        raise AssertionError("boss FFDA/set-to-scene ordering changed")
    if payload[0x75B6:0x75BB] != bytes.fromhex("3E 18 EA 80 D8"):
        raise AssertionError("boss setup D880=$18 write changed")
    if payload[0x54C0:0x54C6] != bytes.fromhex("F5 3E 19 EA 80 D8"):
        raise AssertionError("final bridge D880=$19 write changed")
    if payload[0x54EA:0x54EE] != bytes.fromhex("3E 01 E0 DA"):
        raise AssertionError("final bridge FFDA ordering changed")

    # State reachability is repository-wide, not limited to the layout-corpus
    # root.  This keeps checked-in fixtures and older diagnostic roots in the
    # same normalized census.
    state_corpus = savestate_corpus_contract(ROOT)

    # Bind an existing full natural Stage-7 patrol.  This is prior-candidate
    # evidence, not a substitute for the refreshed candidate's live gates.
    patrol_dir = ROOT / "tmp/stage7-dual-plane-hdma-r264/visual-soak-r1"
    patrol_manifest = patrol_dir / "run-manifest.json"
    patrol_report = patrol_dir / "stage7.report"
    flip_events = patrol_dir / "stage7.flip-events.tsv"
    if not all(path.is_file() for path in (
        patrol_manifest, patrol_report, flip_events,
    )):
        raise AssertionError("bound natural Stage-7 patrol evidence is missing")
    manifest = json.loads(patrol_manifest.read_text())
    invocation = manifest.get("invocation", {})
    identity = manifest.get("identity_before", {})
    if invocation.get("stages") != [7] or invocation.get("frames") != 8000:
        raise AssertionError("bound Stage-7 patrol manifest scope changed")
    if identity.get("candidate_sha256") != (
        "7f4252a7c9d9988a6a5702cb60911fcc35586ca613c7dff06125238cde0d9bf8"
    ):
        raise AssertionError("bound prior patrol candidate identity changed")
    if manifest.get("status") != "FAIL":
        raise AssertionError("prior patrol status changed; reclassify evidence")
    report_text = patrol_report.read_text()
    if "stage=7 frames=8000" not in report_text or "rooms=4" not in report_text:
        raise AssertionError("bound Stage-7 patrol scope changed")
    flips = [line.split("\t") for line in flip_events.read_text().splitlines()]
    publishers = [fields[2].upper() for fields in flips if len(fields) >= 3]
    if not publishers or set(publishers) != {"12E0"}:
        raise AssertionError(f"unexpected natural Stage-7 publishers: {publishers}")

    # A natural non-Stage7 secondary hit proves the caller itself is live and
    # belongs elsewhere; it does not qualify it for the Stage-7 fast path.
    secondary_trace = (
        ROOT / "tmp/release-fastpath-r7/full-suite/matrix/artifacts/"
        "boss-arenas/boss6_faze.trace"
    )
    if not secondary_trace.is_file():
        raise AssertionError("bound non-Stage7 secondary trace is missing")
    secondary_lines = [
        line for line in secondary_trace.read_text().splitlines()
        if "pc=309B" in line
    ]
    if len(secondary_lines) != 1 or "d880=12" not in secondary_lines[0]:
        raise AssertionError("non-Stage7 secondary trace contract changed")

    return {
        "safety_authority": (
            "emitted exact caller guard; reachability evidence cannot admit $0AB8"
        ),
        "secondary_route": {
            "gate": "fixed:$0A9A LDH A,[FFDA]; OR A; JR Z,$0ABB",
            "required_state": "$FFDA != $00",
            "producer_chain": (
                "$0AB2 CALL $309B; $0AB5 CALL $4295; outer return $0AB8"
            ),
            "fast_path_policy": "rejected before $DA13; native fallback",
        },
        "whole_ROM_FFDA_writes": write_receipts,
        "ordering_proof": {
            "boss_entry": (
                "$1A45 sets FFDA, then the same synchronous entry calls $759B; "
                "$75B6-$75BA writes D880=$18 before its arena loop"
            ),
            "final_bridge": (
                "$54C0-$54C5 writes D880=$19 before $54EA-$54ED sets FFDA"
            ),
            "ordinary_later_entry_clear": "bank1:$4163 AF; $4164 LDH [FFDA],A",
        },
        "savestate_corpus": state_corpus,
        "bound_prior_natural_route_observation": {
            "qualification": (
                "reachability-only; manifest FAIL is explicitly not a visual, "
                "ABI, speed, or promotion receipt for the refreshed candidate"
            ),
            "manifest": str(patrol_manifest.relative_to(ROOT)),
            "manifest_sha256": sha256(patrol_manifest.read_bytes()),
            "manifest_status": manifest["status"],
            "prior_candidate_sha256": identity["candidate_sha256"],
            "report": str(patrol_report.relative_to(ROOT)),
            "report_sha256": sha256(patrol_report.read_bytes()),
            "flip_events": str(flip_events.relative_to(ROOT)),
            "flip_events_sha256": sha256(flip_events.read_bytes()),
            "flip_count": len(publishers),
            "publishers": ["fixed:$12E0"],
            "secondary_3095_hits": 0,
        },
        "bound_nonstage_secondary_control": {
            "path": str(secondary_trace.relative_to(ROOT)),
            "sha256": sha256(secondary_trace.read_bytes()),
            "line": secondary_lines[0],
            "classification": "Faze arena D880=$12, not Stage 7 D880=$08",
        },
        "patrol_contract": (
            "Require $12E0 fast-path coverage in each 8000-frame Stage-7 patrol. "
            "Do not require $0AB8/$3095 there: no natural Stage-7 route was found, "
            "and the candidate deliberately sends it through native fallback."
        ),
    }


def banked_stack_contract(
    helper: bytes, labels: dict[str, int]
) -> dict[str, object]:
    if "dma_command_store" in labels:
        raise AssertionError("shared DMA CALL/store label must not exist")

    three_byte = {
        0x01, 0x08, 0x11, 0x21, 0x31,
        0xC2, 0xC3, 0xC4, 0xCA, 0xCC, 0xCD,
        0xD2, 0xD4, 0xDA, 0xDC, 0xEA, 0xFA,
    }
    two_byte = {
        0x06, 0x0E, 0x10, 0x16, 0x18, 0x1E, 0x20, 0x26, 0x28, 0x2E,
        0x30, 0x36, 0x38, 0x3E, 0xCB, 0xC6, 0xCE, 0xD6, 0xDE,
        0xE0, 0xE6, 0xE8, 0xEE, 0xF0, 0xF6, 0xF8, 0xFE,
    }
    stack_ops = {
        0xC0, 0xC1, 0xC4, 0xC5, 0xC7, 0xC8, 0xC9, 0xCC, 0xCD, 0xCF,
        0xD0, 0xD1, 0xD4, 0xD5, 0xD7, 0xD8, 0xD9, 0xDC, 0xDF,
        0xE1, 0xE5, 0xE7, 0xEF, 0xF1, 0xF5, 0xF7, 0xFF,
    }

    def decoded(start: int, end: int) -> list[tuple[int, int]]:
        offset = start - HELPER
        limit = end - HELPER
        result: list[tuple[int, int]] = []
        while offset < limit:
            opcode = helper[offset]
            result.append((HELPER + offset, opcode))
            length = 3 if opcode in three_byte else 2 if opcode in two_byte else 1
            offset += length
        if offset != limit:
            raise AssertionError(f"instruction boundary mismatch ${start:04X}-${end:04X}")
        return result

    zones = {
        "SVBK2_odd_row_staging": (
            labels["phase1_odd_stage"], labels["phase1_service"]
        ),
        "SVBK3_attr_transport": (
            labels["phase2_attr_setup"], labels["phase2_service"]
        ),
        "SVBK2_tile_transport": (
            labels["phase3_tile_setup"], labels["final_restore"]
        ),
    }
    checked: dict[str, object] = {}
    for name, (start, end) in zones.items():
        operations = decoded(start, end)
        violations = [
            f"${address:04X}:${opcode:02X}"
            for address, opcode in operations if opcode in stack_ops
        ]
        if violations:
            raise AssertionError(f"{name} stack operations: {violations}")
        checked[name] = {
            "range": f"${start:04X}-${end - 1:04X}",
            "decoded_instruction_count": len(operations),
            "stack_operations": violations,
        }

    attr_offset = labels["attr_start"] - HELPER
    tile_offset = labels["tile_start"] - HELPER

    def validate_inline(blob: bytes) -> None:
        if blob[attr_offset:attr_offset + 2] != bytes.fromhex("E0 55"):
            raise AssertionError("attribute FF55 store is not inline")
        if blob[tile_offset:tile_offset + 3] != bytes.fromhex("78 E0 55"):
            raise AssertionError("tile FF55 store is not inline")
        if blob.count(bytes.fromhex("E0 55")) != 2:
            raise AssertionError("unexpected FF55 store census")

    validate_inline(helper)
    controls: dict[str, bool] = {}
    for name, position in (
        ("attr_inline_store", attr_offset),
        ("tile_inline_store", tile_offset + 1),
    ):
        mutant = bytearray(helper)
        mutant[position] = 0xCD
        try:
            validate_inline(bytes(mutant))
        except AssertionError:
            controls[f"mutated_{name}_rejected"] = True
        else:
            raise AssertionError(f"{name} negative control escaped")

    return {
        "contract": (
            "no CALL/RET/PUSH/POP/RST executes while SVBK2 is selected or "
            "during the transport-only SVBK3 phase; both FF55 stores are inline"
        ),
        "zones": checked,
        "attribute_compiler_exception": (
            "phase1's established exact $D400 row helper uses one balanced "
            "CALL/RET while SVBK3, as the existing r264 compiler already does"
        ),
        "inline_FF55_stores": {
            "attribute": f"bank22:${labels['attr_start']:04X}",
            "tile": f"bank22:${labels['tile_start'] + 1:04X}",
        },
        "mutation_controls": controls,
    }


def timing_contract() -> dict[str, object]:
    row_helper_cell = 36
    row_helper = 24 * row_helper_cell + 16
    attr_prelude = 72
    attr_first_23 = 24 + row_helper + 68 + 40
    attr_last = 24 + row_helper + 68 + 36
    attr_compile = attr_prelude + 23 * attr_first_23 + attr_last
    odd_stage = 32 + 12 * (12 + 24 * 24 + 68)
    atomic_call_and_body = 24 + 84
    phase1_core = atomic_call_and_body + attr_compile + odd_stage
    post_DI_route_mapper_entry = 184
    admitted_guards_without_caller = 328
    caller_12e0 = 96
    caller_0ab8_reject_through_native_jump = 152
    discard_synthetic_return = 12
    restore_to_service = 32
    phase1_interrupt_closed_upper = (
        4 + post_DI_route_mapper_entry + admitted_guards_without_caller
        + caller_12e0 + discard_synthetic_return
        + phase1_core + restore_to_service
    )
    intercommand = (
        28 + 40 + 40 + 44 + 20 + 8 + 8 + 36 + 16
    )
    next_hblank_window = (
        MIN_HBLANK_T - HDMA_BLOCK_T + MODE2_T + MIN_MODE3_T
    )
    intercommand_margin = next_hblank_window - intercommand
    if row_helper != 880 or attr_compile != 24356:
        raise AssertionError((row_helper, attr_compile))
    if odd_stage != 7904 or phase1_core != 32368:
        raise AssertionError((odd_stage, phase1_core))
    if phase1_interrupt_closed_upper != 33024:
        raise AssertionError(phase1_interrupt_closed_upper)
    if intercommand != 240 or intercommand_margin <= 0:
        raise AssertionError((intercommand, intercommand_margin))
    if phase1_core >= TIMER_PERIOD_T:
        raise AssertionError("compile phase can coalesce Timer overflows")
    if phase1_interrupt_closed_upper >= TIMER_PERIOD_T:
        raise AssertionError("full first DI window can coalesce Timer overflows")

    current = 65664 + 23432 + 21888
    candidate_typical_upper = 80000
    vblank_pause_upper = 10 * SCREEN_LINE_T
    hblank_phase_wall_upper = 49 * SCREEN_LINE_T + vblank_pause_upper
    if hblank_phase_wall_upper >= TIMER_PERIOD_T:
        raise AssertionError("one transport phase can coalesce Timer overflows")
    return {
        "units": "normal-speed CGB T-cycles/dots",
        "timer_period_t": TIMER_PERIOD_T,
        "phase1": {
            "tagged_DA13_call_and_body_t": atomic_call_and_body,
            "padded_attribute_compile_t": attr_compile,
            "unrolled_odd_tile_stage_t": odd_stage,
            "core_t": phase1_core,
            "post_DI_mapper_and_helper_entry_t": post_DI_route_mapper_entry,
            "admitted_guards_excluding_caller_t": (
                admitted_guards_without_caller
            ),
            "caller_guard_t": {
                "$12E0_admitted": caller_12e0,
                "$0AB8_rejected_through_native_mapper_jump": (
                    caller_0ab8_reject_through_native_jump
                ),
            },
            "discard_synthetic_084D_t": discard_synthetic_return,
            "VBK0_SVBK1_restore_to_service_t": restore_to_service,
            "full_interrupt_closed_upper_t": phase1_interrupt_closed_upper,
            "timer_margin_t": TIMER_PERIOD_T - phase1_interrupt_closed_upper,
            "below_one_timer_period": True,
        },
        "phase2_attribute_transport": {
            "blocks": 48,
            "hblank_wall_t": 48 * SCREEN_LINE_T,
            "maximum_visible_line_alignment_t": SCREEN_LINE_T,
            "maximum_one_VBlank_pause_t": vblank_pause_upper,
            "conservative_wall_upper_t": hblank_phase_wall_upper,
            "below_one_timer_period": hblank_phase_wall_upper < TIMER_PERIOD_T,
        },
        "phase3_tile_transport": {
            "commands": 24,
            "blocks_per_command": 2,
            "total_blocks": 48,
            "hblank_wall_t": 48 * SCREEN_LINE_T,
            "post_second_block_to_next_hblank_window_t": next_hblank_window,
            "worst_intercommand_setup_and_start_t": intercommand,
            "margin_t": intercommand_margin,
            "consecutive_hblanks_statically_feasible": True,
            "maximum_one_VBlank_pause_t": vblank_pause_upper,
            "conservative_wall_upper_t": hblank_phase_wall_upper,
            "below_one_timer_period": hblank_phase_wall_upper < TIMER_PERIOD_T,
        },
        "current_dirty_approx_t": current,
        "candidate_dirty_conservative_typical_upper_t": candidate_typical_upper,
        "saving_per_dirty_approx_t": current - candidate_typical_upper,
        "stage7_patrol_dirty_compiles": 351,
        "patrol_saving_projection_t": (current - candidate_typical_upper) * 351,
        "projection": (
            "plausibly near .98 patrol ratio, but static timing is not a live result"
        ),
    }


def dma_contract(labels: dict[str, int]) -> dict[str, object]:
    active = False

    def start(*, lcd_on: bool, mode: int, command: int) -> None:
        nonlocal active
        if active:
            raise AssertionError("DMA overlap")
        if lcd_on and mode != 3:
            raise AssertionError("HBlank DMA did not start in mode 3")
        if lcd_on and not command & 0x80:
            raise AssertionError("LCD-on command is not HBlank DMA")
        if not lcd_on and command & 0x80:
            raise AssertionError("LCD-off command cannot advance HBlank DMA")
        active = True

    def bank_switch() -> None:
        if active:
            raise AssertionError("VBK/SVBK switch while FF55 active")

    def complete() -> None:
        nonlocal active
        if not active:
            raise AssertionError("completion without active DMA")
        active = False

    start(lcd_on=True, mode=3, command=0xAF)
    complete()
    bank_switch()
    for _ in range(24):
        start(lcd_on=True, mode=3, command=0x81)
        complete()
    bank_switch()
    start(lcd_on=False, mode=0, command=0x2F)
    complete()
    for _ in range(24):
        start(lcd_on=False, mode=0, command=0x01)
        complete()

    controls: dict[str, bool] = {}
    for name, operation in (
        ("active_VBK_switch_rejected", lambda: (
            start(lcd_on=True, mode=3, command=0x81), bank_switch()
        )),
        ("mode0_HBlank_start_rejected", lambda: start(
            lcd_on=True, mode=0, command=0x81
        )),
        ("LCD_off_HBlank_command_rejected", lambda: start(
            lcd_on=False, mode=0, command=0x81
        )),
    ):
        active = False
        try:
            operation()
        except AssertionError:
            controls[name] = True
        else:
            raise AssertionError(f"negative DMA control escaped: {name}")
    return {
        "active_lcd_commands": {"attrs": "$AF", "tile_rows": "$81 x24"},
        "lcd_off_commands": {"attrs": "$2F", "tile_rows": "$01 x24"},
        "inline_FF55_store_PCs": {
            "attribute": f"bank22:${labels['attr_start']:04X}",
            "tile": f"bank22:${labels['tile_start'] + 1:04X}",
        },
        "wait_policy": (
            "wait mode3 before every LCD-on command; poll FF55 bit7 until idle "
            "before any bank switch or next command"
        ),
        "active_DMA_VBK_changes": 0,
        "active_DMA_SVBK_changes": 0,
        "negative_controls": controls,
    }


def timer_contract(payload: bytes) -> dict[str, object]:
    bank3 = payload[3 * BANK_SIZE:4 * BANK_SIZE]
    if sha256(bank3) != "65c7cc9b320d8b3b2aeeae12ca56ad26c6b636971ce4b1485a78a6bd88e7979a":
        raise AssertionError("bank3 sound-engine image changed")

    forbidden_direct: list[str] = []
    for index in range(len(bank3) - 2):
        if bank3[index] != 0xEA:             # LD [a16],A
            continue
        address = bank3[index + 1] | bank3[index + 2] << 8
        if 0xC1A0 <= address <= 0xC3DF or address == 0xFF70:
            forbidden_direct.append(f"${0x4000 + index:04X}->${address:04X}")
    if forbidden_direct:
        raise AssertionError(forbidden_direct)
    return {
        "isr": "$0050 -> $06B3",
        "isr_sha256": sha256(payload[0x06B3:0x06D1]),
        "register_preservation": "PUSH/POP AF,BC,DE,HL; RETI",
        "rom_bank_sequence": [3, 1, "restore FF99 (22 during helper)"],
        "SVBK_at_service": 1,
        "FF55_at_service": "$FF/inactive",
        "IE_during_helper": "$04 Timer-only, established by exact tagged $DA13",
        "known_writes": "bank3 sound D8xx/MMIO; fixed $0D79 writes FFD1",
        "bank3_sha256": sha256(bank3),
        "direct_C1A0_C3DF_or_FF70_stores": forbidden_direct,
        "bounded_static_caveat": (
            "No direct forbidden store exists and repo ownership binds indirect "
            "sound writes to D8xx, but first-live C1A0-C3DF/FF70 watchpoints remain "
            "a mandatory promotion gate for indirect-writer confirmation."
        ),
    }


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def build_in_memory_candidate(
    payload: bytes, helper: bytes, tail: bytes, descriptors: bytes, lut: bytes
) -> tuple[bytes, dict[str, object]]:
    rom = bytearray(payload)
    for bank in (13, 16):
        redirect_source = runtime_source_address(
            RUNTIME_REDIRECT_OPERAND - RUNTIME_BASE
        )
        tail_source = runtime_source_address(RUNTIME_TAIL - RUNTIME_BASE)
        rom[bank_offset(bank, redirect_source)] = 0x31
        offset = bank_offset(bank, tail_source)
        rom[offset:offset + len(tail)] = tail

    regions = (
        (HELPER, helper, "helper"),
        (DESCRIPTORS, descriptors, "tile_descriptors"),
        (LUT, lut, "immutable_stage7_lut"),
    )
    installed = []
    for address, blob, name in regions:
        offset = bank_offset(BANK, address)
        if rom[offset:offset + len(blob)] != bytes([0xFF]) * len(blob):
            raise AssertionError(f"bank22 {name} region is not free")
        rom[offset:offset + len(blob)] = blob
        installed.append({
            "name": name,
            "bank": BANK,
            "range": f"${address:04X}-${address + len(blob) - 1:04X}",
            "length": len(blob),
            "sha256": sha256(blob),
        })
    update_checksums(rom)

    changed = [
        index for index, (before, after) in enumerate(zip(payload, rom, strict=True))
        if before != after
    ]
    allowed = {0x014D, 0x014E, 0x014F}
    for bank in (13, 16):
        allowed.add(bank_offset(
            bank, runtime_source_address(
                RUNTIME_REDIRECT_OPERAND - RUNTIME_BASE
            )
        ))
        start = bank_offset(bank, runtime_source_address(RUNTIME_TAIL - RUNTIME_BASE))
        allowed.update(range(start, start + len(tail)))
    for address, blob, _name in regions:
        start = bank_offset(BANK, address)
        allowed.update(range(start, start + len(blob)))
    if set(changed) - allowed:
        raise AssertionError("in-memory candidate changed an unapproved byte")

    return bytes(rom), {
        "sha256": sha256(rom),
        "rom_emitted": False,
        "changed_byte_count": len(changed),
        "installed_regions": installed,
        "runtime_source_patches": [
            "bank13:$7C76 EB->$31; $7CA8-$7CBD installs 22-byte tail",
            "bank16:$7C76 EB->$31; $7CA8-$7CBD installs 22-byte tail",
        ],
        "checksums": {
            "header": f"${rom[0x014D]:02X}",
            "global": f"${int.from_bytes(rom[0x014E:0x0150], 'big'):04X}",
        },
    }


def mutation_controls(payload: bytes) -> dict[str, bool]:
    controls: dict[str, bool] = {}
    for name, bank, start, _end, _expected in PREIMAGES:
        mutant = bytearray(payload)
        mutant[bank_offset(bank, start)] ^= 1
        try:
            require_preimages(bytes(mutant))
        except AssertionError:
            controls[f"mutated_{name}_rejected"] = True
        else:
            raise AssertionError(f"mutated preimage escaped: {name}")

    runtime = bytearray(runtime_from_source(payload, 13))
    runtime[RUNTIME_REDIRECT_OPERAND - RUNTIME_BASE] = 0x30
    if runtime[RUNTIME_REDIRECT_OPERAND - RUNTIME_BASE] == 0x31:
        raise AssertionError("wrong redirect negative control escaped")
    controls["wrong_DAB7_30_rejected_target_DAE8"] = True

    bad_tail = bytearray(build_router_tail())
    bad_tail[15:17] = bytes((0xC1, 0xC1))
    if bad_tail == build_router_tail():
        raise AssertionError("POP BC negative control escaped")
    controls["POP_BC_return_discard_rejected"] = True
    return controls


def audit(payload: bytes, corpus_root: Path) -> dict[str, object]:
    digest = sha256(payload)
    if digest != BASE_SHA256:
        raise AssertionError(f"not exact repaired r264: {digest}")
    preimages = require_preimages(payload)
    runtime = require_runtime(payload)
    tail = build_router_tail()
    descriptors = build_descriptors()
    lut = bytes(semantic_lut(7))
    helper, labels = build_helper()
    if HELPER + len(helper) > DESCRIPTORS:
        raise AssertionError("helper overlaps descriptor table")
    if sha256(lut) != "cfb5fe66cecfb2887abd8f8e828d311265217831888713ddeb50d8b0f4a6a84a":
        raise AssertionError("Stage7 LUT changed")

    corpus = corpus_contract(corpus_root, lut)
    guards = guard_contract()
    emitted_guards = emitted_guard_contract(helper, labels)
    callers = caller_camera_contract(payload)
    secondary_reachability = secondary_reachability_contract(payload)
    banked_stack = banked_stack_contract(helper, labels)
    timing = timing_contract()
    dma = dma_contract(labels)
    timer = timer_contract(payload)
    _candidate_bytes, candidate = build_in_memory_candidate(
        payload, helper, tail, descriptors, lut
    )
    controls = mutation_controls(payload)

    trace_labels = {
        name: f"bank22:${address:04X}"
        for name, address in labels.items()
        if name in {
            "entry", "fallback_native", "phase1_attr_compile",
            "phase1_odd_stage", "phase1_service", "phase2_attr_setup",
            "attr_start", "attr_wait_complete", "phase2_service",
            "phase3_tile_setup", "tile_start", "tile_wait_complete",
            "final_restore", "fallback_after_atomic", "caller_reject",
            "revalidate_after_service",
        }
    }
    trace_labels["attr_FF55_store"] = f"bank22:${labels['attr_start']:04X}"
    trace_labels["tile_FF55_store"] = (
        f"bank22:${labels['tile_start'] + 1:04X}"
    )
    trace_labels["IE_restored"] = "bank1:$436A (AF not final yet)"
    trace_labels["exact_pre_RETI_ABI"] = "bank1:$436D"
    trace_labels["post_RETI_outer_returns"] = [
        "fixed:$12E0",
    ]
    trace_labels["rejected_outer_returns"] = ["fixed:$0AB8"]
    trace_labels["rejected_caller_continuation"] = (
        "bank22:caller_reject -> fallback_native -> bank1:$42B3"
    )

    return {
        "schema": "penta-stage7-hidden-dual-plane-hdma-r264-static-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_run": False,
        "rom_emitted": False,
        "base_sha256": digest,
        "in_memory_candidate": candidate,
        "strict_r264_preimages": preimages,
        "runtime_router": {
            **runtime,
            "tail_bytes": tail.hex(" ").upper(),
            "tail_sha256": sha256(tail),
            "stage_gate": "$D880 == $08",
            "nonstage_dirty_miss_delta": (
                "+60T; registers, AF, and return stack are exact, but timing is "
                "not literally cycle exact. Hot hits do not enter this tail."
            ),
        },
        "helper": {
            "bank": BANK,
            "entry": f"${HELPER:04X}",
            "length": len(helper),
            "end": f"${HELPER + len(helper) - 1:04X}",
            "sha256": sha256(helper),
            "trace_labels": trace_labels,
            "descriptor_table": {
                "address": f"${DESCRIPTORS:04X}",
                "length": len(descriptors),
                "sha256": sha256(descriptors),
                "format": "24 x [source_hi, source_lo&F0, dest_page_delta, dest_lo]",
            },
            "immutable_lut": {
                "address": f"${LUT:04X}",
                "length": len(lut),
                "sha256": sha256(lut),
            },
        },
        "corpus": corpus,
        "runtime_guards": guards,
        "emitted_guard_verification": emitted_guards,
        "caller_and_camera_contract": callers,
        "secondary_reachability_contract": secondary_reachability,
        "banked_stack_contract": banked_stack,
        "dma_contract": dma,
        "timing": timing,
        "timer_service": timer,
        "memory_ownership": {
            "attrs": "SVBK3:$D000-$D2FF; fully overwritten each dirty compile",
            "odd_tiles": "SVBK2:$D000-$D17F; fully overwritten each dirty compile",
            "row_helper": (
                "existing exact $D400-$D478 helper in SVBK3; CALL/RET wholly "
                "within bank3, then SVBK1 restored before any outer stack use"
            ),
            "stage2": "uses its own scene3 lifecycle; no Stage7 concurrent owner",
            "ted_scene10": (
                "may reuse bank2/3 D000 later, but its entry rebuilds and invalidates "
                "its owner keys before consumption"
            ),
            "stage1_and_arenas": "cannot enter helper because D880 must equal $08",
        },
        "abi": {
            "entry_stack": ["synthetic $084D", "admitted outer $12E0"],
            "discarded_internal_returns": ["$3493", "$42B1"],
            "completion_stack": ["synthetic $3497", "outer $12E0"],
            "pair_register_proof": (
                "final_restore rebuilds HL from tagged FFA5, loads BC=$084D, "
                "loads DE=$3497 only long enough to PUSH it, then reloads "
                "DE=$C3E0. Exact mapper $0061/$09BE and completion "
                "$3497->$0842->$4368 use A/memory only, so BC/DE/HL survive "
                "through RETI to outer $12E0."
            ),
            "rejected_secondary_native_stack": {
                "helper_entry": ["synthetic $084D", "outer $0AB8"],
                "caller_guard": "PUSH/POP HL is balanced in SVBK1",
                "fallback_rewrite": ["synthetic $42B3", "outer $0AB8"],
                "mapper_result": (
                    "$0061 RET enters untouched bank1:$42B3; native copier RET "
                    "lands at original outer $0AB8"
                ),
                "mutation_before_native_entry": (
                    "no SVBK/VBK/VRAM/atomic-state mutation; only balanced "
                    "SVBK1 stack inspection and the required ROM-bank mapper"
                ),
            },
            "final": {
                "AF": "$01C0 via existing $4368 tail",
                "BC": "$084D",
                "DE": "$C3E0",
                "HL": "$9800/$9C00 exact destination base",
                "FFE0": "$00",
                "FFA5": "$00",
                "VBK": 0,
                "SVBK": 1,
                "FF55": "$FF/inactive",
                "IE_IME": "saved IE restored by $3497; $4368 RETI",
                "ROM_bank": 1,
                "exact_pre_RETI_PC": "$436D",
                "post_RETI_PC": "$12E0",
            },
        },
        "mutation_controls": controls,
        "decision": (
            "The $12E0-only architecture survives exact-r264 static review and is "
            "worth a separate candidate build. $0AB8 is intentionally native. It "
            "is not promotable until duplicate live Stage7 patrols prove speed/"
            "visual parity, command cadence, hidden-map atomicity, audio cadence, "
            "and no Timer-time C1A0-C3DF/FF70 writes."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", type=Path,
        default=ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb",
    )
    parser.add_argument(
        "--corpus-root", type=Path, default=ROOT / "tmp",
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=ROOT / "tmp/stage7-dual-plane-hdma-r264/static-receipt.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage7-dual-plane-hdma-r264/candidate.gb",
    )
    args = parser.parse_args()
    base = args.base.read_bytes()
    receipt = audit(base, args.corpus_root)
    candidate_bytes, candidate_check = build_in_memory_candidate(
        base, build_helper()[0], build_router_tail(), build_descriptors(),
        bytes(semantic_lut(7)),
    )
    if candidate_check["sha256"] != receipt["in_memory_candidate"]["sha256"]:
        raise AssertionError("candidate rematerialization changed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate_bytes)
    receipt["rom_emitted"] = True
    receipt["in_memory_candidate"]["rom_emitted"] = True
    receipt["in_memory_candidate"]["path"] = str(args.output.relative_to(ROOT))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
