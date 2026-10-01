"""#23/#26: pickup-only checks must not conceal stale scenery colors."""
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from check_secret_pickup_attributes import inspect_planes, serialized_state


class SecretPalettePlanesTests(unittest.TestCase):
    def test_latest_route_retains_in_progress_hidden_map_failures(self):
        import hashlib
        p = ROOT/'tmp/title-local-secret-menu-return-01'
        if not (p/'frame-10800.ss0').exists():
            self.skipTest('local latest-candidate full route unavailable')
        rom = (p/'candidate.gb').read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '8ff1c98d98f6949d39628c0c9fc86a53aae805f25cb8936484f2a00893af5c3c')
        failures = []
        checked = 0
        for path in sorted(p.glob('frame-*.ss0')):
            raw = serialized_state(path)
            if (raw[0x5c80], raw[0x3ba], raw[0x3e4]) != (9,7,0):
                continue
            checked += 1
            result = inspect_planes(raw, rom)
            active = '0x9c00' if raw[0x340] & 8 else '0x9800'
            self.assertFalse([m for m in result['mismatches'] if m['map'] == active])
            if result['mismatches']:
                # Retain FAIL; inactive transaction analysis is not a waiver.
                self.assertEqual(result['status'], 'FAIL')
                self.assertEqual(raw[0x399], 36)
                self.assertEqual(int.from_bytes(raw[0x2a:0x2c], 'little'), 0x5c3c)
                failures.append((path.stem, len(result['mismatches'])))
        self.assertEqual(checked, 29)
        self.assertEqual(failures, [('frame-6600',8), ('frame-6840',16)])

    def fixture(self):
        rom = bytes(0x8000)
        raw = bytearray(0x11800)
        raw[4:8] = (zlib.crc32(rom) & 0xffffffff).to_bytes(4, 'little')
        raw[0x5c80] = 9
        raw[0x3ba] = 7
        return raw, rom

    def test_neutral_cells_are_checked_without_pickups(self):
        result = inspect_planes(*self.fixture())
        self.assertEqual(result['status'], 'PASS_PUBLISHED_PALETTE_PLANES')
        self.assertEqual(result['checked_cells'], 1536)

    def test_stale_scenery_on_either_map_fails(self):
        raw, rom = self.fixture()
        for pos in (0x3c00, 0x4000 + 767):
            raw[pos] = 6
        result = inspect_planes(raw, rom)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(len(result['mismatches']), 2)
        self.assertEqual({m['map'] for m in result['mismatches']}, {'0x9800', '0x9c00'})

    def test_wrong_stage_rejected(self):
        raw, rom = self.fixture()
        raw[0x3ba] = 0
        with self.assertRaisesRegex(ValueError, 'stage07'):
            inspect_planes(raw, rom)

    def test_retained_parent_and_candidate(self):
        for name, count in [('source07-secret-postmenu-right-01', 293),
                            ('select02-secret-postmenu-right-01', 0)]:
            with self.subTest(name=name):
                p = ROOT / 'tmp' / name
                if not (p / 'frame-4800.ss0').exists():
                    self.skipTest('local exact-ROM evidence unavailable')
                result = inspect_planes(serialized_state(p / 'frame-4800.ss0'),
                                        (p / 'candidate.gb').read_bytes())
                self.assertEqual(len(result['mismatches']), count)

    def test_retained_post_encounter_does_not_hide_stale_cells(self):
        # #23/#26: both builds eventually display a plausible Stage1 endpoint.
        # Check the intermediate secret return, where the old build is broken
        # even though its global BG0 palette has already recovered.
        for name, count in [('reported-secret-menu-fullreturn-01', 85),
                            ('select02-secret-menu-fullreturn-01', 0)]:
            with self.subTest(name=name):
                p = ROOT / 'tmp' / name
                if not (p / 'frame-6600.ss0').exists():
                    self.skipTest('local exact-ROM post-encounter evidence unavailable')
                raw = serialized_state(p / 'frame-6600.ss0')
                self.assertEqual(raw[0x3e4], 0, 'must not inspect the open menu')
                self.assertEqual(raw[0xd4:0xdc].hex(), 'ff7f947e4a3d0000')
                result = inspect_planes(raw, (p / 'candidate.gb').read_bytes())
                self.assertEqual(len(result['mismatches']), count)
