"""Verify secret-scene tile-signature palette assignments in exact-ROM states.

Both physical maps are checked, including offscreen cells. Atlas names describe
tile signatures; they do not independently identify secret-item semantics.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zlib
from verify_pickup_class_palettes import PICKUPS, find_signature, serialized_state


def inspect(raw, rom):
    if int.from_bytes(raw[4:8], 'little') != zlib.crc32(rom) & 0xffffffff or raw[16:32] != rom[0x134:0x144]:
        raise ValueError('state/ROM identity mismatch')
    if raw[0x5c80] != 9:
        raise ValueError('expected secret scene09')
    matches = []
    for pickup in PICKUPS:
        for base in (0x1800, 0x1c00):
            tiles = raw[0x400+base:0x400+base+1024]
            for x, y in find_signature(tiles, pickup.tiles):
                pos = 0x2400 + base + y*32 + x
                attrs = [raw[pos+d] for d in (0, 1, 32, 33)]
                matches.append(dict(signature=list(pickup.tiles), atlas_name=pickup.name,
                                    map=hex(0x8000+base), x=x, y=y, attributes=attrs,
                                    expected_palette=pickup.palette,
                                    passed=all(a & 7 == pickup.palette for a in attrs)))
    return dict(status='PASS_SIGNATURE_PALETTES' if matches and all(m['passed'] for m in matches) else 'FAIL',
                matches=matches,
                scope='Snapshot signatures on both maps, including offscreen; not full rendered-scene or temporal acceptance.')


def inspect_planes(raw, rom):
    """Check the secret copier's 24 published rows, including neutral scenery.

    This is the intended tile-ID palette policy, not an independent art-direction
    oracle. Rows 24..31 are outside the copier's output and are not qualified.
    """
    inspect(raw, rom)  # Exact ROM identity and scene validation, not its verdict.
    if raw[0x3ba] != 7:
        raise ValueError('expected secret stage07')
    table = [0] * 256
    for pickup in PICKUPS:
        for tile in pickup.tiles:
            table[tile] = pickup.palette
    mismatches = []
    for base in (0x1800, 0x1c00):
        for index in range(24 * 32):
            tile = raw[0x400 + base + index]
            attr = raw[0x2400 + base + index]
            if attr & 7 != table[tile]:
                mismatches.append(dict(map=hex(0x8000 + base),
                    x=index % 32, y=index // 32, tile=tile,
                    attribute=attr, expected_palette=table[tile]))
    return dict(status='FAIL' if mismatches else 'PASS_PUBLISHED_PALETTE_PLANES',
                checked_cells=1536, mismatches=mismatches,
                scope='Scene09/stage07, both maps rows0..23; tile-ID palette policy only. '
                      'Not CHR, raster timing, unoccupied rows, audio, or full-route acceptance.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom', type=Path)
    p.add_argument('state', type=Path)
    p.add_argument('--sha256', required=True)
    p.add_argument('--whole-plane', action='store_true',
                   help='check all 1536 published cells, including neutral scenery')
    args = p.parse_args()
    rom = args.rom.read_bytes()
    if hashlib.sha256(rom).hexdigest() != args.sha256:
        p.error('ROM SHA256 differs')
    result = (inspect_planes if args.whole_plane else inspect)(serialized_state(args.state), rom)
    result.update(rom_sha256=args.sha256, state_sha256=hashlib.sha256(args.state.read_bytes()).hexdigest())
    print(json.dumps(result, indent=2))
    raise SystemExit(result['status'] == 'FAIL')
