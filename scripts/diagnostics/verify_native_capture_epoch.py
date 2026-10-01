"""Issue #43: qualify a single restored replay's native capture boundary.

This is not an audio-fidelity test. Never crop pre-restore samples to pass it.
Cold-boot captures need a different contract and are not accepted here.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def verify(directory):
    path = directory / 'native.lifecycle.tsv'
    result = {'status': 'FAIL', 'scope': 'Single restored capture boundary only',
              'directory': str(directory.resolve()), 'errors': []}
    if not path.is_file():
        result['errors'].append('Missing lifecycle evidence')
        return result
    raw = path.read_bytes()
    result['lifecycle_sha256'] = hashlib.sha256(raw).hexdigest()
    try:
        rows = list(csv.DictReader(raw.decode().splitlines(), delimiter='\t'))
        if [row['event'] for row in rows] != ['load_begin', 'load_end']:
            raise ValueError('Expected exactly one complete state restoration')
        for row in rows:
            for field in ('emulator_frame', 'video_frames', 'pcm_samples', 'success'):
                row[field] = int(row[field])
        result['events'] = rows
        if rows[0]['success'] != -1 or rows[1]['success'] != 1:
            result['errors'].append('State restoration did not succeed')
        if any(row['pcm_samples'] != 0 or row['video_frames'] != 0 for row in rows):
            result['errors'].append('Audio or video was captured before restoration completed')
        if any(row['emulator_frame'] < 0 for row in rows):
            result['errors'].append('Invalid emulator frame')
    except (ValueError, KeyError, UnicodeError) as error:
        result['errors'].append(str(error))
    if not result['errors']:
        result['status'] = 'PASS'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = verify(args.directory)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
