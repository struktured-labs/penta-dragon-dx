"""Exact combined-build restart evidence; retain failed natural-death attempt."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_gameover_restart import validate,validate_stage_cards
from gameover_sequence import validate_sequence


class StarRestart(unittest.TestCase):
    def test_native_damage_with_normal_prompt_dismissal(self):
        base=ROOT/'tmp/star-source-natural-restart-02'
        if not (base/'receipt.json').exists(): self.skipTest('native damage corpus unavailable')
        receipt=json.loads((base/'receipt.json').read_text())
        self.assertEqual(receipt['status'],'pass')
        self.assertIn('B dismisses',receipt['stimulus'])
        self.assertNotIn('HP=0',receipt['stimulus'])
        self.assertTrue(receipt['hazard_oscillate'])
        validate(base)
        validate_stage_cards(base,saved_game=True)
        self.assertEqual(validate_sequence(base),{'title_frame_pairs':482,'gameover_frames':102})
        self.assertIn('low-health-menu-dismiss', (base/'trace.tsv').read_text())
        # The prompt is original behavior, not a phantom Select from the hack.
        rom=(base/'runtime/candidate.gb').read_bytes()
        original=(ROOT/'rom/Penta Dragon (J).gb').read_bytes()
        self.assertEqual(rom[0x5050:0x5077],original[0x5050:0x5077])
        self.assertEqual(rom[0x5066:0x5071],bytes.fromhex('2194FF CBD6 3E03 EA06DD C9'))

    def test_accelerated_hazard_restart(self):
        base=ROOT/'tmp/star-source-hazard-restart-01'
        if not (base/'receipt.json').exists(): self.skipTest('local restart corpus unavailable')
        receipt=json.loads((base/'receipt.json').read_text())
        self.assertEqual(receipt['rom_sha256'],'d744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5')
        self.assertEqual(receipt['status'],'pass')
        self.assertIn('HP=0',receipt['stimulus'])
        validate(base)
        validate_stage_cards(base,saved_game=True)
        self.assertEqual(validate_sequence(base),{'title_frame_pairs':482,'gameover_frames':102})
        parent=ROOT/'tmp/ted-menu-reinstall-hazard-restart-01'
        images=sorted(base.glob('*.png'))
        self.assertEqual(len(images),867)
        for image in images:
            self.assertEqual(image.read_bytes(),(parent/image.name).read_bytes(),image.name)

    def test_natural_route_failure_not_accepted(self):
        base=ROOT/'tmp/star-source-natural-restart-01'
        if not (base/'receipt.json').exists(): self.skipTest('retained failed route unavailable')
        receipt=json.loads((base/'receipt.json').read_text())
        self.assertEqual(receipt['status'],'failed')
        self.assertIn('exit 2',receipt['error'])
        final=(base/'trace.tsv').read_text().splitlines()[-1].split('\t')
        self.assertEqual(final[:3],['24000','await-damage','0B'])


if __name__=='__main__':unittest.main()
