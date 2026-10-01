"""Issue #33: observed staged-row stack/register balance, not global safety."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def check(rows):
    errors, pending, low, depths = [], None, None, []
    completed = 0
    for row in rows:
        event = row['event']
        if int(row['svbk'], 16) != 1:
            errors.append('row stack outside bank1')
        if event == 'enter':
            if pending is not None:
                errors.append('nested or unfinished row')
            pending, low = row, None
        elif event == 'lowest':
            if pending is None or low is not None:
                errors.append('unpaired or duplicate low-water observation')
            else:
                low = int(row['sp'], 16)
                depths.append(low)
                if int(pending['sp'], 16) - low != 46:
                    errors.append('unexpected row stack depth')
        elif event == 'exit':
            if pending is None or low is None:
                errors.append('exit without complete row observations')
            else:
                for reg, advance in (('sp', 0), ('bc', 0), ('de', 20), ('hl', 20)):
                    if int(row[reg], 16) != (int(pending[reg], 16) + advance) & 65535:
                        errors.append(f'incorrect restored {reg}')
                completed += 1
            pending, low = None, None
        else:
            errors.append('interrupt inside staging' if event == 'timer_inside' else 'unknown event')
    if pending is not None:
        errors.append('terminal partial row')
    if not completed:
        errors.append('missing complete rows')
    return dict(status='FAIL' if errors else 'PASS_OBSERVED_ROW_STACK', errors=errors,
                complete_rows=completed, lowest_sp=min(depths) if depths else None,
                scope='Observed row entry/low-water/exit and timer interrupts only; no all-route ownership or audio claim.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    args = parser.parse_args()
    with args.trace.open() as stream:
        result = check(csv.DictReader(stream, delimiter='\t'))
    result['trace_sha256'] = hashlib.sha256(args.trace.read_bytes()).hexdigest()
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['errors']))
