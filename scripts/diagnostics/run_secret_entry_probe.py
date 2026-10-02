"""Single-flight secret replay; exact-ROM states only, diagnostic not qualification."""
import os,sys,subprocess,json,hashlib
import shutil
import zlib
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'scripts/diagnostics'))
from normalize_mgba_state_pc import png_chunks
if len(sys.argv) != 3:
 raise SystemExit('usage: run_secret_entry_probe.py cold|EXACT_STATE OUTPUT_NAME (ENTRY_ROM required)')
source=(root/sys.argv[1]).resolve()
rom=(root/os.environ['ENTRY_ROM']).resolve()
out=(root/'tmp'/sys.argv[2]).resolve()
if out.parent != (root/'tmp').resolve():
 raise ValueError('output must be a fresh immediate child of repository tmp')
cold=sys.argv[1]=='cold'
if not cold:
 raw=zlib.decompress(dict(png_chunks(source.read_bytes()))[b'gbAs'])
 if len(raw) != 71680:
  raise ValueError('unsupported serialized state size')
 if int.from_bytes(raw[4:8],'little') != zlib.crc32(rom.read_bytes())&0xffffffff or raw[16:32] != rom.read_bytes()[0x134:0x144]:
  raise ValueError('state/ROM identity mismatch; retargeting is prohibited')
out.mkdir(exist_ok=False)
if not cold: shutil.copyfile(source,out/'identity.ss0')
shutil.copyfile(rom,out/'candidate.gb')
shutil.copyfile(Path(__file__).with_name('probe_secret_entry.lua'),out/'probe.lua')
env=os.environ.copy()
env.update(ENTRY_OUT=str(out),QT_QPA_PLATFORM='offscreen',SDL_AUDIODRIVER='dummy',LD_LIBRARY_PATH=str(root/'tmp/mgba-cgb-latches-r454/build'))
# #43: cold state generation must use the same explicit audio configuration as
# native restored captures. Implicit Qt mute/fast-forward settings can change
# serialized filter capacitors despite identical gameplay telemetry.
env.setdefault('ENTRY_AUDIO_ENABLED', '1')
env['ENTRY_COLD']='1' if cold else '0'
if int(env.get('ENTRY_FRAMES', '1200')) <= 0:
 raise ValueError('ENTRY_FRAMES must be positive')
if env.get('ENTRY_NATIVE_START_GATE'):
 marker=Path(env['ENTRY_NATIVE_START_GATE']).resolve()
 if marker.parent != out:
  raise ValueError('startup marker must be inside this fresh output directory')
capture=None
if env.get('ENTRY_NATIVE_TAP'):
 tap=Path(env['ENTRY_NATIVE_TAP']).resolve()
 bulk=Path('/mnt/data/tmp')
 if not bulk.is_dir() or not os.access(bulk, os.W_OK): bulk=root/'tmp'
 capture=bulk/('penta-'+out.name+'-av')
 capture.mkdir(exist_ok=False)
 env.update(LD_PRELOAD=str(tap),PENTA_NATIVE_AV_PREFIX=str(capture/'native'),ENTRY_AUDIO_ENABLED='1')
# #43 adoption: a restored native capture always uses the pre-first-CPU
# startup barrier, so pre-restore PCM/video can never enter the epoch. The
# ungated path survives only as an explicitly labeled negative control.
native_start_gate=None
if capture and not cold:
 if env.get('ENTRY_NATIVE_START_GATE'):
  native_start_gate='barrier'
 elif env.get('ENTRY_NATIVE_UNGATED_NEGATIVE_CONTROL')=='1':
  native_start_gate='ungated-negative-control'
 else:
  env['ENTRY_NATIVE_START_GATE']=str(out/'native-start-gate')
  native_start_gate='barrier'
audio_options=[]
if env.get('ENTRY_AUDIO_ENABLED')=='1':
 # This Qt build's overrideMute(false) treats any nonnegative fastForwardMute
 # as muted. -1 disables that override, retaining the explicit normal volume.
 for option in ('mute=0','volume=256','fastForwardMute=-1','fastForwardVolume=256'):
  audio_options += ['-C',option]
try:
 with (out/'emulator.log').open('w') as log:
  result=subprocess.run([str(root/'scripts/mgba-qt-singleflight'),'--fastforward']+audio_options+([] if cold else ['-t',str(out/'identity.ss0')])+['--script',str(out/'probe.lua'),str(out/'candidate.gb')],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=40)
except subprocess.TimeoutExpired:
 (out/'receipt.json').write_text(json.dumps({'diagnostic_only':True,'status':'TIMEOUT','complete':False}))
 subprocess.run([str(root/'scripts/check_emulator_processes.sh')],check=False)
 raise
receipt={'diagnostic_only':True,'status':result.returncode,'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'source_state_sha256':None if cold else hashlib.sha256(source.read_bytes()).hexdigest(),'state_change':'cold boot, no save present' if cold else 'none; exact ROM CRC/header checked','observer_memory_writes':False,'keys':env.get('ENTRY_KEYS','0')}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2))
if env.get('ENTRY_ASSIST_HEALTH')=='1':
 receipt['observer_memory_writes']=True
 receipt['assistance']='physical WRAM DCBB=FF health only when scene02; no cursor/scene/palette/cache/position writes (#37 correction)'
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2))
receipt['probe_sha256']=hashlib.sha256((out/'probe.lua').read_bytes()).hexdigest()
receipt['runner_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
receipt['guard_sha256']=hashlib.sha256((root/'scripts/mgba-qt-singleflight').read_bytes()).hexdigest()
receipt['audio_options']=audio_options
receipt['native_start_gate']=native_start_gate
if capture and result.returncode == 0:
 from finalize_native_av_capture import finalize
 receipt['native_capture']=finalize(capture)
 receipt['native_capture_directory']=str(capture)
 receipt['native_tap_sha256']=hashlib.sha256(tap.read_bytes()).hexdigest()
if env.get('ENTRY_ONCE_HP'):
 receipt['observer_memory_writes']=True
 receipt['one_time_health_assistance']='physical bank1 DCBB='+env['ENTRY_ONCE_HP']+' before first frame callback; no scene, palette, cursor, cache or rendering writes'
if env.get('ENTRY_DENSE_INVENTORY')=='1':
 receipt['observer_memory_writes']=True
 receipt['inventory_assistance']='At frame1180 set 30 native inventory slots DCBD..DCDA to explicit dense groups and DCDB=0; no menu tile/attribute writes. Diagnostic inventory, not reconstructed recording.'
receipt['diagnostic_environment']={k:v for k,v in env.items() if k.startswith('ENTRY_')}
if env.get('ENTRY_CONTINUE_TEST')=='1':
 receipt['observer_memory_writes']=True
 receipt['continue_assistance']='relative to cold frame1200 or restored frame0: +1 FFE6=1 credit and physical WRAM DCBB=0 death stimulus; pulsed selected key +180..599; no scene/palette/graphics writes'
if env.get('ENTRY_WARP_BEFORE')=='1' or env.get('ENTRY_ASSIST_RESOURCE')=='1' or env.get('ENTRY_COLD_WARP')=='1' or env.get('ENTRY_CONTINUOUS_SECRET')=='1':
 receipt['observer_memory_writes']=True
 receipt['additional_assistance']='Position assistance sets DC00..03 once: ENTRY_WARP_BEFORE at frame1; ENTRY_COLD_WARP or ENTRY_CONTINUOUS_SECRET at ENTRY_WARP_FRAME (default1201); ENTRY_WARP_X/Y default1240/1344. ENTRY_ASSIST_RESOURCE now refills DCBB health only each frame; leaves DCDD menu cursor and DCDC unchanged (#37). No palette/graphics/cache writes.'
if env.get('ENTRY_MINIBOSS_ASSIST')=='1':
 receipt['observer_memory_writes']=True
 receipt['miniboss_assistance']='DCB8='+env.get('ENTRY_MINIBOSS_SECTION','0')+' once at frame560; from frame560 while FFBF=0: DCBA=1, FFD6=1E, entity activity slots DC85/DC8D/DC95/DC9D/DCA5=0. Right+pulsed A from frame492 until FFBF nonzero. Native descriptor unchanged; assisted spawn, not ordinary player route.'
(out/'receipt.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
raise SystemExit(result.returncode)
