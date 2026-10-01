"""Issue #21: detect split 4x4 Gargoyle OAM geometry in native captures.

Scoped to assisted Stage-1 Gargoyle/Spider replays: FFBF=1/2, slots 4..19.
This is not an all-boss or rendered/audio fidelity verifier.
"""
import argparse
import hashlib
import json
from pathlib import Path

STATE_BYTES = 71680
LAYOUT = (0, 1, 4, 5, 2, 3, 6, 7, 8, 9, 12, 13, 10, 11, 14, 15)


def inspect(stream, expected_frames, boss_id=1):
    if boss_id not in (1, 2):
        raise ValueError('only reviewed Gargoyle/Spider layouts supported')
    digest = hashlib.sha256()
    frames = coherent = 0
    mixed, censored = [], []
    while state := stream.read(STATE_BYTES):
        digest.update(state)
        if len(state) != STATE_BYTES:
            raise ValueError('partial native state')
        frames += 1
        if state[0x3bf] != boss_id:
            continue
        pieces = [state[0x260 + i*4:0x264 + i*4] for i in range(4, 20)]
        if not all(0 < p[0] < 160 and 0 < p[1] < 168 for p in pieces):
            censored.append(frames)
            continue
        origins = sorted({(p[0] - (d//4)*8, p[1] - (d%4)*8)
                          for p, d in zip(pieces, LAYOUT)})
        if len(origins) != 1:
            mixed.append({'frame': frames, 'origins_yx': origins})
        else:
            coherent += 1
    if frames != expected_frames:
        raise ValueError(f'expected {expected_frames} frames, got {frames}')
    return dict(status='PASS' if coherent and not mixed else 'FAIL',
                scope='Fully visible miniboss OAM geometry only; not release qualification',
                boss_id=boss_id,
                states_sha256=digest.hexdigest(), frames=frames,
                coherent_frames=coherent, mixed_frames=mixed,
                not_fully_visible_frames=censored)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('states', type=Path)
    parser.add_argument('--expected-frames', type=int, required=True)
    parser.add_argument('--boss-id', type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    with args.states.open('rb') as stream:
        result = inspect(stream, args.expected_frames, args.boss_id)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
