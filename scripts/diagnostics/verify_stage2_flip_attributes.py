"""Audit both physical VRAM banks at every saved later-stage publication."""
import argparse
import hashlib
import json
from pathlib import Path
from verify_stage7_dual_plane_visual_receipts import serialized_state, VRAM0, VRAM1, WRAM0, WRAM1, CPU_PC, CPU_A, MEMORY_CURRENT_ROM_BANK, MEMORY_CURRENT_WRAM_BANK

RARE=frozenset((0xAE,0xAF,0xBE,0xBF,0xC6,0xC7,0xD6,0xD7))
HEALTH=frozenset((0x88,0x89,0x96,0x98,0x99))
ARROW=frozenset((0xA0,0xA1,0xB0,0xB1))


def expected_attr(stage,tile):
    if stage not in range(2,8):raise ValueError('unknown stage')
    if stage in (2,5,7) and tile in RARE:return 2
    if stage in (3,5,6) and tile in HEALTH:return 1
    if stage==7 and tile in ARROW:return 4
    if stage==4:
        if 1<=tile<=8:return 4
        if tile in (0x2D,0x2E):return 2
    if stage==5 and (2<=tile<=7 or 0x12<=tile<=0x17):return 5
    if stage==7 and tile in (0x19,0x1A):return 5
    return 0


def audit_state(state, site, base, stage=2):
    if site not in (0x7457,0x7462) or base not in (0x9800,0x9C00):
        raise ValueError('unknown publication boundary')
    if int.from_bytes(state[CPU_PC:CPU_PC+2],'little')!=site:
        raise ValueError('publication PC mismatch')
    if int.from_bytes(state[MEMORY_CURRENT_ROM_BANK:MEMORY_CURRENT_ROM_BANK+2],'little')!=13:
        raise ValueError('publisher bank mismatch')
    if state[MEMORY_CURRENT_WRAM_BANK]!=1 or state[WRAM1+0x880]!=stage+1:
        raise ValueError('not live expected-stage WRAM context')
    if (0x9C00 if state[CPU_A]&8 else 0x9800)!=base:
        raise ValueError('selected map mismatch')
    for row in range(24):
        for col in range(24):
            tile=state[WRAM0+0x1A0+row*24+col]
            offset=base-0x8000+row*32+col
            if state[VRAM0+offset]!=tile:
                raise ValueError(f'tile mismatch at {row},{col}')
            expected=expected_attr(stage,tile)
            if state[VRAM1+offset]!=expected:
                raise ValueError(f'attribute mismatch at {row},{col}: tile={tile:02X} actual={state[VRAM1+offset]:02X} expected={expected:02X}')


def audit(directory,stage=2):
    manifest=json.loads((directory/'run-manifest.json').read_text())
    if manifest['status']!='PASS' or not manifest['identity_intact']:
        raise ValueError('soak did not pass')
    if manifest['identity_before']!=manifest['identity_after']:
        raise ValueError('soak identity changed')
    for field in ('candidate','probe','verifier','launcher'):
        digest=hashlib.sha256(Path(manifest[field]).read_bytes()).hexdigest()
        if digest!=manifest['identity_after'][field+'_sha256']:
            raise ValueError('stale identity: '+field)
    records=[];maps=set()
    if stage not in manifest['invocation']['stages']:raise ValueError('stage not in recorded invocation')
    trace=directory/f'stage{stage}.flip-events.tsv'
    for line in trace.read_text().splitlines():
        fields=line.split('\t')
        if len(fields)!=14 or int(fields[11])!=0:raise ValueError('invalid online trace')
        index=int(fields[0]);site=int(fields[2],16);base=int(fields[5],16)
        if index!=len(records)+1 or fields[13]!=f'flip{index:06d}.ss0':
            raise ValueError('invalid state sequence')
        path=directory/(f'stage{stage}.'+fields[13])
        audit_state(serialized_state(path),site,base,stage)
        maps.add(base)
        records.append(dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    if len(records)<20 or maps!={0x9800,0x9C00}:raise ValueError('insufficient two-map coverage')
    return dict(passed=True,stage=stage,candidate_sha256=manifest['identity_after']['candidate_sha256'],
        publications=len(records),tile_cells=len(records)*576,attribute_cells=len(records)*576,
        trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest(),states=records)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path)
    p.add_argument('--stage',type=int,choices=range(2,8),default=2)
    args=p.parse_args()
    print(json.dumps(audit(args.directory,args.stage),indent=2))
