"""#45: inspect every checkpoint in a short secret-return initialization replay.

This is a rendered/map checkpoint check, not native PCM, cycle parity, hardware,
or full-frame-stream qualification. The input must capture every replay frame.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zlib

from PIL import Image
from normalize_mgba_state_pc import png_chunks


def assess(frames):
    if [n for n, _, _ in frames] != list(range(1, len(frames) + 1)):
        raise ValueError('missing or unordered checkpoint')
    start = next((i for i, (_, raw, _) in enumerate(frames)
                  if raw[0x5C80] == 2 and raw[0x3BA] == 0), None)
    if start is None or start == 0 or frames[start-1][1][0x5C80] != 24:
        raise ValueError('missing stage-card to dungeon boundary')
    window = frames[start:start+70]
    if len(window) != 70:
        raise ValueError('truncated initialization window')
    observations = []
    for n, raw, white in window:
        if raw[0x5C80] != 2 or raw[0x3BA] != 0:
            raise ValueError('unexpected scene in initialization window')
        page = 0x2000 if raw[0x340] & 8 else 0x1C00
        bad = sum(raw[page+y*32+x] != raw[0x45A0+y*24+x]
                  for y in range(24) for x in range(24))
        observations.append(dict(frame=n, mismatching_cells=bad, white=white))
        if bad and not white:
            raise ValueError(f'unfinished map is visible at frame {n}: {bad} cells')
    if all(white for _, _, white in window):
        raise ValueError('permanent blanking is not a fix')
    if window[-1][1][0x3C1] == 0 or observations[-1]['mismatching_cells']:
        raise ValueError('gameplay did not resume with a complete map')
    return dict(passed=True, start_frame=window[0][0], observations=observations,
                hidden_unfinished_frames=sum(o['mismatching_cells'] > 0 for o in observations))


def inspect(folder):
    receipt = json.loads((folder/'receipt.json').read_text())
    if receipt.get('status') != 0 or receipt.get('observer_memory_writes') is not False:
        raise ValueError('replay failed or writes memory')
    env = receipt['diagnostic_environment']
    if env.get('ENTRY_CAPTURE_EVERY') != '1':
        raise ValueError('every-frame checkpoints required')
    rom = (folder/'candidate.gb').read_bytes()
    digest = hashlib.sha256(rom).hexdigest()
    if digest != receipt['rom_sha256']:
        raise ValueError('ROM receipt mismatch')
    hashes = {'candidate.gb': digest,
              'receipt.json': hashlib.sha256((folder/'receipt.json').read_bytes()).hexdigest()}
    frames = []
    for n in range(1, int(env['ENTRY_FRAMES']) + 1):
        state = folder/f'frame-{n:04d}.ss0'
        picture = folder/f'frame-{n:04d}.png'
        raw = zlib.decompress(dict(png_chunks(state.read_bytes()))[b'gbAs'])
        if (len(raw) != 71680 or int.from_bytes(raw[4:8], 'little') != zlib.crc32(rom)
                or raw[16:32] != rom[0x134:0x144]):
            raise ValueError('state/ROM identity mismatch')
        with Image.open(picture) as image:
            if image.size != (160, 144):
                raise ValueError('native-size screenshot required')
            white = image.convert('RGB').getextrema() == ((255,255),)*3
        for p in (state, picture):
            hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
        frames.append((n, raw, white))
    result = assess(frames)
    result.update(scope=__doc__, rom_sha256=digest, artifacts=hashes,
                  checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    result = inspect(args.folder)
    with args.output.open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('artifacts','observations')}))
