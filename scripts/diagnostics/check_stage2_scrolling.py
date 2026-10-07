"""#59: visible Stage2 palette consistency during scrolling; not tile geometry."""
import argparse
import hashlib
import json
from pathlib import Path
from check_boss_prelude_handoff import state
from verify_native_capture_epoch import verify as verify_epoch

WATER = (0xAE, 0xAF, 0xBE, 0xBF, 0xC6, 0xC7, 0xD6, 0xD7)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def admit_native(folder, receipt, count):
    if receipt.get('observer_memory_writes') is not False or receipt.get('keys') != '16':
        raise ValueError('require right-only input without memory assistance')
    if receipt.get('native_start_gate') != 'barrier':
        raise ValueError('require native restoration barrier')
    if digest(folder/'identity.ss0') != receipt['source_state_sha256']:
        raise ValueError('changed source state')
    capture = receipt['native_capture']
    directory = Path(receipt['native_capture_directory'])
    if capture['status'] != 'COMPLETE_CAPTURE_FILES':
        raise ValueError('incomplete native capture')
    epoch = verify_epoch(directory)
    if epoch['status'] != 'PASS' or epoch != capture['restored_replay_epoch']:
        raise ValueError('invalid native restoration epoch')
    expected = {'native.s16le', 'native.video', 'native.states', 'native.wav',
                'native.timeline.tsv', 'native.meta.json'}
    if set(capture['hashes']) != expected:
        raise ValueError('missing native artifact binding')
    for name, pin in capture['hashes'].items():
        if digest(directory/name) != pin:
            raise ValueError('changed native artifact: '+name)
    meta = json.loads((directory/'native.meta.json').read_text())
    if meta != capture['metadata'] or meta['frames'] != count or meta['state_bytes'] != 71680:
        raise ValueError('wrong native capture extent')
    if (directory/'native.states').stat().st_size != count*71680:
        raise ValueError('truncated native states')
    return dict(epoch=epoch, hashes=capture['hashes'], frames=count)


def assess(raw):
    if len(raw) != 71680:
        raise ValueError('wrong native state size')
    if raw[0x5C80] not in (3, 11) or (raw[0x3B7], raw[0x3BA]) != (3, 1):
        raise ValueError('expected Stage2 gameplay on every captured frame')
    lcd, x, y = raw[0x340], raw[0x343], raw[0x342]
    if not lcd & 0x80 or lcd & 0x20:
        raise ValueError('LCD off/window is outside the gameplay oracle')
    policy = bytes(2 if tile in WATER else 0 for tile in range(256))
    if raw[0x4A00:0x4B00] != policy:
        raise ValueError('wrong Stage2 palette policy')
    page = 0x400 if lcd & 8 else 0
    rows = {(y + pixel) // 8 % 32 for pixel in range(144)}
    cols = {(x + pixel) // 8 % 32 for pixel in range(160)}
    bad, water = [], 0
    for row in sorted(rows):
        for col in sorted(cols):
            cell = page + row * 32 + col
            tile, attr = raw[0x1C00 + cell], raw[0x3C00 + cell]
            expected = policy[tile]
            water += expected == 2
            if attr & 7 != expected:
                bad.append(dict(row=row, col=col, tile=tile,
                                attribute=attr, expected_palette=expected))
    return dict(passed=not bad, checked_cells=len(rows)*len(cols),
                water_cells=water, mismatches=bad, scx=x, scy=y,
                page=page, low_health=raw[0x5C80] == 11,
                world_x=int.from_bytes(raw[0x6000:0x6002], 'little'),
                world_y=int.from_bytes(raw[0x6002:0x6004], 'little'))


def inspect(folder):
    receipt = json.loads((folder/'receipt.json').read_text())
    env = receipt['diagnostic_environment']
    count = int(env['ENTRY_FRAMES'])
    if receipt['status'] != 0 or count < 180 or env.get('ENTRY_CAPTURE_EVERY') != '1':
        raise ValueError('require complete every-frame replay of at least180 frames')
    rom = (folder/'candidate.gb').read_bytes()
    pin = hashlib.sha256(rom).hexdigest()
    if pin != receipt['rom_sha256']:
        raise ValueError('candidate identity changed')
    native = admit_native(folder, receipt, count)
    expected = [f'frame-{i:04d}.ss0' for i in range(1, count+1)]
    if sorted(p.name for p in folder.glob('frame-*.ss0')) != expected:
        raise ValueError('missing or extra captured state')
    checks = []
    for frame, name in enumerate(expected, 1):
        path = folder/name
        raw = state(path, rom)
        try:
            assessment = assess(raw)
        except ValueError as error:
            # Retain unsupported/LCD-off frames as failures, never drop them.
            assessment = dict(passed=False, error=str(error))
        checks.append(dict(frame=frame, state_sha256=digest(path),
                           screenshot_sha256=digest(path.with_suffix('.png')),
                           **assessment))
    supported = [c for c in checks if 'error' not in c]
    coverage = dict(
        every_frame_palette_correct=all(c['passed'] for c in checks),
        # Page alternation alone can happen while stationary. Require both
        # scroll-coordinate variation and actual player world movement.
        camera_moves=len({(c['scx'], c['scy']) for c in supported}) > 1,
        player_moves=len({(c['world_x'], c['world_y']) for c in supported}) > 1,
        low_health_exercised=any(c['low_health'] for c in supported),
        water_visible=any(c['water_cells'] for c in supported),
    )
    return dict(passed=all(coverage.values()), scope=__doc__, coverage=coverage,
                rom_sha256=pin, frames=count, checkpoints=checks, native=native,
                receipt_sha256=hashlib.sha256((folder/'receipt.json').read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.folder)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'checkpoints'}))
    raise SystemExit(0 if result['passed'] else 1)
