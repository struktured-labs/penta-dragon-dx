"""#54 serial real-emulator loader test with the played ROM as negative control.

This tests all native stage header bytes and call/return registers, not rendered
gameplay or audio fidelity. Stage index is explicitly injected at the native call.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
# Use the shared project guard, not a separate worktree lock or raw emulator.
HOST=Path('/home/struktured/projects/penta-dragon-dx').resolve()
GUARD=HOST/'scripts/mgba-qt-singleflight'
BOOT=HOST/'scripts/diagnostics/probe_stage_integrity.lua'
PROBE=Path(__file__).with_name('probe_clean_stage_headers.lua')
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from runtime_tools import emulator_runtime_snapshot, reject_known_broken_cgb_runtime


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract_differences(values, control, target, require_native_common_timing):
    failures=[]
    for key in ('af_after','bc_after','de_after','hl_after','sp_after','bank','dc09_after'):
        if values[key]!=control[key]:
            failures.append(f'stage{target}: {key} differs from original')
    if require_native_common_timing and target < 7 and values['cycles']!=control['cycles']:
        failures.append(f'stage{target}: common header timing differs from original')
    return failures


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('original','parent','candidate','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--targets',default='0,1,2,3,4,5,6,7,8')
    p.add_argument('--require-native-common-timing',action='store_true',
                   help='require exact native elapsed cycles for unaffected records0..6 (#62)')
    a=p.parse_args()
    a.output=a.output.resolve()
    if a.output.exists() or (ROOT/'tmp').resolve() not in a.output.parents:
        p.error('fresh worktree tmp output required')
    a.output.mkdir(parents=True)
    os.environ['LD_LIBRARY_PATH']=str(HOST/'tmp/mgba-cgb-latches-r454/build')
    runtime=emulator_runtime_snapshot()
    reject_known_broken_cgb_runtime(runtime)
    targets=[int(s) for s in a.targets.split(',')]
    assert targets and all(0<=s<=8 for s in targets)
    original=a.original.read_bytes()
    report=dict(scope='assisted native loader contract only',inputs={
        name:dict(path=str(path.resolve()),sha256=sha(path)) for name,path in
        [('original',a.original),('parent',a.parent),('candidate',a.candidate),
         ('probe',PROBE),('boot_probe',BOOT),('guard',GUARD),
         ('runner',Path(__file__)),('runtime_tools',ROOT/'scripts/diagnostics/runtime_tools.py')]},
         runtime=runtime,runs=[],failures=[])
    runs={}
    for role in ('original','parent','candidate'):
        for target in targets:
            d=a.output/f'{role}-{target}'
            d.mkdir()
            rom=d/'candidate.gb'
            shutil.copyfile(getattr(a,role),rom)
            result=d/'result.txt'
            env=os.environ.copy()
            env.update(QT_QPA_PLATFORM='offscreen',SDL_AUDIODRIVER='dummy',
                       HEADER_TARGET=str(target),HEADER_OUT=str(result),
                       HEADER_BOOT_PROBE=str(BOOT),STAGE_OUT=str(d/'boot'),STAGE_TARGET='0')
            try:
                with (d/'emulator.log').open('w') as log:
                    run=subprocess.Popen([str(GUARD),'--fastforward','--script',str(PROBE),str(rom)],
                        cwd=HOST,env=env,stdout=log,stderr=subprocess.STDOUT)
                    deadline=time.monotonic()+30
                    stopped_by_owner=False
                    try:
                        while run.poll() is None:
                            if Path(str(result)+'.done').exists():
                                stopped_by_owner=True
                                run.terminate()
                                break
                            if time.monotonic()>deadline:
                                raise subprocess.TimeoutExpired(run.args,30)
                            time.sleep(0.01)
                    finally:
                        if run.poll() is None:
                            run.terminate()
                        try:
                            run.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            run.kill(); run.wait()
            except subprocess.TimeoutExpired:
                subprocess.run([str(HOST/'scripts/check_emulator_processes.sh')])
                raise
            if not stopped_by_owner or not result.exists():
                report['failures'].append(f'{role} {target}: exit {run.returncode}; result_exists={result.exists()}')
                report['passed']=False
                (a.output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
                raise RuntimeError(f'{role} {target}: exit {run.returncode}, see {d}')
            values=dict(line.split('=',1) for line in result.read_text().splitlines())
            expected=original[0x7BB3+target*29:0x7BB3+(target+1)*29].hex()
            row=dict(role=role,target=target,values=values,header_matches=values['header']==expected,
                     result_sha256=sha(result),owner_stopped_after_completion=stopped_by_owner,
                     child_returncode=run.returncode)
            report['runs'].append(row)
            runs[role,target]=row
            if role!='parent' and not row['header_matches']:
                report['failures'].append(f'{role} stage{target}: header mismatch')
            if role=='candidate':
                control=runs['original',target]['values']
                report['failures'].extend(contract_differences(
                    values,control,target,a.require_native_common_timing))
    bad=[t for t in targets if not runs['parent',t]['header_matches']]
    report['negative_control_failed_targets']=bad
    if any(t in (7,8) for t in targets) and not bad:
        report['failures'].append('known-broken parent failed to reject')
    for name,path in [('original',a.original),('parent',a.parent),('candidate',a.candidate),
                      ('probe',PROBE),('boot_probe',BOOT),('guard',GUARD),
                      ('runner',Path(__file__)),('runtime_tools',HOST/'scripts/diagnostics/runtime_tools.py')]:
        if sha(path)!=report['inputs'][name]['sha256']:
            report['failures'].append(f'{name} changed during run')
    if emulator_runtime_snapshot()!=runtime:
        report['failures'].append('runtime changed during run')
    report['passed']=not report['failures']
    report['require_native_common_timing']=a.require_native_common_timing
    (a.output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=report['passed'],failures=report['failures'],negative_control=bad)))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
