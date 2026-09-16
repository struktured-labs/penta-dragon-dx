#!/usr/bin/env python3
"""Repair r366's nested-call stack before restoring the saved LCDC.

Keep r366 immutable as a negative control. Its service is entered through
two CALLs, so saved LCDC is below two return addresses, not at SP.
"""
from pathlib import Path
import hashlib
import json
import build_stage1_title_nightfall_r366 as previous

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'tmp/stage1-title-stack-r367'
OLD_TAIL = bytes.fromhex('AF E0 4F F1 E0 40 3E 0D C9')
# Pop both return addresses before the saved AF, then replace the return
# addresses in the same order. RET and the fixed-bank trampoline consume
# those two words, leaving the saved VBK at the original caller's SP.
NEW_TAIL = bytes.fromhex('AF E0 4F E1 D1 F1 D5 E5 E0 40 3E 0D C9')

def build():
    source, _ = previous.build(previous.BASE.read_bytes(), previous.BASE_RECEIPT.read_bytes())
    service = previous.build_title_service()
    assert service.endswith(OLD_TAIL)
    offset = previous.bank_offset(previous.CODE_BANK, previous.SERVICE_ADDR) + len(service) - len(OLD_TAIL)
    assert source[offset:offset + len(NEW_TAIL)] == OLD_TAIL + bytes([255]) * 4
    rom = bytearray(source)
    rom[offset:offset + len(NEW_TAIL)] = NEW_TAIL
    previous.update_checksums(rom)
    changed = {i for i, (a, b) in enumerate(zip(source, rom)) if a != b}
    assert changed <= set(range(offset, offset + len(NEW_TAIL))) | previous.CHECKSUM_OFFSETS
    assert rom[0x1199:0x119B] == bytes.fromhex('CB BF')
    return bytes(rom), offset

def main():
    rom, offset = build()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / 'candidate.gb'
    if target.exists():
        assert target.read_bytes() == rom, 'refusing to replace different candidate'
    target.write_bytes(rom)
    receipt = {'status': 'STATIC_ONLY_LIVE_TESTS_REQUIRED',
               'candidate': str(target), 'candidate_sha256': hashlib.sha256(rom).hexdigest(),
               'base_sha256': previous.EXPECTED_CANDIDATE_SHA256,
               'offset': offset, 'old_tail': OLD_TAIL.hex(), 'new_tail': NEW_TAIL.hex()}
    (OUTPUT / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))

if __name__ == '__main__':
    main()
