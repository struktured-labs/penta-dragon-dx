#!/usr/bin/env python3
"""Offline ROM-sourced sprite checks for natural Stage-1 menu captures.

Checks the complete preloaded $00-$7F OBJ atlas, including animation frames
not seen in baseline OAM. No baseline image or OAM mask defines correct CHR.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

import verify_stage1_obj_visual_contract as obj
from verify_stage1_natural_menu_bg import (
    enemy_quad_signatures,
    native_stage1_enemy_quads,
    parse_report,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    (0x20000, 'b7eded462baa9ae9e0f7a34a10140d25eced01809b2683ac2e22c639b0f902a6'),
    (0x20100, 'c6e3b2e7a78c188a45fa8d3ba618f5793cf0c7261358a419b44392bd973046eb'),
    (0x20200, '132f433c32190a1fef8b66ddbfb75681dcfa5684f8ddd3fb21a0d109c94cdc34'),
    (0x20400, 'bb68f6cc453a3781c26e633b950eb7112eb5923c8fbea2cffdb53ce8df1922bf'),
    (0x21900, '2a6c0ed037084461d69d035d3dbda73fa69f1556401e87555ff01458a5c13f98'),
    (0x21000, '45a8f48f6a2171503bb2b01406ce0ca1f3a83cb083c8adf87137d8fe438a7b26'),
    (0x22A00, 'e4bd8d561f716bb3aa949e8106b762f6495a752a7fc4cdc2a18720b226fff9e9'),
    (0x20800, 'b1d92aa6457e3f7166958db60ef82eec58ea2bdf37b2f74adf33237d0b0cc779'),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def graphics_authority(rom):
    pages = []
    for address, expected in SOURCES:
        page = rom[address:address+256]
        require(digest(page) == expected, f'OBJ ROM source changed at ${address:05X}')
        pages.append(page)
    return b''.join(pages)


def source_page_evidence():
    """Return the immutable OBJ page identities in JSON-native form."""
    return [[address, expected] for address, expected in SOURCES]


def check_snapshot(data, atlas, contract):
    require(len(data) == 4326, 'malformed OBJ snapshot')
    require(data[:0x800] == atlas, 'physical OBJ CHR differs from original-ROM atlas')
    lcdc, ffbe, ffbf, ffc0, ffd0, _svbk = data[-6:]
    require(ffbf == 0, 'room05 OBJ oracle may not grade a miniboss route')
    expected = obj.expected_obj_cram(contract, ffbf=ffbf, ffc0=ffc0, ffd0=ffd0)
    require(data[4096:4160] == expected, 'OBJ CRAM differs from semantic palette authority')
    height = 16 if lcdc & 4 else 8
    sara = visible = 0
    for slot in range(40):
        y,x,tile,flags = data[4160+4*slot:4164+4*slot]
        if not (0 < x < 168 and y > 16-height and y < 160):
            continue
        visible += 1
        require(tile < 128 and flags & 8 == 0, 'visible sprite selects an unauthenticated CHR page')
        expected_palette = obj.expected_oam_palette(contract, slot=slot, tile=tile, ffbe=ffbe, ffbf=ffbf)
        require(flags & 7 == expected_palette, f'slot {slot} has wrong semantic OBJ palette')
        if slot < 4 and 0x10 <= tile <= 0x2F:
            sara += 1
            require(flags & 128 == 0, 'Sara exposes floor through OBJ priority')
    return {'visible_entries': visible, 'sara_entries': sara}


def native_enemy_oam(data, native_quads):
    """Return exact source-owned members of complete wrap-aware enemy quads."""
    height = 16 if data[-6] & 4 else 8
    objects = []
    for slot in range(40):
        y, x, tile, flags = data[4160 + 4 * slot:4164 + 4 * slot]
        objects.append({
            "slot": slot,
            "x": x - 8,
            "y": y - 16,
            "tile": f"{tile:02X}",
            "flags": f"{flags:02X}",
        })
    owned = {}
    for base, signature in enemy_quad_signatures({
        "height": height, "oam_objects": objects,
    }).items():
        if signature in native_quads:
            for obj in objects[base:base + 4]:
                owned[int(obj["slot"])] = (
                    str(obj["tile"]), str(obj["flags"]),
                )
    return owned


def bind(candidate, report_path, open_frame=1200, close_frame=1380,
         *, expected_room=0x05):
    candidate = candidate.resolve()
    rom = candidate.read_bytes()
    report = parse_report(report_path)
    require(report.get('no_menu_control', '0') == '0',
            'no-menu diagnostic cannot qualify a menu OBJ roundtrip')
    require(report.get('rom_sha256') == digest(rom), 'report targets another ROM hash')
    require(Path(report['rom']).resolve() == candidate, 'report targets another ROM path')
    room_marker = f"scene02:room{expected_room:02X}"
    require(room_marker in report.get('last_preopen', ''),
            'report pre-menu state targets another Stage-1 room')
    require(room_marker in report.get('final_state', ''),
            'report final state targets another Stage-1 room')
    atlas = graphics_authority(rom)
    contract = obj.candidate_contract(rom)
    native_quads = native_stage1_enemy_quads(rom)
    snapshots = {}
    for entry in report.get('obj_contract_trace', '').split(';'):
        match = re.fullmatch(r'f(\d+):p(.+)', entry)
        require(match is not None, 'missing or malformed OBJ capture trace')
        frame, path = int(match[1]), Path(match[2]).resolve()
        require(frame not in snapshots, 'duplicate OBJ frame')
        require(path.parent == report_path.resolve().parent, 'OBJ snapshot escaped report directory')
        snapshots[frame] = path
    expected_frames = {open_frame-1} | set(range(close_frame+2, close_frame+101))
    require(set(snapshots) == expected_frames, 'OBJ baseline/post-close coverage differs')
    evidence = []
    for frame, path in sorted(snapshots.items()):
        data = path.read_bytes()
        owned = native_enemy_oam(data, native_quads)
        evidence.append({
            'frame': frame, 'path': str(path), 'sha256': digest(data),
            'native_enemy_oam': [
                f'{slot}/{tile}/{flags}'
                for slot, (tile, flags) in sorted(owned.items())
            ],
            **check_snapshot(data, atlas, contract),
        })
    require(sum(row['sara_entries'] for row in evidence) >= 100, 'insufficient visible Sara coverage')
    return {'schema':'penta-natural-stage1-obj-v2', 'status':'pass',
            'candidate':str(candidate), 'candidate_sha256':digest(rom),
            'expected_room': f'{expected_room:02X}',
            'report':str(report_path.resolve()), 'report_sha256':digest(report_path.read_bytes()),
            'atlas_sha256':digest(atlas),
            'source_pages':source_page_evidence(),
            'verifier_sha256':digest(Path(__file__).read_bytes()),
            'obj_oracle_sha256':digest(Path(obj.__file__).read_bytes()),
            'snapshots':evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-room', type=lambda value: int(value, 16),
                        default=0x05)
    args = parser.parse_args()
    output = args.output.resolve()
    require((ROOT/'tmp').resolve() in output.parents and not output.exists(), 'output must be fresh under repo tmp/')
    receipt = bind(args.rom, args.report, expected_room=args.expected_room)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2)+'\n')
    print(f'PASS: original-ROM OBJ atlas, semantic palettes and Sara priority on {len(receipt["snapshots"])} snapshots; {output}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(f'FAIL: {error}')
