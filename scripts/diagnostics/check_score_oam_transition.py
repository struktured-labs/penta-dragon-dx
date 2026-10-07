"""#60 rendered-card OAM cleanup gate, requiring a broken control.

This covers lingering hardware sprites, not glyph palettes or all boss art.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import zlib

sys.path.insert(0,str(Path('/home/struktured/projects/penta-dragon-dx/scripts/diagnostics')))
from normalize_mgba_state_pc import png_chunks

def attribute_errors(raw):
    if len(raw)!=71680:raise ValueError('unsupported state layout')
    if raw[0x340]&8:raise ValueError('unexpected card tilemap')
    return [i for i,x in enumerate(raw[0x3C00:0x4000]) if x!=0]

def assess(rows):
    cards=[r for r in rows if r['scene']=='18' and r['stage']=='01']
    scores=[r for r in rows if r['score_poll']=='1']
    gameplay=[r for r in rows if r['scene']=='03' and r['stage']=='01']
    return dict(complete=len(rows)==2400 and rows[-1]['frame']=='2400',
                card_frames=len(cards),
                card_dirty_frames=sum(int(r['visible_oam'])>0 for r in cards),
                card_shadow_dirty_frames=sum(int(r['shadow_oam'])>0 for r in cards),
                score_frames=len(scores),
                score_dirty_frames=sum(int(r['visible_oam'])>0 for r in scores),
                score_shadow_dirty_frames=sum(int(r['shadow_oam'])>0 for r in scores),
                first_score=int(scores[0]['frame']) if scores else None,
                first_card=int(cards[0]['frame']) if cards else None,
                first_gameplay=int(gameplay[0]['frame']) if gameplay else None)

def load(folder):
    report=json.loads((folder/'receipt.json').read_text())
    if not report['complete'] or report['status']!=0:raise ValueError('incomplete producer')
    for name,record in report['artifacts'].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError(f'artifact changed: {name}')
    with (folder/'transition.tsv').open() as f: rows=list(csv.DictReader(f,delimiter='\t'))
    result=assess(rows)
    frames={int(r['frame']) for r in rows if r['score_poll']=='1' or (r['scene']=='18' and r['stage']=='01')}
    captures=[]
    for path in sorted(folder.glob('frame-*.ss0')):
        frame=int(path.stem.split('-')[1])
        if frame not in frames:continue
        raw=zlib.decompress(dict(png_chunks(path.read_bytes()))[b'gbAs'])
        captures.append(dict(frame=frame,nonneutral_cells=attribute_errors(raw)))
    result['attribute_captures']=captures
    return report,result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path);p.add_argument('candidate',type=Path)
    p.add_argument('--attributes',action='store_true',help='also require neutral full card map attributes')
    a=p.parse_args();parent,before=load(a.parent);candidate,after=load(a.candidate)
    failures=[]
    for role,r in [('parent',before),('candidate',after)]:
        if not r['complete'] or r['card_frames']<60 or r['score_frames']<60 or r['first_gameplay'] is None:
            failures.append(role+': route incomplete')
    if before['score_dirty_frames']==0:failures.append('broken control failed to reproduce')
    if any(after[k] for k in ('card_dirty_frames','card_shadow_dirty_frames','score_dirty_frames','score_shadow_dirty_frames')):failures.append('candidate stale sprites')
    if any(before[k]!=after[k] for k in ('first_score','first_card','first_gameplay')):
        failures.append('transition frame timing changed')
    if parent['runtime']!=candidate['runtime']:failures.append('runtime mismatch')
    if parent['inputs_environment']!={**candidate['inputs_environment'],'ENTRY_OUT':parent['inputs_environment']['ENTRY_OUT']}:
        failures.append('input recipe mismatch')
    for key in ('probe','replay','runner'):
        if parent['inputs'][key]['sha256']!=candidate['inputs'][key]['sha256']:failures.append(key+' mismatch')
    if a.attributes:
        if len(after['attribute_captures'])<10:failures.append('insufficient attribute captures')
        if any(c['nonneutral_cells'] for c in after['attribute_captures']):failures.append('candidate stale card attributes')
        if not any(c['nonneutral_cells'] for c in before['attribute_captures']):failures.append('attribute negative control did not reject')
    print(json.dumps(dict(passed=not failures,failures=failures,before=before,after=after),indent=2))
    return 1 if failures else 0

if __name__=='__main__':raise SystemExit(main())
