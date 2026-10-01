#!/usr/bin/env python3
"""Issue #6 trial: keep the four Sara OAM entries interrupt-atomic.

The fixed $10D1 wrapper enters with DI. Previously each entry's WRAM tail
enabled interrupts, allowing VBlank to DMA a partly updated Sara quartet.
Entries 0..2 now defer EI until entry 3. Other slots retain per-entry EI.
No RAM is allocated and both canonical/mirrored installer images are updated.
Experimental until emulator, timing, and lifecycle qualification completes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

PARENT_SHA = 'c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d'
CANDIDATE_SHA = '4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5'
OLD = bytes.fromhex(
    '3E0AEAFF1F781213791213C52A1213474F06D90AFEFF281A4F2ACDA211CD8811'
    'E6F8B11213C179C6084F3E00EAFF1FFB79C9F0BEB70E0228E00D18DD')

def body():
    # Remove dead LD B,tile, but retain the original priority-helper CALL.
    # CP 1 yields carry exactly when FFBE==0, so 1+carry selects Witch=2 or
    # Dragon=1 without a side tail. Disable SRAM and decide EI before restoring
    # BC and doing the native ADD, so its flags and A=C return stay exact.
    code = bytearray.fromhex(
        '3E0A EAFF1F 781213 791213 C5 2A1213 4F06D90A FEFF 2008 '
        'F0BE FE01 3E01 CE00 4F 2A CDA211 CD8811 E6F8 B1 1213 '
        'AF EAFF1F 7B FE10 3801 FB C1 79 C608 4F C9')
    assert len(code) <= len(OLD)
    return bytes(code).ljust(len(OLD), b'\0')

def build(source):
    if hashlib.sha256(source).hexdigest() != PARENT_SHA:
        raise ValueError('requires exact verified restart parent')
    if source[0x10D1:0x10D5] != bytes.fromhex('F3C321DA'):
        raise ValueError('DI wrapper changed')
    if source[0x1188:0x118B] != bytes.fromhex('CBBFC9'):
        raise ValueError('priority fold precondition changed')
    result = bytearray(source)
    for bank in (13,16):
        start = bank*0x4000+0x3B21
        if source[start:start+len(OLD)] != OLD:
            raise ValueError(f'bank {bank} emitter changed')
        result[start:start+len(OLD)] = body()
    result[0x14E:0x150] = ((sum(result[:0x14E])+sum(result[0x150:]))&65535).to_bytes(2,'big')
    if hashlib.sha256(result).hexdigest() != CANDIDATE_SHA:
        raise ValueError('candidate differs from the reviewed atomic-pose patch')
    return bytes(result)

def authenticated_parent(candidate):
    """Authenticate the entire delta before reusing unchanged component ABIs."""
    if hashlib.sha256(candidate).hexdigest() != CANDIDATE_SHA:
        raise ValueError('not the exact Sara atomic-pose candidate')
    parent = bytearray(candidate)
    for bank in (13,16):
        start = bank*0x4000+0x3B21
        if parent[start:start+len(OLD)] != body():
            raise ValueError('atomic emitter differs')
        parent[start:start+len(OLD)] = OLD
    parent[0x14E:0x150] = ((sum(parent[:0x14E])+sum(parent[0x150:]))&65535).to_bytes(2,'big')
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA:
        raise ValueError('unreviewed changes outside the atomic-pose delta')
    return bytes(parent)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, nargs='?')
    parser.add_argument('--original-source', action='store_true',
                        help='rebuild the authenticated restart parent from original source first')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.output.exists() or (root/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('output must be fresh below repository tmp/')
    if bool(args.source) == args.original_source:
        parser.error('choose exactly one parent ROM or --original-source')
    args.output.mkdir(parents=True)
    parent_binding = None
    if args.original_source:
        sys.path.insert(0,str(root/'scripts'))
        import build_restart_candidate as parent_builder
        parent_output = args.output/'restart-parent'
        parent_receipt = parent_builder.build(parent_output)
        args.source = parent_output/'candidate.gb'
        receipt_path = parent_output/'build-receipt.json'
        parent_builder.verify_receipt(receipt_path,args.source.read_bytes())
        parent_binding = dict(receipt=str(receipt_path.resolve()),
            receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            source_fingerprint=parent_receipt['source_fingerprint'])
    candidate = build(args.source.read_bytes())
    (args.output/'candidate.gb').write_bytes(candidate)
    receipt = dict(issue=6, experimental=True, release_qualified=False,
        source_sha256=PARENT_SHA, candidate_sha256=hashlib.sha256(candidate).hexdigest(),
        builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        original_source_parent=parent_binding)
    (args.output/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))
