"""#39 scene-owned editing: equal colors are not palette identity."""
import importlib.util
from pathlib import Path
import struct
import hashlib
import json

import pytest
from palette_test_fixtures import current_states, rom_fixture_path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('stage1_bridge', ROOT/'scripts/mister_palette_bridge.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    rom = rom_fixture_path().read_bytes()
    state = bytearray(181040)
    struct.pack_into('<I', state, 4, 0xB0CA)
    state[520+0x1880] = 2
    state[49832+0x37] = 2
    state[49832+0x41] = 1
    positions = list(range(96, 152, 8)) + list(range(160, 224, 8))
    for pos, offset in zip(positions, m.OFFSETS):
        state[pos:pos+8] = rom[offset:offset+8]
    return rom, bytes(state), positions


@pytest.mark.parametrize('index', range(15))
def test_equal_primary_rows_remain_independently_editable(index):
    rom, state, positions = fixture()
    assert m.stage1_owned_positions(rom, state) == positions
    peer = (index+1) % 7 if index < 7 else 7+(index-6) % 8
    colors = m.decode(rom[m.OFFSETS[peer]:m.OFFSETS[peer]+8])
    if index >= 7:
        assert colors[0] == m.decode(rom[m.OFFSETS[index]:m.OFFSETS[index]+8])[0]
    first, state1, matches = m.patch(rom, state, index, colors)
    assert matches == [positions[index]]
    colors[1] = '#123456'
    second, state2, matches = m.patch(first, state1, index, colors)
    assert matches == [positions[index]]
    assert state2[positions[peer]:positions[peer]+8] == state[positions[peer]:positions[peer]+8]
    assert second[m.OFFSETS[peer]:m.OFFSETS[peer]+8] == rom[m.OFFSETS[peer]:m.OFFSETS[peer]+8]
    assert all(a == b or positions[index] <= i < positions[index]+8
               for i, (a, b) in enumerate(zip(state1, state2)))


def test_equal_private_bg7_is_not_recolored():
    rom, state, _ = fixture()
    state = bytearray(state)
    state[152:160] = state[136:144]  # private teeth row happens to equal BG5
    _, after, matches = m.patch(rom, bytes(state), 5, ['#123456']*4)
    assert matches == [136]
    assert after[152:160] == state[152:160]


def test_old_content_matching_changes_unrelated_private_row(monkeypatch):
    rom, state, _ = fixture()
    state = bytearray(state)
    state[152:160] = state[136:144]
    monkeypatch.setattr(m, 'stage1_owned_positions', lambda *_: None)
    _, after, matches = m.patch(rom, bytes(state), 5, ['#123456']*4)
    assert matches == [136, 152]
    assert after[152:160] != state[152:160]  # retained wrong-owner control


def test_real_emulator_stage1_memory_has_expected_complete_layout():
    # Translation is an offline parser/ownership check, NOT a runnable MiSTer
    # checkpoint or proof of hardware restore. CPU/register formats differ.
    rom, _, positions = fixture()
    if m.sha(rom)!=m.LATE_RETURN_PIN:
        for raw in current_states(rom,1):
            assert_emulator_stage1_memory(rom,raw,positions)
        return
    receipt = json.loads((ROOT/'tmp/final-fade-late-window-exit-01/receipt.json').read_text())
    assert receipt['rom_sha256'] == m.sha(rom)
    stream = Path(receipt['native_capture_directory'])/'native.states'
    with stream.open('rb') as f:
        assert hashlib.file_digest(f, 'sha256').hexdigest() == receipt['native_capture']['hashes']['native.states']
        for frame in (4800, 5000, 6000):
            f.seek((frame-1)*71680)
            raw = f.read(71680)
            assert_emulator_stage1_memory(rom,raw,positions)


def assert_emulator_stage1_memory(rom,raw,positions):
    state = bytearray(181040)
    struct.pack_into('<I', state, 4, 0xB0CA)
    state[520:520+32768] = raw[0x4400:0xC400]
    state[49832:49960] = raw[0x380:0x400]
    state[96:224] = raw[0xD4:0x154]
    assert m.stage1_owned_positions(rom, state) == positions
    alias, resumed, _ = m.patch(rom, state, 0, m.decode(rom[m.OFFSETS[1]:m.OFFSETS[1]+8]))
    _, restored, matches = m.patch(alias, resumed, 0, ['#123456']*4)
    assert matches == [96]
    assert restored[104:112] == state[104:112]


@pytest.mark.parametrize('offset,value', [
    (520+0x1880, 0x0B), (520+0x1F4C, 1), (49832+0x37, 0x0C),
    (49832+0x3A, 1), (49832+0x41, 0), (49832+0x3F, 1),
    (49832+0x50, 1), (49832+0x64, 1), (49832+0x40, 1), (96, 0),
])
def test_ambiguous_override_or_transition_still_rejected(offset, value):
    rom, state, _ = fixture()
    colors = m.decode(rom[m.OFFSETS[1]:m.OFFSETS[1]+8])
    rom, state, _ = m.patch(rom, state, 0, colors)
    state = bytearray(state)
    state[offset] = value if state[offset] != value else value ^ 1
    assert m.stage1_owned_positions(rom, state) is None
    with pytest.raises(ValueError, match='Ambiguous'):
        m.patch(rom, bytes(state), 0, ['#123456']*4)


def test_any_nonpalette_rom_change_invalidates_layout():
    rom, state, _ = fixture()
    assert m.stage1_layout_supported(rom)
    for offset in (0x100, 0x147, 0x36838, 0x36880, 0xFFFFF):
        changed = bytearray(rom)
        changed[offset] ^= 1
        assert not m.stage1_layout_supported(changed)
        assert m.stage1_owned_positions(changed, state) is None
