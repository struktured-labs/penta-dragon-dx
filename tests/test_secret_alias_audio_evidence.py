"""#26 retain failed full native-PCM comparison, not a readiness assertion."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from verify_native_audio_pair import load, compare
from verify_pickup_class_palettes import serialized_state


class SecretAliasAudioEvidence(unittest.TestCase):
    def test_clean_startup_does_not_hide_fast_alias_audio_failure(self):
        pairs = [('secret-parent-gated-audio-01', 'secret-sound-alias-parent-audio-01'),
                 ('secret-fast-gated-audio-01', 'secret-sound-alias-fast-audio-01')]
        wavs = []
        for fresh, retained in pairs:
            path = ROOT / 'tmp' / fresh / 'receipt.json'
            if not path.exists(): self.skipTest('local gated capture unavailable')
            receipt = json.loads(path.read_text())
            self.assertEqual(receipt['native_capture']['restored_replay_epoch']['status'], 'PASS')
            directory = Path(receipt['native_capture_directory'])
            old = Path('/mnt/data/tmp') / f'penta-{retained}-av'
            for filename in ('native.s16le', 'native.video', 'native.states',
                             'native.timeline.tsv', 'native.wav'):
                with self.subTest(run=fresh, file=filename):
                    self.assertEqual((directory / filename).read_bytes(),
                                     (old / filename).read_bytes())
            rate, samples = load(directory / 'native.wav')
            self.assertEqual(rate, 131072)
            wavs.append(samples)
        result, _ = compare(*wavs, rate)
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['first_different_sample'], 35733)
        self.assertEqual(result['different_sample_frames'], 984047)

    def test_exact_candidate_replay_is_deterministic(self):
        first = Path('/mnt/data/tmp/penta-secret-sound-alias-audio-01-av')
        repeat = Path('/mnt/data/tmp/penta-secret-sound-alias-audio-repeat-01-av')
        for name in ('native.s16le', 'native.video', 'native.states',
                     'native.timeline.tsv', 'native.meta.json'):
            with self.subTest(name=name):
                if not (first/name).exists() or not (repeat/name).exists():
                    self.skipTest('local repeat capture unavailable')
                self.assertEqual((first/name).read_bytes(), (repeat/name).read_bytes())

    def test_cross_rom_initial_audio_state_is_not_equivalent(self):
        sources = [
            ('tmp/arena-completion-safe-late-pause-return-01/frame-3600.ss0',
             '3c6c1c0e7f6c68e1bd0dfb71d60f7653a9990430ad132e403c3f06d097b992ca'),
            ('tmp/secret-sound-alias-own-entry-01/frame-3600.ss0',
             'a61ab1d17339d807586dde1a0ad0886ece08b0e735164eaf66ad4a433796b398')]
        states = []
        for name, digest in sources:
            path = ROOT/name
            if not path.exists(): self.skipTest('local source checkpoint unavailable')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            states.append(serialized_state(path))
        parent, candidate = states
        # Pinned mGBA internal/gb/serialize.h: APU and FF10..FF3F.
        self.assertNotEqual(parent[0x48:0xb4], candidate[0x48:0xb4])
        self.assertEqual([i for i in range(0x310, 0x340) if parent[i] != candidate[i]],
                         [0x318, 0x321, 0x322, 0x323, 0x326])
        self.assertEqual(candidate[0x326] & 8, 8)  # Noise channel already active.
        self.assertEqual(parent[0x326] & 8, 0)
        self.assertEqual(int.from_bytes(candidate[0x198:0x1a0], 'little') -
                         int.from_bytes(parent[0x198:0x1a0], 'little'), 8)

    def test_untrimmed_pair_failure_remains_visible(self):
        sources = [
            (Path('/mnt/data/tmp/penta-secret-sound-alias-parent-audio-01-av/native.wav'),
             'c3e56dce7d448921e4e24832df0058600bbb7fafd98c875a62d4a491ac430cef'),
            (Path('/mnt/data/tmp/penta-secret-sound-alias-audio-01-av/native.wav'),
             '43bf69ab3bf228d378f4e305331359bfc5ce97894387b806d7cc274913848a3e')]
        arrays = []
        for path, digest in sources:
            if not path.exists(): self.skipTest('local native audio evidence unavailable')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
            rate, samples = load(path)
            self.assertEqual(rate, 131072)
            self.assertEqual(samples.shape, (1053344, 2))
            arrays.append(samples)
        result, differences = compare(*arrays, rate)
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['first_different_sample'], 7)
        self.assertEqual(result['different_sample_frames'], 1049762)
        self.assertEqual(differences.shape, arrays[0].shape)
        for check in ('same_full_route_silent_blocks', 'same_digital_silence_intervals',
                      'no_larger_sample_discontinuity'):
            self.assertFalse(result['checks'][check])
        self.assertTrue(result['checks']['no_added_clipping'])


if __name__ == '__main__': unittest.main()
