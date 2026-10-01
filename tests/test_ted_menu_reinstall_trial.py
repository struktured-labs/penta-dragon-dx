"""#36 experimental patch bounds and native ready-marker preservation."""
import hashlib
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import build_ted_menu_reinstall_trial as builder


def parent():
    path = ROOT/'tmp/title-local-guard-trial-01/candidate.gb'
    if not path.exists(): pytest.skip('local parent unavailable')
    return path.read_bytes()


def test_exact_parent_and_change_bounds():
    original = parent()
    result = builder.build(original)
    allowed = {0x14E,0x14F}
    for bank, address, count in ((16,0x5CDA,11),(20,0x5CDC,6),(20,0x6C40,17)):
        start=builder.offset(bank,address)
        allowed.update(range(start,start+count))
    assert len(result) == len(original)
    assert all(a == b or i in allowed for i,(a,b) in enumerate(zip(original,result)))
    assert result[builder.offset(16,0x5CDF):builder.offset(16,0x5CE5)] == bytes.fromhex('CAF5C4C34059')
    assert result[builder.offset(20,0x6C40):builder.offset(20,0x6C51)] == bytes.fromhex('FAFFC5FEC92005FA08C5FE203E10C3DC5C')


def test_wrong_parent_rejected():
    with pytest.raises(ValueError,match='exact'):
        builder.build(b'wrong')


def test_retained_two_cycle_hazard_restart_and_parent_images():
    from verify_gameover_restart import validate, validate_stage_cards
    from gameover_sequence import validate_sequence
    folder=ROOT/'tmp/ted-menu-reinstall-hazard-restart-01'
    control=ROOT/'tmp/title-local-guard-hazard-restart-01'
    if not (folder/'receipt.json').exists() or not control.exists():
        pytest.skip('local restart evidence unavailable')
    validate(folder)
    validate_stage_cards(folder,saved_game=True)
    assert validate_sequence(folder)=={'title_frame_pairs':482,'gameover_frames':102}
    images=list(control.glob('*.png'))
    assert images
    for image in images:
        assert image.read_bytes()==(folder/image.name).read_bytes(),image.name


def test_retained_sara_firing_raster():
    from verify_sara_pose import inspect
    folder=ROOT/'tmp/ted-menu-reinstall-sara-fire-01'
    rom=ROOT/'tmp/ted-menu-reinstall-trial-01/candidate.gb'
    if not (folder/'receipt.json').exists() or not rom.exists():
        pytest.skip('local Sara replay unavailable')
    assert hashlib.sha256(rom.read_bytes()).hexdigest()=='4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903'
    result=inspect(folder,2400,rom.read_bytes())
    assert result['status']=='pass'
    assert result['opaque_pixels_checked']==437639
    assert result['categories']=={'no_visible_sara':4,'witch_walking':2396}


def test_retained_three_menus_restore_helper_and_remain_responsive():
    from check_boss_menu_fades import inspect, endpoint_failures, white_return_cadence, return_map_readiness
    from verify_pickup_class_palettes import serialized_state
    folder=ROOT/'tmp/ted-menu-reinstall-roundtrips-01'
    if not (folder/'frame-1080.ss0').exists(): pytest.skip('local trial replay unavailable')
    result=inspect(folder,1080,expected_scene=0x10)
    assert result['status']=='PASS'
    for first,close,last in ((1,240,419),(420,540,719),(720,840,1080)):
        rows=[r for r in result['observations'] if first<=r['frame']<=last]
        assert endpoint_failures(rows)['status']=='PASS'
        assert white_return_cadence(rows,close)['status']=='PASS'
        assert return_map_readiness(folder,last,close)['status']=='PASS'
        state=serialized_state(folder/f'frame-{close+80:04d}.ss0')
        assert state[0x4908:0x490C] == bytes.fromhex('201CE51E')
        assert state[0x3E4] == 0
        assert state[0x60BB] == 0xF0


def test_occupied_cave_rejected_even_with_updated_identity():
    data=bytearray(parent());data[builder.offset(20,0x6C40)]=0
    with patch.object(builder,'PARENT',hashlib.sha256(data).hexdigest()):
        with pytest.raises(ValueError,match='occupied'):
            builder.build(bytes(data))
