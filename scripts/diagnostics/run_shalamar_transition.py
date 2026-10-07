"""#60 diagnostic native boss defeat/score transition from an exact-ROM state."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zlib

ROOT=Path(__file__).resolve().parents[2]
HOST=Path('/home/struktured/projects/penta-dragon-dx').resolve()
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from normalize_mgba_state_pc import png_chunks
from runtime_tools import emulator_runtime_snapshot, reject_known_broken_cgb_runtime
from prepare_native_replay import prepare
from finalize_native_av_capture import finalize

def identity(path):
 return dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ('rom','state','output'): p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--defeat-frame',type=int,default=180)
 p.add_argument('--frames',type=int,default=2400)
 p.add_argument('--native-event-entry',action='store_true',help='inject only native event29 at the live dispatcher; preserve gameplay palette/transition state')
 p.add_argument('--live-boss-entry',action='store_true',help='call native1A2B once from a live016C loop; retain existing scene/cache/palette state')
 p.add_argument('--keys',type=int,default=1)
 p.add_argument('--close-menu-frame',type=int,help='optional six-frame Select pulse before defeat; ordinary input for native low-health auto-menu')
 a=p.parse_args(); out=a.output.resolve()
 if a.defeat_frame<1 or a.frames<a.defeat_frame+2220: p.error('require defeat stimulus and complete 2220-frame transition tail')
 if not 0<=a.keys<=255:p.error('keys must be an 8-bit controller mask')
 if a.close_menu_frame is not None and not 1<=a.close_menu_frame<a.defeat_frame-6:
  p.error('menu-close pulse must finish before defeat stimulus')
 if a.native_event_entry and a.live_boss_entry:p.error('choose one entry diagnostic')
 if out.exists() or (ROOT/'tmp').resolve() not in out.parents: p.error('fresh worktree tmp output required')
 rom=a.rom.read_bytes(); raw=zlib.decompress(dict(png_chunks(a.state.read_bytes()))[b'gbAs'])
 if len(raw)!=71680 or int.from_bytes(raw[4:8],'little')!=zlib.crc32(rom)&0xffffffff or raw[16:32]!=rom[0x134:0x144]:
  p.error('state does not belong to exact ROM; no retargeting')
 os.environ.setdefault('LD_LIBRARY_PATH',str(HOST/'tmp/mgba-cgb-latches-r454/build'))
 runtime=emulator_runtime_snapshot(); reject_known_broken_cgb_runtime(runtime)
 out.mkdir(parents=True)
 paths={'rom':a.rom,'state':a.state,'probe':Path(__file__).with_name('probe_shalamar_transition.lua'),
        'replay':ROOT/'scripts/diagnostics/probe_secret_entry.lua','runner':Path(__file__)}
 report=dict(diagnostic_only=True,runtime=runtime,inputs={k:identity(v) for k,v in paths.items()},
             assistance=f'physical DDA3/4 boss health zero once at frame{a.defeat_frame}; no rendering writes',complete=False)
 for key,name in [('rom','candidate.gb'),('state','identity.ss0'),('probe','probe.lua'),('replay','replay.lua')]:
  shutil.copyfile(paths[key],out/name)
 env=os.environ.copy(); env.update(ENTRY_OUT=str(out),ENTRY_COLD='0',ENTRY_FRAMES=str(a.frames),
   TRANSITION_DEFEAT_FRAME=str(a.defeat_frame),
   ENTRY_CAPTURE_EVERY='30',ENTRY_KEYS=str(a.keys),ENTRY_PULSE_A='1',ENTRY_AUDIO_ENABLED='1',
   SECRET_REPLAY_PROBE=str(out/'replay.lua'),QT_QPA_PLATFORM='offscreen',SDL_AUDIODRIVER='dummy')
 env.pop('TRANSITION_CLOSE_MENU_FRAME',None)
 if a.close_menu_frame is not None:
  env['TRANSITION_CLOSE_MENU_FRAME']=str(a.close_menu_frame)
  report['assistance']+=f'; ordinary six-frame Select pulse at{a.close_menu_frame}; no menu memory writes'
 if a.native_event_entry:
  if rom[0x13F4:0x13F9]!=bytes.fromhex('21761BE0D3') or rom[0x1BC8:0x1BCA]!=bytes.fromhex('2B1A'):
   raise ValueError('native event dispatch preimage changed')
  env['TRANSITION_NATIVE_EVENT']='1'
  report['assistance']+='; once at live13F4 after120 frames replace selected event A with29; no PC/SP/scene/palette/cache resets'
 if a.live_boss_entry:
  if rom[0x1A2B:0x1A2F]!=bytes.fromhex('F0BFA7C0'):raise ValueError('boss entry preimage changed')
  env['TRANSITION_LIVE_ENTRY']='1'
  report['assistance']+='; once at mainloop016C after120 frames push016C on current stack and call native1A2B; no scene/cache/palette resets; synthetic boss call, not ordinary-input entry'
 # #67: restore and install every observer before the first CPU instruction.
 # Preparation builds the adapter for the exact resolved core; no cached tap.
 report['native_runtime']=prepare(out,env)
 env['ENTRY_NATIVE_DEFER_START']='1'
 report['inputs_environment']={k:v for k,v in env.items() if k.startswith(('ENTRY_','TRANSITION_'))}
 try:
  with (out/'emulator.log').open('w') as log:
   result=subprocess.run([str(ROOT/'scripts/mgba-qt-singleflight'),'--fastforward',
    '-C','mute=0','-C','volume=256','-C','fastForwardMute=-1','-C','fastForwardVolume=256',
    '-t',str(out/'identity.ss0'),'--script',str(out/'probe.lua'),str(out/'candidate.gb')],
    cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=50)
  report['status']=result.returncode
  if result.returncode==0:
   report['native_capture']=finalize(Path(report['native_runtime']['capture_directory']))
   capture=report['native_capture']
   if capture['restored_replay_epoch']['status']!='PASS' or capture['metadata']['frames']!=a.frames:
    raise RuntimeError('invalid native restore epoch or incomplete native capture')
  report['complete']=result.returncode==0 and (out/f'frame-{a.frames:04d}.png').exists()
  rows=list(csv.DictReader((out/'transition.tsv').open(),delimiter='\t'))
  report['complete']=report['complete'] and [int(r['frame']) for r in rows]==list(range(1,a.frames+1))
  report['complete']=report['complete'] and any(r['score_poll']=='1' for r in rows) and any(r['stage']=='01' for r in rows)
  if a.native_event_entry:report['complete']=report['complete'] and '13F4_EVENT29' in (out/'score-edges.tsv').read_text()
  if a.live_boss_entry:report['complete']=report['complete'] and '016C_CALL1A2B' in (out/'score-edges.tsv').read_text()
  if not report['complete']: raise RuntimeError('incomplete replay; inspect emulator.log')
 except Exception as error:
  report['error']=str(error)
  subprocess.run([str(ROOT/'scripts/check_emulator_processes.sh')],check=False)
  raise
 finally:
  report['artifacts']={f.name:identity(f) for f in out.iterdir() if f.is_file()}
  (out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'complete':report['complete'],'output':str(out)}))

if __name__=='__main__': main()
