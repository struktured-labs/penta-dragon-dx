"""#59: settled low-health Stage2 physical maps must match their tile policy.

Checks the assisted late-boss-defeat recipe, not exact OBS history or timing/audio.
"""
import argparse
import hashlib
import json
from pathlib import Path
from check_boss_prelude_handoff import state


def assess(raw):
    if (raw[0x5C80],raw[0x3BA],raw[0x3B7]) != (11,1,3):
        raise ValueError('expected low-health Stage2 gameplay')
    expected=bytearray(256)
    for tile in (0xAE,0xAF,0xBE,0xBF,0xC6,0xC7,0xD6,0xD7):expected[tile]=2
    if raw[0x4A00:0x4B00] != expected:
        raise ValueError('wrong Stage2 material policy')
    mismatches=[]
    for m in range(2):
        # Physical VRAM bank0 tiles and bank1 attributes, both pages.
        for y in range(24):
            for x in range(24):
                cell=m*0x400+y*32+x
                want=expected[raw[0x1C00+cell]]
                got=raw[0x3C00+cell]
                if got!=want:mismatches.append((m,x,y,got,want))
    if mismatches:raise ValueError(f'{len(mismatches)} stale/missing attribute cells: {mismatches[:4]}')
    return dict(passed=True,physical_maps=2,checked_cells=1152)


def inspect(folder):
    receipt=json.loads((folder/'receipt.json').read_text())
    if not receipt['complete'] or receipt['status']!=0:raise ValueError('incomplete replay')
    env=receipt['inputs_environment']
    required={'ENTRY_ONCE_HP':'109','ENTRY_FRAMES':'4200','TRANSITION_DEFEAT_FRAME':'1800','TRANSITION_LIVE_ENTRY':'1'}
    if any(env.get(k)!=v for k,v in required.items()):raise ValueError('wrong low-health recipe')
    for name,item in receipt['artifacts'].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('changed replay artifact: '+name)
    rom=(folder/'candidate.gb').read_bytes()
    results=[]
    for frame in range(3900,4201,30):
        results.append(dict(frame=frame,**assess(state(folder/f'frame-{frame:04d}.ss0',rom))))
    return dict(passed=True,scope=__doc__,checkpoints=results,
                rom_sha256=hashlib.sha256(rom).hexdigest(),
                receipt_sha256=hashlib.sha256((folder/'receipt.json').read_bytes()).hexdigest())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    result=inspect(args.folder)
    with args.output.open('x') as out:json.dump(result,out,indent=2);out.write('\n')
    print(json.dumps(result))
