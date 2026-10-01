#!/usr/bin/env python3
"""#31 read-only oracle for every observed 48-byte native projectile source.

With --copies also checks native position-adjusted destination records.
Does not certify all patterns, combat outcomes, video, timing or hardware.
Missing/malformed rows fail.
"""
import argparse
import hashlib
import json
from pathlib import Path
from build_native_projectile_templates import STOCK_SHA


def compare(rows, stock, rom):
    findings=[]
    count=0
    patterns=set()
    for row in rows:
        frame,bank,address,payload=row.split()
        frame,bank,address=int(frame),int(bank,16),int(address,16)
        data=bytes.fromhex(payload)
        if (frame<=0 or not 0<=bank<len(rom)//0x4000
                or not 0x4000<=address<=0x7FD0 or len(data)!=48):
            raise ValueError('invalid projectile source observation')
        offset=bank*0x4000+address-0x4000
        if data != rom[offset:offset+48]:
            raise ValueError('observed bytes do not match bound ROM bank/address')
        expected=stock[13*0x4000+address-0x4000:13*0x4000+address-0x4000+48]
        if len(expected)!=48:
            raise ValueError('original cartridge pattern is truncated')
        differences=[i for i,(a,b) in enumerate(zip(data,expected)) if a!=b]
        count+=1
        patterns.add(address)
        if differences:
            findings.append(dict(frame=frame,bank=bank,address=address,
                                 differing_offsets=differences))
    if count==0:
        raise ValueError('no projectile patterns observed')
    return dict(passed=not findings,observations=count,
                pattern_addresses=sorted(patterns),failures=findings)


def compare_copies(rows, stock, rom):
    sources=[]
    failures=[]
    for row in rows:
        frame,bank,address,bc,destination,source,copied=row.split()
        sources.append(' '.join((frame,bank,address,source)))
        bc=int(bc,16)
        expected=bytearray.fromhex(source)
        actual=bytes.fromhex(copied)
        if int(destination,16)!=0xDC55 or not 0<=bc<=65535 or len(expected)!=48 or len(actual)!=48:
            raise ValueError('invalid projectile copy observation')
        for offset in range(0,48,6):
            expected[offset+2]=(expected[offset+2]+(bc&255))&255
            expected[offset+3]=(expected[offset+3]+(bc>>8))&255
        differences=[i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b]
        if differences:
            failures.append(dict(frame=int(frame),differing_offsets=differences))
    result=compare(sources,stock,rom)
    result['copy_failures']=failures
    result['passed']=result['passed'] and not failures
    return result


def verify(folder, stock_path, copies=False):
    stock=stock_path.read_bytes()
    sha=lambda data:hashlib.sha256(data).hexdigest()
    if sha(stock)!=STOCK_SHA:
        raise ValueError('original cartridge reference required')
    rom_path=folder/'candidate.gb'
    trace=folder/('projectile-copies.tsv' if copies else 'projectile-sources.tsv')
    receipt=json.loads((folder/'receipt.json').read_text())
    if receipt['rom_sha256']!=sha(rom_path.read_bytes()):
        raise ValueError('run ROM identity mismatch')
    if receipt['probe_sha256']!=sha((folder/'probe.lua').read_bytes()) or receipt['status']!=0:
        raise ValueError('probe identity mismatch or incomplete run')
    result=(compare_copies if copies else compare)(trace.read_text().splitlines(),stock,rom_path.read_bytes())
    if copies and result['observations']!=len((folder/'projectile-sources.tsv').read_text().splitlines()):
        raise ValueError('source/copy observation counts differ')
    result.update(issue=31,scope=('observed source and destination copies' if copies else 'observed source patterns only')+'; not all-pattern/rendered/hardware qualification',
                  rom_sha256=receipt['rom_sha256'],trace_sha256=sha(trace.read_bytes()),
                  probe_sha256=receipt['probe_sha256'])
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    parser.add_argument('--stock',type=Path,default=Path('rom/Penta Dragon (J).gb'))
    parser.add_argument('--copies',action='store_true',help='require complete native destination-copy observations')
    args=parser.parse_args()
    result=verify(args.capture,args.stock,args.copies)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)
