#!/usr/bin/env python3
"""Experiment: reuse an early VBlank for the 48-block attribute DMA."""
from pathlib import Path
import hashlib
import json
import build_interrupt_checked_vblank_r373 as prior

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/deferred-commit-guard-r374/candidate.gb'
BASE_SHA = '85b390e48d1d8405acc1f03dee3de8944610e35206f9dbd53be1c0e3e6682922'
OUT = ROOT / 'tmp/early-vblank-dma-r375'


def make_wait():
    code, labels, jumps = bytearray(), {}, []
    def emit(s): code.extend(bytes.fromhex(s))
    def mark(s): labels[s] = len(code)
    def jr(op, target):
        code.extend((op, 0))
        jumps.append((len(code)-1, target))
    emit('F0 40 CB 7F')
    jr(0x28, 'lcd_off')
    mark('poll')
    emit('F0 44 E6 FC FE 90')
    jr(0x20, 'poll')
    emit('F3 F0 44 E6 FC FE 90')
    jr(0x28, 'ready')
    emit('FB')
    jr(0x18, 'poll')
    mark('lcd_off')
    emit('F3')
    mark('ready')
    for operand, target in jumps:
        delta = labels[target]-operand-1
        assert -128 <= delta <= 127
        code[operand] = delta & 255
    return bytes(code)


WAIT = make_wait()


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('wrong exact r374 base')
    old = prior.dma.SERVICE_CODE.replace(prior.OLD_WAIT, prior.WAIT)
    new = prior.dma.SERVICE_CODE.replace(prior.OLD_WAIT, WAIT)
    offset = prior.dma.SERVICE
    assert source[offset:offset+len(old)] == old
    assert len(new) <= len(old)
    rom = bytearray(source)
    rom[offset:offset+len(old)] = new + b'\xff'*(len(old)-len(new))
    prior.dma.update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise SystemExit('refusing to overwrite different candidate')
    target.write_bytes(rom)
    receipt = {'schema': 'penta-early-vblank-dma-r375-build-v1',
               'base_sha256': BASE_SHA,
               'candidate_sha256': hashlib.sha256(rom).hexdigest(),
               'experimental': True, 'live_tested': False,
               'guard_hex': WAIT.hex()}
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(receipt['candidate_sha256'])
