"""#70 fixture identity/coverage mutations fail without any emulator launch."""
import copy
from pathlib import Path
from unittest.mock import patch
import zlib

import pytest
import palette_test_fixtures as fixtures


def evidence():
    rom=bytes(512)
    raw=bytearray(71680)
    raw[4:8]=zlib.crc32(rom).to_bytes(4,'little')
    raw[0x5C80]=3;raw[0x3BA]=1
    encoded=b'explicit-unit-state'
    manifest={'rom_sha256':fixtures.sha(rom),'stages':{'2':[
        {'path':'unused-unit-state','sha256':fixtures.sha(encoded)}]}}
    return rom,raw,encoded,manifest


def validate(rom,raw,encoded,manifest):
    import normalize_mgba_state_pc
    with patch.object(Path,'read_bytes',return_value=encoded), patch.object(
            normalize_mgba_state_pc,'png_chunks',return_value=[(b'gbAs',zlib.compress(raw))]):
        return fixtures.validated_states(manifest,rom,2)


def test_explicit_valid_state():
    rom,raw,encoded,manifest=evidence()
    assert validate(rom,raw,encoded,manifest)==[raw]


@pytest.mark.parametrize('offset',[4,16,0x5C80,0x3BA])
def test_wrong_rom_or_dungeon_identity(offset):
    rom,raw,encoded,manifest=evidence();raw[offset]^=1
    with pytest.raises(ValueError):validate(rom,raw,encoded,manifest)


def test_missing_duplicate_changed_fixture_rejected():
    rom,raw,encoded,manifest=evidence()
    for change in ('missing','duplicate','hash','rom'):
        m=copy.deepcopy(manifest)
        if change=='missing':m['stages']['2']=[]
        elif change=='duplicate':m['stages']['2']*=2
        elif change=='hash':m['stages']['2'][0]['sha256']='wrong'
        else:m['rom_sha256']='wrong'
        with pytest.raises(ValueError):validate(rom,raw,encoded,m)


def test_missing_manifest_does_not_launch_emulator(monkeypatch):
    monkeypatch.delenv('PENTA_TEST_PALETTE_STATES',raising=False)
    with pytest.raises(ValueError,match='no emulator'):
        fixtures.current_states(bytes(512),2)


def test_complete_unique_gate_inventory():
    fixtures.validate_gate_inventory(dict(
        selected_gates=['a','b'],
        results=[dict(name='b',status='passed'),dict(name='a',status='passed')]))


@pytest.mark.parametrize('change', ['empty','missing','extra','duplicate_result',
                                   'duplicate_selection','failed','running'])
def test_invalid_gate_inventory(change):
    matrix=dict(selected_gates=['a','b'],
                results=[dict(name='a',status='passed'),dict(name='b',status='passed')])
    if change=='empty':matrix=dict(selected_gates=[],results=[])
    elif change=='missing':matrix['results'].pop()
    elif change=='extra':matrix['results'].append(dict(name='c',status='passed'))
    elif change=='duplicate_result':matrix['results'].append(dict(name='a',status='passed'))
    elif change=='duplicate_selection':matrix['selected_gates'].append('a')
    else:matrix['results'][0]['status']=change
    with pytest.raises(ValueError,match='inventory'):
        fixtures.validate_gate_inventory(matrix)
