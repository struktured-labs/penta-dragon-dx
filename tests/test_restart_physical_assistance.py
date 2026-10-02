"""#41 saved-game setup must not overwrite the selected graphics scratch bank."""
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from verify_gameover_restart import assistance_summary, validate, validate_stage_cards
from gameover_sequence import validate_sequence


def test_counter_summary_rejects_missing_or_inconsistent_counts():
    fields = 'native_assistance_writes=8\n' + ''.join(
        f'native_assistance_svbk_{bank}=1\n' for bank in range(8))
    with patch.object(Path, 'read_text', return_value=fields):
        assert assistance_summary(Path('unused'))['writes'] == 8
    with patch.object(Path, 'read_text', return_value=fields.replace('writes=8', 'writes=9')):
        with pytest.raises(ValueError, match='inconsistent'):
            assistance_summary(Path('unused'))
    with patch.object(Path, 'read_text', return_value=''):
        with pytest.raises(KeyError):
            assistance_summary(Path('unused'))


def test_fresh_saved_game_restart_and_unchanged_pictures():
    folder = ROOT/'tmp/late-return-physical-save-restart-01'
    receipt = json.loads((folder/'receipt.json').read_text())
    pin = '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb'
    assert receipt['status'] == 'pass' and receipt['saved_game_fixture']
    assert receipt['rom_sha256'] == pin
    assert hashlib.sha256((folder/'runtime/candidate.gb').read_bytes()).hexdigest() == pin
    for file, field in [('probe.lua', 'probe_sha256'), ('verifier.py', 'verifier_sha256')]:
        assert hashlib.sha256((folder/file).read_bytes()).hexdigest() == receipt[field]
    for filename, digest in receipt['artifacts'].items():
        assert hashlib.sha256((folder/filename).read_bytes()).hexdigest() == digest
    counts = assistance_summary(folder)
    assert counts == receipt['native_assistance']
    assert counts['writes'] == 122 and counts['physical_bank'] == 1
    assert counts['selected_svbk_counts'] == {str(b): 122 if b == 1 else 0 for b in range(8)}
    validate(folder)
    validate_stage_cards(folder, True)
    assert validate_sequence(folder) == {'title_frame_pairs': 482, 'gameover_frames': 102}
    # This route never selected a scratch bank during setup; do not claim a
    # visible failure was reproduced. Compare every retained old PNG unchanged.
    old = ROOT/'tmp/late-return-gameover-restart-01'
    old_receipt = json.loads((old/'receipt.json').read_text())
    assert old_receipt['rom_sha256'] == pin
    pictures = [name for name in old_receipt['artifacts'] if name.endswith('.png')]
    assert len(pictures) >= 825
    for name in pictures:
        assert hashlib.sha256((old/name).read_bytes()).hexdigest() == old_receipt['artifacts'][name]
        assert (folder/name).read_bytes() == (old/name).read_bytes()
