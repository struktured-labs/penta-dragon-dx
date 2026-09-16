#!/usr/bin/env python3
"""Serial native menu raster checks across twelve input/frame alignments.

Uses only the checked-in single-flight verifier. No emulator override,
state injection, image masks, or first-frame grace period is supported.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = Path(__file__).with_name('verify_menu_window_order.py')
OPEN_FRAMES = tuple(range(1196, 1208))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rom, output = args.rom.resolve(), args.output.resolve()
    if (ROOT / 'tmp').resolve() not in output.parents:
        parser.error('output must be below repository tmp/')
    if not rom.is_file() or output.exists():
        parser.error('ROM must exist and output must be fresh')
    output.mkdir(parents=True)
    identity = sha(rom)
    receipt = {'schema': 'penta-menu-phase-sweep-v1', 'status': 'running',
               'candidate': str(rom), 'candidate_sha256': identity,
               'verifier_sha256': sha(VERIFIER), 'phases': []}
    receipt_path = output / 'receipt.json'

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')

    save()
    for frame in OPEN_FRAMES:
        report = output / f'open-{frame}.report'
        log = output / f'open-{frame}.log'
        command = [sys.executable, str(VERIFIER), str(rom), '--output', str(report),
                   '--frames', str(frame+300), '--open-frame', str(frame),
                   '--close-frame', str(frame+180)]
        try:
            with log.open('wb') as stream:
                result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                        timeout=90, cwd=ROOT, check=False)
        except subprocess.TimeoutExpired:
            # A timed-out parent must not leave an emulator behind. Check before
            # another launch; no retry/parallel launch is performed here.
            subprocess.run([str(ROOT / 'scripts/check_emulator_processes.sh')], check=False)
            receipt['status'] = 'fail'
            receipt['failure'] = f'timeout at open frame {frame}'
            save()
            return 1
        phase = {'open_frame': frame, 'command': command, 'exit_code': result.returncode,
                 'log': str(log), 'log_sha256': sha(log)}
        if report.is_file():
            phase.update(report=str(report), report_sha256=sha(report))
        receipt['phases'].append(phase)
        if result.returncode != 0 or sha(rom) != identity:
            receipt['status'] = 'fail'
            receipt['failure'] = f'open frame {frame}; see {log}'
            save()
            print(receipt['failure'])
            return 1
        save()
    receipt['status'] = 'pass'
    save()
    print(f'PASS: all {len(OPEN_FRAMES)} menu phases, including first visible raster; {receipt_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
