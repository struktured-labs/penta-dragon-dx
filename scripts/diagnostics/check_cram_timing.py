"""#25/#35: retain every observed blocked CRAM write; never hide other paths."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def check(rows):
    rows = list(rows)
    blocked = []
    errors = []
    previous = -1
    for row in rows:
        cycle = int(row['cycle'])
        if cycle <= previous:
            errors.append('nonmonotonic write cycles')
        previous = cycle
        mode = int(row['mode'])
        if mode not in range(4) or row['port'] not in ('FF69', 'FF6B'):
            errors.append('invalid LCD mode or CRAM port')
        if int(row['lcdc'], 16) & 0x80 and mode == 3:
            blocked.append(dict(row))
    if not rows:
        errors.append('no observed CRAM writes')
    return dict(status='FAIL' if errors or blocked else 'PASS_OBSERVED_WRITES',
                writes=len(rows), blocked_writes=blocked, errors=errors,
                scope='All supplied write observations; not capture completeness, '
                      'observer neutrality, rendered output, or audio qualification.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace', type=Path)
    a = p.parse_args()
    with a.trace.open() as stream:
        result = check(csv.DictReader(stream, delimiter='\t'))
    result['trace_sha256'] = hashlib.sha256(a.trace.read_bytes()).hexdigest()
    print(json.dumps(result, indent=2))
    raise SystemExit(result['status'] == 'FAIL')
