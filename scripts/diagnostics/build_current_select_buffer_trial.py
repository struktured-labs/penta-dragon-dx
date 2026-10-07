"""#34 exact current-parent experiment; not enabled in the release builder.

Reuse the historical latch implementation byte-for-byte, replacing only its
terminal scene classifier to recognize the native low-health alias. Physical
bank7 ownership outside the measured routes and timing still need qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path

import build_select_buffer_trial as legacy

PARENT = '126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941'
CANDIDATE = 'cb7996f97e319d25084793bc5fa5ca1d8bc96a36e8d65474e1e960a5c2035f6f'
OLD_CONTEXT = bytes.fromhex('0E00 FA09DD B7 C0 F0E4 B7 C0 FA80D8 FE0C D8 FE15 D0 4F C9')
CONTEXT = bytes.fromhex('0E00 FA09DD B7 C0 F0E4 B7 C0 FA80D8 FE0B 2002 F0B7 FE0C D8 FE15 D0 4F C9')


def payload(base, sample):
    original = legacy.payload(base, sample)
    if not original.endswith(OLD_CONTEXT):
        raise ValueError('historical terminal context changed')
    return original[:-len(OLD_CONTEXT)] + CONTEXT


def build(parent):
    if legacy.digest(parent) != PARENT:
        raise ValueError('wrong exact current parent')
    if len(parent) != 0x100000:
        raise ValueError('wrong ROM size')
    if parent[legacy.BANK*16384:(legacy.BANK+1)*16384] != b'\xff'*16384:
        raise ValueError('bank37 is occupied')
    for offset, expected in (
        (0xA8, legacy.EDGE), (0x36F60, legacy.SAMPLE),
        (0x09BE, bytes.fromhex('E099 EA0021 C9')),
        (0x847, bytes.fromhex('CD6100 CD806C C36100')),
    ):
        if parent[offset:offset+len(expected)] != expected:
            raise ValueError(f'hook ABI changed at {offset:06X}')
    result = bytearray(parent)
    wrapper = bytes.fromhex('C5 D5 E5 F099 F5 3E25 CDBE09 CD806D E1 F5 7C CDBE09 F1 E1 D1 C1 C9')
    result[0xA8:0xA8+len(legacy.EDGE)] = wrapper + bytes(len(legacy.EDGE)-len(wrapper))
    result[0x36F60:0x36F68] = bytes.fromhex('B0 47 3E25 00 CDBE09')
    rendezvous = legacy.BANK*16384 + 0x6F65-0x4000
    result[rendezvous:rendezvous+6] = bytes.fromhex('CDBE09 C3806C')
    for base, sample in ((0x6C80, True), (0x6D80, False)):
        code = payload(base, sample)
        if len(code) >= 256:
            raise ValueError('latch payload exceeds its reservation')
        offset = legacy.BANK*16384 + base-0x4000
        result[offset:offset+len(code)] = code
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2, 'big')
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository-local tmp output required')
    result = build(args.parent.read_bytes())
    if legacy.digest(result) != CANDIDATE:
        raise ValueError('construction differs from measured trial')
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(result)
    receipt = dict(issue=34, status='BUILT_NOT_RELEASE_QUALIFIED',
                   parent_sha256=PARENT, candidate_sha256=CANDIDATE,
                   builders=[dict(path=str(p.resolve()), sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                             for p in (Path(__file__), Path(legacy.__file__))])
    (args.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
