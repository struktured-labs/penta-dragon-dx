#!/usr/bin/env python3
"""Issue #23 geometry-only regression with stock and known-broken controls.

Uses assisted positioning/resources, but enters through native game logic.
Does not qualify palettes, secret exit, audio, or hardware compatibility.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zlib

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from mgba_singleflight import resolve_binary
from build_secret_chr_restore import PARENT_SHA, STOCK_SHA, build, digest
from normalize_mgba_state_pc import png_chunks


def run(rom, out, expected):
    out.mkdir()
    shutil.copyfile(rom,out/'candidate.gb')
    probe=Path(__file__).with_name('probe_secret_chr_entry.lua')
    shutil.copyfile(probe,out/'probe.lua')
    env=os.environ.copy()
    env.update(SECRET_CHR_OUT=str(out),QT_QPA_PLATFORM='offscreen',SDL_AUDIODRIVER='dummy')
    started=time.monotonic()
    with (out/'emulator.log').open('w') as log:
        status=subprocess.run([str(ROOT/'scripts/mgba-qt-singleflight'),'--fastforward',
          '--script',str(out/'probe.lua'),str(out/'candidate.gb')],env=env,
          stdout=log,stderr=subprocess.STDOUT,timeout=45).returncode
    if status:
        raise RuntimeError(f'emulator exited {status}; do not bypass single-flight')
    with (out/'frames.tsv').open() as handle:
        rows=list(csv.DictReader(handle,delimiter='\t'))
    actual=(out/'secret-chr.bin').read_bytes()
    state=zlib.decompress(dict(png_chunks((out/'final.ss0').read_bytes()))[b'gbAs'])
    if len(state)!=0x11800:raise ValueError('unknown mGBA serialized-state layout')
    mismatches=[i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b]
    result=dict(rom_sha256=digest(rom.read_bytes()),frames=len(rows),
       complete=len(rows)==3600 and len(actual)==2048,
       terminal_scene=int(rows[-1]['scene']),terminal_stage=int(rows[-1]['stage']),
       entry_frame=next((int(r['frame']) for r in rows if r['scene']=='9'),None),
       mismatching_offsets=mismatches,chr_exact=len(actual)==2048 and not mismatches,
       stage1_png_sha256=digest((out/'frame-1200.png').read_bytes()),
       bg0=state[0xD4:0xDC].hex(),
       main_loop_timeline=[int(r['main_loop_hits']) for r in rows],
       wall_seconds=time.monotonic()-started)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path)
    p.add_argument('candidate',type=Path)
    p.add_argument('--stock',type=Path,default=ROOT/'rom/Penta Dragon (J).gb')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--palette-sources',action='store_true',help='also verify the exact palette-source fix layered on the CHR fix')
    a=p.parse_args();out=a.output.resolve()
    if out.exists() or (ROOT/'tmp').resolve() not in out.parents:
        p.error('output must be fresh beneath repository tmp/')
    parent,stock,candidate=a.parent.read_bytes(),a.stock.read_bytes(),a.candidate.read_bytes()
    expected_candidate=build(parent,stock)
    if a.palette_sources:
        from build_secret_palette_sources import build as palette_build
        expected_candidate=palette_build(expected_candidate)
    if digest(parent)!=PARENT_SHA or digest(stock)!=STOCK_SHA or candidate!=expected_candidate:
        p.error('ROM provenance or candidate delta mismatch')
    out.mkdir(parents=True)
    probe=Path(__file__).with_name('probe_secret_chr_entry.lua')
    binding=dict(verifier_sha256=digest(Path(__file__).read_bytes()),
        probe_sha256=digest(probe.read_bytes()),
        builder_sha256=digest(Path(__file__).with_name('build_secret_chr_restore.py').read_bytes()),
        core_binary=str(resolve_binary('qt').resolve()),
        core_binary_sha256=digest(resolve_binary('qt').resolve().read_bytes()),
        guard_sha256=digest((ROOT/'scripts/mgba_singleflight.py').read_bytes()),
        ld_library_path=os.environ.get('LD_LIBRARY_PATH',''))
    binding['state_reader_sha256']=digest(Path(__file__).with_name('normalize_mgba_state_pc.py').read_bytes())
    if a.palette_sources:
        binding['palette_builder_sha256']=digest(Path(__file__).with_name('build_secret_palette_sources.py').read_bytes())
    linked=subprocess.run(['ldd',str(resolve_binary('qt').resolve())],
                          capture_output=True,text=True,check=True).stdout
    binding['linked_libraries']={}
    for line in linked.splitlines():
        words=line.split()
        target=next((Path(word) for word in words if word.startswith('/')),None)
        if target is not None and target.is_file():
            binding['linked_libraries'][str(target.resolve())]=digest(target.read_bytes())
    (out/'bindings.json').write_text(json.dumps(binding,indent=2)+'\n')
    # Sequential by design: one emulator owns the project slot at a time.
    results={name:run(rom,out/name,stock[0x37400:0x37C00])
             for name,rom in [('stock',a.stock),('broken',a.parent),('candidate',a.candidate)]}
    checks={
      'all_runs_complete':all(r['complete'] for r in results.values()),
      'all_native_secret_entries':all(r['entry_frame'] and r['terminal_scene']==9 and r['terminal_stage']==7 for r in results.values()),
      'stock_geometry_exact':results['stock']['chr_exact'],
      'known_broken_rejected':not results['broken']['chr_exact'],
      'candidate_geometry_exact':results['candidate']['chr_exact'],
      'stage1_picture_unchanged':results['broken']['stage1_png_sha256']==results['candidate']['stage1_png_sha256'],
      'entry_timing_unchanged':results['broken']['entry_frame']==results['candidate']['entry_frame'],
      'main_loop_cadence_unchanged':results['broken']['main_loop_timeline']==results['candidate']['main_loop_timeline'],
    }
    if a.palette_sources:
        expected_bg0=candidate[0x36800:0x36808].hex()
        checks['secret_BG0_uses_Dungeon_palette']=results['candidate']['bg0']==expected_bg0
        checks['broken_BG0_rejected']=results['broken']['bg0']!=expected_bg0
    receipt=dict(scope='assisted native secret-entry geometry'+(' and BG0 source' if a.palette_sources else ' only'),release_qualified=False,
      assistance='position DC00..03 at frame1201; health DCBB only thereafter (#37); native cursor DCDD and DCDC untouched; no graphics/palette/cache writes',
      bindings=binding,checks=checks,status='PASS' if all(checks.values()) else 'FAIL',
      results={n:{k:v for k,v in r.items() if k!='main_loop_timeline'} for n,r in results.items()})
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(status=receipt['status'],checks=checks)))
    return 0 if all(checks.values()) else 1


if __name__=='__main__':
    raise SystemExit(main())
