"""One complete guarded art upload must finish before tooth repair is ready."""
import hashlib
import build_stage1_single_art_upload_r293 as original
from build_stage5_dead_pointer_moves_r435 import ROOT, guard

BASE = ROOT / 'tmp/stage5-dead-pointer-moves-r435/candidate.gb'
SHA = '6b5d6a65fa9ccbbb9bc001eabb56082cf23b310e67c0573545a7c67412a4036c'
OUT = ROOT / 'tmp/single-recovery-art-r436'
SITE = 13 * 0x4000 + 0x2A33


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('requires exact r435')
    assert source[SITE:SITE+13] == original.ENTRY_OLD
    # The admission changed to a guarded VBlank path since r293. Do not
    # transplant its old admission. All three DMA bodies and completion
    # gates still match, proving one pass uploads the complete256bytes.
    head = 13 * 0x4000 + 0x2A0E
    assert source[head:head+22] == bytes.fromhex('FA 5B DF 3C E6 03 28 E1 FA 80 D8 E6 F7 FE 02 C4 25 5D C0 C3 74 74')
    for bank, address, expected in original.LOADER_BLOBS[1:]:
        offset = bank * 0x4000 + address - 0x4000
        assert source[offset:offset+len(expected)] == expected
    result = bytearray(source)
    result[SITE:SITE+13] = original.ENTRY_NEW
    guard.update_checksums(result)
    return bytes(result)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise ValueError('immutable candidate collision')
    target.write_bytes(rom)
    print(hashlib.sha256(rom).hexdigest())
