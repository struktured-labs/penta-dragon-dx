#!/usr/bin/env python3
"""#14: narrow secret-doorway visual gate, not collision/speed qualification.

Capture recipe: cold boot; position assist1240/1344 at frame1201; Down through
1212, no keys afterwards; capture1216. Resource assistance is explicit. The
stock reference hides all four Sara quadrants in a reviewed black region.
No historical state is loaded. Run captures sequentially under single-flight.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zlib
from PIL import Image
from verify_pickup_class_palettes import serialized_state

STOCK_SHA = '2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30'


def capture(folder):
    rom_path = folder / 'candidate.gb'
    state_path = folder / 'frame-1216.ss0'
    frame_path = folder / 'frame-1216.png'
    rom = rom_path.read_bytes()
    state = serialized_state(state_path)
    if int.from_bytes(state[4:8], 'little') != zlib.crc32(rom) & 0xffffffff:
        raise ValueError('savestate/ROM identity mismatch')
    world = tuple(int.from_bytes(state[i:i+2], 'little') for i in (0x6000, 0x6002))
    if world != (1240, 1356) or state[0x5c80] != 2 or state[0x3ba] != 0:
        raise ValueError('not the reviewed Stage-1 doorway position/scene')
    positions = [(state[0x260+i*4], state[0x261+i*4]) for i in range(4)]
    if positions != [(80,80), (80,88), (88,80), (88,88)]:
        raise ValueError('Sara OAM footprint differs from reviewed doorway')
    image = Image.open(frame_path).convert('RGB')
    if image.size != (160,144):
        raise ValueError('capture must retain native dimensions')
    pixels = [image.getpixel((x,y)) for y in range(64,80) for x in range(72,88)]
    if sum(p != (0,0,0) for p in image.getdata()) <= 256:
        raise ValueError('blank background cannot qualify doorway occlusion')
    return dict(world=world, camera=state[0x342:0x344].hex(),
                priority=[bool(state[0x263+i*4] & 128) for i in range(4)],
                nonblack=sum(p != (0,0,0) for p in pixels),
                bindings={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in (rom_path,state_path,frame_path,folder/'probe.lua')} )


def verify(stock, candidate):
    reference, trial = capture(stock), capture(candidate)
    if reference['bindings']['candidate.gb'] != STOCK_SHA:
        raise ValueError('reference is not the original cartridge')
    if reference['bindings']['frame-1216.png'] != '540e8fd604baf33b5e094e72ee0cdbe7244dcc13f2eceecd95cfdf5fcb6c08a3':
        raise ValueError('stock screenshot differs from reviewed reference')
    if reference['nonblack'] or not all(reference['priority']):
        raise ValueError('stock does not establish the reviewed opaque overhang')
    if trial['camera'] != reference['camera']:
        raise ValueError('stock and candidate cameras differ')
    return dict(issue=14, scope='single reviewed opaque doorway; collision, floor bleed, speed and audio unqualified',
                stock=reference, candidate=trial, covered_pixels=256,
                passed=trial['nonblack'] == 0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stock', type=Path)
    parser.add_argument('candidate', type=Path)
    args = parser.parse_args()
    result = verify(args.stock,args.candidate)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)
