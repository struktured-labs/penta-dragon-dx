"""Restore hazard scanning in room03; remove an inherited speed-only bypass."""
import hashlib
from build_stage5_dead_pointer_moves_r435 import ROOT, guard

BASE = ROOT / 'tmp/single-recovery-art-r436/candidate.gb'
SHA = '37b4e9c8b4eed6621be28103d2df9a0ffb6484ca1f9d80497d956c8b8b99f2c3'
OUT = ROOT / 'tmp/restore-room03-scanner-r437'
SITE = 19 * 0x4000 + 0x2B7A
OLD = bytes.fromhex('F0 BD FE 03 C2 B7 61 C1 D1 C5 C9')
NEW = bytes.fromhex('C3 B7 61') + bytes(8)


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('requires exact r436')
    assert source[SITE:SITE+len(OLD)] == OLD
    # CALL6B70 is entered with saved HL on stack. The actual scanner owns
    # its normal unwind; the deleted POP BC/POP DE/PUSH BC was skip-only.
    assert source[SITE-10:SITE-3] == bytes.fromhex('CB 58 28 06 C3 B7 61')
    result = bytearray(source)
    result[SITE:SITE+len(OLD)] = NEW
    guard.update_checksums(result)
    return bytes(result)


if __name__ == '__main__':
    result = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != result:
        raise ValueError('immutable candidate collision')
    target.write_bytes(result)
    print(hashlib.sha256(result).hexdigest())
