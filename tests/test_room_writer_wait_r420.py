import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_room_writer_wait_r420 as r


class RoomWriterWait(unittest.TestCase):
    def test_exact_scope(self):
        source = r.BASE.read_bytes()
        candidate = r.build(source)
        allowed = {0, 1, 0x14D, 0x14E, 0x14F}
        allowed.update(range(r.ENTRY, r.ENTRY + 3))
        allowed.update(range(r.OFFSET, r.OFFSET + len(r.CODE)))
        self.assertTrue(all(i in allowed for i, (a, b) in
                            enumerate(zip(source, candidate)) if a != b))
        self.assertEqual(candidate[r.PACK_OFFSET:r.PACK_OFFSET+len(r.PACK)], r.PACK)
        with self.assertRaises(ValueError):
            r.build(candidate)

    def test_emitted_helper_stack_store_and_wait(self):
        # Execute the emitted helper, including branch displacements. Simulate
        # asynchronous completion on the third READY read, not on room writes.
        for stage in range(7):
            for incoming in (0, 1, 3, 5, 255):
                for pending in (0, 0x48):
                    pc, sp, hl, a, z = 0, 0xDFF0, 0xABCD, 21, False
                    mem = {0xDFF5: incoming, 0xFFBA: stage,
                           0xFFC4: pending, 0xFFBD: 3}
                    reads = 0
                    for _ in range(100):
                        op = r.CODE[pc]; pc += 1
                        if op == 0xE5:
                            sp -= 2; mem[sp] = hl & 255; mem[sp+1] = hl >> 8
                        elif op == 0xF0:
                            address = 0xFF00 + r.CODE[pc]; pc += 1
                            if address == 0xFFC4:
                                reads += 1
                                if reads == 3: mem[address] = 0
                            a = mem[address]
                        elif op == 0xFE:
                            z = a == r.CODE[pc]; pc += 1
                        elif op == 0x20:
                            offset = r.CODE[pc]; pc += 1
                            if not z: pc += offset if offset < 128 else offset-256
                        elif op == 0xCB:
                            self.assertEqual(r.CODE[pc], 0x77); pc += 1
                            z = not (a & 0x40)
                        elif op == 0xF8:
                            hl = sp + r.CODE[pc]; pc += 1
                        elif op == 0x7E:
                            a = mem[hl]
                        elif op == 0xE0:
                            address = 0xFF00 + r.CODE[pc]; pc += 1
                            if stage == 6: self.assertFalse(mem[0xFFC4] & 0x40)
                            mem[address] = a
                        elif op == 0xC3:
                            self.assertEqual(r.CODE[pc:pc+2], bytes.fromhex('83 6C'))
                            break
                        else:
                            self.fail(f'unexpected opcode {op:02x}')
                    else: self.fail('helper did not terminate')
                    self.assertEqual(mem[0xFFBD], incoming)
                    self.assertEqual(a, stage)
                    self.assertEqual(sp, 0xDFEE)
                    self.assertEqual(mem[sp] + 256*mem[sp+1], 0xABCD)
                    self.assertEqual(reads, (3 if pending else 1) if stage == 6 else 0)


if __name__ == '__main__':
    unittest.main()
