#!/usr/bin/env python3
"""Issue #6: ordinary-input Sara Witch pose-publication regression.

Captures every frame, rejects mixed walking-pose generations, and retains all
startup, transition, non-walking and absent observations as explicit categories.
This is a focused emulator gate, not hardware or complete-game qualification.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from PIL import Image

import verify_frame_flicker as capture

ROOT = Path(__file__).resolve().parents[2]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def runtime_identity():
    # Match the single-flight wrapper's deterministic default; never permit
    # a hidden executable override in this verifier.
    os.environ.pop('PENTA_MGBA_QT_BIN', None)
    binary = next(p.resolve(strict=True) for p in (
        Path('/home/struktured/bin/mgba-qt'), Path('/usr/bin/mgba-qt'),
        Path('/usr/local/bin/mgba-qt')) if p.is_file())
    linked = subprocess.check_output(['ldd',str(binary)], text=True)
    core = next(Path(line.split('=>',1)[1].split()[0]).resolve(strict=True)
                for line in linked.splitlines() if 'libmgba.so' in line and '=>' in line)
    return {name:dict(path=str(path),sha256=sha(path)) for name,path in (
        ('emulator',binary),('core',core),('guard',ROOT/'scripts/mgba_singleflight.py'))}

def check_rows(rows, expected_frames):
    failures, poses, categories = [], Counter(), Counter()
    if len(rows) != expected_frames:
        failures.append(dict(reason='incomplete capture', observed=len(rows), expected=expected_frames))
    for index, row in enumerate(rows, 1):
        if int(row['sample']) != index:
            failures.append(dict(sample=index, reason='nonconsecutive sample'))
        entries = [entry for entry in capture.parse_oam(row['visible_oam']) if entry['slot'] < 4]
        if not entries:
            categories['no_visible_sara'] += 1
            continue
        tiles = [entry['tile'] for entry in entries]
        if int(row['ffbe'],16) != 0 or any(t < 0x20 or t >= 0x30 for t in tiles):
            categories['outside_witch_walking_contract'] += 1
            continue
        categories['witch_walking'] += 1
        pose = tuple(tiles)
        poses[','.join(f'{tile:02X}' for tile in pose)] += 1
        if len(entries) != 4 or len({tile//4 for tile in tiles}) != 1 or len(set(tiles)) != 4:
            failures.append(dict(sample=index, frame=int(row['frame']), tiles=tiles,
                                 reason='incomplete or mixed walking pose'))
        if len(entries) == 4:
            # Tile identity alone misses a position update interrupted between
            # quadrants. Slot order is top-left/right, bottom-left/right even
            # when native art/attributes mirror the walking pose.
            origins = sorted({(entry['y'] - (entry['slot']//2)*8,
                               entry['x'] - (entry['slot']%2)*8)
                              for entry in entries})
            if len(origins) != 1:
                failures.append(dict(sample=index, frame=int(row['frame']),
                                     reason='split walking geometry', origins_yx=origins))
    if categories['witch_walking'] < min(500, expected_frames):
        failures.append(dict(reason='insufficient walking coverage'))
    if len(poses) < 4:
        failures.append(dict(reason='insufficient pose changes'))
    return dict(status='fail' if failures else 'pass', frames=len(rows), categories=dict(categories),
                poses=dict(poses), failures=failures)

def expected_pixels(row, rom):
    """Decode opaque Witch walking pixels from candidate art and sampled OAM.

    This is a sprite-content check, not whole-frame image equality. Raw full
    images remain unmodified; extra/background pixels are not excused as a
    claimed exact comparison. Unsupported forms are reported separately.
    """
    if int(row['ffbe'],16) != 0 or int(row['lcdc'],16) & 4:
        return None
    entries = [e for e in capture.parse_oam(row['visible_oam']) if e['slot'] < 4]
    if any(not 0x20 <= e['tile'] < 0x30 or e['attr'] & 8 for e in entries):
        return None
    cram, pixels = bytes.fromhex(row['obj_cram']), {}
    for entry in entries:
        attr = entry['attr']
        for dy in range(8):
            sy = 7-dy if attr & 64 else dy
            offset = 0x20000+entry['tile']*16+sy*2
            lo,hi = rom[offset:offset+2]
            for dx in range(8):
                bit = dx if attr & 32 else 7-dx
                index = ((lo>>bit)&1) | (((hi>>bit)&1)<<1)
                x,y = entry['x']-8+dx,entry['y']-16+dy
                if index and 0 <= x < 160 and 0 <= y < 144:
                    at = (attr&7)*8+index*2
                    word = int.from_bytes(cram[at:at+2],'little')
                    values = [(word>>shift)&31 for shift in (0,5,10)]
                    pixels.setdefault((x,y),tuple((v<<3)|(v>>2) for v in values))
    return pixels

def missing_pixels(image, expected):
    return [dict(x=x,y=y,expected=list(color),actual=list(image.getpixel((x,y))))
            for (x,y),color in expected.items() if image.getpixel((x,y)) != color]

def inspect(directory, frames, rom):
    with (directory/'gameplay.tsv').open() as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    result = check_rows(rows, frames)
    images, opaque_pixels, unsupported = [], 0, []
    for i,row in enumerate(rows,1):
        path = directory/f'gameplay.frame{i:04d}.png'
        images.append(dict(sample=i, sha256=sha(path)))
        with Image.open(path) as source:
            if source.size != (160,144):
                raise ValueError('native unscaled frame required')
            expected = expected_pixels(row,rom)
            if expected is None:
                unsupported.append(i)
            else:
                opaque_pixels += len(expected)
                missing = missing_pixels(source.convert('RGB'),expected)
                if missing:
                    result['failures'].append(dict(sample=i,reason='opaque Sara pixels differ',pixels=missing))
    result['images'] = images
    result['opaque_pixels_checked'] = opaque_pixels
    result['raster_unsupported_samples'] = unsupported
    result['status'] = 'fail' if result['failures'] else 'pass'
    result['trace_sha256'] = sha(directory/'gameplay.tsv')
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=2400)
    parser.add_argument('--period', type=int, default=45)
    parser.add_argument('--fire', action='store_true')
    parser.add_argument('--timeout', type=float, default=90)
    args = parser.parse_args()
    out, rom = args.output.resolve(), args.rom.resolve(strict=True)
    allowed = [(ROOT/'tmp').resolve(), Path('/mnt/data/tmp').resolve()]
    if out.exists() or not any(base in out.parents for base in allowed):
        parser.error('output must be fresh beneath project tmp/ or /mnt/data/tmp/')
    if args.frames < 720 or args.period < 1:
        parser.error('at least 720 frames and a positive turn period required')
    identity = sha(rom)
    runtime = runtime_identity()
    os.environ['FLICKER_ROUTE'] = 'sara-turns-fire' if args.fire else 'sara-turns'
    os.environ['FLICKER_TURN_PERIOD'] = str(args.period)
    start = time.monotonic()
    capture.run_probe(str(ROOT/'scripts/mgba-qt-singleflight'), rom, out, 'gameplay', args.frames, args.timeout)
    result = inspect(out, args.frames, rom.read_bytes())
    assert sha(rom) == identity, 'ROM changed during replay'
    result.update(schema='penta-sara-pose-v1', issue=6, scope='walking-pose emulator regression only',
        rom=str(rom), rom_sha256=identity, probe_sha256=sha(capture.PROBE),
        verifier_sha256=sha(Path(__file__)), capture_driver_sha256=sha(Path(capture.__file__)),
        launcher_sha256=sha(ROOT/'scripts/mgba-qt-singleflight'),
        runtime_library_path=os.environ.get('LD_LIBRARY_PATH',''),
        runtime=runtime,
        route=os.environ['FLICKER_ROUTE'], turn_period=args.period,
        elapsed_seconds=time.monotonic()-start)
    assert runtime_identity() == runtime, 'runtime changed during replay'
    (out/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'images'},indent=2))
    return 0 if result['status'] == 'pass' else 1

if __name__ == '__main__':
    raise SystemExit(main())
