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


def synthetic_writes():
    """Exercise the oracle without depending on ignored emulator artifacts.

    This is a mutation-test input, not a hardware or ROM ownership proof.
    """
    return [dict(address=address,pc=pc,value=value,bank='25',svbk='FF',ie='00')
            for address,pc,value in (
                ('DF81','6CAE','04'),('DF82','6CB2','0C'),
                ('DF81','6DA5','00'),('DF82','6DA9','00'))]


def test_synthetic_valid_writer_inventory():
    assert not failures(synthetic_writes())


@pytest.mark.parametrize('field,value', [('ie','04'), ('bank','0D'),
                                       ('svbk','F9'), ('pc','1234'), ('value','FF')])
def test_bad_write_is_rejected(field, value):
    rows = synthetic_writes()
    rows[0][field] = value
    assert failures(rows)


def test_missing_end_address_is_rejected():
    assert failures([r for r in synthetic_writes() if r['address'] != 'DF82'])


@pytest.mark.parametrize('address,value', [('DF81','04'),('DF81','00'),
                                          ('DF82','0C'),('DF82','00')])
def test_missing_lifecycle_value_is_rejected(address,value):
    rows=synthetic_writes()
    for row in rows:
        if row['address']==address and row['value']==value:
            row['value']='00' if value!='00' else ('04' if address=='DF81' else '0C')
    assert failures(rows)


def test_empty_trace_does_not_pass():
    assert failures([])
