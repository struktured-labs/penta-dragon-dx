import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from hazard_mutations_r442 import mutants, authenticate
from source_observer_fixtures import observer_fixtures


class HazardMutations(unittest.TestCase):
    def test_r453_exact_controls_and_no_extra_changes(self):
        source = observer_fixtures()['r453']
        plans = {
            'forced-visible-menu-repair': ((0x1B72, bytes.fromhex('CD A0 42 C9')), (0x1DCB, bytes.fromhex('CD A0 42 C9'))),
            'short-endpoint-span': ((0x4E2D4, b'\x0a'),),
            'missing-alternate-phase': ((0x4E2CB, bytes.fromhex('F6 61')),),
            'short-right-endpoint-span': ((0x4E1A5, b'\x09'),),
        }
        for name, patches in plans.items():
            changed = bytearray(source)
            for offset, new in patches:
                changed[offset:offset + len(new)] = new
            checksum = (sum(changed[:0x14E]) + sum(changed[0x150:])) & 0xFFFF
            changed[0x14E:0x150] = checksum.to_bytes(2, 'big')
            self.assertEqual(authenticate(source, bytes(changed)), name)
            changed[0x200] ^= 1
            with self.assertRaises(ValueError): authenticate(source, bytes(changed))
        with self.assertRaises(ValueError): authenticate(source, source)
        with self.assertRaises(ValueError): authenticate(source + b'changed', source)

    def test_closed_set_and_preserved_close_handoff(self):
        source = observer_fixtures()['r442']
        controls = mutants(source)
        self.assertEqual(len(controls), 4)
        for name, payload in controls.items():
            self.assertEqual(authenticate(source, payload), name)
            self.assertEqual(payload[0x77A8:0x77AC], source[0x77A8:0x77AC])
            self.assertEqual(payload[0x1B6F:0x1B72], source[0x1B6F:0x1B72])
            self.assertEqual(payload[0x1DC8:0x1DCB], source[0x1DC8:0x1DCB])
            extra = bytearray(payload); extra[0x200] ^= 1
            with self.assertRaises(ValueError): authenticate(source, bytes(extra))
        with self.assertRaises(ValueError): authenticate(source, source)
        extra = bytearray(source); extra[0x200] ^= 1
        with self.assertRaises(ValueError): mutants(bytes(extra))
