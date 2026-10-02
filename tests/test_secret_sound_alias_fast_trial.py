"""#26 preserve healthy routing instructions while handling low-health aliases."""
import unittest
import hashlib
from pathlib import Path
from test_secret_sound_alias_trial import route
import build_secret_sound_alias_fast_trial as fast
from build_secret_combined_copy_trial import gate as old_gate


class FastAlias(unittest.TestCase):
    def test_own_cold_checkpoint_preserves_parent_audio_and_clocks(self):
        from verify_pickup_class_palettes import serialized_state
        root = Path(__file__).resolve().parents[1]
        paths = [root/'tmp/arena-completion-safe-late-pause-return-01/frame-3600.ss0',
                 root/'tmp/secret-sound-alias-fast-own-entry-01/frame-3600.ss0']
        if not all(p.exists() for p in paths): self.skipTest('local checkpoints unavailable')
        self.assertEqual(hashlib.sha256(paths[1].read_bytes()).hexdigest(),
                         'e7eeb9b599312a83779369c69602ccd7413d0abde26662a7bbe59a8ab5b6207c')
        a,b = map(serialized_state, paths)
        for start,end in ((0x48,0xb4),(0x1d8,0x260),(0x310,0x340),
                          (0xc,0x10),(0x198,0x1a0),(0x154,0x168)):
            self.assertEqual(a[start:end], b[start:end])

    def test_healthy_prefix_changes_only_untaken_branch_destination(self):
        old, new = old_gate(), fast.gate()
        self.assertEqual([i for i in range(len(old)) if old[i] != new[i]], [16])
        self.assertEqual(old[15], 0x20)  # JR NZ after CP 0A.
        # Raw09 branches before this operand, raw0A leaves the branch untaken.
        # Stage!=07 branches straight to the original native entry.

    def test_exhaustive_scene_routing(self):
        code = fast.gate()
        for raw in range(256):
            for canonical in range(256):
                expected = 'secret' if raw in (9,10) or raw == 11 and canonical in (9,10) else 'native'
                self.assertEqual(route(code, 7, raw, canonical), expected)
        for stage in range(256):
            if stage != 7:
                for raw in (9,10,11):
                    self.assertEqual(route(code, stage, raw, 9), 'native')
