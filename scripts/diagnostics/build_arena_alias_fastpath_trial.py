"""#27: retain native scene-cache hit cost; resolve aliases only on misses.

Experimental. Compact the equivalent title/story classification to fit the
original112-byte detector slot. Do not change native sound-state writes.
"""
import argparse
import hashlib
import json
from pathlib import Path
from compose_ending_bgp_handoff_r518 import Asm
from build_arena_sound_alias_trial import payload as alias_payload

PARENT = '35a8d40bc9ed8cf3d967d0c01df0674bcf119a0ec0364ef1bcb60493a9448af7'
OLD_DETECTOR = '0097866f0577915fb02cadc5154f44d45214ba6d31748b9acc08e21140044cfd'


def detector():
    a = Asm(0x6F90)
    a.db(*bytes.fromhex('FA80D8 210DDF BE C8'))  # original hot path bytewise
    a.db(*bytes.fromhex('3E14 CDBE09 F1 C8'))
    a.db(*bytes.fromhex('CDFC7C 77 FE02'))
    a.jr(0x30,'classify')
    a.db(*bytes.fromhex('C3436D'))
    a.label('classify')
    a.db(*bytes.fromhex('D615 FE08'))
    a.jr(0x30,'game')
    a.db(0xFE,2)
    a.jr(0x28,'game')  # scene17 follows existing non-title route
    a.db(0xFE,4)
    a.jr(0x38,'title')
    a.db(0xFE,6)
    a.jr(0x30,'title')
    a.db(*bytes.fromhex('AF EA08DF'))  # scenes19/1A clear story state
    a.label('title')
    a.db(*bytes.fromhex('3E5A EA02DF C3436D'))
    a.label('game')
    # Restore original scene and apply the original arena normalization.
    a.db(*bytes.fromhex('C615 D60C'))
    a.jr(0x38,'dungeon')
    a.db(0xFE,9)
    a.jr(0x30,'default')
    a.db(*bytes.fromhex('C672 67 2E00 3E17 CD4708'))
    a.jr(0x18,'copy')
    a.label('dungeon')
    a.db(*bytes.fromhex('F0BA B7'))
    a.jr(0x28,'reset')
    a.db(*bytes.fromhex('C3E77F'))
    a.label('reset')
    a.db(*bytes.fromhex('AF EA53DF EA57DF'))
    a.label('default')
    a.db(*bytes.fromhex('210070'))
    a.label('copy')
    a.db(*bytes.fromhex('1100C6 0600'))
    a.label('byte')
    a.db(*bytes.fromhex('2A 12 13 05'))
    a.jr(0x20,'byte')
    a.db(0xC9)
    code = a.finish()
    if len(code)>112:
        raise ValueError(f'detector exceeds reserved slot: {len(code)}')
    return code + bytes(112-len(code))


def build(parent):
    if hashlib.sha256(parent).hexdigest()!=PARENT:
        raise ValueError('exact graphics-owner parent required')
    if hashlib.sha256(parent[0x36F90:0x37000]).hexdigest()!=OLD_DETECTOR:
        raise ValueError('detector preimage differs')
    code=alias_payload()
    if code[-3:]!=bytes.fromhex('C3926F'):
        raise ValueError('resolver return contract differs')
    code=code[:-3]+bytes.fromhex('C39A6F')
    result=bytearray(parent)
    for addr,blob in ((0x6DE0,code),(0x6F9A,bytes.fromhex('CDBE09 C3E06D'))):
        pos=20*16384+addr-16384
        if parent[pos:pos+len(blob)]!=b'\xff'*len(blob):
            raise ValueError('private mapper/helper cave occupied')
        result[pos:pos+len(blob)]=blob
    result[0x36F90:0x37000]=detector()
    result[0x14E:0x150]=((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    root=Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        p.error('fresh repository tmp output required')
    rom=build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(rom)
    receipt=dict(issue=27,experimental=True,release_qualified=False,parent_sha256=PARENT,
                 candidate_sha256=hashlib.sha256(rom).hexdigest(),
                 builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 resolver_builder_sha256=hashlib.sha256(Path(__file__).with_name('build_arena_sound_alias_trial.py').read_bytes()).hexdigest(),
                 scope='native byte-exact cache-hit prefix; alias miss only; condensed scene routing unqualified')
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
