"""#27/#59: fresh assisted secret/boss/Stage2 checkpoints and broken control.

This is not an organic combat, audio, or complete visual-route qualification.
Both ROMs cold-boot independently; savestates are never retargeted.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import build_boss_prelude_inline_rearm as layout
import check_boss_prelude_handoff as checker
import playtest_successor_lineage as lineage
import lowhealth_candidate_lineage
from prepare_native_replay import prepare as prepare_native

ROOT = Path(__file__).resolve().parents[2]


def return_checkpoint_frame(rows, available, replay_frames=240):
    """Select a captured card state before the observed secret-return edge."""
    if [int(row['frame']) for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError('missing or unordered cold-prefix frame')
    secret_seen = False
    boundaries = []
    for previous, current in zip(rows, rows[1:]):
        if previous['stage'] == '07' and previous['scene'] in ('09', '0A'):
            secret_seen = True
        if (secret_seen and previous['scene'] == '18' and previous['stage'] == '00'
                and current['scene'] == '02' and current['stage'] == '00'):
            boundaries.append(int(current['frame']))
    if len(boundaries) != 1:
        raise ValueError('one observed secret-return boundary required')
    boundary = boundaries[0]
    candidates = [int(row['frame']) for row in rows
                  if int(row['frame']) in available and row['scene'] == '18'
                  and row['stage'] == '00' and int(row['frame']) < boundary
                  and boundary - int(row['frame']) + 69 <= replay_frames]
    if not candidates:
        raise ValueError('no pre-return card checkpoint with complete initialization tail')
    return max(candidates), boundary


def select_return_checkpoint(prefix, rom):
    receipt = json.loads((prefix / 'receipt.json').read_text())
    if receipt['status'] != 0 or receipt['rom_sha256'] != hashlib.sha256(rom).hexdigest():
        raise ValueError('cold-prefix receipt does not identify a completed candidate run')
    trace = prefix / 'trace.tsv'
    rows = list(csv.DictReader(trace.open(), delimiter='\t'))
    if len(rows) != int(receipt['diagnostic_environment']['ENTRY_FRAMES']):
        raise ValueError('incomplete cold-prefix trace')
    available = {int(path.stem.split('-')[1]) for path in prefix.glob('frame-*.ss0')}
    frame, boundary = return_checkpoint_frame(rows, available)
    path = prefix / f'frame-{frame:04d}.ss0'
    raw = checker.state(path, rom)
    if raw[0x5C80] != 24 or raw[0x3BA] != 0:
        raise ValueError('selected state is not the observed Stage1 return card')
    return path, dict(checkpoint_frame=frame, observed_return_frame=boundary,
                      state_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest(),
                      receipt_sha256=hashlib.sha256((prefix / 'receipt.json').read_bytes()).hexdigest())


def broken_control(rom):
    if not lineage.is_candidate(rom):
        raise ValueError('exact playtest candidate required')
    if rom[layout.HOOK:layout.HOOK + len(layout.NEW)] != layout.NEW:
        raise ValueError('unexpected rearm preimage')
    result = bytearray(rom)
    result[layout.HOOK:layout.HOOK + len(layout.OLD)] = layout.OLD
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    expected = layout.PARENT
    if lowhealth_candidate_lineage.is_candidate(rom):
        # #59: preserve each exact child's footer while reversing only rearm.
        # Replay authenticates all new owners before admitting the control.
        lowhealth_candidate_lineage.source_replay(rom)
        expected = {
            lowhealth_candidate_lineage.CANDIDATE_SHA:
                "a73288eb3ae486f8c431cde5ba69ba59d6932ccb3d579848926ef8bba01888fd",
            lowhealth_candidate_lineage.TITLE_CANDIDATE_SHA:
                "acc3d07674300458053942b2afc0c8ac9e6000b2c4c77b8a758619b68739ab60",
            lowhealth_candidate_lineage.TITLE_RETRY_SHA:
                "15264f4c19e649bf9c0c85e863e13d9b8f1586f4d5af574524046c1efff488fc",
        }[hashlib.sha256(rom).hexdigest()]
    # The experimental descendant's control retains all low-health changes:
    # revert only prelude rearm. It is not a historical played parent.
    if hashlib.sha256(result).hexdigest() != expected:
        raise ValueError('control is not the exact rearm-only reversal')
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
        # #59: normal-health soaks do not exercise raw scene0B. Keep the
        # dedicated low-health boss-to-Stage2 recipe in the release gate,
        # using this exact candidate's own independently captured cold state.
        low_env = {k: v for k, v in os.environ.items()
                   if not k.startswith(('ENTRY_', 'TRANSITION_'))}
        low_env['ENTRY_ONCE_HP'] = '109'
        low = out / 'candidate-lowhealth-transition'
        subprocess.run([sys.executable, str(Path(__file__).with_name('run_shalamar_transition.py')),
                        '--rom', str(out / 'candidate.gb'),
                        '--state', str(out / 'candidate-secret/frame-7200.ss0'),
                        '--output', str(low), '--live-boss-entry',
                        '--defeat-frame', '1800', '--frames', '4200'],
                       cwd=ROOT, env=low_env, check=True)
        low_report = out / 'lowhealth-stage2-attributes.json'
        subprocess.run([sys.executable, str(Path(__file__).with_name('check_lowhealth_stage2_attributes.py')),
                        str(low), '--output', str(low_report)], cwd=ROOT, check=True)
        report['low_health_stage2'] = json.loads(low_report.read_text())
        # #59: exercise scrolling with actual water exposure, not just a
        # stationary settled map. Restore only this ROM's own checkpoint.
        scroll_env = {k: v for k, v in os.environ.items()
                      if not k.startswith(('ENTRY_', 'TRANSITION_'))}
        runtime_env = scroll_env.copy()
        report['scroll_native_runtime'] = prepare_native(out, runtime_env)
        scroll_env.update(ENTRY_ROM=str(out / 'candidate.gb'), ENTRY_FRAMES='240',
                          ENTRY_CAPTURE_EVERY='1', ENTRY_KEYS='16',
                          ENTRY_NATIVE_TAP=runtime_env['LD_PRELOAD'])
        capture_id = Path(report['scroll_native_runtime']['capture_directory']).name
        scroll = out / ('candidate-lowhealth-scroll-' + capture_id)
        subprocess.run([sys.executable, str(Path(__file__).with_name('run_secret_entry_probe.py')),
                        str(low / 'frame-4200.ss0'), str(scroll)],
                       cwd=ROOT, env=scroll_env, check=True)
        scroll_report = out / 'lowhealth-stage2-scrolling.json'
        subprocess.run([sys.executable, str(Path(__file__).with_name('check_stage2_scrolling.py')),
                        str(scroll), '--output', str(scroll_report)], cwd=ROOT, check=True)
        report['low_health_stage2_scrolling'] = json.loads(scroll_report.read_text())
        # #45: every-frame return visibility, using this candidate's own cold
        # checkpoint. This replay adds no memory assistance or state retargeting.
        boundary_env = {k: v for k, v in os.environ.items()
                        if not k.startswith(('ENTRY_', 'TRANSITION_'))}
        boundary_env.update(ENTRY_ROM=str(out / 'candidate.gb'), ENTRY_FRAMES='240',
                            ENTRY_CAPTURE_EVERY='1', ENTRY_KEYS='1', ENTRY_PULSE_A='1')
        boundary = out / 'candidate-return'
        return_state, report['return_checkpoint_selection'] = select_return_checkpoint(
            out / 'candidate-secret', rom)
        subprocess.run([sys.executable, str(Path(__file__).with_name('run_secret_entry_probe.py')),
                        str(return_state), str(boundary)],
                       cwd=ROOT, env=boundary_env, check=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name('check_secret_return_visibility.py')),
                        str(boundary), '--output', str(out / 'return-visibility.json')],
                       cwd=ROOT, check=True)
        report['return_visibility'] = json.loads((out / 'return-visibility.json').read_text())
        report['passed'] = True
    finally:
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
