#!/usr/bin/env python3
"""Static footprint and instruction-level tests for experimental r517."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "r517", HERE / "compose_ending_bgp_handoff_r517.py"
)
assert SPEC and SPEC.loader
r476 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r476)

source = r476.BASE.read_bytes()
candidate, receipt = r476.build(source)
body_offset = r476.off(r476.CAVE_BANK, r476.BODY)
body = candidate[body_offset:body_offset + int(receipt["body_len"])]
labels = {name: int(address, 16) for name, address in receipt["labels"].items()}
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


# Exact, disjoint patch footprint.
allowed = set(range(body_offset, body_offset + len(body))) | {0x14D, 0x14E, 0x14F}
postfinal_offset = r476.off(1, r476.POSTFINAL_SCENE)
allowed.update(range(postfinal_offset, postfinal_offset + 6))
postfinal_entry_offset = r476.off(r476.CAVE_BANK, r476.POSTFINAL_BANK20_ENTRY)
allowed.update(range(postfinal_entry_offset, postfinal_entry_offset + 3))
allowed.update(range(r476.CREDITS_FADE_CALL, r476.CREDITS_FADE_CALL + 3))
allowed.update(range(r476.CREDITS_FADE_WRAPPER, r476.CREDITS_FADE_WRAPPER + 6))
credits_entry_offset = r476.off(
    r476.CAVE_BANK, r476.CREDITS_FADE_BANK20_CONT
)
allowed.update(range(credits_entry_offset, credits_entry_offset + 4))
allowed.update(range(
    r476.CREDITS_FADE_OUT_CALL, r476.CREDITS_FADE_OUT_CALL + 3
))
allowed.update(range(r476.STORY_FADE_OUT_CALL, r476.STORY_FADE_OUT_CALL + 3))
allowed.update(range(r476.STORY_FADE_IN_JUMP, r476.STORY_FADE_IN_JUMP + 3))
allowed.update(range(
    r476.STORY_COMBINED_FADE_OUT_CALL,
    r476.STORY_COMBINED_FADE_OUT_CALL + 3,
))
allowed.update(range(
    r476.EPILOGUE_COMBINED_FADE_OUT_CALL,
    r476.EPILOGUE_COMBINED_FADE_OUT_CALL + 3,
))
allowed.update(range(r476.EPILOGUE_FADE_OUT_CALL,
                     r476.EPILOGUE_FADE_OUT_CALL + 3))
allowed.update(range(r476.STORY_FADE_WRAPPER, r476.STORY_FADE_WRAPPER + 6))
story_entry_offset = r476.off(r476.CAVE_BANK, r476.STORY_FADE_BANK20_CONT)
allowed.update(range(story_entry_offset, story_entry_offset + 4))
for bank in (13, 16):
    palette_hook_offset = r476.off(bank, r476.PALETTE_PUBLISHER)
    palette_stub_offset = r476.off(bank, r476.PALETTE_RESUME_STUB)
    allowed.update(range(palette_hook_offset, palette_hook_offset + 8))
    allowed.update(range(palette_stub_offset, palette_stub_offset + 4))
palette_entry_offset = r476.off(r476.CAVE_BANK, r476.PALETTE_BANK20_ENTRY)
allowed.update(range(palette_entry_offset, palette_entry_offset + 3))
switch = bytes((0x3E, r476.CAVE_BANK, 0xEA, 0x00, 0x21, 0x00))
for name, (address, _preimage, _continuation, entry) in r476.SITES.items():
    for bank in (13, 16):
        offset = r476.off(bank, address)
        allowed.update(range(offset, offset + 6))
        check(candidate[offset:offset + 6] == switch,
              f"{name} bank {bank} switch differs")
    entry_offset = r476.off(r476.CAVE_BANK, entry)
    allowed.update(range(entry_offset, entry_offset + 3))
    expected = labels[name.lower()]
    check(candidate[entry_offset] == 0xC3, f"{name} entry is not JP")
    check(int.from_bytes(candidate[entry_offset + 1:entry_offset + 3], "little") == expected,
          f"{name} entry target differs")
changed = {
    index for index, (before, after) in enumerate(zip(source, candidate))
    if before != after
}
check(changed <= allowed,
      f"unexpected changed offsets: {sorted(hex(x) for x in changed - allowed)[:8]}")
check(r476.BODY + len(body) <= min(site[3] for site in r476.SITES.values()),
      "body overlaps the bank-20 story entry stubs")
check(hashlib.sha256(candidate).hexdigest() == receipt["candidate_sha256"],
      "candidate digest differs")

check(candidate[0x0F5A:0x0F66] == source[0x0F5A:0x0F66],
      "native BG fade was changed")
check(candidate[0x73BA:0x73BD] == source[0x73BA:0x73BD]
      == bytes.fromhex("CD 51 0F"), "pre-final fade caller was changed")
check(candidate[0x74F1:0x74F4] == source[0x74F1:0x74F4]
      == bytes.fromhex("CD 51 0F"), "bank-1 fade caller was changed")
check(candidate[r476.CREDITS_FADE_CALL:r476.CREDITS_FADE_CALL + 3]
      == bytes((0xCD, r476.CREDITS_FADE_WRAPPER & 0xFF,
                r476.CREDITS_FADE_WRAPPER >> 8)),
      "credits fade caller does not use its private trampoline")
check(candidate[r476.CREDITS_FADE_WRAPPER:r476.CREDITS_FADE_WRAPPER + 6]
      == bytes.fromhex("F5 3E 14 CD 61 00"),
      "credits fade mapper trampoline differs")
check(candidate[credits_entry_offset:credits_entry_offset + 2]
      == bytes.fromhex("F1 C3")
      and int.from_bytes(candidate[credits_entry_offset + 2:credits_entry_offset + 4], "little")
      == labels["credits_fade_dispatch"], "credits bank-20 entry differs")
check(candidate[r476.CREDITS_FADE_OUT_CALL:r476.CREDITS_FADE_OUT_CALL + 3]
      == bytes((0xCD, r476.CREDITS_FADE_OUT_WRAPPER & 0xFF,
                r476.CREDITS_FADE_OUT_WRAPPER >> 8)),
      "credits fade-out caller does not use its private trampoline")
check(r476.CREDITS_FADE_OUT_WRAPPER == r476.CREDITS_FADE_WRAPPER,
      "credits callers no longer share one mapper trampoline")
check(candidate[r476.STORY_FADE_OUT_CALL:r476.STORY_FADE_OUT_CALL + 3]
      == bytes((0xCD, r476.STORY_FADE_WRAPPER & 0xFF,
                r476.STORY_FADE_WRAPPER >> 8)),
      "story fade-out caller does not use synchronized trampoline")
check(candidate[r476.STORY_FADE_IN_JUMP:r476.STORY_FADE_IN_JUMP + 3]
      == bytes((0xC3, r476.STORY_FADE_WRAPPER & 0xFF,
                r476.STORY_FADE_WRAPPER >> 8)),
      "story fade-in tail jump does not use synchronized trampoline")
check(candidate[
          r476.STORY_COMBINED_FADE_OUT_CALL:
          r476.STORY_COMBINED_FADE_OUT_CALL + 3
      ] == bytes((0xCD, r476.STORY_FADE_WRAPPER & 0xFF,
                  r476.STORY_FADE_WRAPPER >> 8)),
      "story combined fade-out does not use synchronized trampoline")
check(candidate[
          r476.EPILOGUE_COMBINED_FADE_OUT_CALL:
          r476.EPILOGUE_COMBINED_FADE_OUT_CALL + 3
      ] == bytes((0xCD, r476.STORY_FADE_WRAPPER & 0xFF,
                  r476.STORY_FADE_WRAPPER >> 8)),
      "epilogue combined fade-out does not use synchronized trampoline")
check(candidate[r476.EPILOGUE_FADE_OUT_CALL:r476.EPILOGUE_FADE_OUT_CALL + 3]
      == bytes((0xCD, r476.STORY_FADE_WRAPPER & 0xFF,
                r476.STORY_FADE_WRAPPER >> 8)),
      "epilogue fade-out does not use synchronized trampoline")
check(candidate[r476.STORY_FADE_WRAPPER:r476.STORY_FADE_WRAPPER + 6]
      == bytes.fromhex("F5 3E 14 CD 61 00"),
      "story fade mapper trampoline differs")
check(candidate[story_entry_offset:story_entry_offset + 2]
      == bytes.fromhex("F1 C3")
      and int.from_bytes(candidate[story_entry_offset + 2:story_entry_offset + 4], "little")
      == labels["story_fade_dispatch"], "story bank-20 entry differs")
for bank in (13, 16):
    loader_offset = r476.off(bank, 0x6900)
    check(candidate[loader_offset:loader_offset + 6]
          == source[loader_offset:loader_offset + 6],
          f"bank {bank} native palette-loader head was changed")
    palette_hook_offset = r476.off(bank, r476.PALETTE_PUBLISHER)
    check(candidate[palette_hook_offset:palette_hook_offset + 8]
          == bytes((0x3E, bank, 0xF5, 0x3E, r476.CAVE_BANK,
                    0xCD, r476.FIXED_SWITCH & 0xFF,
                    r476.FIXED_SWITCH >> 8)),
          f"bank {bank} palette mapper handoff differs")
    palette_stub_offset = r476.off(bank, r476.PALETTE_RESUME_STUB)
    check(candidate[palette_stub_offset:palette_stub_offset + 4]
          == bytes((0xE1, 0xC3, r476.PALETTE_QUAD_WRITE & 0xFF,
                    r476.PALETTE_QUAD_WRITE >> 8)),
          f"bank {bank} palette source-resume stub differs")
    palette_tail_offset = r476.off(bank, r476.PALETTE_QUAD_WRITE)
    check(candidate[palette_tail_offset:palette_tail_offset + 9]
          == source[palette_tail_offset:palette_tail_offset + 9]
          == bytes.fromhex("2A E2 2A E2 2A E2 2A E2 C9"),
          f"bank {bank} native palette source tail changed")
check(candidate[palette_entry_offset] == 0xC3
      and int.from_bytes(candidate[palette_entry_offset + 1:palette_entry_offset + 3],
                         "little") == labels["palette_guard"],
      "bank-20 palette guard entry differs")
check(candidate[0x0F66:0x0F79] == source[0x0F66:0x0F79],
      "native OBP fade was changed")
check(candidate[postfinal_offset:postfinal_offset + 6]
      == bytes((0xF5, 0x3E, r476.CAVE_BANK, 0xEA, 0x00, 0x21)),
      "post-final scene handoff differs")
check(candidate[postfinal_entry_offset] == 0xC3
      and int.from_bytes(candidate[postfinal_entry_offset + 1:postfinal_entry_offset + 3], "little")
      == labels["postfinal_blank"], "post-final bank-20 entry differs")
check(candidate[0x0F7A:0x0FC0] == source[0x0F7A:0x0FC0],
      "native combined BG/OBJ fades were changed")

deck = (
    source[r476.off(13, 0x6800):r476.off(13, 0x6838)]
    + source[r476.off(13, 0x68F8):r476.off(13, 0x6900)]
)
check(deck[56:64] == bytes.fromhex("ff7f107e00380000"),
      "tuned story BG7 source differs")
check(deck[56:64] != source[r476.off(13, 0x6838):r476.off(13, 0x6840)],
      "test no longer distinguishes tuned BG7 from raw alias")

# The post-final preblank has the only matched SVBK1 pair.
executable = body[:labels["restore_order"] - r476.BODY]
check(b"\xE0\x99" not in executable, "payload writes FF99")
check(executable.count(b"\xE0\x70") == 2,
      "payload SVBK selector/restore footprint differs")


class Machine:
    def __init__(self, cram: bytes | bytearray, *, wram=None, hram=None,
                 advance_ffd4=False):
        self.cram = bytearray(cram)
        self.bcps = 0
        self.wram = dict(wram or {})
        self.hram = dict(hram or {})
        self.advance_ffd4 = advance_ffd4

    def read(self, address: int) -> int:
        if address < 0x4000:
            return source[address]
        if address == 0xFF68:
            return self.bcps
        if address == 0xFF69:
            return self.cram[self.bcps & 0x3F]
        if address == 0xFFD4 and self.advance_ffd4:
            self.hram[address] = min(4, self.hram.get(address, 0) + 1)
        if address >= 0xFF00:
            return self.hram.get(address, 0)
        return self.wram.get(address, 0)

    def write(self, address: int, value: int) -> None:
        value &= 0xFF
        if address == 0xFF68:
            self.bcps = value
        elif address == 0xFF69:
            self.cram[self.bcps & 0x3F] = value
            if self.bcps & 0x80:
                self.bcps = 0x80 | ((self.bcps + 1) & 0x3F)
        elif address >= 0xFF00:
            self.hram[address] = value
        else:
            self.wram[address] = value


def execute(machine: Machine, entry: int, *, regs=(0x05, 0x33, 0x44, 0x55, 0x66, 0x77), initial_a=0, initial_stack=None):
    a = initial_a
    b, c, d, e, h, l = regs
    f = 0
    pc = entry
    stack: list[tuple[str, object]] = list(initial_stack or [])
    cycles = 0

    def byte(address: int) -> int:
        if r476.BODY <= address < r476.BODY + len(body):
            return body[address - r476.BODY]
        raise AssertionError(f"instruction fetch escaped body at ${address:04X}")

    def set_cp(left: int, right: int) -> None:
        nonlocal f
        f = (0x80 if left == right else 0) | (0x10 if left < right else 0)

    def set_z(value: int) -> None:
        nonlocal f
        f = 0x80 if (value & 0xFF) == 0 else 0

    for _step in range(10000):
        op = byte(pc)
        cycles += {
            0xE0: 12, 0xF0: 12, 0xEA: 16, 0xFA: 16, 0xCD: 24,
            0xC2: 16, 0xC3: 16, 0xCA: 16, 0xD2: 16, 0xC9: 16, 0xC8: 12,
            0xD0: 12, 0xD8: 12, 0x20: 12, 0x28: 12, 0x30: 12,
            0x18: 12, 0x22: 8, 0x23: 8, 0x2A: 8, 0x56: 8, 0xCF: 16,
        }.get(op, 8)
        if op == 0xC5:
            stack.append(("bc", (b, c))); pc += 1
        elif op == 0xD5:
            stack.append(("de", (d, e))); pc += 1
        elif op == 0xE5:
            stack.append(("hl", (h, l))); pc += 1
        elif op == 0xF5:
            stack.append(("af", (a, f))); pc += 1
        elif op == 0xC1:
            kind, value = stack.pop(); assert kind == "bc"; b, c = value; pc += 1
        elif op == 0xD1:
            kind, value = stack.pop(); assert kind == "de"; d, e = value; pc += 1
        elif op == 0xE1:
            kind, value = stack.pop(); assert kind == "hl"; h, l = value; pc += 1
        elif op == 0xF1:
            kind, value = stack.pop(); assert kind == "af"; a, f = value; pc += 1
        elif op == 0x78:
            a = b; pc += 1
        elif op == 0x79:
            a = c; pc += 1
        elif op == 0x7A:
            a = d; pc += 1
        elif op == 0x7B:
            a = e; pc += 1
        elif op == 0x7E:
            address = (h << 8) | l
            a = (byte(address)
                 if r476.BODY <= address < r476.BODY + len(body)
                 else machine.read(address))
            pc += 1
        elif op == 0x57:
            d = a; pc += 1
        elif op == 0x4F:
            c = a; pc += 1
        elif op == 0x47:
            b = a; pc += 1
        elif op == 0x5E:
            e = machine.read((h << 8) | l) if not (r476.BODY <= (h << 8) | l < r476.BODY + len(body)) else byte((h << 8) | l); pc += 1
        elif op == 0x56:
            d = machine.read((h << 8) | l) if not (r476.BODY <= (h << 8) | l < r476.BODY + len(body)) else byte((h << 8) | l); pc += 1
        elif op == 0x54:
            d = h; pc += 1
        elif op == 0x5D:
            e = l; pc += 1
        elif op == 0x62:
            h = d; pc += 1
        elif op == 0x6B:
            l = e; pc += 1
        elif op == 0x3E:
            a = byte(pc + 1); pc += 2
        elif op == 0x06:
            b = byte(pc + 1); pc += 2
        elif op == 0x16:
            d = byte(pc + 1); pc += 2
        elif op == 0x1E:
            e = byte(pc + 1); pc += 2
        elif op == 0x21:
            l = byte(pc + 1); h = byte(pc + 2); pc += 3
        elif op == 0xFA:
            address = byte(pc + 1) | (byte(pc + 2) << 8)
            a = machine.read(address); pc += 3
        elif op == 0xEA:
            address = byte(pc + 1) | (byte(pc + 2) << 8)
            machine.write(address, a); pc += 3
        elif op == 0xF0:
            a = machine.read(0xFF00 | byte(pc + 1)); pc += 2
        elif op == 0xE0:
            machine.write(0xFF00 | byte(pc + 1), a); pc += 2
        elif op == 0xE2:
            machine.write(0xFF00 | c, a); pc += 1
        elif op == 0xFE:
            set_cp(a, byte(pc + 1)); pc += 2
        elif op == 0xB7:
            set_z(a); pc += 1
        elif op == 0xB8:
            set_cp(a, b); pc += 1
        elif op == 0xAF:
            a = 0; set_z(a); pc += 1
        elif op == 0xE6:
            a &= byte(pc + 1); set_z(a); pc += 2
        elif op == 0xF6:
            a |= byte(pc + 1); set_z(a); pc += 2
        elif op == 0xEE:
            a ^= byte(pc + 1); set_z(a); pc += 2
        elif op == 0x3C:
            a = (a + 1) & 0xFF; set_z(a); pc += 1
        elif op == 0x05:
            b = (b - 1) & 0xFF; set_z(b); pc += 1
        elif op == 0x07:
            a = ((a << 1) | (a >> 7)) & 0xFF; pc += 1
        elif op == 0x2A:
            address = (h << 8) | l
            a = byte(address) if r476.BODY <= address < r476.BODY + len(body) else machine.read(address)
            l += 1
            if l > 0xFF:
                l &= 0xFF; h = (h + 1) & 0xFF
            pc += 1
        elif op == 0x22:
            address = (h << 8) | l
            machine.write(address, a)
            l += 1
            if l > 0xFF:
                l &= 0xFF; h = (h + 1) & 0xFF
            pc += 1
        elif op == 0x23:
            value = ((h << 8) | l) + 1
            h, l = (value >> 8) & 0xFF, value & 0xFF
            pc += 1
        elif op in (0x20, 0x28, 0x30, 0x38, 0x18):
            delta = byte(pc + 1)
            if delta >= 0x80:
                delta -= 0x100
            take = {
                0x20: not bool(f & 0x80),
                0x28: bool(f & 0x80),
                0x30: not bool(f & 0x10),
                0x38: bool(f & 0x10),
                0x18: True,
            }[op]
            pc += 2
            if take:
                pc += delta
        elif op in (0xC2, 0xC3, 0xCA, 0xD2):
            target = byte(pc + 1) | (byte(pc + 2) << 8)
            take = {
                0xC3: True,
                0xC2: not bool(f & 0x80),
                0xCA: bool(f & 0x80),
                0xD2: not bool(f & 0x10),
            }[op]
            if not take:
                pc += 3
            elif target in (r476.FIXED_SWITCH, r476.FIXED_SWITCH_RET, 0x09BE):
                if target == 0x09BE:
                    machine.write(0xFF99, a)
                return {"exit": "switch", "bank": a, "stack": stack,
                        "regs": (b, c, d, e, h, l), "cycles": cycles + 56}
            else:
                pc = target
        elif op == 0xCD:
            target = byte(pc + 1) | (byte(pc + 2) << 8)
            stack.append(("ret", pc + 3)); pc = target
        elif op == 0xD7:                    # RST $10: HL += A
            value = ((h << 8) | l) + a
            h, l = (value >> 8) & 0xFF, value & 0xFF
            pc += 1
        elif op == 0xCF:                    # RST $08: BGP write + $10D5 tail
            machine.write(0xFF47, a)
            if machine.read(0xFFC1) != 0 and machine.read(0xFFE4) != 0:
                a = 0xE4
                machine.write(0xFF47, a)
            pc += 1
        elif op in (0xC0, 0xC8, 0xD0, 0xD8, 0xC9):
            take = {
                0xC0: not bool(f & 0x80),
                0xC8: bool(f & 0x80),
                0xD0: not bool(f & 0x10),
                0xD8: bool(f & 0x10),
                0xC9: True,
            }[op]
            if not take:
                pc += 1
            elif not stack:
                return {"exit": "ret", "bank": None, "stack": stack,
                        "regs": (b, c, d, e, h, l), "cycles": cycles}
            else:
                kind, value = stack.pop(); assert kind == "ret", (op, kind)
                pc = int(value)
        else:
            raise AssertionError(f"unhandled opcode ${op:02X} at ${pc:04X}")
    raise AssertionError("instruction runner exceeded step bound")


CRAM0 = bytes(((index * 37) + 11) & 0xFF for index in range(64))


def service(name: str, machine: Machine):
    return execute(machine, labels[name])


def set_context(machine: Machine, *, bgp=0xE4, ffd4=0, ffe4=1, d880=0x1A,
                d889=1, dce2=0, dce8=5, fff9=0, dcf0=5, row=0):
    machine.hram.update({0xFF47: bgp, 0xFFE4: ffe4, 0xFFF9: fff9,
                         0xFFD4: ffd4, 0xFF99: 0x0D})
    machine.wram.update({0xD880: d880, 0xD889: d889, 0xDCE2: dce2,
                         0xDCE8: dce8, 0xDCF0: dcf0, r476.ROW: row})


# The shared publisher guard preserves BC/DE and returns to the source bank.
# Suppressed paths advance four source bytes directly; native paths stack both
# the live HL and the $71F0 resume address so the untouched source-bank tail
# performs the actual ROM reads and CRAM writes after the mapper RET.
for d880, d889, bgp, suppress in (
    (0x16, 1, 0xE4, True),
    (0x1A, 1, 0xFF, True),
    (0x1A, 1, 0xE4, False),
    (0x00, 0x0C, 0xFF, True),
    (0x00, 0x0C, 0xE4, False),
    (0x0D, 1, 0xFF, False),
):
    m = Machine(CRAM0, wram={0xC000: 0x11, 0xC001: 0x22,
                             0xC002: 0x33, 0xC003: 0x44})
    set_context(m, d880=d880, d889=d889, bgp=bgp)
    m.hram[0xFF40] = 0x00
    m.bcps = 0x80
    result = execute(
        m,
        labels["palette_guard"],
        regs=(0x05, 0x69, 0x44, 0x55, 0xC0, 0x00),
        initial_a=r476.CAVE_BANK,
        initial_stack=[("af", (0x0D, 0x00))],
    )
    expected_stack = (
        [] if suppress else
        [("hl", (0xC0, 0x00)), ("hl", (0x71, 0xF0))]
    )
    check(result["exit"] == "switch" and result["bank"] == 0x0D
          and result["stack"] == expected_stack,
          f"palette guard did not restore bank13 for {d880:02X}/{bgp:02X}")
    expected_hl = (0xC0, 0x04) if suppress else (0x71, 0xF0)
    check(result["regs"] == (0x05, 0x69, 0x44, 0x55, *expected_hl),
          f"palette guard register/source ABI drifted for {d880:02X}/{bgp:02X}")
    check(bytes(m.cram) == CRAM0,
          f"bank-20 guard read CRAM or source ROM for {d880:02X}/{bgp:02X}")


# Fade values: exact mirrors, cheap idempotence, and sub-frame changed paths.
m = Machine(CRAM0); set_context(m, bgp=0xFF)
first = service("mirror_story", m)
check(m.cram == bytes(64) and m.wram[r476.STATE] == r476.MIRROR_FF,
      "FF did not make all BG palettes black")
check(first["cycles"] < 5500, f"FF mirror too expensive: {first['cycles']} T")
steady = service("mirror_story", m)
check(m.cram == bytes(64) and steady["cycles"] < 500,
      f"steady FF path is not cheap: {steady['cycles']} T")

m = Machine(CRAM0, wram={r476.STATE: r476.MIRROR_FF})
set_context(m, bgp=0xFF, d880=0x1A, fff9=0)
m.bcps = 0x95
service("mirror_story", m)
check(m.cram == bytes(64) and m.bcps == 0x95,
      "post-final story did not reassert overwritten black or restore BCPS")

m.hram[0xFF47] = 0xFE
fe = service("mirror_story", m)
check(m.cram == bytes.fromhex("4a29000000000000") * 8,
      "FE mirror differs from DMG row")
check(fe["cycles"] < 5500, f"FE mirror too expensive: {fe['cycles']} T")
m.hram[0xFF47] = 0xF9
f9 = service("mirror_story", m)
check(m.cram == bytes.fromhex("94524a2900000000") * 8,
      "F9 mirror differs from DMG row")
check(f9["cycles"] < 5500, f"F9 mirror too expensive: {f9['cycles']} T")

# The fixed credits caller remains active after FFF9 selects the END page;
# that context must use the full eight-row ending mirror rather than BG1 only.
m = Machine(CRAM0); set_context(m, fff9=1, d880=0x16)
execute(m, labels["mirror_credits_value"], initial_a=0xFE)
check(m.cram == bytes.fromhex("4a29000000000000") * 8,
      "FFF9 END fade was routed through the credits-only BG1 mirror")

# Credits reassert black exactly once only after the native loader has
# overwritten the first FF fill; BCPS is restored and E4 can reveal normally.
m = Machine(CRAM0, wram={r476.STATE: r476.MIRROR_FF})
set_context(m, bgp=0xFF, d880=0x16, fff9=0, row=r476.ENDING_DONE_ROW)
m.bcps = 0x8A
service("mirror_ending", m)
check(m.cram == bytes(64)
      and m.wram[r476.STATE] == r476.CREDITS_BLACK_SETTLED
      and m.bcps == 0x8A,
      "credits did not settle overwritten CRAM to black or restore BCPS")
m.hram[0xFF47] = 0xE4
service("mirror_ending", m)
check(m.wram[r476.STATE] == r476.ENDING_RESTORE + 1,
      "settled credits black did not advance into page reveal")

m = Machine(bytes(64), wram={r476.STATE: r476.MIRROR_FF})
set_context(m, bgp=0xFF, d880=0x16, fff9=0)
service("mirror_ending", m)
check(m.wram[r476.STATE] == r476.MIRROR_FF and m.cram == bytes(64),
      "credits marked an already-black CRAM deck as overwritten")

for bgp, marker, row in (
    (0x00, r476.MIRROR_00, "ff7fff7fff7fff7f"),
    (0x40, r476.MIRROR_40, "ff7fff7fff7f9452"),
    (0x84, r476.MIRROR_84, "ff7f9452ff7f4a29"),
    (0x90, r476.MIRROR_90, "ff7fff7f94524a29"),
    (0xC4, r476.MIRROR_C4, "ff7f9452ff7f0000"),
    (0xD9, r476.MIRROR_D9, "94524a2994520000"),
    (0xEE, r476.MIRROR_EE, "4a2900004a290000"),
):
    m = Machine(CRAM0); set_context(m, bgp=bgp)
    generic = service("mirror_story", m)
    check(m.cram == bytes.fromhex(row) * 8 and m.wram[r476.STATE] == marker,
          f"BGP ${bgp:02X} mirror differs from its DMG row")
    check(generic["cycles"] < 5500,
          f"BGP ${bgp:02X} generic mirror too expensive: {generic['cycles']} T")

# Art 5 reveal: exact BG0/BG2/tuned-BG7, temporary BG6->BG0 alias,
# then restore every unused row while retaining BG6->BG0 for the cleaner.
m = Machine(bytes.fromhex("94524a2900000000") * 8,
            wram={r476.STATE: r476.MIRROR_F9})
set_context(m, bgp=0xE4, dcf0=5)
service("mirror_story", m)
for slot in (0, 2, 7):
    check(m.cram[slot * 8:(slot + 1) * 8] == deck[slot * 8:(slot + 1) * 8],
          f"art 5 reveal missed BG{slot}")
check(m.cram[48:56] == deck[0:8], "art 5 BG6 alias is not BG0")
check(m.wram[r476.STATE] == r476.STORY_RESTORE,
      "art 5 did not arm incremental restore")
for _ in range(7):
    service("mirror_story", m)
check(m.wram[r476.STATE] == r476.STORY_RESTORE + 7,
      "story restore did not stop before BG6")
service("mirror_story", m)
aliased_deck = deck[:48] + deck[:8] + deck[56:]
check(m.wram[r476.STATE] == 0 and m.cram == aliased_deck,
      "story deck did not retain only the deliberate BG6->BG0 alias")

# Art 4 and art 7 immediate working sets.
for art, slots, alias6 in ((4, (0, 3, 4, 5), True),
                           (7, (0, 2, 6, 7), False)):
    m = Machine(bytes.fromhex("94524a2900000000") * 8,
                wram={r476.STATE: r476.MIRROR_F9})
    set_context(m, dcf0=art)
    service("mirror_story", m)
    for slot in slots:
        check(m.cram[slot * 8:(slot + 1) * 8] == deck[slot * 8:(slot + 1) * 8],
              f"art {art} reveal missed BG{slot}")
    if alias6:
        check(m.cram[48:56] == deck[0:8], "art 4 BG6 alias differs")
    else:
        for _ in range(8):
            service("mirror_story", m)
        check(m.wram[r476.STATE] == 0 and m.cram == deck,
              "art 7 did not settle to the exact full deck")

# Credits/END/epilogue keep all eight rows aliased to their sole visible owner
# for the page lifetime. E7 is a normal raster state, not a gray request.
for d880, fff9, dce2, selected in (
    (0x16, 0, 0, 1), (0x16, 1, 0, 2), (0x00, 1, 0, 0), (0x00, 1, 1, 3),
):
    m = Machine(bytes.fromhex("94524a2900000000") * 8,
                wram={r476.STATE: r476.MIRROR_F9})
    set_context(m, bgp=0xE4, d880=d880, dce2=dce2, fff9=fff9,
                row=r476.ENDING_DONE_ROW)
    service("mirror_ending", m)
    check(m.cram == deck[selected * 8:(selected + 1) * 8] * 8,
          f"uniform ending reveal selected wrong BG row {selected}")
    visible_addresses = {
        0x9800 + row * 32 + column
        for row in range(18) for column in range(20)
    }
    if d880 == 0x16 and fff9 == 0:
        check(m.wram[r476.STATE] == r476.ENDING_RESTORE + 1,
              "credits did not arm its bounded row repair")
        for _ in range(17):
            service("mirror_ending", m)
        check(m.wram[r476.STATE] == r476.ENDING_WAIT
              and {m.wram.get(address) for address in visible_addresses} == {1}
              and m.hram.get(0xFF4F, 0) == 0,
              "credits did not publish the exact 20x18 BG1 page")
        padding = {
            0x9800 + row * 32 + column
            for row in range(18) for column in range(20, 32)
        }
        check(all(address not in m.wram for address in padding),
              "credits repair touched 32-column map padding")
    else:
        check(m.wram[r476.STATE] == r476.ENDING_WAIT
              and all(address not in m.wram for address in visible_addresses),
              f"ending row {selected} unexpectedly touched credits attributes")
    before = bytes(m.cram)
    for address in visible_addresses:
        m.wram.pop(address, None)
    m.hram[0xFF47] = 0xE7
    service("mirror_ending", m)
    check(bytes(m.cram) == before and m.wram[r476.STATE] == r476.ENDING_WAIT,
          "E7 changed CRAM or bypassed the row-completion wait")
    check(all(address not in m.wram for address in visible_addresses),
          f"ending row {selected} repeated the one-shot credits repair")
    m.wram[r476.ROW] = r476.ENDING_DONE_ROW
    for _ in range(8):
        service("mirror_ending", m)
    check(m.wram[r476.STATE] == r476.ENDING_WAIT and m.cram == before,
          f"ending row {selected} did not retain its uniform page alias")

m = Machine(bytes(64), wram={r476.STATE: r476.MIRROR_FF})
set_context(m, bgp=0xE7, d880=0x00, d889=0x0C, dce2=1, fff9=1)
service("mirror_ending", m)
check(m.cram == bytes(64) and m.wram[r476.STATE] == r476.MIRROR_FF,
      "transient epilogue raster BGP overwrote an active black fade deck")

# Site guards preserve caller registers and route exact continuations. A
# title-like S2 call cannot mutate CRAM even with garbage in the story state.
m = Machine(CRAM0, wram={r476.STATE: 0x7F, 0xDCE8: 2})
set_context(m, bgp=0xFF, ffe4=1, dce8=2)
site = execute(m, labels["s1"], regs=(2, 0x33, 0x44, 0x55, 0x66, 0x77))
targets = [((value[0] << 8) | value[1]) for kind, value in site["stack"] if kind == "hl"]
check(site["bank"] == 0x0D and targets[-1] == r476.SITES["S1"][2],
      "S1 opening did not route to exact continuation")
check(m.wram[r476.STATE] == 0 and m.cram == CRAM0,
      "S1 opening touched the CGB palette mirror")

m = Machine(CRAM0, wram={r476.STATE: 0x7F})
set_context(m, bgp=0xFF, ffe4=0, d880=0x16)
site = execute(m, labels["s2"])
targets = [((value[0] << 8) | value[1]) for kind, value in site["stack"] if kind == "hl"]
check(targets[-1] == r476.INACTIVE and m.cram == CRAM0
      and m.wram[r476.STATE] == 0x7F,
      "S2 title/other guard touched mirror state or missed inactive route")

print("PASS" if not failures else "FAIL")
for failure in failures:
    print("  -", failure)
print("body bytes", len(body))
print("candidate sha256", hashlib.sha256(candidate).hexdigest())
sys.exit(1 if failures else 0)
