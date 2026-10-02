"""#32/#36: authenticate Ted fixture addresses without approving retargeting."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import generate_stream_boss_states as generator


class ReturnFadeTedProfile(unittest.TestCase):
    def test_late_return_trial_latch_profile_is_not_retarget_permission(self):
        rom = (ROOT/'tmp/stream-late-return-source-01/candidate.gb').read_bytes()
        parent = (ROOT/'tmp/return-cgb-fade-trial-16/candidate.gb').read_bytes()
        pin = hashlib.sha256(rom).hexdigest()
        self.assertEqual(pin,
                         '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
        self.assertEqual(rom[0x44000:0x48000], parent[0x44000:0x48000])
        self.assertEqual(hashlib.sha256(rom[0x44000:0x48000]).hexdigest(),
                         '6aa4f5f8105b300176429bfe69b7dce4688720f915982e3a6243202acc9ce8d7')
        self.assertTrue(generator.relocated_ted_latches(rom))
        self.assertNotIn(pin, generator.PENTA_SYNC_INHERITORS_SHA256)
        changed = bytearray(rom)
        changed[0x44364] ^= 1
        self.assertFalse(generator.relocated_ted_latches(changed))

    def test_current_three_menus_and_historical_failure(self):
        from check_boss_menu_fades import inspect_roundtrips
        from verify_pickup_class_palettes import serialized_state
        current = ROOT / 'tmp/return-fade16-ted-menus-01'
        broken = ROOT / 'tmp/ted-menu-broken-roundtrips-gated-01'
        if not (current / 'verification.json').exists() or not (broken / 'verification.json').exists():
            self.skipTest('current and broken emulator evidence unavailable')
        result = inspect_roundtrips(current, 16)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual([c['status'] for c in result['cycles']], ['PASS'] * 3)
        self.assertEqual(inspect_roundtrips(broken, 16)['status'], 'FAIL')
        frames = sorted(current.glob('frame-*.ss0'))
        self.assertEqual(len(frames), 1080)
        for frame in frames:
            state = serialized_state(frame)
            self.assertEqual(state[0x5c80], 16)
            self.assertLess(state[0x60dd], 10)

    def test_exact_ted_abi_and_unknown_rejection(self):
        candidate = ROOT / 'tmp/return-cgb-fade-trial-16/candidate.gb'
        parent = ROOT / 'tmp/stream-presentation-source-01/candidate.gb'
        if not candidate.exists() or not parent.exists():
            self.skipTest('local pinned ROMs unavailable')
        rom, old = candidate.read_bytes(), parent.read_bytes()
        pin = hashlib.sha256(rom).hexdigest()
        self.assertEqual(pin, '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b')
        self.assertEqual(hashlib.sha256(old).hexdigest(),
                         'd744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5')
        self.assertEqual(rom[0x44000:0x48000], old[0x44000:0x48000])
        self.assertEqual(hashlib.sha256(rom[0x44000:0x48000]).hexdigest(),
                         '6aa4f5f8105b300176429bfe69b7dce4688720f915982e3a6243202acc9ce8d7')
        self.assertEqual([i for i in range(0x150, 0x4000) if rom[i] != old[i]],
                         [0x15db, 0x15dc])
        self.assertTrue(generator.relocated_ted_latches(rom))
        self.assertNotIn(pin, generator.PENTA_SYNC_INHERITORS_SHA256)
        mutated = bytearray(rom)
        mutated[0x44364] ^= 1
        self.assertFalse(generator.relocated_ted_latches(mutated))


if __name__ == '__main__':
    unittest.main()
