"""#6 bounded raster check from runtime sprite art, not static ROM tiles.

Unsupported priority/8x16/OPRI cases remain explicit. Frame-end state cannot
prove scanline ownership; differences are investigation leads, not tear causes.
"""
import argparse
from collections import Counter
import hashlib
import json
import mmap
from pathlib import Path

STATE_BYTES = 71680
VIDEO_BYTES = 160 * 144 * 4


def expected_pixels(state):
    if len(state) != STATE_BYTES:
        raise ValueError('exact native state required')
    if state[0x3b7] != 2 or state[0x3c1] != 1:
        return 'outside_active_stage1', {}
    if state[0x340] & 0x86 != 0x82:
        return 'unsupported_lcdc', {}
    if state[0x36c] & 1:
        return 'unsupported_dmg_object_priority', {}
    pieces = [state[0x260+i*4:0x264+i*4] for i in range(4)]
    if any(a & 0x80 for y,x,t,a in pieces):
        return 'priority_requires_background_composition', {}
    pixels = {}
    for y,x,tile,attr in pieces:
        for dy in range(8):
            sy = 7-dy if attr & 64 else dy
            at = 0x400 + (0x2000 if attr & 8 else 0) + tile*16 + sy*2
            lo,hi = state[at:at+2]
            for dx in range(8):
                bit = dx if attr & 32 else 7-dx
                index = ((lo >> bit) & 1) | (((hi >> bit) & 1) << 1)
                px,py = x-8+dx,y-16+dy
                if not index or not (0 <= px < 160 and 0 <= py < 144):
                    continue
                at = 0x114 + (attr & 7)*8 + index*2
                word = int.from_bytes(state[at:at+2], 'little')
                # Native mGBA capture's five-bit expansion; no normalization.
                rgb = bytes(((word >> shift) & 31)*33//4 for shift in (0,5,10))
                pixels.setdefault((px,py),rgb)  # lowest OAM index owns overlap
    return ('checked' if pixels else 'no_opaque_sara_pixels'), pixels


def compare_frame(state, video):
    if len(video) != VIDEO_BYTES:
        raise ValueError('exact native video frame required')
    category,pixels = expected_pixels(state)
    missing = []
    for (x,y),rgb in pixels.items():
        at = (y*160+x)*4
        if video[at:at+3] != rgb:
            missing.append(dict(x=x,y=y,expected=list(rgb),actual=list(video[at:at+3])))
    return category,len(pixels),missing


def inspect(directory, frames):
    categories,scenes,failures = Counter(),Counter(),[]
    pixels = 0
    with (directory/'native.states').open('rb') as sf, (directory/'native.video').open('rb') as vf:
        identities = {}
        for name,stream in (('native.states',sf),('native.video',vf)):
            identities[name] = hashlib.file_digest(stream,'sha256').hexdigest()
            stream.seek(0)
        with mmap.mmap(sf.fileno(),0,access=mmap.ACCESS_READ) as states, mmap.mmap(vf.fileno(),0,access=mmap.ACCESS_READ) as video:
            if len(states)!=frames*STATE_BYTES or len(video)!=frames*VIDEO_BYTES:
                raise ValueError('capture frame counts differ')
            for i in range(frames):
                state = states[i*STATE_BYTES:(i+1)*STATE_BYTES]
                category,count,missing = compare_frame(state,video[i*VIDEO_BYTES:(i+1)*VIDEO_BYTES])
                categories[category]+=1
                pixels+=count
                if category=='checked': scenes[f'{state[0x5c80]:02X}']+=1
                if missing: failures.append(dict(frame=i+1,pixels=missing))
    return dict(status='DIFFERENCES' if failures else 'NO_DIFFERENCES_IN_CHECKED_PIXELS',
                scope='Active canonical Stage1 Sara opaque pixels only; unsupported frames retained; not release qualification',
                frames=frames,categories=dict(categories),checked_raw_scenes=dict(scenes),
                opaque_pixels=pixels,failures=failures,identities=identities,
                checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    parser.add_argument('--frames',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    output=args.output.resolve()
    if output.exists() or (root/'tmp').resolve() not in output.parents:
        parser.error('fresh repository tmp output required')
    result=inspect(args.capture,args.frames)
    output.mkdir(parents=True)
    (output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='failures'},indent=2))
    print('frames with differences:',len(result['failures']))
