"""Compose existing issue14/21/23/27/33 experiments, never a release promotion.

Inputs remain exact authenticated source07 and reported parent. Every branch
is rebuilt by its issue-owned builder. Independent overlays must have unchanged
preimages in the combined candidate; conflicting bytes fail rather than win.
"""
import argparse
import hashlib
import json
from pathlib import Path

import build_sara_doorway_priority as ceiling
import build_secret_combined_copy_trial as secret
import build_menu_quartet_trial as menu
import build_boss_vblank_guard as boss
import build_boss_menu_black_trial as fade


def digest(data):
    return hashlib.sha256(data).hexdigest()


def overlay(current, base, variant):
    # Ceiling/secret work expands the ROM with dedicated banks. Existing
    # same-size branch overlays may touch only their authenticated prefix.
    if len(current) < len(base) or len(base) != len(variant):
        raise ValueError('overlay sizes differ')
    changed = [i for i, (a, b) in enumerate(zip(base, variant))
               if a != b and i not in (0x14E, 0x14F)]
    conflicts = [i for i in changed if current[i] != base[i]]
    if conflicts:
        raise ValueError(f'overlay preimage conflict: {list(map(hex, conflicts[:16]))}')
    result = bytearray(current)
    for i in changed:
        result[i] = variant[i]
    return bytes(result), changed


def build(source, reported, defer_ceiling=False):
    """defer_ceiling omits the #14 doorway helper (release lock 2026-10-01).

    Its CPU cost desyncs the attract demo, and the cheaper scratch-B helper
    moves the cold doorway route, so #14 is deferred rather than shipped.
    """
    if digest(source) != ceiling.SOURCE07_SHA or digest(reported) != fade.PARENT:
        raise ValueError('exact source07 and reported parents required')
    current = source if defer_ceiling else ceiling.build(source, combined=True)
    current = secret.build(current, scratch_bank=6, yield_between_rows=True)
    current, _ = menu.build(current, stage_row=True, fast_compile=True)
    records = []
    for name, base, variant in (
            ('boss-vblank', source, boss.build(source)),
            ('boss-menu-fade', reported, fade.build(reported))):
        current, changed = overlay(current, base, variant)
        records.append(dict(name=name, base_sha256=digest(base),
                            branch_sha256=digest(variant), changed_offsets=changed))
    result = bytearray(current)
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    return bytes(result), records


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source07', type=Path)
    p.add_argument('reported', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.output.resolve()
    if out.exists() or (root/'tmp').resolve() not in out.parents:
        p.error('fresh repository tmp output required')
    candidate, branches = build(args.source07.read_bytes(), args.reported.read_bytes())
    out.mkdir()
    (out/'candidate.gb').write_bytes(candidate)
    receipt = dict(experimental=True, release_qualified=False, issues=[14,21,23,27,33],
                   candidate_sha256=digest(candidate), branches=branches,
                   source07_sha256=ceiling.SOURCE07_SHA, reported_sha256=fade.PARENT,
                   builders={str(Path(m.__file__).resolve()):digest(Path(m.__file__).read_bytes())
                             for m in (ceiling, secret, menu, boss, fade)},
                   composer_sha256=digest(Path(__file__).read_bytes()),
                   limitations=['composition untested', 'audio not qualified',
                                'not all reported bugs reproduced or fixed'])
    (out/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
