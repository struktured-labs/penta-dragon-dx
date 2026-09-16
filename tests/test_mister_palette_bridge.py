import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).resolve().parents[1] / 'scripts/mister_palette_bridge.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PaletteTests(unittest.TestCase):
    def test_supported_sources_get_distinct_stems_without_hardware_calls(self):
        for pin in (m.PIN, m.ROW_GUARD_PIN):
            with patch.object(Path, 'read_bytes', return_value=b'fixture'), \
                 patch.object(m, 'sha', return_value=pin), \
                 patch.object(m.Bridge, 'ssh', side_effect=AssertionError('hardware access')):
                bridge = m.Bridge(Path('explicit-source.gbc'))
                self.assertEqual(bridge.source_pin, pin)
                self.assertEqual(bridge.stem, 'Penta-Dragon-DX-' + pin[:12])

    def test_unknown_source_is_rejected(self):
        with patch.object(Path, 'read_bytes', return_value=b'unknown'):
            with self.assertRaisesRegex(ValueError, 'exact supported pin'):
                m.Bridge(Path('unknown.gbc'))

    def test_labels_cover_stable_palette_ids(self):
        self.assertEqual(len(m.LABELS), len(m.NAMES))
        self.assertEqual(len(m.LABELS), len(m.OFFSETS))
        self.assertIn('Rotating spike', m.LABELS[5][0])
        self.assertIn('not protruding teeth', m.LABELS[5][1])

    def fixture(self):
        rom = bytearray(524288)
        state = bytearray(181040)
        struct.pack_into('<I', state, 4, 0xB0CA)
        row = m.encode(['#000000', '#ff0000', '#00ff00', '#0000ff'])
        rom[m.OFFSETS[9]:m.OFFSETS[9]+8] = row
        state[176:184] = row
        return bytes(rom), bytes(state)

    def test_only_palette_and_checksum_change(self):
        rom, state = self.fixture()
        new, ss, matches = m.patch(rom, state, 9, ['#000000', '#ffffff', '#00ff00', '#0000ff'])
        self.assertEqual(matches, [176])
        self.assertTrue(all(a == b or i in range(176, 184) for i, (a,b) in enumerate(zip(state, ss))))
        self.assertTrue(all(a == b or i in range(m.OFFSETS[9], m.OFFSETS[9]+8) or i in (334,335) for i,(a,b) in enumerate(zip(rom,new))))
        self.assertEqual(int.from_bytes(new[334:336], 'big'), (sum(new[:334])+sum(new[336:])) & 65535)

    def test_inactive_override_rejected(self):
        rom, state = self.fixture()
        state = state[:96] + bytes([255])*64 + state[160:]
        with self.assertRaisesRegex(ValueError, 'not active'):
            m.patch(rom, state, 0, ['#ffffff']*4)

    def test_transparency_preserved(self):
        rom, state = self.fixture()
        with self.assertRaisesRegex(ValueError, 'transparent'):
            m.patch(rom, state, 9, ['#ffffff']*4)

    def test_state_layout_rejected(self):
        rom, state = self.fixture()
        with self.assertRaisesRegex(ValueError, 'layout'):
            m.patch(rom, state[:-1], 9, ['#ffffff']*4)

    def test_rgb_roundtrip(self):
        for value in range(32):
            row = struct.pack('<4H', *([value | value << 5 | value << 10]*4))
            self.assertEqual(m.encode(m.decode(row)), row)


if __name__ == '__main__':
    unittest.main()
