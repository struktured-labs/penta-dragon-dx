"""#22: exact 46eb star rendering and collected inventory menu round trip."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import zlib

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from verify_pickup_class_palettes import serialized_state

PIN = '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb'


class LateReturnStar(unittest.TestCase):
    def test_uncollected_star_across_menu_close_all_frames(self):
        base = ROOT / 'tmp'
        prior = base / 'late-return-star-live-01/frame-1500.ss0'
        for name, terminal in [('menu', 360), ('resume', 180)]:
            directory = base / f'late-return-star-uncollected-{name}-01'
            if not (directory / 'receipt.json').exists():
                self.skipTest('local uncollected star evidence unavailable')
            receipt = json.loads((directory / 'receipt.json').read_text())
            rom = (directory / 'candidate.gb').read_bytes()
            self.assertEqual(hashlib.sha256(rom).hexdigest(), PIN)
            self.assertEqual(receipt['rom_sha256'], PIN)
            self.assertEqual(receipt['status'], 0)
            self.assertFalse(receipt['observer_memory_writes'])
            self.assertEqual(receipt['source_state_sha256'], hashlib.sha256(prior.read_bytes()).hexdigest())
            self.assertEqual(receipt['probe_sha256'], hashlib.sha256((directory / 'probe.lua').read_bytes()).hexdigest())
            prior = directory / f'frame-{terminal:04d}.ss0'
            state = serialized_state(prior)
            self.assertEqual((state[0x5c80], state[0x3e4]), (2, int(name == 'menu')))
            self.assertEqual(state[0x60bd:0x60dc], bytes(31))
        with Image.open(base / 'late-return-star-live-01/frame-1500.png') as source:
            reference = source.convert('RGB').crop((72, 80, 88, 96))
        directory = base / 'late-return-star-uncollected-resume-01'
        self.assertEqual(len(list(directory.glob('frame-*.ss0'))), 180)
        for frame in range(1, 181):
            state = serialized_state(directory / f'frame-{frame:04d}.ss0')
            self.assertEqual(int.from_bytes(state[4:8], 'little'), zlib.crc32(rom) & 0xffffffff)
            self.assertEqual(state[16:32], rom[0x134:0x144])
            self.assertEqual((state[0x5c80], state[0x3e4]), (2, int(frame == 1)))
            self.assertEqual(state[0x60bd:0x60dc], bytes(31))
            with Image.open(directory / f'frame-{frame:04d}.png') as source:
                actual = source.convert('RGB').crop((72, 80, 88, 96))
            self.assertIsNone(ImageChops.difference(reference, actual).getbbox(), f'frame {frame}')
        with Image.open(base / 'five-point-star-live-01/frame-1500.png') as source:
            broken = source.convert('RGB').crop((72, 80, 88, 96))
        self.assertIsNotNone(ImageChops.difference(reference, broken).getbbox())

    def test_render_collection_and_inventory_resume(self):
        prior = None
        expected = bytearray(31)
        for name, frame, paused in [('live', 1500, 0), ('collect', 120, 0),
                                     ('menu', 360, 1), ('resume', 180, 0)]:
            directory = ROOT / 'tmp' / f'late-return-star-{name}-01'
            if not (directory / 'receipt.json').exists():
                self.skipTest('local exact-ROM star evidence unavailable')
            receipt = json.loads((directory / 'receipt.json').read_text())
            rom = (directory / 'candidate.gb').read_bytes()
            self.assertEqual(hashlib.sha256(rom).hexdigest(), PIN)
            self.assertEqual(receipt['rom_sha256'], PIN)
            self.assertEqual(receipt['status'], 0)
            self.assertEqual(receipt['probe_sha256'], hashlib.sha256(
                (directory / 'probe.lua').read_bytes()).hexdigest())
            if prior is not None:
                self.assertFalse(receipt['observer_memory_writes'])
                self.assertEqual(receipt['source_state_sha256'],
                                 hashlib.sha256(prior.read_bytes()).hexdigest())
                expected[0xdcd1 - 0xdcbd] = 15
            else:
                self.assertTrue(receipt['observer_memory_writes'])
                self.assertEqual(receipt['diagnostic_environment']['ENTRY_COLD_WARP'], '1')
            prior = directory / f'frame-{frame:04d}.ss0'
            state = serialized_state(prior)
            self.assertEqual(int.from_bytes(state[4:8], 'little'), zlib.crc32(rom) & 0xffffffff)
            self.assertEqual(state[16:32], rom[0x134:0x144])
            self.assertEqual((state[0x5c80], state[0x3e4]), (2, paused))
            self.assertEqual(state[0x60bd:0x60dc], expected)
        with Image.open(ROOT / 'tmp/late-return-star-live-01/frame-1500.png') as source:
            current = source.convert('RGB')
        for point in ((80, 84), (80, 86), (79, 87)):
            self.assertEqual(current.getpixel(point), (255, 255, 0))
        # Full pickup-region comparison, including a retained known-broken control.
        for control, identical in [('five-point-star-fixed-live-01', True),
                                   ('five-point-star-live-01', False)]:
            with Image.open(ROOT / 'tmp' / control / 'frame-1500.png') as reference:
                delta = ImageChops.difference(current.crop((72, 80, 88, 96)),
                    reference.convert('RGB').crop((72, 80, 88, 96)))
            self.assertEqual(delta.getbbox() is None, identical)


if __name__ == '__main__':
    unittest.main()
