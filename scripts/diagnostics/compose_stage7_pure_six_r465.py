#!/usr/bin/env python3
"""Experimental Stage-7 six-tile pure copier; not release-qualified.

Only Stage 7, LCD-on, even-page (pure tile) publications take the appended
96-window copier. Atomic/fused work and every other stage retain r456d's
reviewed bank-28 helper. The fast copier is fully unrolled so INC E is used
except at real source-page crossings; its worst six-tile group costs 41
machine cycles from the last mode-3 observation to the final VRAM write,
inside the conservative 41.75-cycle mode-0+mode-2 envelope.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import compose_stage1_wide_copy_r445 as emitter


BASE = ROOT / "tmp/attract-blank-r456d/candidate.gb"
BASE_SHA256 = "69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722"
OUT = ROOT / "tmp/stage7-pure-six-r465"
CLASS_GATE = bytes.fromhex("06 18 F0 BA B7 28 07 F0 01 1F 38 02 06 00")
BASE_ARGS = dict(
    exit_c0=True,
    r5_table=None,
    class_gate=True,
    ei_gap=True,
    fused=True,
)


def base_helper() -> bytes:
    return emitter.emit(emitter.PATTERNS["5"], **BASE_ARGS)


def rel8(code: bytearray, operand: int, target: int) -> None:
    delta = target - (operand + 1)
    if not -128 <= delta <= 127:
        raise ValueError(f"relative branch out of range: {delta}")
    code[operand] = delta & 0xFF


def emit_fast_copier(*, include_prefix: bool = False) -> tuple[bytes, dict]:
    """Emit 24 rows x four safe six-tile groups, returning timing evidence."""

    code = bytearray()
    if include_prefix:
        code += bytes.fromhex("11 A0 C1 0E 41")  # DE=$C1A0; C=STAT
    critical_cycles: list[int] = []
    source = emitter.SRC0
    group_sources: list[list[int]] = []
    for _row in range(emitter.ROWS):
        for _group in range(4):
            poll_mode3 = len(code) + 1
            code += bytes.fromhex("F3 F2 E6 03 FE 03 20 00")
            rel8(code, len(code) - 1, poll_mode3)
            poll_mode0 = len(code)
            code += bytes.fromhex("F2 0F 38 00")
            rel8(code, len(code) - 1, poll_mode0)

            group = []
            critical = 11  # conservative reviewed wait-to-first-write onset
            for tile in range(6):
                group.append(source)
                code += bytes.fromhex("1A 22")  # LD A,(DE); LD (HL+),A
                if tile == 5:
                    code += bytes.fromhex("13")  # off the final-write path
                elif source & 0xFF == 0xFF:
                    code += bytes.fromhex("13")  # exact page carry
                    critical += 6
                else:
                    code += bytes.fromhex("1C")  # page-local INC E
                    critical += 5
                source += 1
            critical += 4  # final LD A,(DE); LD (HL+),A
            code += bytes.fromhex("FB 00")  # EI; NOP service point
            group_sources.append(group)
            critical_cycles.append(critical)
        code += bytes.fromhex("7D C6 08 6F 30 01 24")  # destination row stride
    code += bytes.fromhex("0E 00 3E 01 C9")  # original exit C=0,A=1,Z=1
    assert source == emitter.SRC0 + emitter.ROWS * emitter.COLS
    return bytes(code), {
        "group_count": len(group_sources),
        "cells": sum(map(len, group_sources)),
        "group_sources": group_sources,
        "critical_cycles": critical_cycles,
        "maximum_critical_cycles": max(critical_cycles),
        "groups_with_source_page_crossing": sum(
            1 for group in group_sources
            if (group[0] >> 8) != (group[-1] >> 8)
        ),
    }


def emit_dispatcher(
    *, dispatcher_address: int, fast_address: int, normal_return: int
) -> bytes:
    """Route only Stage7/LCD-on/pure copies to the appended fast body."""

    code = bytearray()
    normal_branches: list[int] = []
    code += bytes.fromhex("F0 BA FE 06 20 00")  # FFBA == 6
    normal_branches.append(len(code) - 1)
    code += bytes.fromhex("F0 01 1F 38 00")  # FF01 even (pure page)
    normal_branches.append(len(code) - 1)
    code += bytes.fromhex("F0 40 07 30 00")  # LCDC.7 set
    normal_branches.append(len(code) - 1)
    code += bytes((0xC3, fast_address & 0xFF, fast_address >> 8))
    normal = len(code)
    for operand in normal_branches:
        rel8(code, operand, normal)
    code += CLASS_GATE
    code += bytes((0xC3, normal_return & 0xFF, normal_return >> 8))
    if fast_address:
        assert dispatcher_address + len(code) <= fast_address
    return bytes(code)


def code_pair() -> tuple[bytes, bytes, dict]:
    old = base_helper()
    gate_index = old.find(CLASS_GATE)
    if gate_index < 0 or old.find(CLASS_GATE, gate_index + 1) >= 0:
        raise ValueError("base helper class gate is not unique")
    dispatcher_address = emitter.ORG + len(old)
    fast, evidence = emit_fast_copier()
    provisional = emit_dispatcher(
        dispatcher_address=dispatcher_address,
        fast_address=0,
        normal_return=emitter.ORG + gate_index + len(CLASS_GATE),
    )
    fast_address = dispatcher_address + len(provisional)
    dispatcher = emit_dispatcher(
        dispatcher_address=dispatcher_address,
        fast_address=fast_address,
        normal_return=emitter.ORG + gate_index + len(CLASS_GATE),
    )
    if len(dispatcher) != len(provisional):
        raise AssertionError("dispatcher size changed during address fixup")
    new_prefix = bytearray(old)
    new_prefix[gate_index:gate_index + 3] = bytes(
        (0xC3, dispatcher_address & 0xFF, dispatcher_address >> 8)
    )
    new = bytes(new_prefix) + dispatcher + fast
    evidence.update(
        gate_index=gate_index,
        dispatcher_address=dispatcher_address,
        fast_address=fast_address,
        normal_return=emitter.ORG + gate_index + len(CLASS_GATE),
        old_size=len(old),
        new_size=len(new),
        end_address=emitter.ORG + len(new),
        windows_per_stage7_pure=emitter.ROWS * 4,
        old_windows_per_pure=emitter.ROWS * 6,
    )
    if evidence["end_address"] > 0x8000:
        raise ValueError("appended helper overflows bank 28")
    return old, new, evidence


def execute_dispatcher(
    code: bytes,
    *,
    address: int,
    fast_address: int,
    normal_return: int,
    ffba: int,
    ff01: int,
    lcdc: int,
) -> tuple[str, int | None]:
    """Execute the exact dispatcher bytes for exhaustive route tests."""

    pc = 0
    a = b = 0
    zero = carry = False
    for _ in range(100):
        opcode = code[pc]
        pc += 1
        if opcode == 0xF0:
            register = code[pc]
            pc += 1
            a = {0xBA: ffba, 0x01: ff01, 0x40: lcdc}[register]
        elif opcode == 0xFE:
            value = code[pc]
            pc += 1
            zero, carry = a == value, a < value
        elif opcode == 0x20:
            delta = code[pc]
            pc += 1
            if not zero:
                pc += delta - 256 if delta > 127 else delta
        elif opcode == 0x38:
            delta = code[pc]
            pc += 1
            if carry:
                pc += delta - 256 if delta > 127 else delta
        elif opcode == 0x30:
            delta = code[pc]
            pc += 1
            if not carry:
                pc += delta - 256 if delta > 127 else delta
        elif opcode == 0x1F:
            carry = bool(a & 1)
            a >>= 1
        elif opcode == 0x07:
            carry = bool(a & 0x80)
            a = ((a << 1) | int(carry)) & 0xFF
        elif opcode == 0x06:
            b = code[pc]
            pc += 1
        elif opcode == 0xB7:
            zero, carry = a == 0, False
        elif opcode == 0x28:
            delta = code[pc]
            pc += 1
            if zero:
                pc += delta - 256 if delta > 127 else delta
        elif opcode == 0xC3:
            target = code[pc] | code[pc + 1] << 8
            if target == fast_address:
                return "fast", None
            if target == normal_return:
                return "normal", b
            pc = target - address
        else:
            raise AssertionError(f"unmodeled dispatcher opcode {opcode:02X}")
    raise AssertionError("dispatcher did not terminate")


def build(source: bytes) -> tuple[bytes, dict]:
    if hashlib.sha256(source).hexdigest() != BASE_SHA256:
        raise ValueError("requires exact retained r456d base")
    old, new, evidence = code_pair()
    start = emitter.off(emitter.BANK, emitter.ORG)
    if source[start:start + len(old)] != old:
        raise ValueError("reviewed bank28 helper preimage changed")
    extension = source[start + len(old):start + len(new)]
    if extension != b"\xFF" * len(extension):
        raise ValueError("bank28 extension cave is occupied")
    result = bytearray(source)
    result[start:start + len(new)] = new
    emitter.update_checksums(result)
    return bytes(result), evidence


def main() -> int:
    candidate, evidence = build(BASE.read_bytes())
    OUT.mkdir(exist_ok=True)
    candidate_path = OUT / "candidate.gb"
    if candidate_path.exists() and candidate_path.read_bytes() != candidate:
        raise ValueError("immutable candidate collision")
    candidate_path.write_bytes(candidate)
    receipt = {
        "schema": "penta-stage7-pure-six-r465-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "scope": (
            "bank28 Stage7 LCD-on pure tile publications only: "
            "96 HBlank windows instead of 144"
        ),
        "evidence": evidence,
    }
    (OUT / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
