"""Issue #6: the production central emitter publishes Sara as one quartet."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_v302_title_fix as build


def execute_tail(code, c, e):
    """Run the landed tail. EI must follow SRAM-off and precede the ADD."""
    a = flags = 0
    enabled = False
    stack = [c]
    pc = 0
    writes = []
    for _ in range(32):
        op = code[pc]
        pc += 1
        if op == 0xAF:
            a, flags = 0, 0x80
        elif op == 0xEA:
            addr = int.from_bytes(code[pc:pc + 2], "little")
            pc += 2
            writes.append((addr, a))
        elif op == 0x7B:
            a = e
        elif op == 0xFE:
            value = code[pc]
            pc += 1
            flags = 0x40 | (0x80 if a == value else 0) | (0x10 if a < value else 0)
        elif op == 0x38:
            rel = code[pc]
            pc += 1
            if flags & 0x10:
                pc += rel if rel < 128 else rel - 256
        elif op == 0xFB:
            enabled = True
        elif op == 0xC1:
            c = stack.pop()
        elif op == 0x79:
            a = c
        elif op == 0xC6:
            value = code[pc]
            pc += 1
            total = a + value
            flags = (
                (0x80 if total & 255 == 0 else 0)
                | (0x20 if (a & 15) + (value & 15) > 15 else 0)
                | (0x10 if total > 255 else 0)
            )
            a = total & 255
        elif op == 0x4F:
            c = a
        elif op == 0xC9:
            return a, flags, enabled, writes, c
        else:
            raise AssertionError(f"unexpected opcode {op:02X}")
    raise AssertionError("tail did not return")


class SaraEmitterAtomicityTests(unittest.TestCase):
    def test_production_image_matches_reviewed_trial(self):
        image = build.build_oam_central_emitter()
        self.assertEqual(image, build.ATOMIC_SARA_EMITTER)
        self.assertEqual(len(image), 60)
        self.assertNotEqual(image, build.TORN_SARA_EMITTER)
        # One EI, and only the carry skip can pass over it.
        self.assertEqual(image.count(0xFB), 1)
        ei = image.index(0xFB)
        self.assertEqual(image[ei - 2:ei], bytes((0x38, 0x01)))

    def test_palette_fold_matches_witch_versus_dragon(self):
        for form in range(256):
            palette = 1 + int(form < 1)
            self.assertEqual(palette, 2 if form == 0 else 1)

    def test_tail_defers_only_the_first_three_slots(self):
        image = build.build_oam_central_emitter()
        tail = image[image.index(bytes.fromhex("AFEAFF1F")):]
        for slot in range(40):
            returned, flags, enabled, writes, _ = execute_tail(
                tail, 0x20, 4 * (slot + 1)
            )
            self.assertEqual(writes, [(0x1FFF, 0)])
            self.assertEqual(enabled, slot >= 3)
            self.assertEqual(returned, 0x28)
            self.assertEqual(flags & 0x10, 0)

    def test_install_rewrites_both_live_banks_and_nothing_else(self):
        rom = bytearray(17 * 0x4000)
        rom[0x10D1:0x10D5] = bytes.fromhex("F3C321DA")
        for bank in (2, 13, 16):
            off = bank * 0x4000 + (build.OAM_CENTRAL_EMITTER_ADDR - 0x4000)
            rom[off:off + 60] = build.TORN_SARA_EMITTER
        untouched = rom[0x200:0x240]
        replaced = build.install_atomic_sara_emitters(rom)
        self.assertEqual(replaced, (2, 13, 16))
        for bank in (2, 13, 16):
            off = bank * 0x4000 + (build.OAM_CENTRAL_EMITTER_ADDR - 0x4000)
            self.assertEqual(rom[off:off + 60], build.ATOMIC_SARA_EMITTER)
        self.assertEqual(rom[0x200:0x240], untouched)
        build.write_global_checksum(rom)
        total = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
        self.assertEqual(rom[0x14E:0x150], total.to_bytes(2, "big"))

    def test_native_wrapper_is_not_rewritten(self):
        rom = bytearray(17 * 0x4000)
        rom[0x10D1:0x10D5] = bytes.fromhex("00000000")
        off = 13 * 0x4000 + (build.OAM_CENTRAL_EMITTER_ADDR - 0x4000)
        rom[off:off + 60] = build.TORN_SARA_EMITTER
        self.assertEqual(build.install_atomic_sara_emitters(rom), ())
        self.assertEqual(rom[off:off + 60], build.TORN_SARA_EMITTER)

    def test_reviewed_parent_rebuilds_the_trial_candidate(self):
        root = Path(__file__).resolve().parents[1]
        parent = root / "tmp/spike-death-trial-05/candidate.gb"
        candidate = root / "tmp/sara-atomic-pose-source-16/candidate.gb"
        if not parent.is_file() or not candidate.is_file():
            self.skipTest("retained trial ROMs are not in this checkout")
        rom = bytearray(parent.read_bytes())
        replaced = build.install_atomic_sara_emitters(rom)
        build.write_global_checksum(rom)
        self.assertEqual(replaced, (13, 16))
        self.assertEqual(bytes(rom), candidate.read_bytes())

    def test_missing_bank16_image_is_rejected(self):
        rom = bytearray(17 * 0x4000)
        rom[0x10D1:0x10D5] = bytes.fromhex("F3C321DA")
        off = 13 * 0x4000 + (build.OAM_CENTRAL_EMITTER_ADDR - 0x4000)
        rom[off:off + 60] = build.ATOMIC_SARA_EMITTER
        with self.assertRaises(AssertionError):
            build.install_atomic_sara_emitters(rom)


if __name__ == "__main__":
    unittest.main()
