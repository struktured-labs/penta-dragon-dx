"""#67 exact, complete same-ROM transition repeat; no alignment or masks."""
import argparse
import hashlib
import json
from pathlib import Path

from check_score_oam_transition import input_recipe, load
from verify_native_capture_epoch import verify

STREAMS = {'native.s16le', 'native.video', 'native.states', 'native.wav',
           'native.timeline.tsv', 'native.meta.json'}


def card_failures(cards):
    errors=[]
    if not cards['complete'] or cards['first_gameplay'] is None:
        errors.append('incomplete transition timeline')
    if cards['card_frames']<60 or cards['score_frames']<60:
        errors.append('insufficient card coverage')
    if any(cards[key] for key in ('card_dirty_frames','card_shadow_dirty_frames',
                                 'score_dirty_frames','score_shadow_dirty_frames')):
        errors.append('lingering card sprites')
    if len(cards['attribute_captures'])<10 or any(c['nonneutral_cells'] for c in cards['attribute_captures']):
        errors.append('missing or dirty card attribute captures')
    return errors


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate(folder):
    receipt, cards = load(folder)
    errors=card_failures(cards)
    if errors:
        raise ValueError('; '.join(errors))
    for item in receipt['inputs'].values():
        if digest(Path(item['path'])) != item['sha256']:
            raise ValueError('changed replay input or tool')
    runtime = receipt['native_runtime']
    for name, expected in runtime['bindings'].items():
        if digest(Path(name)) != expected:
            raise ValueError('changed native runtime dependency')
    if digest(folder/'native-runtime/native-replay.so') != runtime['adapter_sha256']:
        raise ValueError('changed native adapter')
    capture = Path(runtime['capture_directory'])
    if verify(capture)['status'] != 'PASS':
        raise ValueError('invalid native restore boundary')
    native = receipt['native_capture']
    if set(native['hashes']) != STREAMS:
        raise ValueError('missing or extra native streams')
    meta = json.loads((capture/'native.meta.json').read_text())
    if meta != native['metadata'] or meta['frames'] != cards['expected_frames']:
        raise ValueError('native frame count or metadata differs')
    sizes = {'native.s16le': meta['samples']*meta['channels']*meta['sample_bytes'],
             'native.video': meta['frames']*meta['width']*meta['height']*meta['pixel_bytes'],
             'native.states': meta['frames']*meta['state_bytes']}
    for name, size in sizes.items():
        if size <= 0 or (capture/name).stat().st_size != size:
            raise ValueError('incomplete native stream')
    hashes = {name: digest(capture/name) for name in STREAMS}
    if hashes != native['hashes']:
        raise ValueError('changed native evidence')
    return dict(inputs={k: v['sha256'] for k, v in receipt['inputs'].items()},
                recipe=input_recipe(receipt, folder), runtime=receipt['runtime'],
                adapter=runtime['adapter_sha256'], native_bindings=runtime['bindings'],
                hashes=hashes)


def differences(first, second):
    failures = [key+' differs' for key in ('inputs', 'recipe', 'runtime', 'adapter', 'native_bindings')
                if first[key] != second[key]]
    if set(first['hashes']) != STREAMS or set(second['hashes']) != STREAMS:
        failures.append('missing or extra native streams')
    failures += [name+' differs' for name in sorted(STREAMS)
                 if first['hashes'].get(name) != second['hashes'].get(name)]
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('first', type=Path)
    parser.add_argument('second', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        first, second = validate(args.first), validate(args.second)
        errors = differences(first, second)
        result = dict(status='FAIL' if errors else 'PASS', failures=errors,
                      first=first, second=second, scope=__doc__)
    except (ValueError, KeyError, OSError) as error:
        result = dict(status='FAIL', failures=[str(error)], scope=__doc__)
    with args.output.open('x') as file:
        json.dump(result, file, indent=2)
        file.write('\n')
    print(result['status'], result['failures'])
    return result['status'] != 'PASS'


if __name__ == '__main__':
    raise SystemExit(main())
