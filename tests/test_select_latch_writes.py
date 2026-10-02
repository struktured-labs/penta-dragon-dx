import csv
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from check_select_latch_writes import failures


def evidence():
    path = ROOT/'tmp/select-buffer-latch721-03/latch-writes.tsv'
    if not path.exists():
        pytest.skip('local replay unavailable')
    with path.open() as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


def test_observed_two_byte_write_ownership():
    assert not failures(evidence())


@pytest.mark.parametrize('field,value', [('ie','04'), ('bank','0D'),
                                       ('svbk','F9'), ('pc','1234'), ('value','FF')])
def test_bad_write_is_rejected(field, value):
    rows = evidence()
    rows[0][field] = value
    assert failures(rows)


def test_missing_end_address_is_rejected():
    assert failures([r for r in evidence() if r['address'] != 'DF82'])


def test_empty_trace_does_not_pass():
    assert failures([])
