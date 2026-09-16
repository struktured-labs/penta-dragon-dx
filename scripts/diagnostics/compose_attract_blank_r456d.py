"""Scope the white transaction to the authenticated native title-idle caller.

At $416C the original return is $01AA for demo and $0165 for real START.
The bank trampoline adds two return words; the service saves BC and HL.
Thus SP+8 holds the original return, without borrowing gameplay RAM.
"""
import hashlib
import json
from compose_attract_blank_r456c import service as old_service
from compose_attract_blank_r456 import BASE, BASE_SHA, PREIMAGE, ROOT
from compose_boss_sync_dma_r454 import off, update_checksums

OUT = ROOT / 'tmp/attract-blank-r456d'


def service():
    old = old_service()
    done = old.index(bytes.fromhex('E1C1AF3E01E0F4EA09DDC9'))
    # Preserve all old relative branches: insert before their source/targets.
    guard = bytearray.fromhex('F8082AFEAA20007EFE012000')
    guard[6] = done - 5 + len(guard) - 7
    guard[11] = done - 5
    return old[:5] + guard + old[5:]


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('requires exact r455')
    if source[0x416C:0x4176] != PREIMAGE:
        raise ValueError('native entry preimage changed')
    if source[0x1A7:0x1AA] != bytes.fromhex('CDF140'):
        raise ValueError('native demo caller changed')
    if source[18*0x4000:19*0x4000] != b'\xff'*0x4000:
        raise ValueError('bank 18 occupied')
    result = bytearray(source)
    result[0x416C:0x4176] = bytes.fromhex('3E12CD4708') + bytes(5)
    code = service()
    result[off(18,0x6C80):off(18,0x6C80)+len(code)] = code
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
    (OUT/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
