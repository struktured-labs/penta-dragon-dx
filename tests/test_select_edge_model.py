"""Design checks for #34; passing these does NOT qualify an unpatched ROM."""
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from select_edge_model import SelectEdgeModel


def test_short_press_survives_release_without_sticky_raw():
    model = SelectEdgeModel()
    model.sample(4)
    model.sample(0)
    assert model.raw == 0
    assert model.consume(0) == 4
    assert model.consume(0) == 0


def test_held_press_does_not_repeat_but_repress_does():
    model = SelectEdgeModel()
    model.sample(4)
    assert model.consume(4) == 4
    for _ in range(20):
        model.sample(4)
        assert model.consume(0) == 0
    model.sample(0)
    model.sample(4)
    assert model.consume(0) == 4


def test_masked_press_is_consumed_not_delayed_until_unmask():
    model = SelectEdgeModel()
    model.sample(4)
    assert model.consume(0, 251) == 0
    assert model.consume(0, 255) == 0


def test_boundary_discards_pending_and_does_not_rearm_held_button():
    model = SelectEdgeModel()
    model.sample(4)
    model.boundary()
    model.sample(4)
    assert model.consume(0) == 0
    model.sample(0)
    model.sample(4)
    assert model.consume(0) == 4


def test_disabled_paths_clear_pending():
    model = SelectEdgeModel()
    model.sample(4)
    assert model.consume(4, enabled=False) == 0
    assert model.pending == 0
    model.sample(0)
    model.sample(4, enabled=False)
    assert model.consume(0) == 0


def test_all_other_button_and_mask_combinations_remain_native():
    for raw in range(256):
        model = SelectEdgeModel()
        model.sample(raw)
        assert model.raw == raw
        assert model.pending == raw & 4
        for mask in range(256):
            model.pending = raw & 4
            got = model.consume(raw, mask)
            assert got == raw & mask


def test_retained_failed_trace_is_delivered_only_by_model():
    path = ROOT / 'tmp/palette-window-select-phase721-01/input-events.tsv'
    if not path.exists():
        pytest.skip('local retained emulator evidence unavailable')
    with path.open() as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    model = SelectEdgeModel(raw=int(rows[0]['raw'], 16))
    observed, modeled = [], []
    for row in rows:
        frame, value = int(row['frame']), int(row['value'], 16)
        if frame > 740:
            break
        if row['address'] == 'FF93':
            model.sample(value)
            assert model.raw == value
        elif row['address'] == 'FF94':
            edge = model.consume(value)
            if frame >= 721:
                observed.append((frame, value & 4))
                modeled.append((frame, edge & 4))
    assert observed == [(727, 0), (734, 0)]
    assert modeled == [(727, 4), (734, 0)]
