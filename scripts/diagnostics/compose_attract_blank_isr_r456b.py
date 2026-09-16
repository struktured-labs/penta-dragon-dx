"""Honor native demo-white BGP in the existing VBlank ISR, without main-loop waits."""
import hashlib
import json
from pathlib import Path
from build_later_hdma_overlap import Asm
from compose_boss_sync_dma_r454 import off, update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/arena-palette-storage-r455/candidate.gb'
BASE_SHA = '6e5e7a61ddd1a44c0db6aed123528477c5531716fa16d73b083c67d64abfcbe9'
OUT = ROOT / 'tmp/attract-blank-isr-r456b'
ORIGINAL_HEAD = bytes.fromhex('F040CB7FCA006D')


def service():
    a = Asm(0x7E00)
    a.db(0xF5, 0xF0, 0x47, 0xB7)
    a.jr(0x20, 'done')
    a.db(0xFA, 0x80, 0xD8, 0xFE, 2)
    a.jr(0x20, 'done')
    a.db(0xFA, 0x09, 0xDD, 0x3D)
    a.jr(0x20, 'done')
    a.db(0xF0, 0xBA, 0xB7)
    a.jr(0x20, 'done')
    a.db(0xF0, 0x44, 0xD6, 0x90, 0xFE, 6)
    a.jr(0x30, 'done')
    a.db(0xF0, 0x68, 0xF5, 0x3E, 0x80, 0xE0, 0x68)
    for _ in range(4):
        a.db(0x3E, 0xFF, 0xE0, 0x69, 0x3E, 0x7F, 0xE0, 0x69)
    a.db(0xF1, 0xE0, 0x68)
    a.label('done')
    a.db(0xF1, *ORIGINAL_HEAD, 0xC3, 0x87, 0x6C)
    return a.finish()


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA: raise ValueError('requires exact r455')
    start = off(25, 0x6C80)
    if source[start:start+7] != ORIGINAL_HEAD: raise ValueError('ISR head changed')
    code = service(); cave = off(25, 0x7E00)
    if source[cave:cave+len(code)] != b'\xff'*len(code): raise ValueError('ISR cave occupied')
    result = bytearray(source)
    result[start:start+7] = bytes.fromhex('C3007E') + bytes(4)
    result[cave:cave+len(code)] = code
    update_checksums(result)
    return bytes(result)


if __name__ == '__main__':
    result = build(BASE.read_bytes()); OUT.mkdir(parents=True,exist_ok=True)
    target = OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=result: raise ValueError('immutable candidate collision')
    target.write_bytes(result)
    receipt = dict(experimental=True,promotable=False,base_sha256=BASE_SHA,
                   candidate_sha256=hashlib.sha256(result).hexdigest(), service_bytes=len(service()))
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
