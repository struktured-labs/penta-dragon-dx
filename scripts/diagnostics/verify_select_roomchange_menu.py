#!/usr/bin/env python3
"""#81 regression: Select 2 frames after an FFBD change must not double the HUD.

Runs the deterministic Stage-1 tour on the provided ROM (the official JP
candidate) and, when possible, on an English image produced by re-applying
the committed JP->EN translation delta. Fails if any post-open watch frame
has HP bars at both y=31-33 and y=131-133, or if the tour never opens the
menu after a room-id change.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name('probe_select_roomchange_menu.lua')
MGBA = ROOT / 'scripts/mgba-qt-singleflight'
OFFICIAL_JP_SHA = '91d58599d3df5dde80131ce20d0a639d7056d015dc91cedd2e699b66a141ba18'
OFFICIAL_EN_SHA = '631b24a4fadb6257581cd6a4b5d951d68c47990a002b2418ce02dae00645c464'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    rom[0x014E:0x0150] = ((sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF).to_bytes(2, 'big')


def hp_bar_rows(path: Path) -> list[list[int]]:
    """Return inclusive y-ranges of a 3-row red/white HP bar, Carmelo-validated."""
    im = Image.open(path).convert('RGB')
    px = im.load()
    w, h = im.size
    hits = []
    y = 0
    while y < h:
        if sum(1 for x in range(w) if px[x, y] in {(255, 0, 0), (255, 255, 255)}) >= 40:
            start = y
            while y < h and sum(1 for x in range(w) if px[x, y] in {(255, 0, 0), (255, 255, 255)}) >= 40:
                y += 1
            if y - start == 3:
                hits.append([start, y - 1])
        else:
            y += 1
    return hits


def is_double_hud(path: Path) -> bool:
    rows = hp_bar_rows(path)
    tops = {lo for lo, hi in rows}
    return 31 in tops and 131 in tops


def apply_english_delta(jp: bytes, official_jp: bytes, official_en: bytes) -> bytes:
    if sha(official_jp) != OFFICIAL_JP_SHA or sha(official_en) != OFFICIAL_EN_SHA:
        raise ValueError('official JP/EN translation pair identity differs')
    if len(jp) != len(official_jp) or len(official_jp) != len(official_en):
        raise ValueError('JP/EN translation pair size differs')
    out = bytearray(jp)
    for i, (a, b) in enumerate(zip(official_jp, official_en)):
        if a != b and i not in (0x14D, 0x14E, 0x14F):
            out[i] = b
    update_checksums(out)
    return bytes(out)


def find_official_pair() -> tuple[Path, Path] | None:
    candidates = [
        (ROOT / 'tmp/roms-main/JP.gbc', ROOT / 'tmp/roms-main/EN.gbc'),
        (ROOT / 'rom/working/penta_dragon_dx_FIXED.gb',
         ROOT / 'rom/working/penta_dragon_dx_en.gb'),
    ]
    for jp, en in candidates:
        if jp.is_file() and en.is_file() and sha(jp.read_bytes()) == OFFICIAL_JP_SHA \
                and sha(en.read_bytes()) == OFFICIAL_EN_SHA:
            return jp, en
    return None


def run_probe(rom: Path, output: Path, env: dict[str, str]) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(rom, output / 'rom.gb')
    command = [
        str(MGBA),
        '--fastforward',
        '-C', f'savegamePath={output}',
        '-C', f'savestatePath={output}',
        str(output / 'rom.gb'),
        '--script', str(PROBE.resolve()),
    ]
    child = dict(env)
    for key in ('PENTA_MGBA_LOCK', 'PENTA_MGBA_QT_BIN'):
        child.pop(key, None)
    child['CAP_OUT'] = str(output)
    child['CAP_STOP'] = child.get('CAP_STOP', '2000')
    child['SEL_DELAY'] = '2'
    child['QT_QPA_PLATFORM'] = 'offscreen'
    child['SDL_AUDIODRIVER'] = 'dummy'
    child.pop('WAYLAND_DISPLAY', None)
    result = subprocess.run(command, cwd=str(ROOT), env=child, check=False,
                            timeout=120)
    shots = sorted(output.glob('w*.png'))
    doubles = [p.name for p in shots if is_double_hud(p)]
    changes = 0
    if (output / 'trans.tsv').is_file():
        changes = sum(1 for line in (output / 'trans.tsv').read_text().splitlines()
                      if 'room_change_' in line)
    return {
        'rom_sha256': sha(rom.read_bytes()),
        'returncode': result.returncode,
        'watch_shots': len(shots),
        'room_changes': changes,
        'double_hud': doubles,
    }


def evaluate(report: dict, label: str) -> list[str]:
    errors = []
    if report['room_changes'] < 2 or report['watch_shots'] < 2:
        errors.append(f'{label}: tour did not exercise Select 2 frames after a room change')
    if report['double_hud']:
        errors.append(f'{label}: double HUD on {report["double_hud"]}')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('--en-rom', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    reports = {}
    errors = []
    jp_report = run_probe(args.rom.resolve(), output / 'jp', env)
    reports['jp'] = jp_report
    errors.extend(evaluate(jp_report, 'JP'))

    en_path = args.en_rom
    if en_path is None:
        pair = find_official_pair()
        if pair is not None:
            en_bytes = apply_english_delta(
                args.rom.read_bytes(), pair[0].read_bytes(), pair[1].read_bytes())
            en_path = output / 'en-applied.gbc'
            en_path.write_bytes(en_bytes)
    if en_path is not None:
        en_report = run_probe(en_path.resolve(), output / 'en', env)
        reports['en'] = en_report
        errors.extend(evaluate(en_report, 'EN'))
    else:
        errors.append('EN ROM was not provided and the official JP/EN pair was not found')

    (output / 'receipt.json').write_text(json.dumps({
        'schema': 'penta-select-roomchange-menu-v1',
        'reports': reports,
        'errors': errors,
    }, indent=2) + '\n')
    if errors:
        print('FAIL: ' + '; '.join(errors), file=sys.stderr)
        return 1
    print(json.dumps({'status': 'PASS', 'reports': reports}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
