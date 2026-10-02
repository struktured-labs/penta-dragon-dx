import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
from check_boss_map_publication import check


def rows():
    return [dict(kind='bgp', value=f'{v:02X}', source='00'*576, map='00'*576,
                 frame=str(i), cycle=str(i*100))
            for i,v in enumerate([0xE4,0x90,0x40,0,0,0x40,0x90,0xE4])]


def test_complete_publications_pass():
    assert not check(rows())['errors']


@pytest.mark.parametrize('index', range(8))
def test_corruption_at_every_publication_rejected(index):
    events = rows()
    events[index]['map'] = '01'+'00'*575
    assert check(events)['status'] == 'FAIL'


def test_missing_event_and_short_snapshot_rejected():
    assert check(rows()[:-1])['status'] == 'FAIL'
    events = rows()
    events[-1]['source'] = ''
    assert check(events)['status'] == 'FAIL'
