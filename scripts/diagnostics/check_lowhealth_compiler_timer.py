"""#59 narrow Timer-latency gate; NOT native-PCM fidelity approval."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

TIMER_PERIOD=94208
MAX_GAP=TIMER_PERIOD*3//2


def assess(rows):
    timers=[r for r in rows if r['kind']=='timer']
    if len(timers)<1300:raise ValueError('incomplete 900-frame Timer trace')
    cycles=[int(r['cycle']) for r in timers]
    gaps=[b-a for a,b in zip(cycles,cycles[1:])]
    if min(gaps)<=0 or max(gaps)>MAX_GAP:raise ValueError('nonmonotonic or delayed Timer service')
    if min(int(r['frame']) for r in timers)>1 or max(int(r['frame']) for r in timers)!=899:
        raise ValueError('missing trace boundary')
    inside=[r for r in timers if r['bank']=='1E']
    if not inside:raise ValueError('compiler service not exercised')
    if any(r['svbk']!='01' or r['scene']!='0B' or r['canonical']!='03' or r['stage']!='01' for r in inside):
        raise ValueError('wrong compiler interrupt context')
    return dict(passed=True,timer_hits=len(timers),compiler_timer_hits=len(inside),
                max_gap_cycles=max(gaps),limit_cycles=MAX_GAP,all_gaps_cycles=gaps)


def inspect(observed,plain):
    receipts=[json.loads((p/'receipt.json').read_text()) for p in (observed,plain)]
    for r in receipts:
        if r['status']!=0 or r['native_capture']['metadata']['frames']!=900:
            raise ValueError('incomplete native replay')
    for field in ('rom_sha256','source_state_sha256','probe_sha256','runner_sha256','native_tap_sha256'):
        if receipts[0][field]!=receipts[1][field]:raise ValueError('observer identity mismatch: '+field)
    hashes={}
    for filename in ('native.s16le','native.video','native.states','native.timeline.tsv'):
        values=[]
        for r in receipts:
            value=hashlib.sha256((Path(r['native_capture_directory'])/filename).read_bytes()).hexdigest()
            if value!=r['native_capture']['hashes'][filename]:raise ValueError('changed native artifact')
            values.append(value)
        if values[0]!=values[1]:raise ValueError('observer changed '+filename)
        hashes[filename]=values[0]
    trace=observed/'sound-timing.tsv'
    result=assess(list(csv.DictReader(trace.open(),delimiter='\t')))
    result.update(scope=__doc__,observer_neutrality=hashes,rom_sha256=receipts[0]['rom_sha256'],
                  bindings={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (trace,observed/'receipt.json',plain/'receipt.json',Path(__file__))})
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('observed',type=Path);p.add_argument('plain',type=Path)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=inspect(args.observed,args.plain)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='all_gaps_cycles'}))
