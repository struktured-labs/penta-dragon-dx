#!/usr/bin/env python3
"""Build an experimental Stage-7-only VBlank service bypass on r465.

The wrapper's first call currently runs the Stage-1 art loader and the
death/story service even in exact gameplay scene $08.  Bank 13's $570E slot
is occupied by the Stage-7 transition selector, so this patch moves that
selector to the dead bytes immediately after the wrapper's unconditional
``JP $7100`` and retargets its sole bank-13 caller.  The reclaimed 16-byte
slot then holds an exact-scene-$08 early return followed by the original
DCFD loader guard and death-service tail jump.

Bank 16 has different live code at $6EDD; its selector and caller remain
byte-exact.  No RAM, renderer, copier, palette data, or interrupt state is
changed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "tmp/stage7-pure-six-r465/candidate.gb"
BASE_SHA256 = "0071dd21b3ef49978e2dc4eb277e3d49e056c510965c0b6c39d006fe3dfc21ab"
OUT = ROOT / "tmp/stage7-guarded-services-r467"
BANK = 13
STAGE7_FRONT = 0x5407
OLD_SELECTOR_ADDR = 0x570E
NEW_SELECTOR_ADDR = 0x6EDD
WRAPPER_PAIR = 0x6F20
ORIGINAL_STUB_ADDR = 0x6ED3

OLD_FRONT = bytes.fromhex("C3 0E 57 00 00 00")
NEW_FRONT = bytes.fromhex("C3 DD 6E 00 00 00")
SELECTOR = bytes.fromhex("3E 31 EA B7 DA CD 9C 54 C3 22 54 00 00 00 00 00")
DEAD_SLED = bytes.fromhex("18 00 18 00 18 00 18 00 18 00 18 00 18 00 00 00")
ORIGINAL_STUB = bytes.fromhex("FA FD DC B7 C4 0E 6A C3 00 71")
OLD_PAIR = bytes.fromhex("CD D3 6E CD 60 6A")
NEW_PAIR = bytes.fromhex("CD 0E 57 CD 60 6A")

# LD A,[$D880]; CP $08; RET Z;
# LD A,[$DCFD]; OR A; CALL NZ,$6A0E; JP $7100
GUARDED_STUB = bytes.fromhex(
    "FA 80 D8 FE 08 C8 FA FD DC B7 C4 0E 6A C3 00 71"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def offset(bank: int, address: int) -> int:
    if bank <= 0 or not 0x4000 <= address < 0x8000:
        raise ValueError((bank, address))
    return bank * 0x4000 + address - 0x4000


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x134:0x14D]:
        header = (header - value - 1) & 0xFF
    rom[0x14D] = header
    total = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E:0x150] = total.to_bytes(2, "big")


def require(source: bytes, bank: int, address: int, expected: bytes, label: str) -> int:
    start = offset(bank, address)
    actual = source[start:start + len(expected)]
    if actual != expected:
        raise ValueError(
            f"{label} preimage moved at bank{bank}:${address:04X}: "
            f"{actual.hex()} != {expected.hex()}"
        )
    return start


def absolute_references(bank_payload: bytes, target: int) -> list[int]:
    """Return JP/CALL instruction sites with an exact little-endian target."""

    result: list[int] = []
    target_bytes = target.to_bytes(2, "little")
    absolute_opcodes = {0xC2, 0xC3, 0xC4, 0xCA, 0xCC, 0xCD, 0xD2, 0xD4,
                        0xDA, 0xDC}
    for index in range(len(bank_payload) - 2):
        if bank_payload[index] in absolute_opcodes \
                and bank_payload[index + 1:index + 3] == target_bytes:
            result.append(0x4000 + index)
    return result


def model_guard(code: bytes, *, scene: int, dcfd: int) -> list[str]:
    """Execute the emitted guard's relevant SM83 instructions."""

    pc = 0
    a = 0
    zero = False
    calls: list[str] = []
    for _ in range(16):
        opcode = code[pc]
        pc += 1
        if opcode == 0xFA:
            address = code[pc] | code[pc + 1] << 8
            pc += 2
            a = {0xD880: scene, 0xDCFD: dcfd}[address]
        elif opcode == 0xFE:
            zero = a == code[pc]
            pc += 1
        elif opcode == 0xB7:
            zero = a == 0
        elif opcode == 0xC8:
            if zero:
                return calls
        elif opcode == 0xC4:
            address = code[pc] | code[pc + 1] << 8
            pc += 2
            if not zero:
                if address != 0x6A0E:
                    raise AssertionError(address)
                calls.append("stage1_art_loader")
        elif opcode == 0xC3:
            address = code[pc] | code[pc + 1] << 8
            if address != 0x7100:
                raise AssertionError(address)
            calls.append("death_story_service")
            return calls
        else:
            raise AssertionError(f"unmodeled opcode ${opcode:02X}")
    raise AssertionError("guard did not terminate")


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    if digest(source) != BASE_SHA256:
        raise ValueError("requires exact r465 candidate")
    front = require(source, BANK, STAGE7_FRONT, OLD_FRONT, "Stage-7 front")
    selector = require(
        source, BANK, OLD_SELECTOR_ADDR, SELECTOR, "Stage-7 selector"
    )
    relocated = require(
        source, BANK, NEW_SELECTOR_ADDR, DEAD_SLED, "dead selector sled"
    )
    pair = require(source, BANK, WRAPPER_PAIR, OLD_PAIR, "VBlank service pair")
    require(source, BANK, ORIGINAL_STUB_ADDR, ORIGINAL_STUB, "original service stub")

    bank_payload = source[BANK * 0x4000:(BANK + 1) * 0x4000]
    old_selector_refs = absolute_references(bank_payload, OLD_SELECTOR_ADDR)
    relocated_refs = absolute_references(bank_payload, NEW_SELECTOR_ADDR)
    if old_selector_refs != [STAGE7_FRONT]:
        raise ValueError(f"unexpected bank-13 $570E references: {old_selector_refs}")
    if relocated_refs:
        raise ValueError(f"dead $6EDD sled has references: {relocated_refs}")

    result = bytearray(source)
    result[front:front + len(NEW_FRONT)] = NEW_FRONT
    result[relocated:relocated + len(SELECTOR)] = SELECTOR
    result[selector:selector + len(GUARDED_STUB)] = GUARDED_STUB
    result[pair:pair + len(NEW_PAIR)] = NEW_PAIR
    update_checksums(result)

    changed = [
        index for index, (before, after) in enumerate(zip(source, result))
        if before != after
    ]
    allowed = {0x14D, 0x14E, 0x14F}
    for start, size in (
        (front, len(NEW_FRONT)),
        (selector, len(GUARDED_STUB)),
        (relocated, len(SELECTOR)),
        (pair, len(NEW_PAIR)),
    ):
        allowed.update(range(start, start + size))
    if not set(changed) <= allowed:
        raise AssertionError("candidate changed outside its exact patch regions")

    return bytes(result), {
        "old_selector_references": [f"bank13:${value:04X}" for value in old_selector_refs],
        "new_selector_address": "bank13:$6EDD",
        "guard_address": "bank13:$570E",
        "wrapper_first_call": "bank13:$6F20 CALL $570E",
        "bank16_unchanged": source[16 * 0x4000:17 * 0x4000]
        == bytes(result[16 * 0x4000:17 * 0x4000]),
        "changed_offsets": [hex(value) for value in changed],
    }


def main() -> int:
    candidate, evidence = build(BASE.read_bytes())
    OUT.mkdir(exist_ok=True)
    target = OUT / "candidate.gb"
    if target.exists() and target.read_bytes() != candidate:
        raise ValueError("immutable candidate collision")
    target.write_bytes(candidate)
    receipt = {
        "schema": "penta-stage7-guarded-services-r467-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": digest(candidate),
        "scope": (
            "exact scene $08 returns before the Stage-1 art loader and "
            "death/story service; all other scenes retain the original calls"
        ),
        "evidence": evidence,
    }
    (OUT / "build-receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
