"""#37: actual native item use, not only rendering an assisted menu."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_pickup_class_palettes import serialized_state
from check_secret_pickup_attributes import inspect_planes


class NativeItemAssistance(unittest.TestCase):
    def test_pause_effect_spans_secret_return(self):
        """Coverage assertion only: these trials do NOT reproduce yellow trails."""
        for prefix in ('reported', 'star'):
            base=ROOT/'tmp'/f'{prefix}-late-pause-return-01'
            if not (base/'receipt.json').exists():
                self.skipTest('late pause-item route unavailable')
            receipt=json.loads((base/'receipt.json').read_text())
            self.assertEqual(receipt['status'],0)
            for field, filename in (('rom_sha256','candidate.gb'),('probe_sha256','probe.lua')):
                self.assertEqual(receipt[field],hashlib.sha256((base/filename).read_bytes()).hexdigest())
            with (base/'trace.tsv').open() as f:
                route=list(csv.DictReader(f,delimiter='\t'))
            with (base/'item-action.tsv').open() as f:
                items=list(csv.DictReader(f,delimiter='\t'))
            self.assertEqual([int(r['frame']) for r in route],list(range(1,12001)))
            self.assertEqual([int(r['frame']) for r in items],list(range(1,12001)))
            first=next(r for r in items if int(r['pause_timer']))
            self.assertEqual((first['frame'],first['pause_timer'],first['slot1']),('7261','60','8'))
            returned=next(r for r in route[7500:] if (r['scene'],r['stage'])==('02','00'))
            self.assertGreater(int(items[int(returned['frame'])-1]['pause_timer']),0)
            self.assertEqual(items[-1]['pause_timer'],'0')
            self.assertGreater(len({(r['world_x'],r['world_y']) for r in route[10000:]}),50)

    def test_pause_item_then_secret_movement_palette_control(self):
        for name,fixed in (('reported-pause-item-scroll-01',False),
                           ('star-pause-item-scroll-01',True)):
            with self.subTest(run=name):
                base=ROOT/'tmp'/name
                if not (base/'receipt.json').exists():
                    self.skipTest('item-use movement diagnostic unavailable')
                receipt=json.loads((base/'receipt.json').read_text())
                self.assertEqual(receipt['status'],0)
                self.assertEqual(receipt['diagnostic_environment']['ENTRY_KEYS'],'17')
                rom=(base/'candidate.gb').read_bytes()
                self.assertEqual(hashlib.sha256(rom).hexdigest(),receipt['rom_sha256'])
                self.assertEqual(receipt['rom_sha256'],
                    'd744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5'
                    if fixed else '4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5')
                with (base/'item-action.tsv').open() as f:
                    items=list(csv.DictReader(f,delimiter='\t'))
                self.assertEqual(len(items),6000)
                first=next(r for r in items if int(r['pause_timer']))
                self.assertEqual((first['frame'],first['cursor'],first['pause_timer'],first['slot1']),
                                 ('3361','1','60','8'))
                self.assertTrue(all(int(r['cursor'])<10 for r in items if r['menu']=='1'))
                for frame in (3480,3600,4800,6000):
                    raw=serialized_state(base/f'frame-{frame:04d}.ss0')
                    result=inspect_planes(raw,rom)
                    self.assertEqual(len(result['mismatches']),0 if fixed else 337)
                with (base/'trace.tsv').open() as f:
                    route=list(csv.DictReader(f,delimiter='\t'))
                self.assertEqual(route[3425]['room'],'01')
                self.assertEqual((route[-1]['scene'],route[-1]['stage'],route[-1]['room']),
                                 ('09','07','03'))

    def test_health_only_seven_stage_comparison(self):
        base=ROOT/'tmp/star-seven-stage-native-cursor-01'
        if not (base/'manifest.json').exists():
            self.skipTest('health-only stage comparison unavailable')
        manifest=json.loads((base/'manifest.json').read_text())
        self.assertEqual(manifest['status'],'pass')
        self.assertEqual(manifest['original_rom_sha256'],
            '4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903')
        self.assertEqual(manifest['dx_rom_sha256'],
            'd744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5')
        for key,name in (('probe_sha256','probe_stage_side_by_side.lua'),
                         ('verifier_sha256','capture_stage_side_by_side.py')):
            self.assertEqual(manifest[key],hashlib.sha256(
                (ROOT/'scripts/diagnostics'/name).read_bytes()).hexdigest())
        self.assertEqual(set(manifest['stages']),{f'stage{i}' for i in range(1,8)})
        for stage,record in manifest['stages'].items():
            with self.subTest(stage=stage):
                self.assertEqual(record['og_image_sha256'],record['dx_image_sha256'])
                for side in ('og','dx'):
                    self.assertEqual((base/stage/side/'run.done').read_text().strip(),'ok')
                    images=sorted((base/stage/side).glob('run.f*.png'))
                    self.assertEqual(len(images),4)
                    self.assertEqual([hashlib.sha256(p.read_bytes()).hexdigest() for p in images],
                                     record[side+'_image_sha256'])
        self.assertEqual(manifest['stages']['stage5']['semantic_palette_audit']['status'],'pass')

    def test_corrected_secret_geometry_campaign(self):
        path=ROOT/'tmp/secret-palette-cursor-corrected-01/receipt.json'
        if not path.exists(): self.skipTest('corrected secret campaign unavailable')
        receipt=json.loads(path.read_text())
        self.assertEqual(receipt['status'],'PASS')
        self.assertEqual(len(receipt['checks']),10)
        self.assertTrue(all(receipt['checks'].values()))
        self.assertIn('health DCBB only',receipt['assistance'])
        for key,name in (('probe_sha256','probe_secret_chr_entry.lua'),
                         ('verifier_sha256','verify_secret_chr_entry.py')):
            source=(ROOT/'scripts/diagnostics'/name).read_bytes()
            self.assertEqual(receipt['bindings'][key],hashlib.sha256(source).hexdigest())
        results=receipt['results']
        self.assertEqual(results['candidate']['rom_sha256'],
            'e2473cbaf4060896afaa7f30b5fc250729887ae02cc12cb15f183ea3bfa09405')
        self.assertFalse(results['broken']['chr_exact'])
        for name in ('stock','broken','candidate'):
            self.assertEqual(results[name]['frames'],3600)
            self.assertTrue(results[name]['complete'])

    def test_checked_in_health_assistance_leaves_cursor_native(self):
        for name in ('probe_secret_chr_entry.lua','probe_menu_icon_palettes.lua',
                     'probe_stage_side_by_side.lua','probe_stage1_no_bleed.lua',
                     'probe_boss_speed_parity.lua','probe_stage_speed.lua'):
            source=(ROOT/'scripts/diagnostics'/name).read_text()
            self.assertNotIn('write8(0xDCDD, 0x17)',source)
            self.assertNotIn('write8(0x1CDD,0x17)',source)
            self.assertNotIn('write8(0xDCDC, 0xFF)',source)
            self.assertNotIn('write8(0xDCDD, 0xFF)',source)
            self.assertNotIn('write8(0x1CDC,255)',source)

    def test_native_cursor_and_pause_handler_contract(self):
        path=ROOT/'rom/Penta Dragon (J).gb'
        if not path.exists(): self.skipTest('original ROM unavailable')
        rom=path.read_bytes()
        # Inventory selector: DCBD +10*DCDB + DCDD; pages contain10 slots.
        self.assertEqual(rom[0x1E08:0x1E1A],bytes.fromhex(
            'FADB DC 87 47 87 87 80 21BDDC D7 FADDDC D7 46 C9'))
        self.assertEqual(rom[0x21BE+12:0x21BE+14],bytes.fromhex('3D78'))
        self.assertEqual(rom[0x783D:0x7845],bytes.fromhex('3E3C EAF1DC C39877'))

    def test_retained_bad_cursor_is_rejected(self):
        p=ROOT/'tmp/reported-dense-secret-return-01/frame-3360.ss0'
        if not p.exists(): self.skipTest('retained bad assistance unavailable')
        raw=serialized_state(p)
        self.assertEqual(raw[0x3E4],1)
        self.assertEqual(raw[0x60DD],0x17)
        self.assertFalse(0 <= raw[0x60DD] < 10)

    def test_actual_pause_item_activation(self):
        for name in ('reported-pause-item-return-01','star-pause-item-return-01'):
            with self.subTest(name=name):
                p=ROOT/'tmp'/name
                if not (p/'receipt.json').exists(): self.skipTest('local item-action run unavailable')
                receipt=json.loads((p/'receipt.json').read_text())
                self.assertEqual(receipt['status'],0)
                with (p/'item-action.tsv').open() as f:
                    rows=list(csv.DictReader(f,delimiter='\t'))
                self.assertEqual(len(rows),10800)
                menu=[r for r in rows if r['menu']=='1']
                self.assertTrue(menu)
                self.assertTrue(all(0 <= int(r['cursor']) < 10 for r in menu))
                active=[r for r in rows if int(r['pause_timer'])>0]
                self.assertTrue(active)
                self.assertEqual(active[0]['pause_timer'],'60')
                self.assertEqual(active[0]['menu'],'0')
                self.assertEqual(active[0]['group'],'1')
                self.assertEqual(active[0]['cursor'],'1')
                self.assertEqual(rows[3298]['slot1'],'7')
                self.assertEqual(active[0]['slot1'],'8')
                self.assertEqual(rows[-1]['pause_timer'],'0')
                final=serialized_state(p/'frame-10800.ss0')
                # The corrected cursor/resource setup changes the trajectory:
                # both runs return to Stage1, then reach a native miniboss.
                # Do not mistake a plausible dungeon PNG for terminal scene02.
                with (p/'trace.tsv').open() as f:
                    route=list(csv.DictReader(f,delimiter='\t'))
                self.assertTrue(any(int(r['frame'])>8000 and (r['scene'],r['stage'])==('02','00') for r in route))
                self.assertEqual((final[0x5C80],final[0x3BA],final[0x3E4],final[0x3BF]),(10,0,0,2))


if __name__=='__main__': unittest.main()
