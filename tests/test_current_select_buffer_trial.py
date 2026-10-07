"""#34 construction guards; emulator qualification is separate."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_current_select_buffer_trial as current
import build_select_buffer_trial as legacy


def fixture():
    parent = bytearray(b'\xff'*0x100000)
    for offset, code in ((0xA8, legacy.EDGE), (0x36F60, legacy.SAMPLE),
                         (0x09BE, bytes.fromhex('E099 EA0021 C9')),
                         (0x847, bytes.fromhex('CD6100 CD806C C36100'))):
        parent[offset:offset+len(code)] = code
    return bytes(parent)


@pytest.mark.parametrize('base,sample', [(0x6C80, True), (0x6D80, False)])
def test_only_terminal_classifier_changes(base, sample):
    before = legacy.payload(base, sample)
    after = current.payload(base, sample)
    assert after == before[:-len(current.OLD_CONTEXT)] + current.CONTEXT
    assert len(after) < 256


def test_unpinned_rom_rejected():
    with pytest.raises(ValueError, match='exact current parent'):
        current.build(fixture())


@pytest.mark.parametrize('offset', [0xA8, 0x36F60, 0x09BE, 0x847, 37*16384])
def test_hook_and_reservation_guards_survive_repin(offset):
    data = bytearray(fixture())
    data[offset] ^= 1
    with patch.object(current, 'PARENT', legacy.digest(data)):
        with pytest.raises(ValueError):
            current.build(data)


def test_bounded_diff_and_checksum_without_mutating_legacy():
    parent = fixture()
    historical_pin = legacy.PARENT
    with patch.object(current, 'PARENT', legacy.digest(parent)):
        result = current.build(parent)
    assert legacy.PARENT == historical_pin
    allowed = {0x14E, 0x14F} | set(range(0xA8, 0xA8+len(legacy.EDGE)))
    allowed |= set(range(0x36F60, 0x36F68))
    for base, sample in ((0x6C80, True), (0x6D80, False)):
        offset = legacy.BANK*16384 + base-0x4000
        allowed |= set(range(offset, offset+len(current.payload(base, sample))))
    offset = legacy.BANK*16384 + 0x6F65-0x4000
    allowed |= set(range(offset, offset+6))
    assert len(result) == len(parent)
    assert {i for i, (a, b) in enumerate(zip(parent, result)) if a != b} <= allowed
    assert int.from_bytes(result[0x14E:0x150], 'big') == (sum(result[:0x14E])+sum(result[0x150:]))&65535
