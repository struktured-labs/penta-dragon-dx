"""#59 bounded scrolling capture. Diagnostic, not a visual pass/fail oracle."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
HOST=Path('/home/struktured/projects/penta-dragon-dx').resolve()
GUARD=HOST/'scripts/mgba-qt-singleflight'
PROBE=Path(__file__).with_name('probe_stage_integrity.lua')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--target',type=int,default=1)
    p.add_argument('--frames',type=int,default=720)
    a=p.parse_args()
    out=a.output.resolve()
    if out.exists() or (ROOT/'tmp').resolve() not in out.parents or a.frames<=0:
        p.error('fresh worktree tmp output and positive frames required')
    out.mkdir(parents=True)
    rom=out/'candidate.gb';shutil.copyfile(a.rom,rom)
    probe=out/'probe.lua';shutil.copyfile(PROBE,probe)
    prefix=out/'stage'
    env=os.environ.copy()
    env.update(QT_QPA_PLATFORM='offscreen',SDL_AUDIODRIVER='dummy',
               STAGE_TARGET=str(a.target),STAGE_OUT=str(prefix),STAGE_PATROL_FRAMES=str(a.frames))
    receipt=dict(rom_sha256=digest(rom),probe_sha256=digest(probe),guard_sha256=digest(GUARD),
                 runner_sha256=digest(Path(__file__)),target=a.target,frames=a.frames,
                 assistance='native level selector and physical bank1 health refill',
                 diagnostic_only=True,complete=False)
    started=time.monotonic()
    with (out/'emulator.log').open('w') as log:
        child=subprocess.Popen([str(GUARD),'--fastforward','--script',str(probe),str(rom)],
                               cwd=HOST,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            while child.poll() is None:
                if Path(str(prefix)+'.done').exists():
                    receipt['complete']=True
                    break
                if time.monotonic()-started>45:
                    receipt['timeout']=True
                    break
                time.sleep(.02)
        finally:
            if child.poll() is None:
                child.terminate()
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired: child.kill();child.wait()
    receipt.update(returncode=child.returncode,wall_seconds=time.monotonic()-started,
                   artifacts={f.name:digest(f) for f in out.iterdir() if f.is_file()})
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    subprocess.run([str(HOST/'scripts/check_emulator_processes.sh')],check=True)
    print(json.dumps(dict(complete=receipt['complete'],output=str(out))))
    return 0 if receipt['complete'] else 1


if __name__=='__main__':
    raise SystemExit(main())
