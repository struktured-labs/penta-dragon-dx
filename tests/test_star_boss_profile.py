"""#22/#36 combined-build boss fixture ABI, not gameplay acceptance."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
import generate_stream_boss_states as generator


class StarBossProfile(unittest.TestCase):
    def test_shalamar_adjacent_phase_preserves_failure_scope(self):
        import csv
        from check_boss_menu_fades import inspect_roundtrips
        from verify_pickup_class_palettes import serialized_state
        normal=ROOT/'tmp/star-shalamar-native-inventory-menus-01'
        adjacent=ROOT/'tmp/star-shalamar-native-inventory-phase721-01'
        if not (adjacent/'verification.json').exists():
            self.skipTest('Shalamar phase controls unavailable')
        self.assertEqual(inspect_roundtrips(normal,12)['status'],'PASS')
        result=inspect_roundtrips(adjacent,12,721)
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual([r['status'] for r in result['cycles']],['PASS']*3)
        self.assertEqual(result['scene_route_failures'][0]['frame'],998)
        with (adjacent/'input-events.tsv').open() as f:
            events=list(csv.DictReader(f,delimiter='\t'))
        self.assertTrue(any(r['address']=='FF94' and int(r['value'],16)&4
                            and 721<=int(r['frame'])<741 for r in events))
        final=serialized_state(adjacent/'frame-1080.ss0')
        self.assertEqual(final[0x3b7],12)

    def test_corrected_entry_escape_and_three_menus(self):
        from check_boss_menu_fades import inspect_roundtrips
        from verify_pickup_class_palettes import serialized_state
        entry=ROOT/'tmp/star-ted-native-inventory-state-02/boss4_ted.ss0'
        escape=ROOT/'tmp/star-ted-native-inventory-escape-02/frame-0600.ss0'
        replay=ROOT/'tmp/star-ted-native-inventory-menus-02'
        if not entry.exists() or not (replay/'verification.json').exists():
            self.skipTest('corrected Ted route unavailable')
        for p in (entry,escape):
            raw=serialized_state(p)
            self.assertEqual((raw[0x5c80],raw[0x60bb],raw[0x60dd]),(16,240,0))
        result=inspect_roundtrips(replay,16)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual([c['status'] for c in result['cycles']],['PASS']*3)
        final=serialized_state(replay/'frame-1080.ss0')
        self.assertEqual(final[0x3e4],0)
        self.assertLess(final[0x60dd],10)

    def test_boss_generator_does_not_overwrite_inventory(self):
        for name in ('probe_generate_boss_state.lua','probe_stage_integrity.lua'):
            probe=(ROOT/'scripts/diagnostics'/name).read_text()
            self.assertNotIn('write8(0xDCDC',probe)
            self.assertNotIn('write8(0xDCDD',probe)
            self.assertIn('write8(0xDCBB, 0xF0)',probe)

    def test_unescaped_ted_failure_matches_parent(self):
        import json
        trial=ROOT/'tmp/star-source-ted-menus-01'
        parent=ROOT/'tmp/ted-parent-entry-menus-control-02'
        if not (trial/'verification.json').exists() or not (parent/'verification.json').exists():
            self.skipTest('retained unescaped Ted controls unavailable')
        a=json.loads((trial/'verification.json').read_text())
        b=json.loads((parent/'verification.json').read_text())
        self.assertEqual(a['status'],'FAIL')
        self.assertEqual(a['failures'],b['failures'])
        pictures=sorted(parent.glob('frame-*.png'))
        self.assertEqual(len(pictures),1080)
        for picture in pictures:
            self.assertEqual(picture.read_bytes(),(trial/picture.name).read_bytes())

    def test_exact_data_only_descendant(self):
        source=ROOT/'tmp/stream-presentation-source-01/candidate.gb'
        parent=ROOT/'tmp/ted-menu-reinstall-trial-01/candidate.gb'
        if not source.exists() or not parent.exists():
            self.skipTest('local source/parent unavailable')
        rom,old=source.read_bytes(),parent.read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(),
            '4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903')
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
            'd744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5')
        self.assertEqual(rom[16*0x4000:],old[16*0x4000:])
        self.assertEqual(rom[:0x14e],old[:0x14e])
        self.assertEqual(rom[0x150:0x4000],old[0x150:0x4000])
        self.assertIn(hashlib.sha256(rom).hexdigest(),generator.PENTA_SYNC_INHERITORS_SHA256)
        self.assertTrue(generator.relocated_ted_latches(rom))
        unknown=bytearray(rom);unknown[0x200]^=1
        self.assertNotIn(hashlib.sha256(unknown).hexdigest(),generator.PENTA_SYNC_INHERITORS_SHA256)


if __name__=='__main__': unittest.main()
