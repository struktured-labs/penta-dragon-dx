"""Skip first-room coordinate colors on native respawn; retain entry metadata."""
import hashlib
from pathlib import Path
from build_stage5_private_pointer_r424 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'tmp/stage5-private-pointer-r424/candidate.gb'
SHA = 'a36469fed9b7a47d5949c867865c13064efa3c575803fb76464698064b7e071b'
OUT = ROOT / 'tmp/respawn-entry-colors-r430'


def service(source):
    body = source[0x355E5:0x355FB]
    tail = source[0x36C30:0x36C40]
    finish = source[0x36E70:0x36E80]
    lower = source[0x3560A:0x3562D]
    assert body[-3:] == bytes.fromhex('C3 30 6C')
    assert tail[-3:] == bytes.fromhex('C3 70 6E')
    assert finish[-3:] == bytes.fromhex('C3 0A 56')
    assert lower[-5:] == bytes.fromhex('AF E0 4F 2F C9')
    # The wrapper restores VBK0 and the original A=FF / ZNH flags.
    cold = body[:-3] + tail[:-3] + finish[:-3] + lower[:-5] + bytes.fromhex('3E 0D C9')
    skip = bytes.fromhex('3E 05 E0 91 3E FF EA 0D DF 3E 0D C9')
    assert len(cold) < 128
    return bytes.fromhex('F0 E1 B7 20') + bytes([len(cold)]) + cold + skip


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('requires exact r424')
    code = service(source)
    start = 29 * 0x4000 + 0x2C80
    assert source[start:start + len(code)] == b'\xff' * len(code)
    wrapper = bytes.fromhex('3E 1D CD 47 08 AF E0 4F 2F C9')
    rom = bytearray(source)
    rom[start:start + len(code)] = code
    rom[0x355E5:0x355FB] = wrapper.ljust(22, b'\0')
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
