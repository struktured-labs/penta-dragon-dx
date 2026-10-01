import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from compose_stream_presentation_trial import overlay, build, digest


def test_overlay_conflict_is_rejected():
    base = bytes(512)
    variant = bytearray(base)
    variant[10] = 1
    current = bytearray(base)
    current[10] = 2
    with pytest.raises(ValueError, match='preimage conflict'):
        overlay(bytes(current), base, bytes(variant))


def test_overlay_preserves_expanded_banks_and_defers_checksum():
    base = bytes(512)
    variant = bytearray(base)
    variant[10] = 1
    variant[0x14E] = 99
    current = base + b'new bank'
    result, changed = overlay(current, base, bytes(variant))
    assert changed == [10]
    assert result[10] == 1
    assert result[0x14E] == 0
    assert result[512:] == b'new bank'


def test_retained_composition_is_rebuilt_and_preserves_existing_chain():
    source = ROOT/'tmp/stream-regressions-source-07/candidate.gb'
    parent = ROOT/'tmp/sara-atomic-pose-source-16/candidate.gb'
    previous = ROOT/'tmp/ceiling-secret-fast-menu-composition-01/candidate.gb'
    if not all(p.exists() for p in (source, parent, previous)):
        pytest.skip('local immutable parents unavailable')
    result, records = build(source.read_bytes(), parent.read_bytes())
    assert digest(result) == 'e8002aea7117e6416b546e39655d7c792959913af66c827c28223bf6b01b6c57'
    old = previous.read_bytes()
    assert len(result) == len(old)
    allowed = {0x14E, 0x14F}
    for record in records:
        allowed.update(record['changed_offsets'])
    assert {i for i,(a,b) in enumerate(zip(old,result)) if a!=b} <= allowed
