import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from check_boss_menu_fades import scene_route_failures
from verify_pickup_class_palettes import serialized_state


def test_unchanged_arena_is_accepted():
    assert scene_route_failures([dict(frame=1,scene=0x10)],0x10)==[]


@pytest.mark.parametrize('scene',[0x0B,0x17,0x01,None])
def test_exit_or_missing_scene_is_not_a_boss_menu(scene):
    rows=[dict(frame=1,scene=0x10),dict(frame=57,scene=scene)]
    result=scene_route_failures(rows,0x10)
    assert len(result)==1 and result[0]['frame']==57


def test_no_observations_is_not_a_pass():
    assert scene_route_failures([],0x10)


@pytest.mark.parametrize('directory,exit_frame',[
    ('select-buffer-ted-menus-02',57),('source07-ted-menu-control-01',57),
    ('stock-ted-menu-control-01',55)])
def test_retained_ted_route_exits_before_first_select(directory,exit_frame):
    path=ROOT/'tmp'/directory
    if not path.exists():pytest.skip('local replay unavailable')
    rows=[dict(frame=f,scene=serialized_state(path/f'frame-{f:04d}.ss0')[0x5C80])
          for f in range(1,120)]
    failures=scene_route_failures(rows,0x10)
    assert failures and failures[0]['frame']==exit_frame
