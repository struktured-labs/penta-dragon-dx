"""Read-only CGB background oracle for settled mGBA restart checkpoints.

Layout: mGBA include/mgba/internal/gb/serialize.h, version 0x00400003.
No emulator state is edited; sprites are deliberately not part of terrain.
"""
import struct
import zlib
from PIL import Image, ImageChops, ImageDraw


def read_state(path):
    data = path.read_bytes()
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('expected PNG savestate')
    offset, states = 8, []
    while offset + 12 <= len(data):
        length = struct.unpack_from('>I', data, offset)[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        if offset + length + 12 > len(data):
            raise ValueError('truncated savestate chunk')
        if zlib.crc32(kind + payload) & 0xffffffff != struct.unpack_from('>I', data, offset + 8 + length)[0]:
            raise ValueError('savestate chunk CRC mismatch')
        if kind == b'gbAs':
            states.append(zlib.decompress(payload))
        offset += length + 12
    if len(states) != 1 or len(states[0]) != 0x11800:
        raise ValueError('unsupported savestate layout')
    state = states[0]
    if struct.unpack_from('<I', state)[0] != 0x00400003:
        raise ValueError('unsupported savestate version')
    return state


def terrain(state):
    lcdc, scy, scx = state[0x340], state[0x342], state[0x343]
    if not lcdc & 0x80:
        raise ValueError('LCD disabled at terrain checkpoint')
    if lcdc & 0x20 and state[0x34A] < 128 and state[0x34B] < 167:
        raise ValueError('window overlaps terrain checkpoint')
    base = 0x1c00 if lcdc & 8 else 0x1800
    result = bytearray()
    for y in range(32, 128):
        for x in range(160):
            px, py = (x + scx) & 255, (y + scy) & 255
            cell = base + (py // 8) * 32 + px // 8
            tile, attr = state[0x400 + cell], state[0x2400 + cell]
            tx, ty = px & 7, py & 7
            if attr & 0x20: tx = 7 - tx
            if attr & 0x40: ty = 7 - ty
            address = tile * 16 if lcdc & 0x10 else 0x1000 + (tile if tile < 128 else tile - 256) * 16
            address += 0x400 + (0x2000 if attr & 8 else 0) + ty * 2
            color = ((state[address] >> (7 - tx)) & 1) | (((state[address + 1] >> (7 - tx)) & 1) << 1)
            palette = 0xd4 + (attr & 7) * 8 + color * 2
            result.extend(state[palette:palette + 2])
            result.append(attr & 0x80)
    return bytes(result)


def compare_terrain(before, after):
    if terrain(read_state(before)) != terrain(read_state(after)):
        raise ValueError(f'background terrain/colour/priority changed: {before.name} -> {after.name}')


def compare_terrain_captures(before, after):
    compare_terrain(before.with_suffix('.ss0'), after.with_suffix('.ss0'))
    mask = Image.new('L', (160, 144), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((0, 32, 159, 127), fill=255)
    for path in (before, after):
        state = read_state(path.with_suffix('.ss0'))
        height = 16 if state[0x340] & 4 else 8
        if state[0x340] & 2:
            for offset in range(0x260, 0x300, 4):
                y, x = state[offset] - 16, state[offset + 1] - 8
                draw.rectangle((x, y, x + 7, y + height - 1), fill=0)
    if sum(bool(p) for p in mask.getdata()) < 160 * 96 // 2:
        raise ValueError('insufficient unoccluded terrain screenshot coverage')
    with Image.open(before.with_suffix('.png')) as a, Image.open(after.with_suffix('.png')) as b:
        if a.size != (160, 144) or b.size != a.size:
            raise ValueError('expected native terrain screenshots')
        delta = ImageChops.difference(a.convert('RGB'), b.convert('RGB'))
        if Image.composite(delta, Image.new('RGB', a.size), mask).getbbox():
            raise ValueError('terrain screenshot changed outside native sprite bounds')
