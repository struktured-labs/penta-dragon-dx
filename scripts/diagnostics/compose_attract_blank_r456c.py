"""Experimental entry-only white handoff with an interrupt-bounded VBlank wait.

The native demo-start call site has interrupts enabled. Mask only its short
wait/write transaction so the existing ISR cannot consume the entire window.
No per-frame gameplay work is added.
"""
import hashlib
import json
from compose_attract_blank_r456 import BASE, BASE_SHA, PREIMAGE, ROOT
from compose_boss_sync_dma_r454 import off, update_checksums
from build_later_hdma_overlap import Asm

OUT = ROOT / 'tmp/attract-blank-r456c'


def service():
    a = Asm(0x6C80)
    a.db(0xCD, 0x0E, 0x0A, 0xC5, 0xE5)
    a.db(0xFA, 0x80, 0xD8, 0xFE, 2)
    a.jr(0x20, 'done')
    a.db(0xF0, 0xBA, 0xB7)
    a.jr(0x20, 'done')
    a.db(0xF3, 0xF0, 0x68, 0xF5)
    a.db(0xF0, 0x40, 0xCB, 0x7F)
    a.jr(0x28, 'white')
    a.label('wait')
    a.db(0xF0, 0x44, 0xD6, 0x90, 0xFE, 6)
    a.jr(0x30, 'wait')
    a.label('white')
    a.db(0x3E, 0x80, 0xE0, 0x68)
    for _ in range(4):
        a.db(0x3E, 0xFF, 0xE0, 0x69, 0x3E, 0x7F, 0xE0, 0x69)
    a.db(0xF1, 0xE0, 0x68, 0xFB)
    a.label('done')
    a.db(0xE1, 0xC1, 0xAF, 0x3E, 1, 0xE0, 0xF4, 0xEA, 0x09, 0xDD, 0xC9)
    return a.finish()


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('requires exact r455')
    if source[0x416C:0x4176] != PREIMAGE:
        raise ValueError('native attract-start preimage changed')
    if source[18*0x4000:19*0x4000] != b'\xff'*0x4000:
        raise ValueError('retired bank 18 occupied')
    result = bytearray(source)
    result[0x416C:0x4176] = bytes.fromhex('3E12CD4708') + bytes(5)
    code = service()
    result[off(18, 0x6C80):off(18, 0x6C80)+len(code)] = code
    update_checksums(result)
    return bytes(result)


if __name__ == '__main__':
    result = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT/'candidate.gb'
    if target.exists() and target.read_bytes() != result:
        raise ValueError('immutable candidate collision')
    target.write_bytes(result)
    receipt = dict(experimental=True, promotable=False, base_sha256=BASE_SHA,
                   candidate_sha256=hashlib.sha256(result).hexdigest(),
                   service_bytes=len(service()))
    (OUT/'build-receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
