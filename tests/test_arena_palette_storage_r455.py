"""Execute the new LUT loader; assert unrelated tables remain on old path."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import compose_arena_palette_storage_r455 as build


def execute_loader(page):
    code = build.loader()
    memory = bytearray([0xAA]) * 65536
    for p, fn in build.TABLE_BUILDERS.items():
        memory[p << 8:(p << 8) + 256] = bytes(fn())
    pc, a, b, hl, de, z = 0, 0, 0, page << 8, 0, False
    writes = []
    for _ in range(2000):
        op = code[pc]
        pc += 1
        if op == 0x3E:
            a = code[pc]; pc += 1
        elif op == 0xEA:
            address = int.from_bytes(code[pc:pc+2], "little"); pc += 2
            memory[address] = a; writes.append(address)
        elif op == 0x7C:
            a = hl >> 8
        elif op == 0xFE:
            z = a == code[pc]; pc += 1
        elif op in (0x28, 0x20):
            distance = int.from_bytes(code[pc:pc+1], "little", signed=True); pc += 1
            if z if op == 0x28 else not z:
                pc += distance
        elif op in (0x11, 0x21):
            value = int.from_bytes(code[pc:pc+2], "little"); pc += 2
            if op == 0x11: de = value
            else: hl = value
        elif op == 0x06:
            b = code[pc]; pc += 1
        elif op == 0x2A:
            a = memory[hl]; hl = (hl + 1) & 65535
        elif op == 0x12:
            memory[de] = a; writes.append(de)
        elif op == 0x13:
            de = (de + 1) & 65535
        elif op == 0x05:
            b = (b - 1) & 255; z = b == 0
        elif op == 0xC9:
            return memory, writes, hl, a
        else:
            raise AssertionError(f"unmodeled opcode {op:02X}")
    raise AssertionError("loader never returned")


class ArenaPaletteStorage(unittest.TestCase):
    def test_each_arena_only_repairs_declared_tables(self):
        for page in range(0x72, 0x7B):
            memory, writes, hl, a = execute_loader(page)
            self.assertEqual(a, 13, "return mapper must restore bank13")
            self.assertEqual(memory[0xDF02], 0x5A)
            if page in build.TABLE_BUILDERS:
                self.assertEqual(memory[0xC600:0xC700], bytes(build.TABLE_BUILDERS[page]()))
                self.assertEqual(writes, [0xDF02] + list(range(0xC600, 0xC700)))
                self.assertEqual(hl, 0xC600, "existing loop must self-copy")
            else:
                self.assertEqual(writes, [0xDF02])
                self.assertEqual(hl, page << 8)

    @unittest.skipUnless(build.BASE.is_file(), "local candidate unavailable")
    def test_only_owned_bytes_change_and_old_executable_tables_remain(self):
        source = build.BASE.read_bytes()
        result, site = build.build(source)
        allowed = {0x14D, 0x14E, 0x14F} | set(range(site, site + 7))
        for address, length in ((0x6C80, 10), (0x6E00, len(build.dispatch())),
                                (0x6E40, len(build.loader())),
                                (0x7300, 256), (0x7400, 256), (0x7700, 256)):
            start = build.off(23, address)
            allowed.update(range(start, start + length))
        changed = {i for i, (a,b) in enumerate(zip(source, result)) if a != b}
        self.assertLessEqual(changed, allowed)
        self.assertEqual(result[13*16384 + 0x3200:14*16384], source[13*16384 + 0x3200:14*16384])
        self.assertEqual(result[site + 7:site + 9], source[site + 7:site + 9])
