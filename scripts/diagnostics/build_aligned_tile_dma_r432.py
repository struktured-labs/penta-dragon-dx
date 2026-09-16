"""Stage1 normal-speed tile copier: one safe GDMA block on aligned even rows."""
import hashlib
from build_later_hdma_overlap import Asm
from build_six_tile_groups_r405 import service as previous_service, OFFSET
from build_remove_entry_color_seed_r431 import ROOT, update_checksums

BASE = ROOT / 'tmp/remove-entry-color-seed-r431/candidate.gb'
SHA = '838110ba5fe8f7aeb1aae470802fdf38b19a0a05e2f6e41e972fc28f68312042'
OUT = ROOT / 'tmp/aligned-tile-dma-r432'


def row_chunks(row):
    return [(0, 16, 'dma'), (16, 4, 'cpu'), (20, 4, 'cpu')] if row % 2 == 0 else [
        (i, 6, 'cpu') for i in (0, 6, 12, 18)]


def service():
    a = Asm(0x6C80)
    a.db(0xFA, 0x80, 0xD8, 0xFE, 2); a.jp(0xC2, 'fallback')
    a.db(0xF0, 0xBA, 0xB7); a.jp(0xC2, 'fallback')
    a.db(0xF0, 0x4D, 0xCB, 0x7F); a.jp(0xC2, 'fallback')
    a.db(0xF0, 0x40, 0xCB, 0x7F); a.jp(0xCA, 'fallback')
    a.db(0xF0, 0x55, 0xFE, 0xFF); a.jp(0xC2, 'fallback')
    a.db(0xC5, 0x11, 0xA0, 0xC1, 0x0E, 0x41)
    for row in range(24):
        for column, count, kind in row_chunks(row):
            tag = f'{row}_{column}'
            source = 0xC1A0 + row * 24 + column
            a.db(0xF3)
            if kind == 'dma':
                assert source % 16 == 0 and count == 16
                # Set all four DMA registers before polling. VBK0 is the
                # native tile copier's bank; no WRAM bank change is needed.
                a.db(0x3E, source >> 8, 0xE0, 0x51,
                     0x3E, source & 255, 0xE0, 0x52,
                     0x7C, 0xE6, 0x1F, 0xE0, 0x53,
                     0x7D, 0xE0, 0x54)
            a.db(0xF0, 0x44, 0xE6, 0xF8, 0xFE, 0x90); a.jr(0x28, 'copy' + tag)
            a.label('mode3' + tag)
            a.db(0xF2, 0xE6, 3, 0xFE, 3); a.jr(0x20, 'mode3' + tag)
            a.label('mode0' + tag)
            a.db(0xF2, 0x0F); a.jr(0x38, 'mode0' + tag)
            a.label('copy' + tag)
            if kind == 'dma':
                # XOR + LDH launch + 32-dot transfer fit well inside a fresh
                # HBlank; no CPU tile writes follow before the next poll.
                a.db(0xAF, 0xE0, 0x55,
                     0x11, (source + 16) & 255, (source + 16) >> 8,
                     0x2E, (row * 32 + 16) & 255)
            else:
                for i in range(count):
                    a.db(0x1A, 0x13 if (source + i) & 255 == 255 else 0x1C, 0x22)
            a.db(0xFB)
        a.db(0x7D, 0xC6, 8, 0x6F); a.jr(0x30, 'next' + str(row))
        a.db(0x24); a.label('next' + str(row))
    a.db(0xC1, 0x0E, 0, 0xAF, 0x3C, 0xC9)
    a.label('fallback'); a.db(0xAF, 0x3E, 1, 0xC9)
    return a.finish()


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('requires exact r431')
    old, code = previous_service(), service()
    assert source[OFFSET:OFFSET + len(old)] == old
    assert len(code) <= len(old)
    rom = bytearray(source)
    rom[OFFSET:OFFSET + len(old)] = code.ljust(len(old), b'\xff')
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise ValueError('immutable candidate collision')
    target.write_bytes(rom)
    print(hashlib.sha256(rom).hexdigest(), len(service()))
