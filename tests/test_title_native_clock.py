"""#35 retained clock accounting; not waveform or perceptual qualification."""
import csv
import hashlib
from pathlib import Path
import unittest

BASE = Path('/mnt/data/tmp')
STATE_SIZE = 71680


def capture(name):
    path = BASE / f'penta-title-audio-{name}-20260928-01'
    with (path/'native.timeline.tsv').open() as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    raw = (path/'native.states').read_bytes()
    if len(raw) != len(rows) * STATE_SIZE:
        raise ValueError('incomplete state timeline')
    states = [raw[i*STATE_SIZE:(i+1)*STATE_SIZE] for i in range(len(rows))]
    cycles = [int.from_bytes(s[0x198:0x1a0], 'little') for s in states]
    samples = [int(r['pcm_samples']) for r in rows]
    return path, states, cycles, samples


def batch_clock_consistent(cycles, samples):
    # Pinned GB core: 64 master cycles/sample, callbacks in32-sample batches.
    # A diagnostic bound for these cold captures, NOT an audio acceptance gate.
    return bool(cycles) and len(cycles) == len(samples) and all(
        -2048 < cycle - sample*64 <= 0 for cycle, sample in zip(cycles, samples))


class TitleNativeClockTests(unittest.TestCase):
    def setUp(self):
        if not all((BASE/f'penta-title-audio-{n}-20260928-01/native.states').exists()
                   for n in ('control', 'local')):
            self.skipTest('retained native captures unavailable')

    def test_retained_clock_and_lcd_exit_delta(self):
        a, b = capture('control'), capture('local')
        for data, sha in ((a, '2bdf2047a61f81d9b9ca98ef775e5d33e28b7c0ce5ef9c465f4dc2a712be35d3'),
                          (b, '164af9fd5d5d80da0c5cda8fac756531a10e3371beda6776df881f51e4d0ebf9')):
            self.assertEqual(hashlib.sha256((data[0]/'native.states').read_bytes()).hexdigest(), sha)
            self.assertEqual(len(data[1]), 600)
            self.assertTrue(batch_clock_consistent(data[2], data[3]))
        delta = [y-x for x,y in zip(a[2], b[2])]
        self.assertEqual(delta[193:195], [4032, -53448])
        for states in (a[1], b[1]):
            self.assertEqual((states[193][0x5c80], states[194][0x5c80]), (1, 0))
            self.assertTrue(states[193][0x340] & 128)
            self.assertFalse(states[194][0x340] & 128)
        self.assertEqual(delta[-1], -53448)
        self.assertEqual(b[3][-1]-a[3][-1], -832)
        # Count mismatch is real, not made equal by this diagnostic.
        self.assertNotEqual(a[3][-1], b[3][-1])

    def test_missing_pcm_batches_fail_clock_check(self):
        _, _, cycles, samples = capture('local')
        altered = list(samples)
        altered[300:] = [n-64 for n in altered[300:]]
        self.assertFalse(batch_clock_consistent(cycles, altered))
        self.assertFalse(batch_clock_consistent([], []))
