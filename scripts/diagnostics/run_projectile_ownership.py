"""#57 diagnostic weapon matrix, exact-ROM state, no palette/cache assistance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zlib

ROOT=Path(__file__).resolve().parents[2]
HOST=Path('/home/struktured/projects/penta-dragon-dx').resolve()
sys.path.insert(0,str(HOST/'scripts/diagnostics'))
from normalize_mgba_state_pc import png_chunks
from runtime_tools import emulator_runtime_snapshot, reject_known_broken_cgb_runtime

def identity(path):
 return dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('rom','state','output'):p.add_argument('--'+key,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve()
 if out.exists() or (ROOT/'tmp').resolve() not in out.parents:p.error('fresh worktree tmp output required')
 rom=a.rom.read_bytes();raw=zlib.decompress(dict(png_chunks(a.state.read_bytes()))[b'gbAs'])
 if len(raw)!=71680 or int.from_bytes(raw[4:8],'little')!=zlib.crc32(rom)&0xffffffff or raw[16:32]!=rom[0x134:0x144]:
  p.error('exact-ROM state required; retargeting forbidden')
 os.environ['LD_LIBRARY_PATH']=str(HOST/'tmp/mgba-cgb-latches-r454/build')
 runtime=emulator_runtime_snapshot();reject_known_broken_cgb_runtime(runtime)
 inputs={'rom':a.rom,'state':a.state,'probe':Path(__file__).with_name('probe_projectile_ownership.lua'),
         'runner':Path(__file__),'guard':HOST/'scripts/mgba-qt-singleflight'}
 report=dict(diagnostic_only=True,complete=False,runtime=runtime,
  inputs={k:identity(v) for k,v in inputs.items()},runs=[],
  assistance='FFC0 requested weapon each frame; no other memory writes. Not a native pickup reproduction.')
 out.mkdir(parents=True)
 try:
  for power in range(3):
   folder=out/f'power{power}';folder.mkdir()
   for key,name in [('rom','candidate.gb'),('state','identity.ss0'),('probe','probe.lua')]:
    shutil.copyfile(inputs[key],folder/name)
   env=os.environ.copy();env.update(PROJECTILE_OUT=str(folder),PROJECTILE_POWER=str(power),PROJECTILE_STATE=str(folder/'identity.ss0'),
    QT_QPA_PLATFORM='offscreen',SDL_AUDIODRIVER='dummy')
   start=time.monotonic()
   with (folder/'emulator.log').open('w') as log:
    result=subprocess.run([str(inputs['guard']),'--fastforward','-t',str(folder/'identity.ss0'),
     '--script',str(folder/'probe.lua'),str(folder/'candidate.gb')],
     cwd=HOST,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=30)
   record=dict(power=power,status=result.returncode,wall_seconds=time.monotonic()-start,
    artifacts={f.name:identity(f) for f in folder.iterdir() if f.is_file()})
   report['runs'].append(record)
   if result.returncode or not (folder/'frame-0240.ss0').exists():raise RuntimeError('incomplete projectile run')
  if emulator_runtime_snapshot()!=runtime:raise RuntimeError('runtime identity changed')
  if any(identity(v)!=report['inputs'][k] for k,v in inputs.items()):raise RuntimeError('input identity changed')
  report['complete']=True
 except Exception as error:
  report['error']=str(error)
  subprocess.run([str(HOST/'scripts/check_emulator_processes.sh')],check=False)
  raise
 finally:
  (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(dict(complete=report['complete'],output=str(out))))

if __name__=='__main__':main()
