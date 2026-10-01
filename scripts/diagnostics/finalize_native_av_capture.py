"""Validate complete native tap files and wrap untouched PCM in a WAV header."""
import argparse
import hashlib
import json
from pathlib import Path
import wave
try:
    from .verify_native_capture_epoch import verify as verify_epoch
except ImportError:  # Direct CLI and existing diagnostic runners.
    from verify_native_capture_epoch import verify as verify_epoch


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def finalize(directory):
    meta = json.loads((directory / 'native.meta.json').read_text())
    if meta['channels'] != 2 or meta['sample_bytes'] != 2 or not meta['samples'] or not meta['frames']:
        raise ValueError('empty or unsupported native capture')
    sizes = {'s16le': meta['samples'] * 4,
             'video': meta['frames'] * meta['width'] * meta['height'] * meta['pixel_bytes'],
             'states': meta['frames'] * meta['state_bytes']}
    for suffix, size in sizes.items():
        if (directory / f'native.{suffix}').stat().st_size != size:
            raise ValueError(f'truncated native.{suffix}')
    output = directory / 'native.wav'
    # Exclusive creation preserves retained evidence. PCM bytes are unchanged.
    with output.open('xb') as file:
        with wave.open(file, 'wb') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(meta['sample_rate'])
            with (directory / 'native.s16le').open('rb') as pcm:
                while chunk := pcm.read(1024 * 1024):
                    wav.writeframesraw(chunk)
    return dict(status='COMPLETE_CAPTURE_FILES', metadata=meta,
                restored_replay_epoch=verify_epoch(directory),
                scope='File completeness only; not audio fidelity acceptance.',
                hashes={f'native.{suffix}': digest(directory / f'native.{suffix}')
                        for suffix in (*sizes, 'wav', 'timeline.tsv', 'meta.json')})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    args = p.parse_args()
    receipt = args.directory / 'capture-receipt.json'
    if receipt.exists():
        p.error('capture already finalized')
    result = finalize(args.directory)
    result['finalizer_sha256'] = digest(Path(__file__))
    with receipt.open('x') as file:
        file.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
