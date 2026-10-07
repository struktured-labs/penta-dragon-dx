"""#67 exercise receipt rehashing, not just comparison of claimed digests.

The card parser and native epoch verifier are isolated here. These synthetic
files test the receipt validator; they are not emulator acceptance evidence.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import check_shalamar_repeat as check


@pytest.fixture
def bundle(monkeypatch):
    with tempfile.TemporaryDirectory(prefix='repeat-validator-unit-', dir=ROOT/'tmp') as name:
        folder=Path(name)
        capture=folder/'capture';capture.mkdir()
        adapter=folder/'native-runtime/native-replay.so'
        adapter.parent.mkdir();adapter.write_bytes(b'unit adapter')
        tool=folder/'tool';tool.write_bytes(b'unit tool')
        dependency=folder/'dependency';dependency.write_bytes(b'unit dependency')
        meta=dict(frames=3300,samples=10,channels=2,sample_bytes=2,
                  width=1,height=1,pixel_bytes=4,state_bytes=1)
        payloads={'native.s16le':bytes(40),'native.video':bytes(13200),
                  'native.states':bytes(3300),'native.wav':b'unit wav',
                  'native.timeline.tsv':b'unit timeline',
                  'native.meta.json':json.dumps(meta).encode()}
        for key,value in payloads.items():(capture/key).write_bytes(value)
        receipt=dict(inputs={'tool':dict(path=str(tool),sha256=check.digest(tool))},
            runtime={'identity':'unit runtime'},
            native_runtime=dict(bindings={str(dependency):check.digest(dependency)},
                                adapter_sha256=check.digest(adapter),capture_directory=str(capture)),
            native_capture=dict(metadata=meta,hashes={key:check.digest(capture/key) for key in payloads}))
        cards=dict(complete=True,first_gameplay=2525,expected_frames=3300,
                   card_frames=164,score_frames=376,card_dirty_frames=0,
                   card_shadow_dirty_frames=0,score_dirty_frames=0,score_shadow_dirty_frames=0,
                   attribute_captures=[dict(nonneutral_cells=[]) for _ in range(19)])
        monkeypatch.setattr(check,'load',lambda path:(receipt,cards))
        monkeypatch.setattr(check,'input_recipe',lambda report,path:{'recipe':'unit'})
        monkeypatch.setattr(check,'verify',lambda path:dict(status='PASS'))
        yield folder,receipt,cards


def test_valid_bound_files(bundle):
    folder,receipt,_=bundle
    assert check.validate(folder)['hashes']==receipt['native_capture']['hashes']


@pytest.mark.parametrize('relative', ['tool','dependency','native-runtime/native-replay.so',
    'capture/native.s16le','capture/native.video','capture/native.states',
    'capture/native.wav','capture/native.timeline.tsv'])
def test_changed_file_rejected_even_with_unchanged_receipt(bundle,relative):
    folder,_,_=bundle
    path=folder/relative
    data=bytearray(path.read_bytes());data[0]^=1;path.write_bytes(data)
    with pytest.raises(ValueError,match='changed'):
        check.validate(folder)


@pytest.mark.parametrize('stream', ['native.s16le','native.video','native.states'])
def test_truncated_stream_rejected_even_when_digest_updated(bundle,stream):
    folder,receipt,_=bundle
    path=folder/'capture'/stream
    path.write_bytes(path.read_bytes()[:-1])
    receipt['native_capture']['hashes'][stream]=check.digest(path)
    with pytest.raises(ValueError,match='incomplete native stream'):
        check.validate(folder)


def test_invalid_restore_boundary_rejected(bundle,monkeypatch):
    folder,_,_=bundle
    monkeypatch.setattr(check,'verify',lambda path:dict(status='FAIL'))
    with pytest.raises(ValueError,match='restore boundary'):
        check.validate(folder)


def test_metadata_frame_count_cannot_be_rewritten_to_accept_short_run(bundle):
    folder,receipt,_=bundle
    meta=copy.deepcopy(receipt['native_capture']['metadata']);meta['frames']-=1
    path=folder/'capture/native.meta.json';path.write_text(json.dumps(meta))
    receipt['native_capture']['metadata']=meta
    receipt['native_capture']['hashes']['native.meta.json']=check.digest(path)
    with pytest.raises(ValueError,match='frame count'):
        check.validate(folder)


def test_missing_native_stream_inventory(bundle):
    folder,receipt,_=bundle
    receipt['native_capture']['hashes'].pop('native.wav')
    with pytest.raises(ValueError,match='missing or extra'):
        check.validate(folder)
