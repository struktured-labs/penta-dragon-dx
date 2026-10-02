"""Use the current map compiler instead of first-room coordinate color seeds."""
import hashlib
from build_respawn_entry_colors_r430 import ROOT, BASE, SHA, update_checksums

OUT = ROOT / 'tmp/remove-entry-color-seed-r431'
REPLACEMENT = bytes.fromhex('3E 05 E0 91 3E FF EA 0D DF AF E0 4F 2F C9')


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('requires exact r424')
    assert source[0x355E5:0x355E9] == bytes.fromhex('3E 01 E0 4F')
    # Preserve prelude/cache initialization and return AF/VBK contract. The
    # existing compiler owns map attributes; no new map writes are introduced.
    rom = bytearray(source)
    rom[0x355E5:0x355FB] = REPLACEMENT.ljust(22, b'\0')
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
