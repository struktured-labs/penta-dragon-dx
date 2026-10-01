import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from check_boss_menu_fades import endpoint_failures, inspect, white_return_cadence, return_map_readiness
from verify_pickup_class_palettes import serialized_state


def row(frame, bgp, color):
    return dict(frame=frame, bgp=bgp, colors=[color])


def test_both_endpoints_and_transitional_boundary_reported():
    result = endpoint_failures([row(1, 255, [1, 2, 3]), row(2, 255, [0, 0, 0]),
                                row(3, 0, [1, 2, 3]), row(4, 0, [255, 255, 255])])
    assert result['status'] == 'PASS'
    assert result['endpoint_boundary_frames'] == [1, 3]


def test_colored_black_endpoint_is_failure():
    result = endpoint_failures([row(1, 255, [0, 0, 0]), row(2, 255, [0, 255, 255]),
                                row(3, 0, [255, 255, 255]), row(4, 0, [255, 255, 255])])
    assert result['status'] == 'FAIL'
    assert result['failures'][0]['frame'] == 2


def test_missing_endpoints_fail():
    assert endpoint_failures([row(1, 228, [0, 0, 0])])['status'] == 'FAIL'


def test_retained_title_local_shalamar_three_returns():
    import csv
    import hashlib
    from check_boss_map_publication import check
    directory = ROOT/'tmp/title-local-shalamar-menus-01'
    rom = ROOT/'tmp/title-local-guard-trial-01/candidate.gb'
    if not (directory/'frame-1080.ss0').exists() or not rom.exists():
        pytest.skip('local title-guard Shalamar replay unavailable')
    assert hashlib.sha256(rom.read_bytes()).hexdigest() == (
        '8ff1c98d98f6949d39628c0c9fc86a53aae805f25cb8936484f2a00893af5c3c')
    result = inspect(directory, 1080, expected_scene=0x0C)
    assert result['status'] == 'PASS'
    assert result['extra_state_files'] == []
    for first, close, last in ((1,240,419), (420,540,719), (720,840,1080)):
        rows = [r for r in result['observations'] if first <= r['frame'] <= last]
        assert endpoint_failures(rows)['status'] == 'PASS'
        assert white_return_cadence(rows, close)['status'] == 'PASS'
        assert return_map_readiness(directory, last, close)['status'] == 'PASS'
        before = serialized_state(directory/f'frame-{close-120:04d}.ss0')
        for frame, menu in ((close-60,1), (close+80,0)):
            state = serialized_state(directory/f'frame-{frame:04d}.ss0')
            assert state[0x3E4] == menu
            assert state[0xD4:0x154] == before[0xD4:0x154]
    with (directory/'map-events.tsv').open() as stream:
        events = check(csv.DictReader(stream, delimiter='\t'))
    assert events['status'] == 'PASS_EVENT_MAP_SNAPSHOTS'
    assert events['publication_events'] == 8


def test_retained_crystal_second_return_exposes_five_frame_hold():
    directory = ROOT / 'tmp/crystal-menu-roundtrips-08'
    if not directory.exists():
        pytest.skip('local immutable Crystal capture unavailable')
    rows = [dict(frame=n, bgp=serialized_state(
        directory / f'frame-{n:04d}.ss0')[0x347]) for n in range(540, 720)]
    result = white_return_cadence(rows, 540)
    assert result['status'] == 'FAIL'
    assert result['failures'] == [dict(
        reason='intermediate hold must last four frames',
        run=dict(bgp=0x90, first=594, last=598, count=5))]


@pytest.mark.parametrize('boss', ['crystal', 'shalamar'])
def test_retained_selective_vblank_trial_three_returns(boss):
    directory = ROOT / f'tmp/{boss}-menu-roundtrips-10'
    control = ROOT / f'tmp/{boss}-menu-roundtrips-08'
    if not directory.exists() or not control.exists():
        pytest.skip('local immutable trial10 replay unavailable')
    result = inspect(directory, 1080)
    assert result['status'] == 'PASS'
    assert result['extra_state_files'] == []
    for first, close, last in [(1, 240, 419), (420, 540, 719), (720, 840, 1080)]:
        rows = [r for r in result['observations'] if first <= r['frame'] <= last]
        assert endpoint_failures(rows)['status'] == 'PASS'
        assert white_return_cadence(rows, close)['status'] == 'PASS'
        assert return_map_readiness(directory, last, close)['status'] == 'PASS'
        before = serialized_state(directory / f'frame-{close-120:04d}.ss0')
        for frame, menu in [(close-60, 1), (close+80, 0)]:
            state = serialized_state(directory / f'frame-{frame:04d}.ss0')
            # Native menu/renderer also changes IE (4 or7); entry and exit
            # frames cannot establish exact private-wrapper IE restoration.
            baseline = serialized_state(control / f'frame-{frame:04d}.ss0')
            assert state[0x3FF] == baseline[0x3FF], frame
            assert state[0x3E4] == menu, frame
            assert state[0x60FD] == before[0x60FD], frame
            assert state[0xD4:0x154] == before[0xD4:0x154], frame
    # Frame-sampled only: not an interrupt-cycle or audible-fidelity proof.
    for frame in range(1, 1081):
        state = serialized_state(directory / f'frame-{frame:04d}.ss0')
        assert state[0x3FF] & 4, frame


@pytest.mark.parametrize('first,close,last,menu_first', [
    (1, 240, 419, 180), (420, 540, 719, 480), (720, 840, 1080, 780)])
def test_retained_three_menu_roundtrips(first, close, last, menu_first):
    directory = ROOT / 'tmp/shalamar-menu-roundtrips-08'
    control = ROOT / 'tmp/shalamar-stock-button4-01/frame-0180.ss0'
    if not directory.exists() or not control.exists():
        pytest.skip('local immutable roundtrip/control capture unavailable')
    # Explicit adjacent input-defined windows cover the entire capture. Do not
    # feed three returns into the single-return cadence oracle or trim failures.
    result = inspect(directory, 1080)
    assert result['extra_state_files'] == []
    rows = [r for r in result['observations'] if first <= r['frame'] <= last]
    assert endpoint_failures(rows)['status'] == 'PASS'
    assert white_return_cadence(rows, close)['status'] == 'PASS'
    assert return_map_readiness(directory, last, close)['status'] == 'PASS'
    original = serialized_state(control)
    original_base = 0x2000 if original[0x340] & 8 else 0x1C00
    before = serialized_state(directory / f'frame-{close-120:04d}.ss0')
    for frame in range(menu_first, close):
        state = serialized_state(directory / f'frame-{frame:04d}.ss0')
        assert state[0x3E4] == 1, frame
        assert state[0x60FD] == 1, frame
        assert state[0x342:0x344] == bytes(2), frame
        assert state[0xD4:0x154] == before[0xD4:0x154], frame
        assert state[0x45A0:0x47E0] == original[0x45A0:0x47E0], frame
        base = 0x2000 if state[0x340] & 8 else 0x1C00
        # Visible BG only: roundtrip three has 431 off-screen map differences.
        # This deliberately does not assert whole-map/CHR/attribute equality.
        for y in range(18):
            assert state[base+y*32:base+y*32+20] == original[
                original_base+y*32:original_base+y*32+20], (frame, y)
    after = serialized_state(directory / f'frame-{close+80:04d}.ss0')
    assert after[0x3E4] == 0
    assert after[0x60FD] == 1
    assert after[0xD4:0x154] == before[0xD4:0x154]


@pytest.mark.parametrize('variant,expected', [('stock', 'PASS'), ('reported', 'FAIL')])
def test_retained_actual_replays(variant, expected):
    directory = ROOT / f'tmp/shalamar-{variant}-button4-01'
    if not directory.exists():
        pytest.skip('local immutable replay unavailable')
    result = inspect(directory, 600)
    assert result['status'] == expected
    if variant == 'reported':
        assert any(f['reason'] == 'missing settled endpoint' and f['bgp'] == 0
                   for f in result['failures'])


@pytest.mark.parametrize('trial', ['05', '08'])
def test_retained_atomic_handoff_has_both_endpoints_and_restores_live_deck(trial):
    directory = ROOT / f'tmp/shalamar-menu-fades-replay-{trial}'
    if not directory.exists():
        pytest.skip('local experimental replay unavailable')
    result = inspect(directory, 600)
    assert result['status'] == 'PASS'
    before = serialized_state(directory / 'frame-0120.ss0')
    for frame in (180, 239, 320, 600):
        after = serialized_state(directory / f'frame-{frame:04d}.ss0')
        assert after[0xD4:0x154] == before[0xD4:0x154], frame


@pytest.mark.parametrize('suffix,expected', [
    ('stock-button4-01', 'PASS'), ('reported-button4-01', 'FAIL'),
    ('menu-fades-replay-05', 'FAIL'), ('menu-fades-replay-06', 'PASS'),
    ('menu-fades-replay-08', 'PASS')])
def test_retained_white_return_cadence(suffix, expected):
    directory = ROOT / f'tmp/shalamar-{suffix}'
    if not directory.exists():
        pytest.skip('local immutable replay unavailable')
    observations = [dict(frame=n, bgp=serialized_state(
        directory / f'frame-{n:04d}.ss0')[0x347]) for n in range(240, 601)]
    assert white_return_cadence(observations)['status'] == expected


def test_missing_or_slow_white_return_fails():
    observations = []
    for bgp in (0xE4, 0x90, 0x40, 0, 0x40, 0x90, 0xE4):
        for _ in range(4):
            observations.append(dict(frame=240+len(observations), bgp=bgp))
    assert white_return_cadence(observations)['status'] == 'PASS'
    assert white_return_cadence(observations[:8])['status'] == 'FAIL'
    observations.insert(5, dict(frame=245, bgp=0x90))
    assert white_return_cadence(observations)['status'] == 'FAIL'


@pytest.mark.parametrize('suffix,expected', [
    ('stock-button4-01', 'PASS'), ('menu-fades-replay-06', 'FAIL'),
    ('menu-fades-replay-07', 'PASS'), ('menu-fades-replay-08', 'PASS')])
def test_native_map_is_published_before_reveal(suffix, expected):
    directory = ROOT / f'tmp/shalamar-{suffix}'
    if not directory.exists():
        pytest.skip('local immutable replay unavailable')
    result = return_map_readiness(directory)
    assert result['status'] == expected
    if suffix == 'menu-fades-replay-06':
        assert result['failures'][0]['mismatch_count'] == 556


@pytest.mark.parametrize('trial,expected_differences', [('07', 156), ('08', 0)])
def test_menu_construction_preserves_stock_tiles(trial, expected_differences):
    original = ROOT / 'tmp/shalamar-stock-button4-01'
    candidate = ROOT / f'tmp/shalamar-menu-fades-replay-{trial}'
    if not original.exists() or not candidate.exists():
        pytest.skip('local immutable replays unavailable')
    # Same menu/inventory fixture, every frame of its settled pre-close dwell.
    # Compare layout, not RGB: the intended CGB palette differs from DMG.
    for frame in range(180, 240):
        stock = serialized_state(original / f'frame-{frame:04d}.ss0')
        state = serialized_state(candidate / f'frame-{frame:04d}.ss0')
        for start, end in ((0x45A0, 0x47E0), (0x2000, 0x2400)):
            assert sum(a != b for a, b in zip(stock[start:end], state[start:end])) == expected_differences
