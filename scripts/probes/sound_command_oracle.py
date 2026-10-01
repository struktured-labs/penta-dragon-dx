"""Issue #16: distinguish native sound commands from aliased frame samples.

This is an engine-command integrity oracle, not an acoustic-fidelity oracle.
Native PCM must be retained/checked separately for sound-output claims.
"""
from collections import Counter
import csv
import io
import math
import re

CALLERS = {0x26: 0x57B2, 0x0C: 0x79A2}
ENGINE_PCS = {'read': 0x45B6, 'accept': 0x45C7, 'reject': 0x45C2}
REQUEST = re.compile(r'rst_f=(\d+) A=([0-9A-F]+) caller=([0-9A-F]+) '
                     r'bank=([0-9A-F]+) scene=([0-9A-F]+) sp=([0-9A-F]+)')


def inspect_commands(raw: str, engine: str, metrics: dict, frames: int, cgb: bool) -> dict:
    header = re.search(r'# Boot frames: (\d+), measure frames: (\d+)', raw)
    if not header or int(header[2]) != frames or frames < 1:
        raise ValueError('missing/incomplete gameplay measurement')
    first, last = int(header[1]), int(header[1]) + frames
    required = ('transitions', 'command_pulses', 'clear_pulses', 'chained_commands',
                'unpaired_commands', 'max_nonzero_run', 'command_values',
                'dma_unreadable_samples')
    if any(key not in metrics for key in required):
        raise ValueError('missing frame-sample diagnostics')
    if (metrics['transitions'] < 0 or metrics['chained_commands'] != 0
            or metrics['unpaired_commands'] != 0 or metrics['max_nonzero_run'] > 1
            or not set(metrics['command_values']).issubset(CALLERS)):
        raise ValueError('invalid or incomplete sampled command pulse')
    if (any(metrics[key] < 0 for key in required if key != 'command_values')
            or metrics['transitions'] != metrics['command_pulses'] + metrics['clear_pulses']
            or metrics['unpaired_commands'] != metrics['command_pulses'] - metrics['clear_pulses']
            or sum(metrics['command_values'].values()) != metrics['command_pulses']):
        raise ValueError('inconsistent sampled command telemetry')
    requests = []
    for line in raw.splitlines():
        if not line.startswith('rst_f='):
            continue
        match = REQUEST.fullmatch(line)
        if not match:
            raise ValueError('malformed RST request')
        frame = int(match[1])
        command, caller, bank, scene = (int(match[n], 16) for n in (2, 3, 4, 5))
        if (command not in CALLERS or caller != CALLERS[command] or bank != 1
                or scene != 2 or not first <= frame <= last):
            raise ValueError('non-native route request or wrong caller/bank/scene')
        requests.append((frame, command))
    if not requests or len(requests) >= 200:
        raise ValueError('missing or potentially truncated request trace')
    if metrics['command_pulses'] > len(requests):
        raise ValueError('sampled commands exceed native requests')
    rows = list(csv.DictReader(io.StringIO(engine), delimiter='\t'))
    if len(rows) != len(requests) * 2:
        raise ValueError('requests and engine reads/decisions are not one-to-one')
    counts = Counter()
    previous = first
    for index, (request_frame, command) in enumerate(requests):
        read, decision = rows[index * 2:index * 2 + 2]
        for row in (read, decision):
            try:
                event, frame = row['event'], int(row['frame'])
                value, pc, svbk = (int(row[key], 16) for key in ('command', 'pc', 'svbk'))
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError('malformed engine event') from error
            if (event not in ENGINE_PCS or pc != ENGINE_PCS[event] or value != command
                    or not previous <= frame <= last
                    or (cgb and (svbk & 7) not in (0, 1))):
                raise ValueError('invalid engine event/command/WRAM bank/order')
            previous = frame
            counts[f'{event}:{value:02X}'] += 1
        if read['event'] != 'read' or decision['event'] not in ('accept', 'reject'):
            raise ValueError('missing engine read/decision pair')
        # No coalesced or terminally pending requests are silently dropped.
        if not request_frame <= int(read['frame']) <= request_frame + 2:
            raise ValueError('unmatched or delayed request consumption')
        active = int(read['active'], 16)
        expected = 'accept' if active == 0 or active >= command else 'reject'
        if decision['event'] != expected or decision['active'] != read['active']:
            raise ValueError('engine priority decision differs from native semantics')
    if not counts['accept:26']:
        raise ValueError('no accepted shot activity')
    return {'requests': len(requests), 'engine_counts': dict(counts),
            'sampled_transitions': metrics['transitions'], 'measurement_frames': frames,
            'frame_diagnostics': metrics}


def compare_commands(baseline: dict, candidate: dict, tolerance: float = 1.5) -> dict:
    if not math.isfinite(tolerance) or tolerance < 1:
        raise ValueError('invalid command-count tolerance')
    checks = []
    keys = set(baseline['engine_counts']) | set(candidate['engine_counts'])
    for key in sorted(keys):
        expected = baseline['engine_counts'].get(key, 0)
        observed = candidate['engine_counts'].get(key, 0)
        low, high = math.ceil(expected / tolerance), math.floor(expected * tolerance)
        checks.append({'event': key, 'baseline': expected, 'candidate': observed,
                       'minimum': low, 'maximum': high, 'pass': low <= observed <= high})
    return {'status': 'pass' if checks and all(row['pass'] for row in checks) else 'fail',
            'scope': 'native route requests and bank-qualified engine consumption; not acoustic equivalence',
            'tolerance': tolerance, 'checks': checks,
            'baseline': baseline, 'candidate': candidate}
