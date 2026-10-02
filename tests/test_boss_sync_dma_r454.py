"""Execute the emitted guard for every scene and LCD/latch combination."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import compose_boss_sync_dma_r454 as build


def execute(scene, lcdc, latch, code=None):
    code = build.service() if code is None else code
    pc, a, z, carry = 0, 0, False, False
    io = {0x40: lcdc, 0xC4: latch}
    for _ in range(30):
        op = code[pc]
        pc += 1
        if op == 0xFA:
            assert code[pc:pc+2] == b"\x80\xd8"
            a = scene
            pc += 2
        elif op in (0xD6, 0xFE):
            value = code[pc]
            pc += 1
            carry, z = a < value, a == value
            if op == 0xD6:
                a = (a - value) & 255
        elif op in (0xD2, 0xCA):
            target = int.from_bytes(code[pc:pc+2], "little")
            pc += 2
            if (not carry if op == 0xD2 else z):
                assert target == build.ENTRY + len(build.SYNC_PREFIX)
                return "sync", io[0xC4], a
        elif op == 0xF0:
            a = io[code[pc]]
            pc += 1
        elif op == 0xCB:
            assert code[pc] == 0x7F
            pc += 1
            z = not a & 128
        elif op == 0xE6:
            a &= code[pc]
            pc += 1
            z, carry = a == 0, False
        elif op == 0xE0:
            io[code[pc]] = a
            pc += 1
        elif op == 0x3E:
            a = code[pc]
            pc += 1
        elif op == 0xC9:
            return "defer", io[0xC4], a
        else:
            raise AssertionError(f"unmodeled opcode {op:02X}")
    raise AssertionError("guard did not terminate")


class BossSyncDma(unittest.TestCase):
    def test_exhaustive_scene_lcdc_latch_domain(self):
        for scene in range(256):
            for lcdc in (0, 0x80):
                for latch in range(256):
                    route, actual, a = execute(scene, lcdc, latch)
                    deferred = 3 <= scene <= 8 and lcdc == 0x80
                    self.assertEqual(route, "defer" if deferred else "sync")
                    self.assertEqual(actual, latch & 0xF7 if deferred else latch)
                    if deferred:
                        self.assertEqual(a, 1, "mapper must restore bank 1")

    def test_wrong_scene_bound_is_detected(self):
        bad = bytearray(build.service())
        self.assertEqual(bad[6], 6)
        bad[6] = 0x20
        self.assertEqual(execute(0x14, 0x80, 0x9F, bad)[0], "defer")
        self.assertEqual(execute(0x14, 0x80, 0x9F)[0], "sync")
