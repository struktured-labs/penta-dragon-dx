import json, os, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
M = ROOT / 'tmp/rl-suite-20261002-01/matrix'
NEW = ROOT / os.environ.get('GM','tmp/phase5/gm')
ROM = os.environ.get('ROM')
if ROM:
    (NEW/'tested-rom').mkdir(parents=True, exist_ok=True)
    import shutil; shutil.copy(ROM, NEW/'tested-rom/penta_dragon_dx_FIXED.gb')
man = json.loads((M / 'manifest.json').read_text())
gates = {g['name']: g for g in man['results']}
env = os.environ.copy()
env.update(LD_LIBRARY_PATH=str(ROOT/'tmp/mgba-cgb-latches-r454/build'), TMPDIR=str(ROOT/'tmp'), PYTHONDONTWRITEBYTECODE='1')
(NEW/'logs').mkdir(parents=True, exist_ok=True); (NEW/'artifacts').mkdir(exist_ok=True); (NEW/'runtime-tmp').mkdir(exist_ok=True)
rc_all = 0
for name in sys.argv[1:]:
    g = gates[name]
    cmd = [c.replace(str(M), str(NEW)) for c in g['command']]
    t = time.time()
    with open(NEW/'logs'/f'{name}.log', 'w') as log:
        try:
            rc = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=g.get('timeout_seconds', 600)*1.5).returncode
        except subprocess.TimeoutExpired:
            rc = 'timeout'
    print(name, 'rc', rc, f'{time.time()-t:.0f}s', flush=True)
    if rc != 0:
        rc_all = 1
        print('   ', ' | '.join((NEW/'logs'/f'{name}.log').read_text().strip().splitlines()[-4:])[:600], flush=True)
sys.exit(rc_all)
