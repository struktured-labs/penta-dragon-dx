"""#23 mailbox/priority semantics only; not music or acoustic acceptance."""
import argparse
import csv
import json
from pathlib import Path


def check(rows):
    pending = decision = None
    errors, coalesced = [], []
    requests = reads = 0
    last_cycle = -1
    for index, row in enumerate(rows):
        event, command = row['event'], int(row['command'], 16)
        cycle = int(row['cycle'])
        if cycle < last_cycle:
            errors.append(f'{index}: nonmonotonic event clock')
        last_cycle = cycle
        if event == 'request':
            requests += 1
            if pending is not None:
                coalesced.append(pending)
            pending = row
        elif event == 'read':
            reads += 1
            if decision is not None:
                errors.append(f'{index}: prior read lacks a decision')
            if pending is None or pending['command'] != row['command']:
                errors.append(f'{index}: engine consumed an unrequested command')
            pending, decision = None, row
        elif event in ('accept', 'reject'):
            active = int(row['active'], 16)
            expected = 'accept' if active == 0 or active >= command else 'reject'
            if (decision is None or decision['command'] != row['command']
                    or decision['active'] != row['active'] or event != expected):
                errors.append(f'{index}: missing read or non-native priority decision')
            decision = None
        else:
            errors.append(f'{index}: unsupported event')
    if not requests or not reads:
        errors.append('missing request/consumption observations')
    if pending is not None or decision is not None:
        errors.append('terminal pending request or decision; trace incomplete')
    return dict(status='FAIL' if errors else 'PASS_OBSERVED_COMMAND_SEMANTICS',
                errors=errors, requests=requests, reads=reads,
                overwritten_requests=coalesced,
                scope='All traced mailbox events; overwritten requests retained. '
                      'No caller authenticity, music, PCM, or hardware fidelity verdict.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    args = parser.parse_args()
    with args.trace.open() as stream:
        result = check(csv.DictReader(stream, delimiter='\t'))
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['errors']))
