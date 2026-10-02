"""#27 complementary event-time check; does not waive frame-sampled failures."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def check(rows):
    events = [r for r in rows if r['kind'] == 'bgp']
    errors = []
    sequence = [int(r['value'], 16) for r in events]
    if sequence != [0xE4, 0x90, 0x40, 0, 0, 0x40, 0x90, 0xE4]:
        errors.append('incomplete or unexpected second-return fade sequence')
    differences = []
    for row in events:
        source, target = bytes.fromhex(row['source']), bytes.fromhex(row['map'])
        if len(source) != 576 or len(target) != 576:
            errors.append('missing full 24x24 source/map snapshot')
        cells = [i for i, (a, b) in enumerate(zip(source, target)) if a != b]
        if cells:
            differences.append(dict(frame=int(row['frame']), cycle=int(row['cycle']), cells=cells))
    if differences:
        errors.append('map differs at palette publication')
    final_cycle = int(events[-1]['cycle']) if events else None
    later = [r for r in rows if r['kind'] == 'source' and
             final_cycle is not None and int(r['cycle']) > final_cycle]
    return dict(status='FAIL' if errors else 'PASS_EVENT_MAP_SNAPSHOTS', errors=errors,
                publication_differences=differences, publication_events=len(events),
                final_publication_cycle=final_cycle,
                first_later_source_write=later[0] if later else None,
                scope='All traced second-return BGP writes and full selected 24x24 map. '
                      'Not continuous scanout, CHR/attributes, audio, or other returns.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    with a.trace.open() as stream:
        result = check(list(csv.DictReader(stream, delimiter='\t')))
    result['trace_sha256'] = hashlib.sha256(a.trace.read_bytes()).hexdigest()
    result['checker_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with a.output.open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['errors']))
