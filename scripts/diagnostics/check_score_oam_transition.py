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

sys.path.insert(0,str(Path(__file__).resolve().parent))
from normalize_mgba_state_pc import png_chunks

def attribute_errors(raw):
    if len(raw)!=71680:raise ValueError('unsupported state layout')
    if raw[0x340]&8:raise ValueError('unexpected card tilemap')
    return [i for i,x in enumerate(raw[0x3C00:0x4000]) if x!=0]

def input_recipe(report,folder):
    """Normalize only validated output-owned paths, never gameplay inputs."""
    recipe=dict(report['inputs_environment'])
    if recipe.get('ENTRY_OUT')!=str(folder.resolve()):
        raise ValueError('receipt output path differs')
    recipe['ENTRY_OUT']='<output>'
    if 'ENTRY_NATIVE_START_GATE' in recipe:
        if recipe['ENTRY_NATIVE_START_GATE']!=str(folder.resolve()/'native-runtime/ready'):
            raise ValueError('startup marker is not owned by this replay')
        recipe['ENTRY_NATIVE_START_GATE']='<output>/native-runtime/ready'
    return recipe

def assess(rows, expected_frames=2400):
    if not isinstance(expected_frames,int) or expected_frames<1:
        raise ValueError('positive expected frame count required')
    cards=[r for r in rows if r['scene']=='18' and r['stage']=='01']
    scores=[r for r in rows if r['score_poll']=='1']
    # Low health uses scene0B in both dungeons and arenas. Only the native
    # owner proves Stage2 gameplay; never accept every alias as a dungeon.
    gameplay=[r for r in rows if r['stage']=='01' and
              (r['scene']=='03' or (r['scene']=='0B' and r.get('native_scene')=='03'))]
    return dict(complete=[int(r['frame']) for r in rows]==list(range(1,expected_frames+1)),
                expected_frames=expected_frames,
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
    result=assess(rows,int(report['inputs_environment']['ENTRY_FRAMES']))
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
    if input_recipe(parent,a.parent)!=input_recipe(candidate,a.candidate):
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
