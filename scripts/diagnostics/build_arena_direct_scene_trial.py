"""#27 replace global DF0D reads with a bounded native scene resolver.

Only the bank13 installed runtime owns the reclaimed tail. Bank16 retains
its distinct legacy completion tail and original raw reads, not a false
mirror. All-scene installer coverage remains a qualification requirement.
Rejected for promotion: redirecting the shared completion caller bypasses the
bank16 legacy tail if that installer is active. Retained for diagnostic evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path

PARENT='585f5830daa32e59c000f5ddd6b57aab545e55375b46574286702db9fc28e4db'
RESOLVER=bytes.fromhex('FA80D8 FE0B C0 F0B7 D60C FE09 3802 3EFF C60C C9')
FRAGMENTS=((0x569A,36),(0x56CA,36),(0x56FA,5))


def offset(bank,address):return bank*16384+address-16384


def build(parent):
    if hashlib.sha256(parent).hexdigest()!=PARENT:
        raise ValueError('exact fastpath parent required')
    result=bytearray(parent)
    runtime=b''.join(parent[offset(13,a):offset(13,a)+n] for a,n in FRAGMENTS)
    if runtime[56:]!=bytes.fromhex('AF E1 C9 C39734')+bytes(15):
        raise ValueError('bank13 pure-return/completion/padding contract differs')
    if runtime[49:52]!=bytes.fromhex('AF E1 C9') or runtime[9:11]!=bytes.fromhex('282D') or runtime[14:16]!=bytes.fromhex('2828'):
        raise ValueError('shared pure-return contract differs')
    # Both pure paths now use DBD5. A and flags, SP and restored HL are equal.
    code=bytearray(runtime)
    code[10]=0x26
    code[15]=0x21
    code[56:]=RESOLVER+bytes(21-len(RESOLVER))
    code[2:5]=bytes.fromhex('CDDCDB')
    index=0
    for address,length in FRAGMENTS:
        pos=offset(13,address)
        result[pos:pos+length]=code[index:index+length];index+=length
    # The only absolute JP DBDF in the exact ROM is bank1's scanner tail;
    # inline its existing JP3497 destination before reclaiming DBDF.
    if parent[0x4354:0x435A]!=bytes.fromhex('CDF1DB C3DFDB'):
        raise ValueError('completion caller changed')
    refs=[i for i in range(len(parent)-2) if parent[i:i+3]==bytes.fromhex('C3DFDB')]
    if refs!=[0x4357]:raise ValueError('unexpected completion caller')
    result[0x4357:0x435A]=bytes.fromhex('C39734')
    for bank in (13,16):
        for address in (0x7C7A,0x569C,0x563A):
            pos=offset(bank,address)
            if parent[pos:pos+3]!=bytes.fromhex('FA0DDF'):
                raise ValueError('graphics-owner preimage changed')
            result[pos:pos+3]=bytes.fromhex('CDDCDB') if bank==13 else bytes.fromhex('FA80D8')
    result[0x14E:0x150]=((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();root=Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        p.error('fresh repository tmp output required')
    rom=build(args.parent.read_bytes());args.output.mkdir(parents=True)
    (args.output/'candidate.gb').write_bytes(rom)
    receipt=dict(issue=27,experimental=True,release_qualified=False,parent_sha256=PARENT,
                 candidate_sha256=hashlib.sha256(rom).hexdigest(),
                 builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 scope='bank13 runtime direct raw/FFB7 resolver; legacy completion compatibility UNQUALIFIED',
                 promotion_blocker='shared completion redirect may bypass bank16 conditional tail')
    (args.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
