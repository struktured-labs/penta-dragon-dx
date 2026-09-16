"""Preserve native Shalamar illustration assembly after the HP-zero transition.

The VBlank service already bypasses gameplay work during this interval.
The main-loop semantic cache must likewise not crop the illustration's legs.
Living Shalamar and every other arena retain their original decision path.
"""
from pathlib import Path
import hashlib
import json
from compose_boss_sync_dma_r454 import off, update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/attract-blank-r456d/candidate.gb'
BASE_SHA = '69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722'
OUT = ROOT / 'tmp/shalamar-death-r458b'
ENTRY = 0x6000
CAVE = 0x6300
PREIMAGE = bytes.fromhex('FA57C3')


def guard_code():
    # E=scene; return decision A=1 only for Shalamar with native DCBB=0.
    # A=1 requests full native tile publication and generic attr compilation.
    # This prevents both cropping and stale exact-repeat/raw-only planes.
    return (bytes.fromhex('7BFE0C2009FABBDCB720033E01C9')
            + PREIMAGE + bytes.fromhex('C30360'))


def build(source):
    if hashlib.sha256(source).hexdigest() != BASE_SHA:
        raise ValueError('requires exact r456d')
    entry, cave = off(20, ENTRY), off(20, CAVE)
    if source[entry:entry + 3] != PREIMAGE:
        raise ValueError('semantic helper entry changed')
    code = guard_code()
    if source[cave:cave + len(code)] != b'\xff' * len(code):
        raise ValueError('death guard cave occupied')
    result = bytearray(source)
    result[entry:entry + 3] = bytes.fromhex('C30063')
    result[cave:cave + len(code)] = code
    update_checksums(result)
    return bytes(result)


if __name__ == '__main__':
    candidate = build(BASE.read_bytes())
    OUT.mkdir(exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != candidate:
        raise ValueError('immutable candidate collision')
    target.write_bytes(candidate)
    receipt = dict(experimental=True, promotable=False, base_sha256=BASE_SHA,
                   candidate_sha256=hashlib.sha256(candidate).hexdigest())
    (OUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt)
