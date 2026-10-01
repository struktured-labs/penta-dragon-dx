#!/usr/bin/env python3
"""#28 oracle for explicit one-credit/death diagnostics.

Cold Stage1 or state-backed Stage2, not natural progression or hardware.
Requires the full 2400-frame trace, native Continue input observations and
exact ROM/probe bindings. A rejection is a failed result, not missing evidence.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify(folder):
    receipt=json.loads((folder/'receipt.json').read_text())
    env=receipt['diagnostic_environment']
    prompt_relative=env.get('ENTRY_PROMPT_RELATIVE','0')=='1'
    limit=6000 if prompt_relative else 2400
    stage=int(env.get('ENTRY_STAGE','1'))
    approach=env.get('ENTRY_APPROACH_UP','0')=='1'
    if approach and (stage!=2 or not prompt_relative):
        raise ValueError('approach requires Stage2 prompt-relative replay')
    if stage not in (1,2):
        raise ValueError('unsupported stage')
    if receipt['source_state_sha256'] is None:
        if stage!=1 or env.get('ENTRY_COLD')!='1':
            raise ValueError('cold route must be Stage1')
    elif (env.get('ENTRY_COLD')!='0'
          or receipt['source_state_sha256']!=digest(folder/'entry.ss0')):
        raise ValueError('entry state binding differs')
    if (receipt['status']!=0
            or env.get('ENTRY_CONTINUE_TEST')!='1'
            or env.get('ENTRY_FRAMES')!=str(limit) or env.get('ENTRY_KEYS') not in ('0','1','8')):
        raise ValueError('requires completed cold one-credit diagnostic')
    if receipt['rom_sha256']!=digest(folder/'candidate.gb') or receipt['probe_sha256']!=digest(folder/'probe.lua'):
        raise ValueError('ROM or probe binding differs')
    rows=[[int(v,10 if i==0 else 16) for i,v in enumerate(line.split())]
          for line in (folder/'continue.tsv').read_text().splitlines()]
    if any(len(row)!=6 for row in rows) or [r[0] for r in rows]!=list(range(1,limit+1)):
        raise ValueError(f'requires all{limit} ordered frame observations')
    with (folder/'trace.tsv').open() as handle:
        state=list(csv.DictReader(handle,delimiter='\t'))
    if [int(r['frame']) for r in state]!=list(range(1,limit+1)):
        raise ValueError('incomplete state trace')
    for row, snapshot in zip(rows,state):
        if row[1]!=int(snapshot['scene'],16):
            raise ValueError('scene traces disagree')
    if rows[1200][2]!=1:
        raise ValueError('diagnostic credit not observed')
    if rows[1200][1]!=stage+1 or state[1200]['mode']!='01':
        raise ValueError('death stimulus was not in requested active stage')
    death=next((r[0] for r in rows[1201:] if r[1]==0x17),None)
    if death is None:
        raise ValueError('death not reached; not a Continue test')
    polls=[[int(v,10 if i==0 else 16) for i,v in enumerate(line.split())]
           for line in (folder/'continue-poll.tsv').read_text().splitlines()]
    if not polls or any(len(r)!=5 for r in polls):
        raise ValueError('missing/malformed native Continue checks')
    if any(not death<=r[0]<=limit for r in polls):
        raise ValueError('Continue checks outside death replay')
    if any(a[0]>b[0] for a,b in zip(polls,polls[1:])):
        raise ValueError('Continue polls are unordered')
    input_start=polls[0][0]+12 if prompt_relative else 1380
    if prompt_relative and input_start+420>=limit:
        raise ValueError('Continue input window is censored')
    for row in rows[1200:]:
        phase=row[0]-input_start if prompt_relative else row[0]
        expected=int(env['ENTRY_KEYS']) if input_start<=row[0]<input_start+420 and phase%12<6 else 0
        if approach and 1201<row[0]<death:
            expected=64
        if row[5]!=expected:
            raise ValueError('recorded button schedule differs')
    resumed=next((r[0] for r in rows[death:] if r[1]==stage+1),None)
    title=next((r[0] for r in rows[death:] if r[1]==1),None)
    accepted=any(r[1]&1 for r in polls)
    if env['ENTRY_KEYS']=='1':
        passed=bool(accepted and resumed and not title and rows[-1][2]==0
                    and state[-1]['mode']=='01' and rows[-1][1]==stage+1)
    else:
        countdown={r[3] for r in rows[death:] if r[1]==0x17 and r[2]==1}
        passed=bool(not accepted and not resumed and title and set(range(1,11))<=countdown)
    return dict(issue=28,passed=passed,keys=int(env['ENTRY_KEYS']),death_frame=death,
                resumed_frame=resumed,title_frame=title,native_a_edge=accepted,
                poll_observations=len(polls),rom_sha256=receipt['rom_sha256'],
                probe_sha256=receipt['probe_sha256'],
                trace_sha256=digest(folder/'continue.tsv'),
                schedule='native-prompt-relative' if prompt_relative else 'fixed-frame',
                input_start_frame=input_start, frames=limit,
                approach_up=approach,
                scope=f'assisted Stage{stage} Continue input/timeout only; not natural-route/hardware/visual qualification')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    args=parser.parse_args()
    result=verify(args.capture)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)
