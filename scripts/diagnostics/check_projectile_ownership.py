"""#57 hardware-OAM/CRAM separation gate, with same-frame geometry guard."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import zlib

sys.path.insert(0,'/home/struktured/projects/penta-dragon-dx/scripts/diagnostics')
from normalize_mgba_state_pc import png_chunks

def assess(before,after,power):
 if power not in range(3):raise ValueError('unsupported weapon')
 if len(before)!=240 or len(after)!=240:raise ValueError('incomplete route')
 counts=dict(enemy_samples=0,weapon_samples=0,simultaneous_frames=0,broken_shared_samples=0)
 for frame,(a,b) in enumerate(zip(before,after),1):
  for row in (a,b):
   if int(row['frame'])!=frame or int(row['power_requested'])!=power or row['form']!='0':raise ValueError('recipe/sequence mismatch')
  if a['scene']!=b['scene'] or b['scene'] not in ('02','0A','0B'):raise ValueError('gameplay scene mismatch')
  old=bytes.fromhex(a['oam']);new=bytes.fromhex(b['oam'])
  if len(old)!=160 or len(new)!=160:raise ValueError('truncated OAM')
  seen=set()
  for i in range(0,160,4):
   if old[i:i+3]!=new[i:i+3]:raise ValueError('sprite position/tile timeline changed')
   y,x,tile,attr=new[i:i+4]
   if old[i+3]&248!=attr&248:raise ValueError('non-palette attribute changed')
   if tile!=15 and old[i+3]!=attr:raise ValueError('unrelated sprite recolored')
   if not (0<x<168 and 0<y<160):continue
   if tile==15:
    counts['enemy_samples']+=1;seen.add('enemy')
    counts['broken_shared_samples']+=old[i+3]&7==0
    if attr&7!=3:raise ValueError('enemy still uses weapon palette')
   if tile==power+1:
    counts['weapon_samples']+=1;seen.add('weapon')
    if attr&7!=0:raise ValueError('player weapon palette changed')
  counts['simultaneous_frames']+=len(seen)==2
 if min(counts.values())<20:raise ValueError('insufficient simultaneous/negative-control coverage')
 return counts

def load(folder):
 receipt=json.loads((folder/'receipt.json').read_text())
 if not receipt['complete'] or len(receipt['runs'])!=3:raise ValueError('incomplete producer')
 for power,run in enumerate(receipt['runs']):
  if run['power']!=power or run['status']!=0:raise ValueError('failed producer')
  for name,record in run['artifacts'].items():
   if hashlib.sha256((folder/f'power{power}'/name).read_bytes()).hexdigest()!=record['sha256']:raise ValueError('changed artifact')
 return receipt

def compare(parent,candidate):
 before=load(parent);after=load(candidate)
 if before['runtime']!=after['runtime']:raise ValueError('runtime mismatch')
 for k in ('runner','probe','guard'):
  if before['inputs'][k]['sha256']!=after['inputs'][k]['sha256']:raise ValueError('tool mismatch')
 results=[];enemy_colors=set();player_colors=set()
 for power in range(3):
  folders=[p/f'power{power}' for p in (parent,candidate)]
  rows=[list(csv.DictReader((p/'oam.tsv').open(),delimiter='\t')) for p in folders]
  result=assess(*rows,power)
  for frame in range(30,241,30):
   states=[]
   for folder in folders:
    raw=zlib.decompress(dict(png_chunks((folder/f'frame-{frame:04d}.ss0').read_bytes()))[b'gbAs'])
    rom=(folder/'candidate.gb').read_bytes()
    if len(raw)!=71680 or int.from_bytes(raw[4:8],'little')!=zlib.crc32(rom)&0xffffffff or raw[16:32]!=rom[0x134:0x144]:raise ValueError('state/ROM mismatch')
    states.append(raw)
   if states[0][0xd4:0x154]!=states[1][0xd4:0x154]:raise ValueError('palette contents changed')
   enemy_colors.add(states[1][0x12c:0x134]);player_colors.add(states[1][0x114:0x11c])
  results.append(dict(power=power,**result))
 if len(enemy_colors)!=1 or len(player_colors)!=3 or enemy_colors&player_colors:raise ValueError('palette coupling remains')
 return dict(passed=True,scope=__doc__,weapons=results,
  enemy_cram=next(iter(enemy_colors)).hex(),
  parent_receipt_sha256=hashlib.sha256((parent/'receipt.json').read_bytes()).hexdigest(),
  candidate_receipt_sha256=hashlib.sha256((candidate/'receipt.json').read_bytes()).hexdigest())

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('candidate',type=Path)
 p.add_argument('--output',type=Path)
 a=p.parse_args();report=compare(a.parent,a.candidate)
 report['checker_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 rendered=json.dumps(report,indent=2)+'\n'
 if a.output:
  with a.output.open('x') as f:f.write(rendered)
 print(rendered,end='')
