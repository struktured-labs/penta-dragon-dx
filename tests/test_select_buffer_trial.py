"""#34 structural bounds and retained live buffering proof; not full qualification."""
import csv
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import build_select_buffer_trial as builder


def parent_fixture():
    parent = bytearray(b'\xff' * 0x100000)
    parent[0xA8:0xA8+len(builder.EDGE)] = builder.EDGE
    parent[0x36F60:0x36F68] = builder.SAMPLE
    parent[0x09BE:0x09C4] = bytes.fromhex('E099 EA0021 C9')
    parent[0x847:0x850] = bytes.fromhex('CD6100 CD806C C36100')
    return bytes(parent)


def test_only_declared_code_and_checksum_changed():
    parent = parent_fixture()
    with patch.object(builder, 'PARENT', builder.digest(parent)):
        result = builder.build(parent)
    allowed = {0x14E, 0x14F} | set(range(0xA8,0xA8+len(builder.EDGE)))
    allowed |= set(range(0x36F60,0x36F68))
    rendezvous = builder.BANK*16384+0x6F65-0x4000
    allowed |= set(range(rendezvous,rendezvous+6))
    assert result[rendezvous:rendezvous+6] == bytes.fromhex('CDBE09 C3806C')
    assert result[0x36F60:0x36F68] == bytes.fromhex('B0 47 3E25 00 CDBE09')
    for base, sample in [(0x6C80, True), (0x6D80, False)]:
        start = builder.BANK*16384+base-0x4000
        code = builder.payload(base, sample)
        allowed |= set(range(start,start+len(code)))
        assert result[start:start+len(code)] == code
    assert len(parent) == len(result)
    assert {i for i,(a,b) in enumerate(zip(parent,result)) if a!=b} <= allowed
    assert int.from_bytes(result[0x14E:0x150],'big') == (sum(result[:0x14E])+sum(result[0x150:]))&65535


@pytest.mark.parametrize('offset', [0xA8,0x36F60,0x09BE,0x847,37*16384])
def test_preimage_and_cave_guards_even_if_repin_attempted(offset):
    parent = bytearray(parent_fixture())
    parent[offset] ^= 1
    with patch.object(builder, 'PARENT', builder.digest(parent)):
        with pytest.raises(ValueError):
            builder.build(parent)


def test_live_released_select_delivered_and_parent_misses():
    for directory, expected in [('select-buffer-short721-01',True),
                                ('select-buffer-short721-02',True),
                                ('select-buffer-short723-02',True),
                                ('select-buffer-short726-02',True),
                                ('select-buffer-parent-short721-01',False)]:
        path=ROOT/'tmp'/directory/'input-events.tsv'
        if not path.exists():
            pytest.skip('local emulator trace unavailable')
        with path.open() as stream:
            rows=list(csv.DictReader(stream,delimiter='\t'))
        window=[r for r in rows if 721<=int(r['frame'])<=740]
        assert any(r['address']=='FF93' and r['value']=='04' for r in window)
        assert any(r['address']=='FF93' and r['value']=='00' for r in window)
        edges=[r for r in window if r['address']=='FF94']
        assert edges
        buffered=[r for r in edges if int(r['value'],16)&4 and r['raw']=='00']
        assert bool(buffered) == expected
        if expected:
            assert len(buffered)==1
