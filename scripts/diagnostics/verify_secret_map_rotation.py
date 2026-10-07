"""#54: assisted cold secret-area replay rejects native rotations of map RAM.

The native secret header disables this writer. The broken played build must
actually modify C3E5..C3F4; candidate must reach and patrol stage 7 without it.
This does not qualify boss transitions, video neutrality, or audio fidelity.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HOST = Path('/home/struktured/projects/penta-dragon-dx').resolve()
sys.path.insert(0, str(HOST/'scripts/diagnostics'))
from runtime_tools import emulator_runtime_snapshot, reject_known_broken_cgb_runtime


def identity(path):
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def assess(trace, rotations):
    """Evaluate observed behavior, not the receipt's claimed completion flag."""
    secret = [row for row in trace if int(row[2], 16) == 7]
    positions = {(row[9], row[10]) for row in secret}
    changes = [r for r in rotations if 0xC3E5 <= int(r['address'], 16) <= 0xC3F4
               and r['before'] != r['after']]
    return dict(complete=len(trace) == 4800 and int(trace[-1][0]) == 4800,
                secret_frames=len(secret), distinct_positions=len(positions),
                map_rotation_changes=len(changes), rotation_count=len(rotations))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('parent','candidate','output'):
        parser.add_argument('--'+name, required=True, type=Path)
    args=parser.parse_args()
    out=args.output.resolve()
    if out.exists() or (ROOT/'tmp').resolve() not in out.parents:
        parser.error('fresh worktree tmp output required')
    out.mkdir(parents=True)
    os.environ['LD_LIBRARY_PATH']=str(HOST/'tmp/mgba-cgb-latches-r454/build')
    runtime=emulator_runtime_snapshot()
    reject_known_broken_cgb_runtime(runtime)
    paths={'probe':Path(__file__).with_name('probe_secret_map_rotation.lua'),
           'replay':HOST/'scripts/diagnostics/probe_secret_entry.lua',
           'guard':HOST/'scripts/mgba-qt-singleflight',
           'runner':Path(__file__), 'parent':args.parent, 'candidate':args.candidate}
    report=dict(scope=__doc__, inputs={k:identity(v) for k,v in paths.items()},
                runtime=runtime, runs={}, failures=[])
    try:
        for role in ('parent','candidate'):
            folder=out/role; folder.mkdir()
            shutil.copyfile(paths[role],folder/'candidate.gb')
            shutil.copyfile(paths['probe'],folder/'probe.lua')
            shutil.copyfile(paths['replay'],folder/'replay.lua')
            env=os.environ.copy()
            env.update(ENTRY_OUT=str(folder),SECRET_REPLAY_PROBE=str(folder/'replay.lua'),
                       ENTRY_COLD='1',ENTRY_CONTINUOUS_SECRET='1',ENTRY_ASSIST_RESOURCE='1',
                       ENTRY_FLOOR_PATROL='1',ENTRY_FRAMES='4800',ENTRY_CAPTURE_EVERY='30',
                       ENTRY_AUDIO_ENABLED='1',QT_QPA_PLATFORM='offscreen',SDL_AUDIODRIVER='dummy')
            report['runs'][role]={'environment':{k:v for k,v in env.items() if k.startswith('ENTRY_')}}
            with (folder/'emulator.log').open('w') as log:
                result=subprocess.run([str(paths['guard']),'--fastforward','-C','mute=0',
                    '-C','volume=256','-C','fastForwardMute=-1','-C','fastForwardVolume=256',
                    '--script',str(folder/'probe.lua'),str(folder/'candidate.gb')],
                    cwd=HOST,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=50)
            if result.returncode:
                raise RuntimeError(f'{role}: emulator exit {result.returncode}')
            with (folder/'trace.tsv').open() as f:
                rows=list(csv.reader(f,delimiter='\t'))[1:]
            with (folder/'rotations.tsv').open() as f:
                rotations=list(csv.DictReader(f,delimiter='\t'))
            observed=assess(rows,rotations)
            report['runs'][role].update(observed)
            report['runs'][role]['artifacts']={p.name:identity(p) for p in folder.iterdir() if p.is_file()}
            if not observed['complete'] or observed['secret_frames']<1000 or observed['distinct_positions']<10:
                report['failures'].append(f'{role}: insufficient replay coverage')
            if role=='parent' and observed['map_rotation_changes']==0:
                report['failures'].append('broken control did not reproduce map modification')
            if role=='candidate' and observed['rotation_count']:
                report['failures'].append('candidate executed forbidden secret map rotations')
        if emulator_runtime_snapshot()!=runtime:
            report['failures'].append('runtime changed during replay')
        for key,path in paths.items():
            if identity(path)!=report['inputs'][key]:
                report['failures'].append(f'{key} changed during replay')
    except Exception as error:
        report['failures'].append(str(error))
        subprocess.run([str(HOST/'scripts/check_emulator_processes.sh')],check=False)
        raise
    finally:
        report['passed']=not report['failures'] and len(report['runs'])==2
        (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('passed','failures')}))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
