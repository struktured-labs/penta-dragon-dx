"""Exact full-bank ownership, reconstructed independently of the tested ROM.

Banks 24/31 replay pinned historical builders and require their local inputs.
Missing inputs or builder drift fail closed. Other images are pure generators.
"""
from functools import lru_cache
import hashlib
from expansion_bank21_r456 import expected_bank21
from expansion_bank22_r456 import expected_bank22
from expansion_bank23_r456 import expected_bank23
from expansion_bank24_r455 import expected_bank24
from expansion_bank25_r456 import expected_bank25
from expansion_banks26_30_r456 import expected_banks
from expansion_bank31_r455 import expected_bank31

SIZE=16384


@lru_cache(maxsize=1)
def owned_banks():
    images={21:expected_bank21(),22:expected_bank22(),23:expected_bank23(),
            24:expected_bank24(),25:expected_bank25(),31:expected_bank31(),
            **expected_banks()}
    assert set(images)==set(range(21,32))
    assert all(len(image)==SIZE for image in images.values())
    return images


@lru_cache(maxsize=1)
def owned_bank_variants():
    """Independently replay each reviewed expansion-tail ownership lineage."""
    variants = {'reconstructed-r456': owned_banks()}

    import compose_boss_stage7_r475 as r475
    r475_rom, _ = r475.build(r475.BASE.read_bytes())
    variants['reconstructed-r475'] = {
        bank: r475_rom[bank * SIZE:(bank + 1) * SIZE]
        for bank in range(21, 32)
    }

    import compose_stage4_cache_key_r534 as r534
    r534_rom, _ = r534.build(r534.r518.BASE.read_bytes())
    variants['reconstructed-r534'] = {
        bank: r534_rom[bank * SIZE:(bank + 1) * SIZE]
        for bank in range(21, 32)
    }
    # Reconstruct the new owners from authenticated builders, never from
    # the tested ROM's bytes or a permissive bank/hash exception. The menu
    # repair and loading dispatcher claim exact code plus untouched padding.
    import build_stage1_menu_close_trial_r535 as menu
    import build_title_tile_retire_trial_r535 as title
    import build_stage_card_blank_trial_r535 as card
    menu_rom = menu.build(r534_rom, True, True)
    card_rom = card.build(title.build(r534_rom))
    for name, image in (('reconstructed-r535-menu-close', menu_rom),
                        ('reconstructed-r535-loading-retirement', card_rom)):
        variants[name] = {
            bank: image[bank * SIZE:(bank + 1) * SIZE]
            for bank in range(21, 32)
        }
    # Issues #7-#10: reconstruct the new bank25 death-cleanup owner from
    # its SHA-authenticated parent and checked source, not candidate bytes.
    import build_spike_death_trial as spike
    spike_rom = spike.build(
        (spike.ROOT / 'tmp/gameover-row-guard-candidate/candidate.gb').read_bytes()
    )
    variants['reconstructed-spike-death-cleanup'] = {
        bank: spike_rom[bank * SIZE:(bank + 1) * SIZE]
        for bank in range(21, 32)
    }
    assert all(
        set(images) == set(range(21, 32))
        and all(len(image) == SIZE for image in images.values())
        for images in variants.values()
    )
    return variants


def inspect_release_lock_tail(rom):
    """Banks 21..31 equal the spike-death owner outside reviewed delta runs."""
    import release_lock_lineage as lineage
    expected = owned_bank_variants()['reconstructed-spike-death-cleanup']
    rows = {}
    for bank, image in sorted(expected.items()):
        base = bank * SIZE
        observed = rom[base:base + SIZE]
        foreign = [
            i for i in range(SIZE)
            if observed[i] != image[i] and not lineage.touched(base + i, base + i + 1)
        ]
        rows[str(bank)] = {
            'exact': not foreign,
            'expected_sha256': hashlib.sha256(image).hexdigest(),
            'actual_sha256': hashlib.sha256(observed).hexdigest(),
            'release_lock_delta_runs': len(lineage.touched(base, base + SIZE)),
            'method': 'pinned-builder-replay plus reviewed release-lock runs',
        }
    return {'exact': all(row['exact'] for row in rows.values()),
            'mode': 'release-lock-over-spike-death-cleanup', 'banks': rows}


def inspect_tail(rom):
    import release_lock_lineage
    if release_lock_lineage.is_candidate(rom):
        return inspect_release_lock_tail(rom)
    if len(rom)!=32*SIZE:
        return {'exact':False,'reason':'requires 32 full banks','banks':{}}
    actual=rom[21*SIZE:]
    if actual==b'\xff'*len(actual):
        return {'exact':True,'mode':'legacy-erased','banks':{}}
    variants = owned_bank_variants()
    actual_banks = {
        bank: rom[bank * SIZE:(bank + 1) * SIZE]
        for bank in range(21, 32)
    }
    exact_modes = [
        mode for mode, images in variants.items()
        if all(actual_banks[bank] == image for bank, image in images.items())
    ]
    if len(exact_modes) > 1:
        raise AssertionError(f'ambiguous expansion ownership: {exact_modes}')
    if exact_modes:
        mode = exact_modes[0]
    else:
        mode = min(
            variants,
            key=lambda name: sum(
                left != right
                for bank, expected in variants[name].items()
                for left, right in zip(actual_banks[bank], expected)
            ),
        )
    selected = variants[mode]
    rows={}
    for bank,expected in sorted(selected.items()):
        observed=rom[bank*SIZE:(bank+1)*SIZE]
        rows[str(bank)]={'exact':observed==expected,
                         'expected_sha256':hashlib.sha256(expected).hexdigest(),
                         'actual_sha256':hashlib.sha256(observed).hexdigest(),
                         'method':('source-generator'
                                   if mode == 'reconstructed-r456' and bank not in (24,31)
                                   else 'pinned-builder-replay')}
    return {'exact':all(row['exact'] for row in rows.values()),
            'mode':mode,'banks':rows}


def inspect_bank18(rom):
    actual=rom[18*SIZE:19*SIZE]
    if actual==b'\xff'*SIZE:
        return {'exact':True,'mode':'retired-empty'}
    from compose_attract_blank_r456c import service as c
    from compose_attract_blank_r456d import service as d
    for name,fn in (('experimental-r456c',c),('caller-scoped-r456d',d)):
        image=bytearray(b'\xff'*SIZE)
        code=fn();image[0x2C80:0x2C80+len(code)]=code
        if actual==image and rom[0x416C:0x4176]==bytes.fromhex('3E12CD4708')+bytes(5):
            return {'exact':True,'mode':name,'service_bytes':len(code)}
    return {'exact':False,'mode':'unknown-owner'}
