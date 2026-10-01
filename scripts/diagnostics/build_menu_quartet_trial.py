"""Issue #33: four menu attributes per fresh HBlank, experimental only."""
import argparse
import hashlib
import json
from pathlib import Path
from build_later_hdma_overlap import Asm
from build_menu_timer_yield_trial import PARENT, COMBINED_PARENT, ROOT

ENTRY = 0x7E00


def payload(direct_lookup=False):
    a = Asm(ENTRY)
    a.db(0x0E, 5)  # five quartets per 20-cell row
    a.label('group')
    a.db(0xC5, 0xD5, 0xE5)  # counters, source, destination
    for _ in range(4):
        a.db(0x1A, 0x13)
        if direct_lookup:
            # Destination HL is already saved for this quartet.
            a.db(0x6F, 0x26, 0x41, 0x7E)
        else:
            a.db(0xCD, 0x84, 0x40)
        a.db(0xF5)
    # Four AF words on the stack: values at offsets1,3,5,7, reversed.
    a.db(0xF8, 1, 0x46, 0x23, 0x23, 0x4E, 0x23, 0x23,
         0x56, 0x23, 0x23, 0x5E)
    a.db(0xF8, 8, 0x2A, 0x66, 0x6F)  # recover destination HL
    a.label('mode3')
    a.db(0xF0, 0x41, 0xE6, 3, 0xFE, 3)
    a.jr(0x20, 'mode3')
    a.label('mode0')
    a.db(0xF0, 0x41, 0xE6, 3)
    a.jr(0x20, 'mode0')
    a.label('before')
    a.db(0x7B, 0x22, 0x7A, 0x22, 0x79, 0x22, 0x78, 0x22)
    a.label('after')
    a.db(0xE8, 10, 0xD1, 0x13, 0x13, 0x13, 0x13, 0xC1, 0x0D)
    a.jr(0x20, 'group')
    a.db(0xC3, 0x6F, 0x40)  # native hidden-column advance/row loop
    return a.finish(), a.labels


def staged_payload(fast_compile=False):
    a = Asm(0x7C00)
    a.db(0xC5, 0xD5, 0xE5)
    a.label('compile')
    if fast_compile:
        a.db(0x26, 0x41)
        for _ in range(20):
            a.db(0x1A, 0x13, 0x6F, 0x7E, 0xF5)
    else:
        a.db(0x06, 20)
        a.label('compile_loop')
        a.db(0x1A, 0x13, 0x6F, 0x26, 0x41, 0x7E, 0xF5, 0x05)
        a.jr(0x20, 'compile_loop')
    # 40 bytes of transient AF words, plus the saved BC/DE/HL. No IRQ
    # runs while this staging is live. Consume from right to left.
    for group in range(5):
        a.db(0xF8, 1, 0x46, 0x23, 0x23, 0x4E, 0x23, 0x23,
             0x56, 0x23, 0x23, 0x5E)
        a.db(0xF8, 40-8*group, 0x2A, 0x66, 0x6F,
             0x7D, 0xC6, 19-4*group, 0x6F)
        a.label(f'mode3_{group}')
        a.db(0xF0, 0x41, 0xE6, 3, 0xFE, 3)
        a.jr(0x20, f'mode3_{group}')
        a.label(f'mode0_{group}')
        a.db(0xF0, 0x41, 0xE6, 3)
        a.jr(0x20, f'mode0_{group}')
        a.label(f'before_{group}')
        a.db(0x78, 0x32, 0x79, 0x32, 0x7A, 0x32, 0x7B, 0x32)
        a.label(f'after_{group}')
        a.db(0xE8, 8)
    a.db(0xE1, 0xD1, 0xC1, 0x7D, 0xC6, 20, 0x6F)
    for _ in range(20):
        a.db(0x13)
    a.db(0xC3, 0x6F, 0x40)
    return a.finish(), a.labels


def build(parent, direct_lookup=False, stage_row=False, fast_compile=False):
    if fast_compile and not stage_row:
        raise ValueError('fast compile requires staged rows')
    if hashlib.sha256(parent).hexdigest() not in (PARENT, COMBINED_PARENT):
        raise ValueError('exact source07 or ceiling-secret composition required')
    base = 20 * 0x4000
    if parent[base+0x4A:base+0x4D] != bytes.fromhex('0E0AC5'):
        raise ValueError('row preimage differs')
    code, labels = staged_payload(fast_compile) if stage_row else payload(direct_lookup)
    entry = 0x7C00 if stage_row else ENTRY
    cave = base + entry - 0x4000
    if parent[cave:cave+len(code)] != b'\xff'*len(code):
        raise ValueError('cave occupied')
    result = bytearray(parent)
    result[base+0x4A:base+0x4D] = b'\xc3' + entry.to_bytes(2, 'little')
    result[cave:cave+len(code)] = code
    result[0x14e:0x150] = ((sum(result[:0x14e])+sum(result[0x150:]))&65535).to_bytes(2, 'big')
    return bytes(result), labels


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--direct-lookup', action='store_true')
    p.add_argument('--stage-row', action='store_true')
    p.add_argument('--fast-compile', action='store_true')
    args = p.parse_args()
    out = args.output.resolve()
    if out.exists() or (ROOT/'tmp').resolve() not in out.parents:
        p.error('fresh repository tmp required')
    rom, labels = build(args.parent.read_bytes(), args.direct_lookup, args.stage_row, args.fast_compile)
    out.mkdir()
    (out/'candidate.gb').write_bytes(rom)
    receipt = dict(issue=33, experimental=True, release_qualified=False, direct_lookup=args.direct_lookup,
                   stage_row=args.stage_row,
                   fast_compile=args.fast_compile,
                   parent_sha256=hashlib.sha256(args.parent.read_bytes()).hexdigest(), candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   labels=labels)
    (out/'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
