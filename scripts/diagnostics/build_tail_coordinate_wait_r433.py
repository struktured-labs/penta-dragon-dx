"""Coordinate/display ordering with a tail mapper; caller flags are dead."""
import hashlib
from build_stage1_coordinate_wait_r427 import NATIVE, CODE, OFFSET, update_checksums, ROOT

BASE = ROOT / 'tmp/aligned-tile-dma-r432/candidate.gb'
SHA = 'a5fd94d0ea4287a92ed9139e882e32b6f74536a071844697b659c8c2ecb1f164'
OUT = ROOT / 'tmp/tail-coordinate-wait-r433'
HOOK = bytes.fromhex('3E 1D C3 47 08')


def check_callers(source):
    # Only these native CALLs reach the coordinate writer. Both go directly
    # to439F ->423F ->1322 ->436E ->437D; SRL D overwrites all incoming flags
    # before RR E consumes carry. No conditional branch precedes that SRL.
    calls = [i for i in range(0x8000 - 2) if source[i:i+3] == bytes.fromhex('CD 84 42')]
    assert calls == [0x12D1, 0x5090]
    for offset, expected in (
        (0x12D4, 'CD 9F 43'), (0x5093, 'C3 D4 12'),
        (0x439F, 'CD 3F 42 E5 D5 CD 22 13'),
        (0x423F, 'FA 02 DC 6F FA 03 DC 67 FA 00 DC 5F FA 01 DC 57 C9'),
        (0x1322, 'CD 6E 43'), (0x436E, 'CD 7D 43'), (0x437D, 'CB 3A CB 1B'),
    ):
        expected = bytes.fromhex(expected)
        assert source[offset:offset+len(expected)] == expected


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('requires exact r432')
    check_callers(source)
    assert source[0x4284:0x4295] == NATIVE
    assert source[OFFSET:OFFSET+len(CODE)] == b'\xff' * len(CODE)
    rom = bytearray(source)
    rom[0x4284:0x4295] = HOOK.ljust(len(NATIVE), b'\0')
    rom[OFFSET:OFFSET+len(CODE)] = CODE
    update_checksums(rom)
    return bytes(rom)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise ValueError('immutable candidate collision')
    target.write_bytes(rom)
    print(hashlib.sha256(rom).hexdigest())
