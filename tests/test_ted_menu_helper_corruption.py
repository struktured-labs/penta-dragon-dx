"""#36: retain the failed Ted menu replay without calling aggregate PASS success."""
import csv
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from verify_pickup_class_palettes import serialized_state
from check_boss_menu_fades import inspect, endpoint_failures


def test_retained_menu_overwrites_executable_helper_but_not_ready_marker():
    folder = ROOT/'tmp/title-local-ted-escaped-menus-01'
    if not (folder/'frame-1080.ss0').exists():
        pytest.skip('local failed Ted replay unavailable')
    before = serialized_state(folder/'frame-0001.ss0')
    after = serialized_state(folder/'frame-0320.ss0')
    assert before[0x4908] == 0x20
    assert after[0x4908] == 0xFE
    assert before[0x49FF] == after[0x49FF] == 0xC9
    assert before[0x60BB] == after[0x60BB] == 0xF0
    result = inspect(folder, 1080, expected_scene=0x10)
    # Aggregate endpoints are insufficient: only round one ran.
    assert result['status'] == 'PASS'
    for first, last in ((420,719),(720,1080)):
        rows = [r for r in result['observations'] if first <= r['frame'] <= last]
        assert endpoint_failures(rows)['status'] == 'FAIL'


def test_retained_writer_is_native_menu_metatile_copy():
    trace = ROOT/'tmp/title-local-ted-helper-writes-01/helper-writes.tsv'
    if not trace.exists():
        pytest.skip('local write trace unavailable')
    with trace.open() as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    first = next(r for r in rows if r['address'] == 'C508')
    assert (first['frame'], first['old'], first['new'], first['pc']) == ('170','20','FE','1FAB')
