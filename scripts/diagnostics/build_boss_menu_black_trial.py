"""#27 experimental boss-menu CGB palette handoff.

Live BG/OBJ palettes are backed up to experimental SVBK7:DF00-DF7F;
DF80 saves the cache-enable byte across the private return publication.
Read-only 16-byte backup batches precede the fade; publication is one VBlank.
Not release-qualified: all-scene RAM ownership and audio remain unverified.
"""
import argparse
import hashlib
import json
from pathlib import Path
from compose_ending_bgp_handoff_r518 import Asm

PARENT = '4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5'
BASE = 0x4700


def payload():
    a = Asm(BASE)
    # Existing wrapper saved AF; inspect complete original return address.
    a.db(0xE5, 0xF8, 0x05, 0x7E, 0xFE, 0x0A)
    a.absolute(0xC2, 'fallback')
    a.db(0x2B, 0x7E, 0xFE, 0x83)
    a.absolute(0xCA, 'backup')
    a.db(0xFE, 0x8A)
    a.absolute(0xCA, 'black')
    a.db(0xFE, 0x97)
    a.absolute(0xCA, 'restore')
    a.db(0xFE, 0xA2)
    a.absolute(0xCA, 'white_out')
    a.db(0xFE, 0xBB)
    a.absolute(0xCA, 'white_in')
    a.db(0xFE, 0xB8)
    a.absolute(0xCA, 'force_map')
    a.label('fallback')
    a.db(0xE1, 0xF1, 0xC3, 0x2A, 0x74)
    a.label('force_map')
    a.db(0xE1, 0xF1, 0xF5, 0xC5, 0xD5, 0xE5)
    # Disable only the cache decision during this one native publication.
    # Stack remains bank1; no PUSH/POP/CALL while bank7 is selected.
    a.db(0xFA, 0xFD, 0xDC, 0x47, 0xF3, 0x3E, 7, 0xE0, 0x70,
         0x78, 0xEA, 0x80, 0xDF, 0x3E, 1, 0xE0, 0x70,
         0xAF, 0xEA, 0xFD, 0xDC, 0xFB, 0, 0xE1, 0xD1, 0xC1)
    # Saved AF is dead at native4295 (which begins LD A,(DC0B)).
    # Use that slot to call4295 via099A's bank1 restoration, then return0AB8.
    a.db(0xE5, 0xF8, 2, 0x36, 0x95, 0x23, 0x36, 0x42, 0xE1,
         0xC3, 0x9A, 0x09)
    a.label('backup')
    a.db(0xE1, 0xF1, 0xF5, 0xC5, 0xD5, 0xE5)
    a.absolute(0xCD, 'deck')
    a.db(0xE1, 0xD1, 0xC1, 0xF1, 0xC3, 0x55, 0x0D)
    a.label('black')
    a.db(0xE1, 0xF1, 0xF5, 0xC5, 0xD5, 0xE5, 0x16, 0)
    a.absolute(0xCD, 'publish')
    # Own the menu before native construction, not only after it is drawn.
    # Otherwise scene0C's arena sanitizer writes its checker into menu C1A0.
    a.db(0x3E, 1, 0xE0, 0xE4)
    a.db(0xE1, 0xD1, 0xC1, 0xF1, 0x3E, 0xFF, 0xE0, 0x47,
         0xE0, 0x48, 0xE0, 0x49, 0xC3, 0x9A, 0x09)
    a.label('restore')
    a.db(0xE1, 0xF1, 0xF5, 0xC5, 0xD5, 0xE5, 0x16, 1)
    a.absolute(0xCD, 'publish')
    a.db(0xE1, 0xD1, 0xC1, 0xF1)
    # Exact native41E4 body, then bank1 restore preserving AF and HL.
    a.db(0x3E, 0xC4, 0xE0, 0x48, 0x3E, 0, 0xE0, 0x49,
         0x3E, 0xE4, 0xE0, 0x47, 0xC3, 0x9A, 0x09)
    for name, sequence in (('white_out', (0xE4, 0x90, 0x40, 0)),
                           ('white_in', (0, 0x40, 0x90, 0xE4))):
        a.label(name)
        a.db(0xE1, 0xF1, 0xF5, 0xC5, 0xD5, 0xE5)
        if name == 'white_in':
            a.db(0xF3, 0x3E, 7, 0xE0, 0x70, 0xFA, 0x80, 0xDF,
                 0x47, 0x3E, 1, 0xE0, 0x70, 0x78, 0xEA, 0xFD, 0xDC,
                 0xFB, 0)
            # Native307B scroll/LCDC setup, before its JP0F51.
            a.db(*bytes.fromhex('FA87DDE61FE042FA85DDE61FE043FA0BDCB728043E8B18023E83E040'))
        for mapping in sequence:
            a.absolute(0xCD, 'wait_before_publish')
            a.absolute(0xCD, f'map_{mapping:02x}')
        a.db(0xE1, 0xD1, 0xC1)
        if name == 'white_out':
            # Reuse discarded saved-AF slot as a synthetic return into2E12.
            # 099A restores bank1, RET enters native arena setup, whose RET
            # still reaches the untouched caller return0AA2 beneath it.
            a.db(0xE5, 0xF8, 2, 0x36, 0x12, 0x23, 0x36, 0x2E, 0xE1)
        else:
            a.db(0x33, 0x33)
        # Native fade's final DEC B produces Z/N, clears H, preserves C=0.
        a.db(0xAF, 0x3E, 1, 0x3D, 0x3E, sequence[-1], 0xC3, 0x9A, 0x09)
    a.label('wait_before_publish')
    # Three completed native ticks, then window() acquires the fourth before
    # its IRQ. Waiting four here adds an unintended fifth frame per step.
    a.db(*bytes.fromhex('F5AFE0D4F0D4FE0320FAAFE0D4F1C9'))
    for mapping in (0, 0x40, 0x90, 0xE4):
        a.label(f'map_{mapping:02x}')
        a.db(0xF5, 0xE5, 0xF0, 0x68, 0xF5)
        a.absolute(0xCD, 'fade_window')
        a.db(0x3E, 7, 0xE0, 0x70, 0x3E, 0x80, 0xE0, 0x68)
        for row in range(8):
            for color in range(4):
                source = 0xDF00 + row*8 + 2*((mapping >> (2*color)) & 3)
                a.db(0x21, source & 255, source >> 8,
                     0x2A, 0xE0, 0x69, 0x7E, 0xE0, 0x69)
        a.db(0x3E, mapping, 0xE0, 0x47, 0x3E, 1, 0xE0, 0x70,
             0xF1, 0xE0, 0x68, 0xE1, 0xF1, 0xFB, 0, 0xC9)
    a.label('deck')
    a.db(0xF0, 0x68, 0xF5, 0xF0, 0x6A, 0xF5)
    a.db(0x21, 0x00, 0xDF, 0x0E, 0x68, 0x06, 0)
    a.label('batch')
    a.absolute(0xCD, 'window')
    a.db(0x3E, 7, 0xE0, 0x70, 0x1E, 16)
    a.label('byte')
    a.db(0x78, 0xE2, 0x0C, 0xF2, 0x22, 0x0D, 0x04, 0x1D)
    a.jr(0x20, 'byte')
    a.db(0x3E, 1, 0xE0, 0x70, 0xFB, 0x00, 0x78, 0xFE, 64)
    a.jr(0x20, 'batch')
    a.db(0x79, 0xFE, 0x6A)
    a.jr(0x28, 'done')
    a.db(0x0E, 0x6A, 0x06, 0)
    a.jr(0x18, 'batch')
    a.label('done')
    a.db(0xF1, 0xE0, 0x6A, 0xF1, 0xE0, 0x68, 0xC9)
    a.label('publish')
    a.db(0xF0, 0x68, 0xF5, 0xF0, 0x6A, 0xF5)
    a.absolute(0xCD, 'window')
    a.db(0x3E, 7, 0xE0, 0x70, 0x21, 0x00, 0xDF, 0x7A, 0xB7)
    a.absolute(0xCA, 'publish_black')
    for port in (0x68, 0x6A):
        a.db(0x3E, 0x80, 0xE0, port)
        for _ in range(64):
            a.db(0x2A, 0xE0, port + 1)
    a.db(0x3E, 0xE4, 0xE0, 0x47)
    a.absolute(0xC3, 'published')
    a.label('publish_black')
    for port in (0x68, 0x6A):
        a.db(0x3E, 0x80, 0xE0, port, 0xAF)
        for _ in range(64):
            a.db(0xE0, port + 1)
    a.db(0x3E, 0xFF, 0xE0, 0x47)
    a.label('published')
    a.db(0x3E, 1, 0xE0, 0x70, 0xF1, 0xE0, 0x6A,
         0xF1, 0xE0, 0x68, 0xFB, 0x00, 0xC9)
    # Caller is foreground with IME enabled. Wait with native RAM mapped.
    a.label('window')
    # Acquire before VBlank: the native VBlank handler can consume the entire
    # early window. Waiting for 144 with IME enabled starves this foreground
    # loop. Trial08's one-scanline runway can be consumed by a Timer interrupt
    # (Crystal second menu return), delaying a shade by a frame. Acquire at142,
    # still recheck after DI and publish only at144. This adds at most one
    # masked scanline versus trial08; native audio remains to be qualified.
    a.db(0xF0, 0x44, 0xFE, 142)
    a.jr(0x38, 'window')
    a.db(0xFE, 144)
    a.jr(0x30, 'window')
    a.db(0xF3, 0xF0, 0x44, 0xFE, 144)
    a.jr(0x30, 'retry')
    a.label('vblank')
    a.db(0xF0, 0x44, 0xFE, 144)
    a.jr(0x38, 'vblank')
    a.db(0xC9)
    a.label('retry')
    a.db(0xFB, 0x00)
    a.jr(0x18, 'window')
    # White-fade only: prevent native VBlank from consuming the publication
    # window while Timer/STAT remain enabled during the wait. Stack stays in
    # SVBK1. Restore exact IE under DI before returning to the bounded writer.
    # 64-byte mapped publish needs <5 scanlines at normal speed; accept at
    # LY144..148 only, so every write finishes before visible line0.
    a.label('fade_window')
    a.db(0xF5, 0xF0, 0xFF, 0xF5, 0xE6, 0xFE, 0xE0, 0xFF)
    a.label('fade_visible')
    a.db(0xF0, 0x44, 0xFE, 144)
    a.jr(0x30, 'fade_visible')
    a.label('fade_wait')
    a.db(0xF0, 0x44, 0xFE, 144)
    a.jr(0x38, 'fade_wait')
    a.db(0xF3, 0xF0, 0x44, 0xFE, 144)
    a.jr(0x38, 'fade_retry')
    a.db(0xFE, 149)
    a.jr(0x30, 'fade_retry')
    a.db(0xF1, 0xE0, 0xFF, 0xF1, 0xC9)
    a.label('fade_retry')
    a.db(0xFB, 0)
    a.jr(0x18, 'fade_visible')
    return a.finish()


def build(parent):
    if hashlib.sha256(parent).hexdigest() != PARENT:
        raise ValueError('exact reported parent required')
    result = bytearray(parent)
    if parent[0x41E4:0x41F1] != bytes.fromhex('3EC4E0483E00E0493EE4E047C9'):
        raise ValueError('native menu palette-register tail differs')
    for address, old in ((0x0A80, 'CD550D'), (0x0A87, 'CD160A'), (0x0A94, 'CDE441'),
                         (0x0A9F, 'CD0F2E'), (0x0AB5, 'CD9542'), (0x0AB8, 'CD7B30')):
        if parent[address:address+3] != bytes.fromhex(old):
            raise ValueError('menu caller preimage differs')
        result[address:address+3] = bytes.fromhex('CD8942')
    entry = 20*0x4000+0x28F
    if parent[entry:entry+4] != bytes.fromhex('F1C32A74'):
        raise ValueError('credits landing differs')
    result[entry:entry+4] = bytes((0xC3, BASE&255, BASE>>8, 0))
    body = payload()
    offset = 20*0x4000 + BASE - 0x4000
    if parent[offset:offset+len(body)] != bytes([255])*len(body):
        raise ValueError('trial cave occupied')
    result[offset:offset+len(body)] = body
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        p.error('fresh repo-local tmp output required')
    candidate = build(args.parent.read_bytes())
    args.output.mkdir()
    (args.output/'candidate.gb').write_bytes(candidate)
    receipt = dict(issue=27, experimental=True, release_qualified=False,
                   parent_sha256=PARENT, candidate_sha256=hashlib.sha256(candidate).hexdigest(),
                   builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   limitations=['black intermediate fade unmodified', 'added transition latency',
                                'bank7 allocation only scoped to Shalamar', 'audio unverified'])
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
