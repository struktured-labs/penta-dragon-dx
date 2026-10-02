#!/usr/bin/env python3
"""Recheck LY after DI: an IRQ may invalidate the preceding VBlank sample."""
from pathlib import Path
import hashlib
import json
import build_stage1_timer_safe_gdma_r370 as dma
import build_menu_vblank_reveal_r372 as menu

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/menu-vblank-reveal-r372/candidate.gb'
BASE_SHA = '201fe703ea060e666db00c8e9ba9daa515a854f50445aa1c3e2abc1bfe6f461d'
OUT = ROOT / 'tmp/interrupt-checked-vblank-r373'
OLD_WAIT = bytes.fromhex('F0 40 CB 7F 28 0C F0 44 FE 90 30 FA F0 44 FE 90 38 FA F3')


def make_wait():
    code = bytearray()
    labels = {}
    jumps = []
    def emit(s):
        code.extend(bytes.fromhex(s))
    def mark(s):
        labels[s] = len(code)
    def jr(op, target):
        code.extend((op, 0))
        jumps.append((len(code)-1, target))
    emit('F0 40 CB 7F')
    jr(0x28, 'lcd_off')
    mark('wait_end')
    emit('F0 44 FE 90')
    jr(0x30, 'wait_end')
    mark('wait_start')
    emit('F0 44 FE 90')
    jr(0x38, 'wait_start')
    mark('close_irq_window')
    emit('F3 F0 44 FE 90')
    jr(0x28, 'ready')
    # A Timer IRQ consumed the safe edge. Retry without starving music.
    emit('FB')
    jr(0x18, 'wait_end')
    mark('lcd_off')
    emit('F3')
    mark('ready')
    for operand, target in jumps:
        delta = labels[target] - operand - 1
        assert -128 <= delta <= 127
        code[operand] = delta & 255
    return bytes(code), labels


WAIT, LABELS = make_wait()


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r372 base')
    rom = bytearray(source)
    for offset, old in ((dma.SERVICE, dma.SERVICE_CODE), (menu.offset(0x7F00), menu.CODE)):
        assert old.count(OLD_WAIT) == 1
        new = old.replace(OLD_WAIT, WAIT)
        assert source[offset:offset+len(old)] == old
        assert source[offset+len(old):offset+len(new)] == b'\xff' * (len(new)-len(old))
        rom[offset:offset+len(new)] = new
    dma.update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('refusing to overwrite different candidate')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-interrupt-checked-vblank-r373-build-v1',
               'base_sha256': BASE_SHA,
               'candidate_sha256': hashlib.sha256(rom).hexdigest(),
               'experimental': True, 'guard_bytes': WAIT.hex()}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt['candidate_sha256'])
