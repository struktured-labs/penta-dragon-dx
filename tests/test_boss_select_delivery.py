"""#34 retain adjacent-phase failure; a passing phase is not a general fix."""
import csv
import hashlib
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('start,delivery', [(721, 721), (722, 727)])
def test_current_short_press_delivery_and_observer_neutrality(start, delivery):
    captures = []
    for mode in ('on', 'off'):
        directory = ROOT/'tmp'/f'late-return-select-short{start}-{mode}-01'
        if not (directory/'completion.json').exists():
            pytest.skip('optional current short-pulse captures unavailable')
        receipt = json.loads((directory/'completion.json').read_text())
        assert receipt['completed']
        assert receipt['third_entry_hold'] == 1
        assert receipt['select_presses'] == [120, 240, 420, 540, start, 840]
        assert receipt['rom']['sha256'] == '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb'
        for key in ('rom', 'state', 'probe', 'runner', 'native_tap'):
            assert hashlib.sha256(Path(receipt[key]['path']).read_bytes()).hexdigest() == receipt[key]['sha256']
        assert receipt['native_capture']['restored_replay_epoch']['status'] == 'PASS'
        assert receipt['native_capture']['metadata']['frames'] == 1080
        hashes = {}
        for name, expected in receipt['native_capture']['hashes'].items():
            with (Path(receipt['av_output'])/name).open('rb') as stream:
                hashes[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
            assert hashes[name] == expected
        captures.append(hashes)
        report = json.loads((directory/'verification.json').read_text())
        assert report['status'] == 'PASS'
        assert [cycle['status'] for cycle in report['cycles']] == ['PASS']*3
    assert captures[0] == captures[1]  # Same-ROM full primary streams, no masking.
    directory = ROOT/'tmp'/f'late-return-select-short{start}-on-01'
    with (directory/'input-events.tsv').open() as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    window = [r for r in rows if start <= int(r['frame']) < start+20]
    assert any(r['address'] == 'FF93' and r['value'] == '04' for r in window)
    assert any(r['address'] == 'FF93' and r['value'] == '00'
               and int(r['frame']) == start+1 for r in window)
    edges = [r for r in window if r['address'] == 'FF94' and int(r['value'],16)&4]
    assert [int(r['frame']) for r in edges] == [delivery]
    if start == 722:
        assert edges[0]['raw'] == edges[0]['held'] == '00'
        # Native edge processing receives Select after release, without sticky raw.


@pytest.mark.parametrize('directory,start,detected', [
    ('palette-window-select-phase721-01', 721, False),
    ('palette-window-select-phase722-01', 722, True),
    ('stock-select-phase721-01', 721, True),
])
def test_retained_raw_select_and_gameplay_edge(directory, start, detected):
    path = ROOT/'tmp'/directory/'input-events.tsv'
    if not path.exists():
        pytest.skip('local emulator trace unavailable')
    with path.open() as stream:
        rows = list(csv.DictReader(stream, delimiter='\t'))
    # Include release and the following gameplay poll, not just the six-frame
    # held interval. This checks retained facts, not qualification of the ROM.
    window = [r for r in rows if start <= int(r['frame']) < start+20]
    assert any(r['address'] == 'FF93' and int(r['value'],16)&4 for r in window)
    edges = [r for r in window if r['address'] == 'FF94']
    assert edges, 'missing gameplay samples is not a negative control'
    assert any(int(r['value'],16)&4 for r in edges) == detected
