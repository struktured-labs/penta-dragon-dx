"""Issue36: the first successful menu must not conceal two later freezes."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from check_boss_menu_fades import inspect_roundtrips


@pytest.mark.parametrize('name,status,cycles', [
    ('title-local-ted-escaped-menus-01', 'FAIL', ['PASS', 'FAIL', 'FAIL']),
    ('ted-menu-reinstall-roundtrips-01', 'PASS', ['PASS', 'PASS', 'PASS']),
])
def test_retained_ted_cycles(name, status, cycles):
    folder = ROOT/'tmp'/name
    if not (folder/'frame-1080.ss0').exists():
        pytest.skip('retained local replay unavailable')
    result = inspect_roundtrips(folder, 0x10)
    assert result['status'] == status
    assert [c['status'] for c in result['cycles']] == cycles


@pytest.mark.parametrize('frame', [699, 801])
def test_invalid_schedule_fails_before_reading_files(frame):
    with pytest.raises(ValueError):
        inspect_roundtrips(Path('nonexistent'), 0x10, frame)


def test_aggregate_pass_cannot_override_failed_cycle(monkeypatch):
    import check_boss_menu_fades as checker
    monkeypatch.setattr(checker, 'inspect', lambda *args: dict(
        status='PASS', failures=[], observations=[dict(frame=n) for n in range(1,1081)]))
    monkeypatch.setattr(checker, 'endpoint_failures', lambda rows: dict(
        status='PASS' if rows[0]['frame'] == 1 else 'FAIL'))
    monkeypatch.setattr(checker, 'white_return_cadence', lambda *args: dict(status='PASS'))
    monkeypatch.setattr(checker, 'return_map_readiness', lambda *args: dict(status='PASS'))
    result = checker.inspect_roundtrips(Path('unused'), 0x10, 730)
    assert result['status'] == 'FAIL'
    assert [c['first'] for c in result['cycles']] == [1,420,730]
    assert [c['last'] for c in result['cycles']] == [419,729,1080]
    assert [f['cycle'] for f in result['failures']] == [2,3]


@pytest.mark.parametrize('boss,scene,status', [
    ('shalamar',0x0C,'PASS'), ('riff',0x0D,'PASS'),
    ('crystal',0x0E,'PASS'), ('cameo',0x0F,'FAIL'),
    ('cameo-escaped',0x0F,'PASS'), ('troop',0x11,'PASS'),
    ('faze',0x12,'FAIL'), ('faze-escaped',0x12,'FAIL'),
    ('faze-right',0x12,'PASS'),
    ('angela',0x13,'PASS'), ('penta',0x14,'PASS'),
])
def test_latest_boss_menu_expansion_preserves_failed_routes(boss,scene,status):
    import hashlib
    import json
    import zlib
    from verify_pickup_class_palettes import serialized_state
    folder=ROOT/'tmp'/f'ted-fix-{boss}-menus-01'
    if not (folder/'completion.json').exists():
        pytest.skip('local expanded boss replay unavailable')
    launch=json.loads((folder/'launch.json').read_text())
    rom=Path(launch['rom']['path']).read_bytes()
    assert hashlib.sha256(rom).hexdigest() == launch['rom']['sha256'] == (
        '4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903')
    result=inspect_roundtrips(folder,scene)
    assert result['status'] == status
    for frame in range(1,1081):
        raw=serialized_state(folder/f'frame-{frame:04d}.ss0')
        assert int.from_bytes(raw[4:8],'little') == zlib.crc32(rom)
        assert raw[16:32] == rom[0x134:0x144]
    if status == 'FAIL':
        assert result['scene_route_failures']  # Not reclassified as a menu-only pass.
    else:
        assert [c['status'] for c in result['cycles']] == ['PASS']*3
