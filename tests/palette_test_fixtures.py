"""#70 explicit palette fixtures; no device access or implicit emulator launch."""
import atexit
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
CURRENT='126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941'
LEGACY='46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb'


def sha(data):
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=1)
def rom_fixture_path():
    supplied=os.environ.get('PENTA_TEST_STREAM_ROM')
    if supplied:
        path=Path(supplied).resolve()
    else:
        # Build source rather than requiring an ignored historical ROM.
        sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
        from build_stream_source_candidate import build
        scratch=tempfile.TemporaryDirectory(prefix='palette-unit-source-',dir=ROOT/'tmp')
        atexit.register(scratch.cleanup)
        path=Path(scratch.name)/'source/candidate.gb'
        build(path.parent)
    if sha(path.read_bytes()) not in {CURRENT,LEGACY}:
        raise ValueError('palette tests require an exact supported fixture ROM')
    return path


def validated_states(manifest, rom, stage):
    """Parser-test memory only; these are not MiSTer-compatible checkpoints."""
    sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
    from normalize_mgba_state_pc import png_chunks
    if manifest['rom_sha256']!=sha(rom):
        raise ValueError('palette state manifest ROM differs')
    records=manifest['stages'][str(stage)]
    if len(records)<(3 if stage==1 else 1):
        raise ValueError('insufficient distinct state fixtures')
    if len({r['sha256'] for r in records})!=len(records):
        raise ValueError('duplicate state fixtures')
    states=[]
    for record in records:
        encoded=Path(record['path']).read_bytes()
        if sha(encoded)!=record['sha256']:
            raise ValueError('palette state hash differs')
        raw=zlib.decompress(dict(png_chunks(encoded))[b'gbAs'])
        if (len(raw)!=71680 or int.from_bytes(raw[4:8],'little')!=zlib.crc32(rom)&0xffffffff
                or raw[16:32]!=rom[0x134:0x144]):
            raise ValueError('palette state does not belong to exact ROM')
        if raw[0x5C80]!=stage+1 or raw[0x3BA]!=stage-1:
            raise ValueError('palette state is not the requested settled dungeon')
        states.append(raw)
    return states


def current_states(rom,stage):
    path=os.environ.get('PENTA_TEST_PALETTE_STATES')
    if not path:
        raise ValueError('Set PENTA_TEST_PALETTE_STATES to a hash-bound current-ROM state manifest; no emulator is launched implicitly')
    return validated_states(json.loads(Path(path).read_text()),rom,stage)


def validate_gate_inventory(matrix):
    results=matrix['results']
    names=[r['name'] for r in results]
    selected=matrix['selected_gates']
    if (not names or len(set(names))!=len(names)
            or len(set(selected))!=len(selected)
            or any(r['status']!='passed' for r in results)
            or set(names)!=set(selected)):
        raise ValueError('incomplete or duplicate gate inventory')


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Prepare explicit parser fixtures from a completed source suite; never launches an emulator')
    parser.add_argument('--suite-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or (ROOT/'tmp').resolve() not in args.output.resolve().parents:
        parser.error('fresh repository-local tmp manifest required')
    suite=args.suite_root.resolve()
    run=json.loads((suite/'run.json').read_text())
    matrix=json.loads((suite/'matrix/manifest.json').read_text())
    if run['status']!='passed' or matrix['status']!='emulator-pass':
        parser.error('completed passing suite required; running evidence is not a fixture')
    try:
        validate_gate_inventory(matrix)
    except ValueError as error:
        parser.error(str(error))
    rom=(suite/'build/source-a/candidate.gb').read_bytes()
    if sha(rom)!=CURRENT:
        parser.error('exact current source candidate required')
    prefix=suite/'matrix/artifacts/playtest-boss-handoff/candidate-secret'
    paths={'1':[prefix/f'frame-{frame}.ss0' for frame in (6960,7080,7200)],
           '2':[suite/'matrix/artifacts/current-stage-control-states/stage2.ss0']}
    manifest=dict(rom_sha256=sha(rom),
        origin=dict(suite_root=str(suite),run_sha256=sha((suite/'run.json').read_bytes()),
                    matrix_sha256=sha((suite/'matrix/manifest.json').read_bytes())),
        scope='mGBA memory translated only for offline palette-parser tests, never MiSTer restore',
        stages={stage:[dict(path=str(path),sha256=sha(path.read_bytes())) for path in files]
                for stage,files in paths.items()})
    for stage in (1,2):validated_states(manifest,rom,stage)
    with args.output.open('x') as stream:
        json.dump(manifest,stream,indent=2);stream.write('\n')
    print(args.output)


if __name__=='__main__':
    main()
