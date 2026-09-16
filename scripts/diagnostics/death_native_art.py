"""Fresh, independent stock-ROM source planes for Shalamar death artwork."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import verify_boss_publication_cadence as cadence
from generate_stream_boss_states import SUPPORTED_BASE_MD5

ROOT = Path(__file__).resolve().parents[2]


def exact_native_plane(source: bytes, native_planes: set[bytes]) -> bool:
    return len(source) == 576 and source in native_planes


def capture_native_planes(output: Path, timeout: float) -> set[bytes]:
    original = ROOT / 'rom/Penta Dragon (J).gb'
    original_bytes = original.read_bytes()
    if hashlib.md5(original_bytes).hexdigest() != SUPPORTED_BASE_MD5:
        raise ValueError('death oracle requires the supported original ROM')
    original_sha = hashlib.sha256(original_bytes).hexdigest()
    output.mkdir(parents=True, exist_ok=True)
    states = output / 'states'
    with (output / 'state-generation.log').open('w') as log:
        result = subprocess.run([
            sys.executable, str(ROOT / 'scripts/diagnostics/generate_stream_boss_states.py'),
            str(original), '--target', '0', '--output', str(states),
        ], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            timeout=max(60, timeout * 4), check=False)
    if result.returncode:
        raise RuntimeError(f'native death oracle state generation failed: {result.returncode}')
    state = cadence.state_for(states, 0)
    runs = [cadence.capture(original, state, output / f'run-{i}',
                            0, 60, 600, timeout) for i in (1, 2)]
    payloads = [cadence.source_payloads(Path(run['source_trace'])) for run in runs]
    equivalence = cadence.classify_replay_equivalence(
        runs[0], runs[1], payloads[0], payloads[1])
    if not equivalence['deterministic']:
        raise RuntimeError('native death oracle replays disagree')
    if hashlib.sha256(original.read_bytes()).hexdigest() != original_sha:
        raise RuntimeError('original ROM changed while capturing death oracle')
    # Use only planes witnessed independently in both fresh replays.
    planes = set(payloads[0]) & set(payloads[1])
    if not planes:
        raise RuntimeError('native death oracle contains no common source planes')
    receipt = {
        'schema': 'penta-native-death-art-v1', 'status': 'pass',
        'finished_at': datetime.now(timezone.utc).isoformat(),
        'original_rom': str(original.resolve()), 'original_sha256': original_sha,
        'state': str(state.resolve()), 'runs': runs,
        'replay_equivalence': equivalence,
        'native_plane_sha256': sorted(hashlib.sha256(p).hexdigest() for p in planes),
    }
    (output / 'manifest.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return planes
