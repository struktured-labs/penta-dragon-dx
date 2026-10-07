"""#27/#59: fresh assisted secret/boss/Stage2 checkpoints and broken control.

This is not an organic combat, audio, or complete visual-route qualification.
Both ROMs cold-boot independently; savestates are never retargeted.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import build_boss_prelude_inline_rearm as layout
import check_boss_prelude_handoff as checker
import playtest_successor_lineage as lineage

ROOT = Path(__file__).resolve().parents[2]


def broken_control(rom):
    if not lineage.is_candidate(rom):
        raise ValueError('exact playtest candidate required')
    if rom[layout.HOOK:layout.HOOK + len(layout.NEW)] != layout.NEW:
        raise ValueError('unexpected rearm preimage')
    result = bytearray(rom)
    result[layout.HOOK:layout.HOOK + len(layout.OLD)] = layout.OLD
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    if hashlib.sha256(result).hexdigest() != layout.PARENT:
        raise ValueError('control is not the exact pre-rearm parent')
    return bytes(result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    if out.exists() or (ROOT / 'tmp').resolve() not in out.parents:
        p.error('fresh repository tmp output required')
    rom = a.rom.read_bytes()
    control = broken_control(rom)
    out.mkdir(parents=True)
    report = dict(passed=False, scope=__doc__, roms={}, runs=[])
    try:
        for name, data in (('control', control), ('candidate', rom)):
            path = out / (name + '.gb')
            path.write_bytes(data)
            report['roms'][name] = hashlib.sha256(data).hexdigest()
            prefix = out / (name + '-secret')
            env = os.environ.copy()
            # Do not inherit unrelated interactive probe switches.
            env = {k: v for k, v in env.items() if not k.startswith(('ENTRY_', 'TRANSITION_'))}
            env.update(ENTRY_ROM=str(path), ENTRY_FRAMES='7200', ENTRY_RETURN_WALK='1',
                       ENTRY_PULSE_A='1', ENTRY_KEYS='1', ENTRY_ASSIST_RESOURCE='1',
                       ENTRY_CONTINUOUS_SECRET='1', ENTRY_CAPTURE_EVERY='120')
            subprocess.run([sys.executable, str(Path(__file__).with_name('run_secret_entry_probe.py')),
                            'cold', str(prefix)], cwd=ROOT, env=env, check=True)
            clean_env = {k: v for k, v in env.items() if not k.startswith(('ENTRY_', 'TRANSITION_'))}
            subprocess.run([sys.executable, str(Path(__file__).with_name('run_shalamar_transition.py')),
                            '--rom', str(path), '--state', str(prefix / 'frame-7200.ss0'),
                            '--output', str(out / (name + '-transition')), '--live-boss-entry',
                            '--defeat-frame', '900', '--frames', '3300'],
                           cwd=ROOT, env=clean_env, check=True)
            report['runs'].append(name)
        report['comparison'] = checker.compare(out / 'control-transition', out / 'candidate-transition')
        report['passed'] = True
    finally:
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
