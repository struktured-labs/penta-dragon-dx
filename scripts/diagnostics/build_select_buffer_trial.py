"""#34 experimental boss Select latch; NOT release-qualified RAM ownership.

Reserve SVBK7:DF81 (pending) and DF82 (scene owner), after the experimental
menu deck DF00-DF80. Outside active boss scenes every sample/poll clears it.
Cold-boot title sampling initializes it before normal arena entry. Restoring
another ROM's state, skipping that boot path, and all-scene ownership are not
qualified. IE is saved/masked without changing IME, and restored only after
the original WRAM bank and edge writes are complete. Never touch hardware.
"""
import argparse
import hashlib
import json
from pathlib import Path
from compose_ending_bgp_handoff_r518 import Asm

PARENT = 'b09ec41a42967b2fd0fc6e88a8358d5fbfe055dcfef12be89908cf65af7c0fe8'
BANK = 37
EDGE = bytes.fromhex('FA09DD A7 2014 C5 F093 4F F095 A9 A1 47 79 E095 F096 A0 E094 79 C1 C9 AF E095 E094 C9')
SAMPLE = bytes.fromhex('B0 E093 47 3E30 E000')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def context(a):
    # C=0 outside active arena; otherwise exact scene prevents cross-boss leak.
    a.db(*bytes.fromhex('0E00 FA09DD B7 C0 F0E4 B7 C0 FA80D8 FE0C D8 FE15 D0 4F C9'))


def payload(base, sample):
    a = Asm(base)
    if sample:
        a.db(0xC5, 0xD5, 0xE5)
    # D=IE, E=original SVBK. No PUSH/POP/CALL/IRQ while bank7 is mapped.
    a.db(*bytes.fromhex('F0FF 57 AF E0FF F070 5F'))
    a.absolute(0xCD, 'context')
    if sample:
        a.db(*bytes.fromhex('F093 2F A0 E604 67'))  # H=rising Select
    a.db(*bytes.fromhex('3E07 E070 FA82DF B9'))
    a.jr(0x20, 'clear')
    a.db(0x79, 0xB7)
    a.jr(0x28, 'clear')
    a.db(*bytes.fromhex('FA81DF'))
    if sample:
        a.db(0xB4)  # OR H
    a.jr(0x18, 'store')
    a.label('clear')
    # A changed scene discards the edge sampled at the boundary as well.
    a.db(0xAF)
    a.label('store')
    if not sample:
        a.db(0x67, 0xAF)  # H=pending to consume, A=clear
    a.db(*bytes.fromhex('EA81DF 79 EA82DF 7B E070'))
    if sample:
        a.db(*bytes.fromhex('78 E093 3E30 E000 7A E0FF E1 D1 C1 3E0D C3656F'))
    else:
        a.db(*bytes.fromhex('FA09DD B7'))
        a.jr(0x20, 'disabled')
        a.db(*bytes.fromhex('F093 4F F095 A9 A1 B4 47 79 E095 F096 A0 E094 79'))
        a.jr(0x18, 'restore')
        a.label('disabled')
        a.db(*bytes.fromhex('AF E095 E094'))
        a.label('restore')
        a.db(*bytes.fromhex('F5 7A E0FF F1 C9'))
    a.label('context')
    context(a)
    return a.finish()


def build(parent):
    if digest(parent) != PARENT:
        raise ValueError('wrong exact palette-window parent')
    if parent[BANK*16384:(BANK+1)*16384] != b'\xff'*16384:
        raise ValueError('bank37 is occupied')
    if parent[0xA8:0xA8+len(EDGE)] != EDGE:
        raise ValueError('native edge function changed')
    if parent[0x36F60:0x36F68] != SAMPLE:
        raise ValueError('bank13 sampler changed')
    if parent[0x09BE:0x09C4] != bytes.fromhex('E099 EA0021 C9'):
        raise ValueError('fixed mapper ABI changed')
    if parent[0x847:0x850] != bytes.fromhex('CD6100 CD806C C36100'):
        raise ValueError('far-call ABI changed')
    result = bytearray(parent)
    # Preserve every caller register and the service's output AF while restoring
    # the original mapped ROM bank. Use09BE to avoid changing native DC09.
    wrapper = bytes.fromhex('C5 D5 E5 F099 F5 3E25 CDBE09 CD806D E1 F5 7C CDBE09 F1 E1 D1 C1 C9')
    assert len(wrapper) <= len(EDGE)
    result[0xA8:0xA8+len(EDGE)] = wrapper + bytes(len(EDGE)-len(wrapper))
    # Inline mapper-only rendezvous: unlike0847/0061 this does not overwrite
    # native DC09. Incoming09BE RET lands at bank37:6F68. Outgoing CALL at
    # 6F65 switches to13 and its RET lands at the original continuation6F68.
    result[0x36F60:0x36F68] = bytes.fromhex('B0 47 3E25 00 CDBE09')
    rendezvous = BANK*16384 + 0x6F65-0x4000
    result[rendezvous:rendezvous+6] = bytes.fromhex('CDBE09 C3806C')
    for base, sample in ((0x6C80, True), (0x6D80, False)):
        code = payload(base, sample)
        assert len(code) < 256
        offset = BANK*16384 + base-0x4000
        result[offset:offset+len(code)] = code
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository-local tmp output required')
    result = build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(result)
    receipt = dict(issue=34, parent_sha256=PARENT, candidate_sha256=digest(result),
                   builder_sha256=digest(Path(__file__).read_bytes()),
                   experimental=True, release_qualified=False,
                   ram='SVBK7:DF81-DF82; all-scene ownership unqualified',
                   scope='active arena scenes0C..14; no raw or held input replacement')
    (args.output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt))
