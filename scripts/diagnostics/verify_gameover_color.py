#!/usr/bin/env python3
"""Issue #18: compare retained paired cold-boot restart replays, not new hashes.

The legacy verifier intentionally rejects the candidate's changed RGB identity.
This independent oracle requires unchanged glyph geometry, exact accent-only
pixel substitution, identical title/gameplay captures and a complete route.
"""
import argparse
import json
from pathlib import Path
from PIL import Image
from build_gameover_color import build, digest
from verify_death_gameover import GAMEOVER_RGB_SHA256


def compare_gameover(before, after):
    if before.size != (160, 144) or after.size != before.size:
        raise ValueError('not native-sized captures')
    before, after = before.convert('RGB'), after.convert('RGB')
    if digest(before.tobytes()) != GAMEOVER_RGB_SHA256:
        raise ValueError('parent is not the reviewed intact gray GAME OVER')
    old, new = list(before.getdata()), list(after.getdata())
    expected = [(255, 132, 255) if pixel == (173, 173, 173) else pixel for pixel in old]
    count = sum(a != b for a, b in zip(old, new))
    return new == expected and count > 0, count


def verify(parent, candidate, sequence=False):
    parent_rom = (parent / 'runtime/candidate.gb').read_bytes()
    candidate_rom = (candidate / 'runtime/candidate.gb').read_bytes()
    if candidate_rom != build(parent_rom):
        raise ValueError('candidate is not the exact palette-only patch')
    checks = {}
    for label, directory in [('parent', parent), ('candidate', candidate)]:
        checks[label + '_complete_route'] = (directory / 'route.txt').read_text().split() == ['ok', '2', '2', '2']
    checks['full_game_trace_identical'] = (parent / 'trace.tsv').read_bytes() == (candidate / 'trace.tsv').read_bytes()
    changed = []
    for cycle in (1, 2):
        with Image.open(parent / f'gameover-{cycle}.png') as a, Image.open(candidate / f'gameover-{cycle}.png') as b:
            correct, count = compare_gameover(a, b)
            rejected, _ = compare_gameover(a, a)
        checks[f'accent_only_cycle_{cycle}'] = correct
        changed.append(count)
        checks[f'gray_control_rejected_cycle_{cycle}'] = not rejected
    for label in ('title-before', 'title-after-1', 'title-after-2',
                  'stage-before', 'stage-after-1', 'stage-after-2'):
        checks[label + '_unchanged'] = (parent / (label + '.png')).read_bytes() == (candidate / (label + '.png')).read_bytes()
    sequence_failures = []
    if sequence:
        from gameover_sequence import GAMEOVER_AGES, TITLE_AGES
        for cycle in (1, 2):
            for age in GAMEOVER_AGES:
                name = f'sequence-gameover-{cycle}-{age:04d}.png'
                with Image.open(parent / name) as a, Image.open(candidate / name) as b:
                    correct, _ = compare_gameover(a, b)
                if not correct:
                    sequence_failures.append(name)
        for cycle in (0, 1, 2):
            for age in TITLE_AGES:
                name = f'sequence-title-{cycle}-{age:04d}.png'
                if (parent / name).read_bytes() != (candidate / name).read_bytes():
                    sequence_failures.append(name)
        checks['consecutive_frames_correct'] = not sequence_failures
    bindings = {}
    for label, directory in [('parent', parent), ('candidate', candidate)]:
        bindings[label] = {p.name: digest(p.read_bytes()) for p in directory.iterdir()
                           if p.is_file() and p.suffix in ('.png', '.tsv', '.txt', '.json')}
    return dict(issue=18, status='PASS' if all(checks.values()) else 'FAIL', checks=checks,
                changed_accent_pixels=changed, parent_sha256=digest(parent_rom),
                candidate_sha256=digest(candidate_rom), evidence_bindings=bindings,
                verifier_sha256=digest(Path(__file__).read_bytes()),
                builder_sha256=digest(Path(__file__).with_name('build_gameover_color.py').read_bytes()),
                sequence=sequence, sequence_failures=sequence_failures,
                scope='paired accelerated-death cold-boot cycles; ' +
                      ('102 Game Over and 723 title frame pairs' if sequence else 'settled screenshots') +
                      '; no hardware/audio qualification',
                release_qualified=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('candidate', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--sequence', action='store_true')
    a = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if a.output.exists() or (root / 'tmp').resolve() not in a.output.resolve().parents:
        p.error('output must be fresh beneath repository tmp/')
    result = verify(a.parent, a.candidate, a.sequence)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'checks', 'changed_accent_pixels')}))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
