#!/usr/bin/env python3
"""Narrow native-PCM guard for #6/#16, not a perceptual-equivalence claim.

Compare full equal-length stereo PCM without trimming, retiming, resampling,
normalizing or discarding startup. Keep every sample difference. Guard against
added digital silence, clipping, larger discontinuities and level loss/gain.
"""
import argparse
import hashlib
import json
from pathlib import Path
import wave

import numpy as np


def load(path):
    with wave.open(str(path)) as stream:
        if stream.getnchannels() != 2 or stream.getsampwidth() != 2 or stream.getcomptype() != 'NONE':
            raise ValueError('expected uncompressed stereo PCM16')
        rate, count = stream.getframerate(), stream.getnframes()
        raw = stream.readframes(count)
    if len(raw) != count * 4:
        raise ValueError('truncated PCM')
    return rate, np.frombuffer(raw, dtype='<i2').reshape(-1, 2).astype(np.int32)


def measure(samples, rate):
    if samples.ndim != 2 or samples.shape[1] != 2 or len(samples) < rate:
        raise ValueError('at least one second of stereo PCM required')
    zero = np.all(samples == 0, axis=1)
    edges = np.diff(np.r_[False, zero, False].astype(np.int8))
    intervals = [[int(a), int(b)] for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
                 if b - a >= rate * 0.020]
    size = max(1, rate // 20)
    blocks = [float(np.sqrt(np.mean(samples[i:i + size].astype(float) ** 2)))
              for i in range(0, len(samples), size)]
    return {'samples': len(samples), 'sample_rate': rate,
            'rms': float(np.sqrt(np.mean(samples.astype(float) ** 2))),
            'peak': int(np.abs(samples).max()),
            'clipped_samples': int(np.sum(np.abs(samples) >= 32767)),
            'maximum_sample_step': int(np.abs(np.diff(samples, axis=0)).max()),
            'digital_silence_at_least_20ms': intervals,
            'rms_block_samples': size, 'rms_blocks': blocks,
            'silent_blocks': [i for i, value in enumerate(blocks) if value < 0.003 * 32768]}


def compare(parent, candidate, rate):
    if parent.shape != candidate.shape:
        raise ValueError('different native sample counts; do not trim to match')
    a, b = measure(parent, rate), measure(candidate, rate)
    ratio = b['rms'] / a['rms'] if a['rms'] else 0
    checks = {
        'reference_has_activity': a['rms'] >= 0.003 * 32768,
        'level_within_two_percent': 0.98 <= ratio <= 1.02,
        'same_full_route_silent_blocks': a['silent_blocks'] == b['silent_blocks'],
        'same_digital_silence_intervals': a['digital_silence_at_least_20ms'] == b['digital_silence_at_least_20ms'],
        'no_added_clipping': b['clipped_samples'] <= a['clipped_samples'],
        'no_larger_sample_discontinuity': b['maximum_sample_step'] <= a['maximum_sample_step'],
    }
    differences = candidate.astype(np.int32) - parent.astype(np.int32)
    changed = np.flatnonzero(np.any(differences != 0, axis=1))
    return {'status': 'pass' if all(checks.values()) else 'fail', 'checks': checks,
            'scope': 'full-route native-PCM dropout/clipping/level guard; not perceptual or waveform equivalence',
            'parent': a, 'candidate': b, 'rms_ratio': ratio,
            'different_sample_frames': len(changed),
            'first_different_sample': int(changed[0]) if len(changed) else None,
            'last_different_sample': int(changed[-1]) if len(changed) else None,
            'maximum_sample_difference': int(np.abs(differences).max())}, differences


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rate, parent = load(args.parent)
    other_rate, candidate = load(args.candidate)
    if rate != other_rate:
        raise ValueError('different native sample rates; do not resample to match')
    result, differences = compare(parent, candidate, rate)
    args.output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(args.output / 'all-sample-differences.npz', differences=differences)
    result['identities'] = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in (args.parent, args.candidate, Path(__file__))}
    (args.output / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key:value for key,value in result.items() if key not in ('parent','candidate')}, indent=2))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
