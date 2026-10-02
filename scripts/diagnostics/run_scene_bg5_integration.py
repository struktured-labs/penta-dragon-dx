#!/usr/bin/env python3
"""Build the opt-in BG5 experiment; run a full local matrix, never hardware.

If the experimental build fails, run the baseline matrix for regression
coverage and explicitly mark the experiment unqualified in the receipt.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import yaml

ROOT = Path(__file__).resolve().parents[2]


def main():
    out = ROOT / 'tmp' / ('scene-bg5-integration-' + time.strftime('%Y%m%d-%H%M%S'))
    out.mkdir(parents=True, exist_ok=False)
    scratch = out / 'runtime-tmp'
    scratch.mkdir()
    env = dict(os.environ, TMPDIR=str(scratch), TMP=str(scratch), TEMP=str(scratch), PYTHONUNBUFFERED='1')
    subprocess.run(['bash', 'scripts/check_emulator_processes.sh', '--require-none'], cwd=ROOT, check=True)
    document = yaml.safe_load((ROOT / 'palettes/penta_palettes_v097.yaml').read_text())
    document['stage1_hazard_palettes']['RotatingSpikeBody']['enabled'] = True
    palette = out / 'experimental-palettes.yaml'
    palette.write_text(yaml.safe_dump(document, sort_keys=False))
    candidate = out / 'experimental.gbc'
    command = [sys.executable, 'scripts/build_ted_expanded_candidate.py',
               '--output', str(candidate), '--palette-yaml', str(palette),
               '--native-sparse', '--native-pose-table', '--menu-icon-colors']
    print(f'Artifacts: {out}', flush=True)
    with (out / 'experimental-build.log').open('w') as log:
        build = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    receipt = {'experimental_build_returncode': build.returncode,
               'experimental_build_command': command,
               'hardware_used': False,
               'coverage_gap': 'Sara ceiling report lacks exact replay route/fixture'}
    if build.returncode:
        candidate = ROOT / 'tmp/stream-tonight/Penta Dragon DX v3.01.gbc'
        receipt['matrix_subject'] = 'baseline r536; NOT the experimental change'
        print('Experimental build FAILED. Running full baseline regression matrix.', flush=True)
        print('\n'.join((out / 'experimental-build.log').read_text().splitlines()[-12:]), flush=True)
    else:
        receipt['matrix_subject'] = 'experimental scene-local BG5 candidate'
    receipt['rom_path'] = str(candidate)
    receipt['rom_sha256'] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    (out / 'run.json').write_text(json.dumps(receipt, indent=2))
    command = [sys.executable, 'scripts/diagnostics/verify_release_candidate.py',
               str(candidate), '--output', str(out / 'matrix')]
    result = subprocess.run(command, cwd=ROOT, env=env)
    receipt['matrix_returncode'] = result.returncode
    receipt['experimental_qualified'] = False
    (out / 'run.json').write_text(json.dumps(receipt, indent=2))
    subprocess.run(['bash', 'scripts/check_emulator_processes.sh'], cwd=ROOT)
    return 1 if build.returncode or result.returncode else 0


if __name__ == '__main__':
    raise SystemExit(main())
