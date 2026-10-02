"""Execute the new LUT loader; assert unrelated tables remain on old path."""
from pathlib import Path
import hashlib
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import compose_arena_palette_storage_r455 as build
import arena_palette_storage as storage

STREAM_DESCENDANTS = (
    "22b3909b5ef3653abb1a40d227c2f9f0d6d6a276010ca08299af1c688eb15e6c",
    "e2473cbaf4060896afaa7f30b5fc250729887ae02cc12cb15f183ea3bfa09405",
    "7130c04a3ef9ad9239ae693dad9d5d61953437fa3eccc0c137071b79faeacc23",
    "3c5951bf86f429f2d6299ea68704514672b5e90d4726572b8c2981bd2963b73e",
    "b902240052bcdf743dbf4583edcc52b4584b5eae3757c613100238c934483df9",
    "d270fe0fa2359ac86cd4df0d06dca1071ef821e325a4a3cc51a44f698b21b8b6",
    "eebf3f190d9d307cb1d3fa714fa2e68b7890fc5309d5da26682ce38cce0134fc",
)


class StreamDescendantOracle(unittest.TestCase):
    """#30: synthetic layout tests, not ROM or gameplay qualification."""

    def test_descendants_read_relocated_tables_and_reject_corruption(self):
        for identity in STREAM_DESCENDANTS:
            for target in (1, 2, 5):
                with self.subTest(identity=identity, target=target):
                    rom = bytearray(1024 * 1024)
                    expected = bytes(build.TABLE_BUILDERS[0x72 + target]())
                    offset = 23 * 0x4000 + 0x3200 + target * 0x100
                    rom[offset:offset + 256] = expected
                    with patch.object(storage.hashlib, "sha256") as digest:
                        digest.return_value.hexdigest.return_value = identity
                        self.assertEqual(storage.arena_palette_table(bytes(rom), target), expected)
                        rom[offset] ^= 1
                        with self.assertRaisesRegex(ValueError, "differs from its builder"):
                            storage.arena_palette_table(bytes(rom), target)

    def test_descendants_use_cold_penta_and_preserve_ted_instruction_guard(self):
        import generate_stream_boss_states as generator
        for identity in STREAM_DESCENDANTS:
            with self.subTest(identity=identity):
                self.assertIn(identity, generator.PENTA_SYNC_INHERITORS_SHA256)
                rom = bytearray(1024 * 1024)
                rom[0x44364:0x44366] = bytes.fromhex("e072")
                with patch.object(generator.hashlib, "sha256") as digest:
                    digest.return_value.hexdigest.return_value = identity
                    self.assertTrue(generator.relocated_ted_latches(bytes(rom)))
                    rom[0x44365] ^= 1
                    with self.assertRaisesRegex(ValueError, "Ted latch relocation changed"):
                        generator.relocated_ted_latches(bytes(rom))


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
    def test_ted_reinstall_layout_preserves_selector_and_all_tables(self):
        from expansion_bank23_r456 import expected_bank23
        trial = ROOT/'tmp/ted-menu-reinstall-trial-01/candidate.gb'
        parent = ROOT/'tmp/sara-atomic-pose-source-16/candidate.gb'
        if not trial.is_file() or not parent.is_file():
            self.skipTest('local candidates unavailable')
        rom, source = trial.read_bytes(), parent.read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903')
        self.assertEqual(hashlib.sha256(source).hexdigest(),
                         '4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5')
        self.assertEqual(rom[23*16384:24*16384], expected_bank23())
        self.assertEqual(rom[23*16384:24*16384], source[23*16384:24*16384])
        self.assertEqual(rom[0x36FD5:0x36FE1], source[0x36FD5:0x36FE1])
        import generate_stream_boss_states as generator
        for bank in (17,24,25,26,27,29,30,31):
            self.assertEqual(rom[bank*16384:(bank+1)*16384],source[bank*16384:(bank+1)*16384])
        self.assertEqual(rom[0x1A2B:0x1A80],source[0x1A2B:0x1A80])
        self.assertIn(hashlib.sha256(rom).hexdigest(),generator.PENTA_SYNC_INHERITORS_SHA256)
        self.assertTrue(generator.relocated_ted_latches(rom))
        for target in range(9):
            self.assertEqual(storage.arena_palette_table(rom,target),
                             storage.arena_palette_table(source,target))
        # Keep identity constant to exercise the independent content check.
        damaged=bytearray(rom);damaged[23*16384+0x3300] ^= 1
        with patch.object(storage.hashlib,'sha256') as digest:
            digest.return_value.hexdigest.return_value='4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903'
            with self.assertRaisesRegex(ValueError,'differs from its builder'):
                storage.arena_palette_table(bytes(damaged),1)

    def test_select_trial02_layout_against_source_and_recognized_parent(self):
        from expansion_bank23_r456 import expected_bank23
        trial = ROOT/'tmp/select-buffer-trial-02/candidate.gb'
        parent = ROOT/'tmp/sara-atomic-pose-source-16/candidate.gb'
        if not trial.is_file() or not parent.is_file():
            self.skipTest('local candidates unavailable')
        rom, source = trial.read_bytes(), parent.read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '7c5afca573b80fefacfa057338ae8847bb86590f057a188112773076841972ec')
        self.assertEqual(hashlib.sha256(source).hexdigest(),
                         '4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5')
        self.assertEqual(rom[23*16384:24*16384], expected_bank23())
        self.assertEqual(rom[23*16384:24*16384], source[23*16384:24*16384])
        self.assertEqual(rom[17*16384:18*16384], source[17*16384:18*16384])
        from generate_stream_boss_states import relocated_ted_latches
        self.assertTrue(relocated_ted_latches(rom))
        start = 13*16384+0x2FD5
        self.assertEqual(rom[start:start+12], source[start:start+12])
        self.assertEqual(rom[start+3:start+10], bytes.fromhex('2E003E17CD4708'))
        for target in range(9):
            self.assertEqual(storage.arena_palette_table(rom,target),
                             storage.arena_palette_table(source,target))

    def test_retained_menu_trial_inherits_relocated_storage(self):
        from arena_palette_storage import arena_palette_table
        trial = ROOT / 'tmp/shalamar-menu-fades-trial-08/candidate.gb'
        parent = ROOT / 'tmp/sara-atomic-pose-source-16/candidate.gb'
        if not trial.is_file() or not parent.is_file():
            self.skipTest('local immutable menu trial/parent unavailable')
        candidate, source = trial.read_bytes(), parent.read_bytes()
        self.assertEqual(hashlib.sha256(candidate).hexdigest(),
                         'f02af88218fb6ae2fa12f7548549e9a5250c0bbb20cea5a8d2e77443ddad9379')
        for bank in (13, 23):
            self.assertEqual(candidate[bank*16384:(bank+1)*16384],
                             source[bank*16384:(bank+1)*16384])
        for page, fn in build.TABLE_BUILDERS.items():
            self.assertEqual(arena_palette_table(candidate, page-0x72), bytes(fn()))

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
