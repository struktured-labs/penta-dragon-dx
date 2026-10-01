"""#23 selected-map palette policy at LCDC writes; not continuous scanout/audio."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from verify_pickup_class_palettes import PICKUPS


def check(rows):
    table = [0]*256
    for item in PICKUPS:
        for tile in item.tiles:
            table[tile] = item.palette
    observations, errors = [], []
    previous = -1
    for row in rows:
        cycle = int(row['cycle'])
        if cycle <= previous:
            errors.append('nonmonotonic cycles')
        previous = cycle
        tiles, attrs = bytes.fromhex(row['tiles']), bytes.fromhex(row['attrs'])
        if len(tiles) != 768 or len(attrs) != 768:
            errors.append('incomplete selected-map snapshot')
        if (row['scene'], row['stage']) != ('09','07'):
            errors.append('unexpected scene/stage')
        eligible = bool(int(row['lcdc'],16)&128) and row['menu']=='00'
        differences = [i for i,(tile,attr) in enumerate(zip(tiles,attrs))
                       if attr&7 != table[tile]]
        observations.append(dict(frame=int(row['frame']), cycle=cycle,
            lcdc=row['lcdc'], menu=row['menu'], eligible=eligible,
            differences=differences))
    eligible = [r for r in observations if r['eligible']]
    if not eligible:
        errors.append('no LCD-on gameplay observations')
    failures = [r for r in eligible if r['differences']]
    return dict(status='FAIL' if errors or failures else 'PASS_OBSERVED_PUBLICATIONS',
                errors=errors, events=len(observations), eligible_events=len(eligible),
                failures=failures, observations=observations,
                scope='All supplied LCDC events retained; acceptance covers scene09/stage07 '
                      'LCD-on/menu-closed selected map rows0..23. Not capture completeness, '
                      'continuous scanout, CHR, audio, or observer neutrality.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    with a.trace.open() as stream:
        result = check(csv.DictReader(stream, delimiter='\t'))
    result['trace_sha256'] = hashlib.sha256(a.trace.read_bytes()).hexdigest()
    result['checker_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with a.output.open('x') as stream:
        json.dump(result, stream, indent=2)
    print(result['status'], 'events', result['events'], 'eligible', result['eligible_events'],
          'failures', len(result['failures']), 'errors', result['errors'])
    raise SystemExit(result['status']=='FAIL')
