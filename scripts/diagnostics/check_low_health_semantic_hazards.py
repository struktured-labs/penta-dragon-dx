"""Offline cross-check against the reviewed hazard-menu material rules.

Does not qualify publication ownership, geometry, ROM identity or a release.
Consumes captured tile/attribute pairs without using the candidate LUT.
"""
import argparse
import csv
import json
from pathlib import Path


def expected(tile):
    if 1 <= tile <= 4:
        return 0
    if 0x64 <= tile <= 0x69 or 0x74 <= tile <= 0x79:
        return 0x0F
    if tile in {0x60,0x61,0x62,0x6B,0x6C,0x6D,0x6E,0x6F,
                0x70,0x71,0x72,0x7B,0x7C,0x7D,0x7E,0x7F}:
        return 5
    if 0x60 <= tile <= 0x7F:
        return 6
    return None


def analyze(rows):
    result = {}
    for row in rows:
        phase = row['stimulus_phase']
        record = result.setdefault(phase, dict(frames=0, checked_cells=0,
            tooth_cells=0, mismatch_cells=0, mismatch_frames=0, first=None))
        tiles, attrs = bytes.fromhex(row['tile_bytes']), bytes.fromhex(row['attr_bytes'])
        if len(tiles) != len(attrs):
            raise ValueError('unequal tile/attribute samples')
        record['frames'] += 1
        bad = 0
        for index, (tile, actual) in enumerate(zip(tiles, attrs)):
            wanted = expected(tile)
            if wanted is None:
                continue
            record['checked_cells'] += 1
            record['tooth_cells'] += wanted == 15
            if actual != wanted:
                bad += 1
                if record['first'] is None:
                    record['first'] = dict(frame=int(row['frame']), cell=index,
                                           tile=tile, actual=actual, expected=wanted)
        record['mismatch_cells'] += bad
        record['mismatch_frames'] += bad > 0
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    args = parser.parse_args()
    with args.trace.open() as handle:
        print(json.dumps(analyze(csv.DictReader(handle, delimiter='\t')), indent=2))
