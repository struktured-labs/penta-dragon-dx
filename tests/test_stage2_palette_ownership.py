"""#39 Stage2 scenery and pickup copies have one semantic BG4 owner."""
import hashlib
import json
import struct
import sys
import zlib

import pytest

from test_stage1_palette_ownership import ROOT, fixture, m
from palette_test_fixtures import current_states


def stage2_fixture():
    rom, state, _ = fixture()
    state = bytearray(state)
    state[520+0x1880] = state[49832+0x37] = 3
    state[49832+0x3A] = 1
    state[96:104] = state[128:136]
    assert rom[0x37BAC] == 0x20  # actual Stage2 BG0 source table, $6820
    return rom, bytes(state)


def test_sequential_stage2_alias_edits_change_both_bg4_copies_only():
    rom, state = stage2_fixture()
    owners = m.dungeon_owned_positions(rom, state)
    assert owners[0] == [] and owners[4] == [96, 128]
    colors = m.decode(rom[m.OFFSETS[1]:m.OFFSETS[1]+8])
    first, resumed, matches = m.patch(rom, state, 4, colors)
    assert matches == [96, 128]
    second, after, matches = m.patch(first, resumed, 4, ['#123456']*4)
    assert matches == [96, 128]
    assert after[96:104] == after[128:136] == m.encode(['#123456']*4)
    assert after[104:112] == state[104:112]
    assert all(a == b or i in {*range(96, 104), *range(128, 136)}
               for i, (a, b) in enumerate(zip(resumed, after)))
    assert second[m.OFFSETS[1]:m.OFFSETS[1]+8] == rom[m.OFFSETS[1]:m.OFFSETS[1]+8]


def test_inactive_dungeon_row_cannot_steal_equal_bg4_slots():
    rom, state = stage2_fixture()
    rom = bytearray(rom)
    rom[m.OFFSETS[0]:m.OFFSETS[0]+8] = rom[m.OFFSETS[4]:m.OFFSETS[4]+8]
    with pytest.raises(ValueError, match='not active'):
        m.patch(bytes(rom), state, 0, ['#123456']*4)


@pytest.mark.parametrize('offset', [520+0x1880, 520+0x1F4C, 49832+0x37,
                                   49832+0x3A, 49832+0x41, 49832+0x3F,
                                   49832+0x50, 49832+0x64, 49832+0x40, 96])
def test_stage2_unknown_context_rejects_ambiguous_edit(offset):
    rom, state = stage2_fixture()
    rom, state, _ = m.patch(rom, state, 4, m.decode(rom[m.OFFSETS[1]:m.OFFSETS[1]+8]))
    state = bytearray(state)
    state[offset] ^= 1
    assert m.dungeon_owned_positions(rom, state) is None
    with pytest.raises(ValueError, match='Ambiguous'):
        m.patch(rom, bytes(state), 4, ['#123456']*4)


def test_retained_exact_rom_stage2_state_confirms_mapping():
    # Copy memory into a synthetic MiSTer container for offline mapping tests,
    # not a compatible CPU checkpoint and never something to deploy.
    sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
    from normalize_mgba_state_pc import png_chunks
    rom, _ = stage2_fixture()
    if m.sha(rom)!=m.LATE_RETURN_PIN:
        for raw in current_states(rom,2):
            assert_emulator_stage2_memory(rom,raw)
        return
    folder = ROOT/'tmp/late-return-stage2-continue-a-01'
    receipt = json.loads((folder/'receipt.json').read_text())
    encoded = (folder/'entry.ss0').read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == receipt['source_state_sha256']
    assert receipt['rom_sha256'] == m.sha(rom)
    raw = zlib.decompress(dict(png_chunks(encoded))[b'gbAs'])
    assert len(raw) == 71680
    assert int.from_bytes(raw[4:8], 'little') == zlib.crc32(rom)
    assert_emulator_stage2_memory(rom,raw)


def assert_emulator_stage2_memory(rom,raw):
    state = bytearray(181040)
    struct.pack_into('<I', state, 4, 0xB0CA)
    state[520:520+32768] = raw[0x4400:0xC400]
    state[49832:49960] = raw[0x380:0x400]
    state[96:224] = raw[0xD4:0x154]
    assert m.dungeon_owned_positions(rom, state)[4] == [96, 128]
