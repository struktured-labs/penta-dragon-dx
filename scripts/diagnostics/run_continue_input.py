#!/usr/bin/env python3
"""Run guarded #28 cold Stage1 or state-backed Stage2 diagnostics, not hardware."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from verify_continue_input import digest, verify
from runtime_tools import emulator_runtime_snapshot, reject_known_broken_cgb_runtime

ROOT=Path(__file__).resolve().parents[2]
PROBE=Path(__file__).with_name('probe_continue_input.lua')
GUARD=ROOT/'scripts/mgba-qt-singleflight'

def run(rom, output, button, state=None, stage=1, prompt_relative=False, approach_up=False):
    if approach_up and (stage!=2 or not prompt_relative):
        raise ValueError('approach requires Stage2 prompt-relative replay')
    if stage not in (1,2) or (stage==2 and state is None):
        raise ValueError('Stage2 requires an explicit candidate-owned entry state')
    runtime=emulator_runtime_snapshot()
    reject_known_broken_cgb_runtime(runtime)
    output=output.resolve()
    if output.exists() or (ROOT/'tmp').resolve() not in output.parents:
        raise ValueError('output must be fresh beneath repository tmp/')
    output.mkdir(parents=True)
    shutil.copyfile(rom,output/'candidate.gb')
    shutil.copyfile(PROBE,output/'probe.lua')
    if state is not None:
        shutil.copyfile(state,output/'entry.ss0')
    env={k:v for k,v in os.environ.items() if not k.startswith('ENTRY_')}
    env.pop('PENTA_MGBA_QT_BIN',None)
    env.update(ENTRY_OUT=str(output),ENTRY_KEYS=str(button),ENTRY_COLD='0' if state else '1',
               ENTRY_STAGE=str(stage),
               ENTRY_FRAMES='6000' if prompt_relative else '2400',ENTRY_CONTINUE_TEST='1',
               ENTRY_PROMPT_RELATIVE='1' if prompt_relative else '0',
               ENTRY_APPROACH_UP='1' if approach_up else '0',
               QT_QPA_PLATFORM='offscreen',SDL_AUDIODRIVER='dummy')
    if state is not None:
        env['ENTRY_STATE']=str(output/'entry.ss0')
    receipt=dict(rom_sha256=digest(output/'candidate.gb'),probe_sha256=digest(output/'probe.lua'),
                 source_state_sha256=digest(output/'entry.ss0') if state else None,
                 runtime=runtime,observer_memory_writes=True,
                 assistance=('frame1201: FFE6=1 and '
                             + ('DCBB=1 for native decrement-to-zero; ' if stage==2 else 'DCBB=0; ')
                             + 'then native A/Start/neutral input'),
                 diagnostic_environment={k:v for k,v in env.items() if k.startswith('ENTRY_')},
                 launcher_sha256=digest(GUARD),guard_sha256=digest(ROOT/'scripts/mgba_singleflight.py'))
    started=time.monotonic()
    with (output/'emulator.log').open('w') as log:
        try:
            result=subprocess.run([str(GUARD),'--fastforward','--script',str(output/'probe.lua'),
                                   str(output/'candidate.gb')],cwd=ROOT,env=env,
                                  stdout=log,stderr=subprocess.STDOUT,timeout=40)
            receipt['status']=result.returncode
        except subprocess.TimeoutExpired:
            receipt['status']=124
            subprocess.run([str(ROOT/'scripts/check_emulator_processes.sh')],cwd=ROOT,check=False)
    receipt['elapsed_seconds']=time.monotonic()-started
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if receipt['status']:
        raise RuntimeError(f"guarded run failed/status {receipt['status']}; retain {output}")
    report=verify(output)
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--button',choices=['a','start','neutral'],default='a')
    parser.add_argument('--state',type=Path)
    parser.add_argument('--stage',type=int,choices=[1,2],default=1)
    parser.add_argument('--prompt-relative',action='store_true',
                        help='separate 6000-frame diagnostic: input 12 frames after first native Continue poll')
    parser.add_argument('--approach-up',action='store_true',
                        help='Stage2 prompt-relative only: hold Up after health stimulus until native death')
    args=parser.parse_args()
    report=run(args.rom,args.output,dict(a=1,start=8,neutral=0)[args.button],args.state,args.stage,args.prompt_relative,args.approach_up)
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['passed'] else 1)
