"""#23 diagnostic timer-spacing guard; not an acoustic fidelity verdict."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

# Observed D2/FC timer configuration: 46 * 2048 emulator cycle units.
PERIOD = 94208


def secret_context(row):
    # #26: sound aliases are not a scene exit. Do not lose their slow intervals.
    return row['scene'] == '09' or (row['scene'] in ('0A', '0B') and
        row.get('canonical') == '09' and row.get('stage') == '07')


def check(rows):
    timers = [r for r in rows if r['kind'] == 'timer']
    errors, gaps, boundaries = [], [], []
    for row in timers:
        if secret_context(row):
            if (row['tma'], row['tac']) != ('D2', 'FC'):
                errors.append('unsupported secret timer configuration')
            if int(row['svbk'], 16) != 1:
                errors.append('secret timer interrupt outside stack bank1')
    for previous, current in zip(timers, timers[1:]):
        gap = int(current['cycle']) - int(previous['cycle'])
        if gap <= 0:
            errors.append('nonmonotonic timer trace')
        item = dict(start_frame=int(previous['frame']),
                    end_frame=int(current['frame']), cycles=gap)
        if secret_context(previous) and secret_context(current):
            gaps.append(item)
        elif secret_context(previous) or secret_context(current):
            boundaries.append(item)
    if not gaps:
        errors.append('missing secret timer intervals')
    late = [g for g in gaps if g['cycles'] > PERIOD * 3 // 2]
    if late:
        errors.append('secret timer spacing exceeds 1.5 nominal periods')
    return dict(status='FAIL' if errors else 'PASS_OBSERVED_TIMER_SPACING',
                errors=errors, intervals=len(gaps), late_intervals=late,
                maximum_cycles=max((g['cycles'] for g in gaps), default=None),
                scene_boundary_intervals=boundaries,
                terminal_scene=timers[-1]['scene'] if timers else None,
                scope='All consecutive scene09 or explicitly tagged canonical09/stage07 sound-alias timer entries; boundary gaps reported separately. '
                      'First/last interrupt intervals are censored. No audio, transition, '
                      'observer-neutrality, or hardware acceptance claim.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    args = parser.parse_args()
    with args.trace.open() as stream:
        result = check(csv.DictReader(stream, delimiter='\t'))
    result['trace_sha256'] = hashlib.sha256(args.trace.read_bytes()).hexdigest()
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['errors']))
