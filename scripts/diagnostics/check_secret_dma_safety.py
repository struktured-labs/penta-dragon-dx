"""Check observed #23 trial DMA boundaries, not complete hardware timing safety."""
import argparse
import csv
import json
from pathlib import Path

SELECTORS = {('24', '4008'), ('24', '5B5F'), ('24', '5B9F')}


def check(rows, *, selectors=SELECTORS):
    pending = None
    pairs = irqs = 0
    errors = []
    for index, row in enumerate(rows):
        kind = row['kind']
        bank = int(row['svbk'], 16)
        mode = int(row['stat'], 16) & 3
        if kind == 'irq':
            irqs += 1
            if bank == 6:
                errors.append(f'{index}: interrupt with scratch bank selected')
        elif kind == 'svbk':
            if int(row['a'], 16) & 7 == 6 and (row['bank'], row['pc']) not in selectors:
                errors.append(f'{index}: unexpected bank6 selector')
        elif kind in ('before', 'after'):
            if bank != 6 or row['hdma5'] != 'FF' or row['a'] != '01':
                errors.append(f'{index}: DMA bank/command/idle contract differs')
            if kind == 'before':
                if pending is not None:
                    errors.append(f'{index}: unmatched prior DMA start')
                if mode not in (0, 1):
                    errors.append(f'{index}: unsafe observed DMA start mode')
                pending = row
            else:
                if mode == 3:
                    errors.append(f'{index}: DMA ended in rendering mode')
                if pending is None:
                    errors.append(f'{index}: DMA end without start')
                else:
                    if int(row['pc'], 16) != int(pending['pc'], 16) + 2:
                        errors.append(f'{index}: DMA site pairing differs')
                    if int(row['cycle']) <= int(pending['cycle']):
                        errors.append(f'{index}: nonpositive DMA duration')
                    pairs += 1
                pending = None
    if pending is not None:
        errors.append('trace ends during DMA')
    if not pairs or not irqs:
        errors.append('missing DMA or interrupt observations')
    return dict(status='FAIL' if errors else 'PASS_OBSERVED_BOUNDARIES',
                dma_pairs=pairs, interrupt_entries=irqs, errors=errors,
                scope='Trace boundaries only; no proof of unobserved VRAM timing, full bank ownership, or audio fidelity.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace', type=Path)
    args = p.parse_args()
    with args.trace.open() as f:
        result = check(csv.DictReader(f, delimiter='\t'))
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result['errors']))
