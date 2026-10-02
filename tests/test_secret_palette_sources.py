"""Issue #23 palette-source patch guards; synthetic, asset-free fixtures."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

DIAGNOSTICS = Path(__file__).resolve().parents[1] / 'scripts/diagnostics'
with patch.object(sys, 'path', [str(DIAGNOSTICS), *sys.path]):
    spec = importlib.util.spec_from_file_location(
        'secret_palette_sources', DIAGNOSTICS / 'build_secret_palette_sources.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)


class SecretPaletteSourcesTests(unittest.TestCase):
    def setUp(self):
        parent = bytearray(b'\xff' * 0x100000)
        parent[mod.SELECTOR:mod.SELECTOR + len(mod.OLD)] = mod.OLD
        parent[0x37FE0:mod.TABLE] = bytes.fromhex('CDDB71 CDDB71 C9 C38454')
        parent[mod.TABLE:mod.TABLE + 8] = bytes(8)
        parent[0x37BAC:0x37BB2] = bytes.fromhex('200030001800')
        self.parent = bytes(parent)
        pin = patch.object(mod, 'PARENT_SHA', mod.digest(self.parent))
        pin.start()
        self.addCleanup(pin.stop)

    def test_all_eight_stage_indices_use_owned_table(self):
        result = mod.build(self.parent)
        for stage, expected in enumerate([32, 0, 48, 0, 24, 0, 0, 0], 1):
            low = (result[mod.SELECTOR + 9] + stage) & 255
            address = (result[mod.SELECTOR + 12] << 8) | low
            offset = 13 * 0x4000 + address - 0x4000
            self.assertEqual(offset, mod.TABLE + stage - 1)
            self.assertEqual(result[offset], expected)

    def test_only_address_operands_change_in_runtime(self):
        result = mod.build(self.parent)
        selector = bytearray(result[mod.SELECTOR:mod.SELECTOR + len(mod.OLD)])
        selector[9], selector[12] = mod.OLD[9], mod.OLD[12]
        self.assertEqual(selector, mod.OLD)
        self.assertEqual(result[0x37FE0:mod.TABLE], self.parent[0x37FE0:mod.TABLE])
        allowed = set(range(mod.TABLE, mod.TABLE + 8)) | {
            mod.SELECTOR + 9, mod.SELECTOR + 12, 0x14E, 0x14F}
        self.assertEqual(len(result), len(self.parent))
        self.assertTrue(all(a == b or i in allowed
                            for i, (a, b) in enumerate(zip(self.parent, result))))

    def test_normal_stage_sources_and_checksum_preserved(self):
        result = mod.build(self.parent)
        self.assertEqual(result[mod.TABLE:mod.TABLE + 6], self.parent[0x37BAC:0x37BB2])
        self.assertEqual(result[0x37BAC:0x37BB2], self.parent[0x37BAC:0x37BB2])
        self.assertEqual(int.from_bytes(result[0x14E:0x150], 'big'),
                         (sum(result[:0x14E]) + sum(result[0x150:])) & 65535)

    def test_unknown_parent_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact geometry-restored parent'):
            mod.build(self.parent[:-1] + b'\0')

    def test_owned_regions_validated_even_with_updated_pin(self):
        for offset in [mod.SELECTOR, 0x37FE0, mod.TABLE, 0x37BAC]:
            with self.subTest(offset=offset):
                parent = bytearray(self.parent)
                parent[offset] ^= 1
                with patch.object(mod, 'PARENT_SHA', mod.digest(parent)):
                    with self.assertRaises(ValueError):
                        mod.build(bytes(parent))


if __name__ == '__main__':
    unittest.main()
