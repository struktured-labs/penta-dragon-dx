"""#25: scene-local handheld palette must not become a global crow recolor."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from build_handheld_palette_trial import build, offset, payload, COLORS, ENTRY, DATA, PARENT
from verify_pickup_class_palettes import serialized_state


class HandheldPaletteTests(unittest.TestCase):
    def test_current_candidate_menu_retains_local_palette(self):
        entry=ROOT/'tmp/return-fade-audio-enabled-entry-16'
        returned=ROOT/'tmp/return-fade-audio-enabled-exit-16'
        menu=ROOT/'tmp/return-fade16-handheld-menu-01'
        resume=ROOT/'tmp/return-fade16-handheld-resume-01'
        if not all((p/'receipt.json').exists() for p in (entry,returned,menu,resume)):
            self.skipTest('current handheld route evidence unavailable')
        for p in (entry,returned,menu,resume):
            receipt=json.loads((p/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            self.assertEqual(hashlib.sha256((p/'candidate.gb').read_bytes()).hexdigest(),
                             '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b')
        before=serialized_state(entry/'frame-1200.ss0')
        after=serialized_state(returned/'frame-6000.ss0')
        self.assertEqual((before[0x5c80],after[0x5c80]),(2,2))
        rom=(entry/'candidate.gb').read_bytes()
        self.assertEqual(before[0x12c:0x134],rom[0x36858:0x36860])
        self.assertEqual(after[0x12c:0x134],before[0x12c:0x134])
        self.assertNotEqual(before[0x12c:0x134],COLORS)
        source=entry/'frame-3600.ss0'
        self.assertEqual(serialized_state(source)[0x12c:0x134],COLORS)
        for p,paused in ((menu,1),(resume,0)):
            receipt=json.loads((p/'receipt.json').read_text())
            self.assertFalse(receipt['observer_memory_writes'])
            self.assertEqual(receipt['source_state_sha256'],hashlib.sha256(source.read_bytes()).hexdigest())
            source=p/'frame-0180.ss0'
            state=serialized_state(source)
            self.assertEqual((state[0x5c80],state[0x3e4]),(9,paused))
            self.assertEqual(state[0x12c:0x134],COLORS)

    def test_wrong_parent_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact'):
            build(bytes(1024))

    def test_patch_scope_and_mapper_rendezvous(self):
        p = ROOT/'tmp/select-buffer-trial-02/candidate.gb'
        if not p.exists():
            self.skipTest('exact experimental parent not available')
        parent = p.read_bytes()
        self.assertEqual(hashlib.sha256(parent).hexdigest(), PARENT)
        result = build(parent)
        allowed = {0x14e, 0x14f}
        for addr, size in [(0x7320, 3), (ENTRY, len(payload())), (DATA, 8), (0x71e7, 5)]:
            allowed.update(range(offset(addr), offset(addr)+size))
        self.assertFalse([i for i,(a,b) in enumerate(zip(parent,result)) if a!=b and i not in allowed])
        self.assertEqual(result[0x36800:0x36900], parent[0x36800:0x36900])
        self.assertEqual(result[offset(0x71e7):offset(0x71ec)], bytes.fromhex('3e0dcd6100'))
        self.assertEqual(result[0x371ec:0x371f1], bytes.fromhex('7bd1e0ffc9'))

    def test_retained_secret_menu_and_exit_palette_isolation(self):
        parent = ROOT/'tmp/select02-secret-menu-fullreturn-01'
        trial = ROOT/'tmp/handheld-palette-menu-return-01'
        if not (trial/'frame-10800.ss0').exists() or not (parent/'frame-10800.ss0').exists():
            self.skipTest('local full-route evidence unavailable')
        for frame in (1200,3240,3360,3480,3720,6600,10800):
            with self.subTest(frame=frame):
                old = serialized_state(parent/f'frame-{frame:04d}.ss0')
                new = serialized_state(trial/f'frame-{frame:04d}.ss0')
                if frame in (1200,10800):
                    self.assertEqual(new[0x114:0x154], old[0x114:0x154])
                    self.assertNotEqual(new[0x12c:0x134], COLORS)
                else:
                    self.assertEqual(new[0x12c:0x134], COLORS)
                    self.assertNotEqual(old[0x12c:0x134], COLORS)
                    self.assertEqual(new[0x114:0x12c], old[0x114:0x12c])
                    self.assertEqual(new[0x134:0x154], old[0x134:0x154])
                self.assertEqual(new[0xd4:0x114], old[0xd4:0x114])
