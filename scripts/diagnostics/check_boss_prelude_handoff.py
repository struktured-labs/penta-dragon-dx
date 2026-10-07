"""#27/#59 narrow inherited-scene checkpoint gate, not whole-route qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parent))
from normalize_mgba_state_pc import png_chunks

def state(path,rom):
    raw=zlib.decompress(dict(png_chunks(path.read_bytes()))[b'gbAs'])
    if len(raw)!=71680 or int.from_bytes(raw[4:8],'little')!=zlib.crc32(rom)&0xffffffff or raw[16:32]!=rom[0x134:0x144]:raise ValueError('exact ROM state required')
    return raw

def assess(raw,rom,scene):
    if raw[0x5c80] not in (scene,11) or raw[0x3b7]!=scene:raise ValueError('wrong checkpoint scene')
    # The installed cache resolver canonicalizes low-health aliases only for
    # arenas0C..14. Dungeon0B deliberately stays0B, with FFBA choosing its LUT.
    # Authenticate that exact resolver before recognizing its cache contract.
    cache_scene=scene
    if scene==3 and raw[0x5c80]==11:
        resolver=bytes.fromhex('FA80D8FE0B200EF0B7D60CFE0938043E0B1802C60C210DDFBEF53E0DC39A6F')
        if rom[0x52de0:0x52de0+len(resolver)]!=resolver:raise ValueError('unknown dungeon alias resolver')
        if raw[0x3ba]!=1:raise ValueError('wrong dungeon selector')
        cache_scene=11
    if raw[0x391]==0 or raw[0x630d]!=cache_scene:raise ValueError('stale graphics scene')
    if scene==12:
        expected=rom[0x37200:0x37300]
    elif scene==3:
        expected=bytearray(256)
        for tile in (0xae,0xaf,0xbe,0xbf,0xc6,0xc7,0xd6,0xd7):expected[tile]=2
        if raw[0xd4:0xdc]!=rom[0x36820:0x36828]:raise ValueError('Stage2 scenery CRAM is stale')
    else:raise ValueError('unsupported scene')
    if raw[0x4a00:0x4b00]!=expected:raise ValueError('wrong material policy')

def load(folder):
    receipt=json.loads((folder/'receipt.json').read_text())
    if not receipt['complete'] or receipt['status']!=0:raise ValueError('incomplete route')
    for name,item in receipt['artifacts'].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('changed artifact')
    env=receipt['inputs_environment']
    if env['TRANSITION_LIVE_ENTRY']!='1' or env['TRANSITION_DEFEAT_FRAME']!='900' or env['ENTRY_FRAMES']!='3300':raise ValueError('wrong recipe')
    rom=(folder/'candidate.gb').read_bytes()
    initial=state(folder/'identity.ss0',rom)
    if initial[0x391]!=0 or initial[0x630d]!=10:raise ValueError('missing inherited miniboss disarm')
    return receipt,rom

def compare(parent,candidate):
    a,old=load(parent);b,new=load(candidate)
    if a['runtime']!=b['runtime']:raise ValueError('runtime differs')
    for key in ('probe','replay','runner'):
        if a['inputs'][key]['sha256']!=b['inputs'][key]['sha256']:raise ValueError('tools differ')
    results=[]
    for frame,scene in ((900,12),(3000,3)):
        before=state(parent/f'frame-{frame:04d}.ss0',old)
        after=state(candidate/f'frame-{frame:04d}.ss0',new)
        assess(after,new,scene)
        try:assess(before,old,scene)
        except ValueError as e:reason=str(e)
        else:raise ValueError('broken control unexpectedly passes')
        results.append(dict(frame=frame,scene=scene,parent_failure=reason,candidate='PASS'))
    return dict(passed=True,scope=__doc__,checkpoints=results,
        parent_sha256=hashlib.sha256(old).hexdigest(),candidate_sha256=hashlib.sha256(new).hexdigest(),
        receipts={str(p):hashlib.sha256((p/'receipt.json').read_bytes()).hexdigest() for p in (parent,candidate)},
        checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations='Synthetic native call and boss HP stimulus; two settled checkpoints only; entry/cadence/audio/full visual route remain separate gates.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('candidate',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=compare(a.parent,a.candidate);encoded=json.dumps(result,indent=2)+'\n'
    with a.output.open('x') as f:f.write(encoded)
    print(encoded,end='')
