"""#45 shorten masked palette uploads without changing shades or wait sites."""
import argparse
import hashlib
import json
from pathlib import Path

PARENT='f938ae85785b4bc30133dad1c39e5f45ee0bcbea249d94f160132970ce22be29'
DEADLINE_PARENT='8ac7fbe3b290f4743280961541fb81746046e89bbdabde6f2b914e73fd60888c'
PREFIX=bytes.fromhex('3E 07 E0 70 3E 80 E0 68')
SUFFIX=bytes.fromhex('3E 01 E0 70 F1 E0 68 FB 00 C9')


def body(mapping,compact):
    code=bytearray(PREFIX)
    if compact and mapping!=0xe4:code.extend(bytes.fromhex('06 FF 0E 7F'))
    pointer=None
    for row in range(8):
        for color in range(4):
            ci=(mapping>>(2*color))&3
            if ci==0 and mapping!=0xe4:
                code.extend(bytes.fromhex('78 E0 69 79 E0 69' if compact else '3E FF E0 69 3E 7F E0 69'))
            else:
                address=0xdf00+row*8+ci*2
                if not compact or pointer!=address:code.extend((0x21,address&255,address>>8))
                code.extend(bytes.fromhex('2A E0 69 2A E0 69' if compact else '2A E0 69 7E E0 69'))
                pointer=address+2
    code.extend(SUFFIX)
    return bytes(code)


def build(parent):
    if hashlib.sha256(parent).hexdigest() not in (PARENT,DEADLINE_PARENT):
        raise ValueError('exact trial10 or deadline trial14 required')
    result=bytearray(parent);sites=[]
    for mapping in (0,0x40,0x90,0xe4):
        old,new=body(mapping,False),body(mapping,True)
        site=parent.find(old,20*0x4000+0x151c,20*0x4000+0x1cdc)
        if site<0 or parent.find(old,site+1)>=0:raise ValueError('map body missing or ambiguous')
        if len(new)>len(old):raise ValueError('replacement exceeds original body')
        # Padding is after RET: fixed entry addresses/callers stay unchanged.
        result[site:site+len(old)]=new+b'\x00'*(len(old)-len(new))
        sites.append(dict(mapping=mapping,offset=site,old_size=len(old),new_size=len(new)))
    result[0x14e:0x150]=((sum(result[:0x14e])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    return bytes(result),sites


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('parent',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[2]
    if a.output.exists() or (root/'tmp').resolve() not in a.output.resolve().parents:p.error('fresh repository tmp output required')
    parent=a.parent.read_bytes()
    rom,sites=build(parent);a.output.mkdir()
    (a.output/'candidate.gb').write_bytes(rom)
    r=dict(issue=45,experimental=True,release_qualified=False,parent_sha256=hashlib.sha256(parent).hexdigest(),
           candidate_sha256=hashlib.sha256(rom).hexdigest(),sites=sites,
           builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (a.output/'receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
