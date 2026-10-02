#!/usr/bin/env python3
"""Diagnostic opaque OBJ pixel comparison; does not qualify a menu roundtrip.

Only OBJ-priority-zero pixels are compared. BG attribute-priority occlusion
is not modelled: any discrepancy remains a diagnostic failure for review.
"""
import argparse
import json
from pathlib import Path
import re
from PIL import Image
import verify_natural_stage1_obj as authority
from verify_stage1_natural_menu_bg import parse_report


def expected_pixels(data):
    authority.require(len(data) == 4326, 'malformed OBJ snapshot')
    authority.require(data[-6] & 0x82 == 0x82, 'LCD or sprites disabled')
    height = 16 if data[-6] & 4 else 8
    cram = data[4096:4160]
    oam = data[4160:4320]
    for y in range(144):
        # Hardware selects at most ten sprites by Y, including offscreen X.
        selected = [s for s in range(40) if oam[4*s]-16 <= y < oam[4*s]-16+height][:10]
        for x in range(160):
            for slot in selected:
                sy, sx, tile, flags = oam[4*slot:4*slot+4]
                col, row = x-(sx-8), y-(sy-16)
                if not 0 <= col < 8:
                    continue
                if flags & 32: col = 7-col
                if flags & 64: row = height-1-row
                if height == 16: tile = (tile & 254) + row//8
                address = tile*16 + (row%8)*2
                bit = 7-col
                color = ((data[address] >> bit) & 1) | (((data[address+1] >> bit) & 1) << 1)
                if not color: continue
                if not flags & 128:
                    pos = (flags & 7)*8 + color*2
                    word = int.from_bytes(cram[pos:pos+2], 'little')
                    # mGBA expands five-bit channels by bit replication.
                    channels = tuple((word >> s) & 31 for s in (0,5,10))
                    yield x, y, slot, tuple((v << 3) | (v >> 2) for v in channels)
                break


def compare_image(data, im):
    authority.require(im.size == (160,144), 'non-native raster')
    pixels = im.convert('RGB').load()
    checked = bad = 0
    examples = []
    for x,y,slot,want in expected_pixels(data):
        checked += 1
        if pixels[x,y] != want:
            bad += 1
            if len(examples) < 12:
                examples.append(dict(x=x,y=y,slot=slot,expected=want,actual=pixels[x,y]))
    return checked, bad, examples


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom', type=Path)
    ap.add_argument('report', type=Path)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    authority.require((authority.ROOT/'tmp').resolve() in args.output.resolve().parents
                      and not args.output.exists(), 'output must be fresh under repo tmp/')
    rom = args.rom.read_bytes()
    report = parse_report(args.report)
    authority.require(report['rom_sha256'] == authority.digest(rom), 'wrong ROM')
    authority.require(Path(report['rom']).resolve() == args.rom.resolve(), 'wrong ROM path')
    atlas = authority.graphics_authority(rom)
    contract = authority.obj.candidate_contract(rom)
    checked = bad = frames = 0
    examples = []
    for entry in report['obj_contract_trace'].split(';'):
        m = re.fullmatch(r'f(\d+):p(.+)', entry)
        authority.require(m is not None, 'malformed snapshot')
        frame, path = int(m[1]), Path(m[2])
        authority.require(path.resolve().parent == args.report.resolve().parent,
                          'snapshot escaped report directory')
        data = path.read_bytes()
        authority.check_snapshot(data, atlas, contract)
        raster = Path(str(args.report) + f'.raster-f{frame:04d}.png')
        with Image.open(raster) as im:
            count, mismatches, sample = compare_image(data, im)
            checked += count
            bad += mismatches
            examples.extend(dict(frame=frame, **item) for item in sample[:12-len(examples)])
        frames += 1
    result = dict(diagnostic_only=True, frames=frames, checked_pixels=checked,
                  mismatched_pixels=bad, examples=examples,
                  candidate_sha256=authority.digest(rom))
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    return int(bad != 0 or checked == 0)


if __name__ == '__main__':
    raise SystemExit(main())
