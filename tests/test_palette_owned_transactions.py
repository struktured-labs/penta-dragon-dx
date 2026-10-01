"""#39 run real checkpoint/apply/load/undo methods against a fake device."""
import json
from pathlib import Path
import shlex
import struct
import tempfile

import pytest

from test_stage1_palette_ownership import ROOT, fixture, m


def test_failure_receipt_storage_error_preserves_original_error_and_undo(monkeypatch):
    """#48 disk failure during error reporting must not hide the load failure."""
    rom, state, _ = fixture()
    with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as work:
        monkeypatch.setattr(m, 'WORK', Path(work))
        monkeypatch.setattr(m.subprocess, 'run', lambda *a, **kw: pytest.fail('real device access'))
        bridge = m.Bridge(ROOT/'tmp/stream-late-return-source-01/candidate.gb')
        original_stem = bridge.stem
        remote = {}
        monkeypatch.setattr(bridge, 'checkpoint', lambda _: state)
        monkeypatch.setattr(bridge, 'copy', lambda source, target:
                            remote.__setitem__(str(target).split(':', 1)[1], Path(source).read_bytes()))
        monkeypatch.setattr(bridge, 'ssh', lambda command:
                            m.sha(remote[shlex.split(command)[1]]).encode())
        original_error = ValueError('Injected original load error')
        def fail_load(_):
            raise original_error
        monkeypatch.setattr(bridge, 'load', fail_load)
        write_text = Path.write_text
        def fail_terminal_receipt(path, data, *args, **kwargs):
            if path.name == 'receipt.json' and json.loads(data)['status'].startswith('restore failed'):
                raise OSError('Injected disk full')
            return write_text(path, data, *args, **kwargs)
        monkeypatch.setattr(Path, 'write_text', fail_terminal_receipt)
        with pytest.raises(ValueError) as caught:
            bridge.apply(0, ['#123456']*4)
        assert caught.value is original_error
        assert any('Injected disk full' in note for note in caught.value.__notes__)
        assert bridge.history == [(original_stem, rom)]
        # Failed persistence cannot be advertised as a saved failure receipt.
        receipt = json.loads(next(Path(work).glob('edit-*/receipt.json')).read_text())
        assert receipt['status'] == 'uploaded; restore not yet confirmed'
        loads = []
        monkeypatch.setattr(bridge, 'load', loads.append)
        bridge.undo()
        assert loads == [original_stem]
        assert (bridge.stem, bridge.rom, bridge.history) == (original_stem, rom, [])


@pytest.mark.parametrize('second_failure', [None, 'boss', 'launcher', 'load', 'checkpoint', 'readback'])
@pytest.mark.parametrize('stage', [1, 2])
def test_sequential_alias_apply_resume_and_undo(monkeypatch, second_failure, stage):
    if stage == 1:
        rom, initial_state, _ = fixture()
    else:
        from test_stage2_palette_ownership import stage2_fixture
        rom, initial_state = stage2_fixture()
    index = 0 if stage == 1 else 4
    with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as work:
        monkeypatch.setattr(m, 'WORK', Path(work))
        monkeypatch.setattr(m.time, 'sleep', lambda _: None)
        monkeypatch.setattr(m.subprocess, 'run', lambda *a, **kw: pytest.fail('real process/device access'))
        bridge = m.Bridge(ROOT/'tmp/stream-late-return-source-01/candidate.gb')
        initial_stem = bridge.stem
        remote = {'/media/fat/games/GBC/'+initial_stem+'.gbc': rom}
        live = bytearray(initial_state)
        loads, saves, count = [], [], 0
        failing = False
        pending = None

        def copy(source, target):
            source, target = str(source), str(target)
            if source.startswith('rivalmage:'):
                Path(target).write_bytes(remote[source.split(':', 1)[1]])
            else:
                assert target.startswith('rivalmage:')
                data = Path(source).read_bytes()
                if failing and second_failure == 'launcher' and target.endswith('.mgl'):
                    data = b'truncated'
                remote[target.split(':', 1)[1]] = data

        def ssh(command):
            nonlocal live, pending, count
            words = shlex.split(command)
            if command == 'hostname':
                return b'rivalmage\n'
            if command == 'cat /tmp/CORENAME':
                return b'GBC\n'
            if words[:1] == ['sha256sum']:
                return (m.sha(remote[words[1]])+'  '+words[1]+'\n').encode()
            if words[:2] == ['test', '-f']:
                return b'yes\n' if words[2] in remote else b''
            if words[:1] == ['cat']:
                return remote[words[1]]
            if words[:1] == ['printf']:
                pending = Path(words[2].split(' ', 1)[1]).stem
                assert pending == initial_stem or '/media/fat/'+pending+'.mgl' in remote
                loads.append(pending)
                if failing and second_failure == 'load':
                    raise ValueError('Injected load failure')
                return b''
            if words[-3:] == ['combo', 'leftalt', 'f4']:
                if failing and second_failure == 'checkpoint' and len(loads) == 2:
                    raise ValueError('Injected checkpoint failure')
                count += 1
                struct.pack_into('<I', live, 0, count)
                remote[bridge.state_path()] = bytes(live)
                saves.append(bridge.stem)
                return b''
            if words[-2:] == ['combo', 'f4']:
                assert pending is not None
                live = bytearray(remote[bridge.state_path(pending)])
                if failing and second_failure == 'readback' and pending != first_stem:
                    live[96] ^= 1
                return b''
            pytest.fail('unexpected command: '+command)

        monkeypatch.setattr(bridge, 'ssh', ssh)
        monkeypatch.setattr(bridge, 'copy', copy)
        peer = initial_state[104:112]
        bridge.apply(index, m.decode(peer))
        first_stem, first_rom = bridge.stem, bridge.rom
        assert live[96:104] == live[104:112] == peer
        assert len(loads) == 1 and len(saves) == 2
        failing = True
        if second_failure == 'boss':
            live[520+0x1880] = 0x0C
        if second_failure:
            with pytest.raises(ValueError, match={
                'boss': 'Ambiguous', 'launcher': 'Upload hash mismatch',
                'load': 'Injected load failure', 'checkpoint': 'Injected checkpoint failure',
                'readback': 'Restored palette'}[second_failure]):
                bridge.apply(index, ['#123456']*4)
        else:
            bridge.apply(index, ['#123456']*4)
            assert live[96:104] == m.encode(['#123456']*4)
            if stage == 2:
                assert live[128:136] == live[96:104]
            assert live[104:112] == peer
        if second_failure in ('boss', 'launcher'):
            assert loads == [first_stem]
            assert (bridge.stem, bridge.rom, bridge.history) == (
                first_stem, first_rom, [(initial_stem, rom)])
        else:
            assert len(loads) == 2
            assert len(bridge.history) == 2
            failing = False
            bridge.undo()
            assert (bridge.stem, bridge.rom) == (first_stem, first_rom)
            assert live[96:104] == live[104:112] == peer
        failing = False
        bridge.undo()
        assert (bridge.stem, bridge.rom, bridge.history) == (initial_stem, rom, [])
        assert live[96:224] == initial_state[96:224]
        receipts = [json.loads(p.read_text()) for p in Path(work).glob('edit-*/receipt.json')]
        assert receipts
        assert all(r['palette_ownership'] == f'settled-stage{stage}-fixed-slots' for r in receipts)
        if second_failure in ('load', 'checkpoint', 'readback'):
            failed = [r for r in receipts if r['status'] == 'restore failed; Undo available']
            assert len(failed) == 1
            assert failed[0]['failure_phase'] == {
                'load': 'load', 'checkpoint': 'confirmation-checkpoint',
                'readback': 'palette-readback'}[second_failure]
            assert failed[0]['error_type'] == 'ValueError'
            assert failed[0]['error']
        else:
            assert all(r['status'].startswith('palette readback passed') for r in receipts)
