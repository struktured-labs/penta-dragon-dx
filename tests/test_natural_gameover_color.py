"""#18 natural-damage evidence, not an isolated spike-contact replay."""
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from gameover_sequence import GAMEOVER_AGES, validate_sequence
from verify_gameover_color import compare_gameover
from verify_gameover_restart import validate


def test_current_natural_death_restart_and_reported_gray_negative_control():
    folders = []
    for name, pin in (
        ('reported-natural-restart-01',
         '4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5'),
        ('late-return-natural-restart-01',
         '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb'),
    ):
        folder = ROOT/'tmp'/name
        receipt = json.loads((folder/'receipt.json').read_text())
        assert receipt['rom_sha256'] == pin
        assert hashlib.sha256((folder/'runtime/candidate.gb').read_bytes()).hexdigest() == pin
        assert receipt['status'] == 'pass'
        assert receipt['stimulus'].startswith('movement-driven native damage;')
        assert not receipt['hazard_death'] and not receipt['saved_game_fixture']
        assert receipt['hazard_oscillate'] and receipt['hazard_walk_frames'] == 1600
        for field, filename in (
            ('probe_sha256', 'probe_gameover_restart.lua'),
            ('verifier_sha256', 'verify_gameover_restart.py'),
            ('sequence_oracle_sha256', 'gameover_sequence.py'),
            ('terrain_oracle_sha256', 'restart_terrain.py'),
        ):
            source_dir = ('tmp/restart-source-before-physical-save-01'
                          if filename in ('probe_gameover_restart.lua', 'verify_gameover_restart.py')
                          else 'scripts/diagnostics')
            assert hashlib.sha256((ROOT/source_dir/filename).read_bytes()).hexdigest() == receipt[field]
        for filename, digest in receipt['artifacts'].items():
            assert hashlib.sha256((folder/filename).read_bytes()).hexdigest() == digest
        assert (folder/'route.txt').read_text().split() == ['ok', '2', '2', '2']
        validate(folder)
        assert validate_sequence(folder) == {'title_frame_pairs': 482, 'gameover_frames': 102}
        folders.append(folder)
    # Both legacy restart verdicts pass: only this requirement-specific oracle
    # distinguishes the reported missing color from the corrected output.
    for cycle in (1, 2):
        for age in GAMEOVER_AGES:
            name = f'sequence-gameover-{cycle}-{age:04d}.png'
            with Image.open(folders[0]/name) as before, Image.open(folders[1]/name) as after:
                correct, count = compare_gameover(before, after)
                assert correct and count > 0
                assert compare_gameover(before, before) == (False, 0)
