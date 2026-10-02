"""#46: exact terminal-generation handling, with corruption counterexamples."""
from pathlib import Path
import csv
import hashlib
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from check_boss_menu_fades import return_map_generation, return_map_readiness, inspect_roundtrips


class ReturnMapGeneration(unittest.TestCase):
    def test_trace_control_neutrality_and_completed_page_flip(self):
        captures=[]
        for name in ('shalamar-map-publication-window-01','shalamar-map-publication-control-01'):
            path=ROOT/'tmp'/name/'receipt.json'
            if not path.exists():self.skipTest('local publication replay unavailable')
            receipt=json.loads(path.read_text())
            self.assertEqual(receipt['status'],0)
            self.assertFalse(receipt['observer_memory_writes'])
            self.assertEqual(receipt['rom_sha256'],'916ebb1858c6b9e91491081d82e93d00d283180ef44323f1f29c37a033e48deb')
            self.assertEqual(receipt['source_state_sha256'],'154c8c0051cfa3785516e14a908f22e3d2d190719c22a39b8f717d6d975d8681')
            self.assertEqual(receipt['native_capture']['metadata']['frames'],60)
            captures.append(receipt)
        for ext in ('video','states','s16le','timeline.tsv'):
            hashes=[]
            for receipt in captures:
                path=Path(receipt['native_capture_directory'])/f'native.{ext}'
                digest=hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(digest,receipt['native_capture']['hashes'][path.name])
                hashes.append(digest)
            self.assertEqual(*hashes)
        raw=(Path(captures[0]['native_capture_directory'])/'native.states').read_bytes()
        def state(frame):return raw[(frame-1)*71680:frame*71680]
        def selected(s):
            page=0x2000 if s[0x340]&8 else 0x1c00
            return bytes(s[page+r*32+c] for r in range(24) for c in range(24))
        completed=state(17)[0x45a0:0x47e0]
        for frame in range(18,24):self.assertEqual(selected(state(frame)),completed)
        self.assertNotEqual(state(18)[0x45a0:0x47e0],completed)
        self.assertEqual(state(24)[0x340]&8,0)
        self.assertEqual(selected(state(24)),state(24)[0x45a0:0x47e0])
        with (ROOT/'tmp/shalamar-map-publication-window-01/return-publication.tsv').open() as stream:
            writes=list(csv.DictReader(stream,delimiter='\t'))
        flips=[r for r in writes if r['address']=='FF40' and r['old']=='8B' and r['new']=='83']
        self.assertEqual((int(flips[0]['frame']),int(flips[0]['ly'])),(23,8))

    def fixture(self):
        previous=bytearray(71680)
        previous[0x347]=0x90
        source=bytes(i%251 for i in range(576))
        previous[0x45a0:0x47e0]=source
        for row in range(24):
            previous[0x1c00+row*32:0x1c00+row*32+24]=source[row*24:row*24+24]
        current=bytearray(previous)
        current[0x347]=0xe4
        current[0x45a0]^=1
        return previous,current

    def test_terminal_retains_completed_pose_and_reports_next_source_difference(self):
        previous,current=self.fixture()
        differences,generation=return_map_generation(current,previous)
        self.assertEqual(generation,'previous_completed_source')
        self.assertEqual(differences,[dict(row=0,column=0,expected=1,actual=0)])

    def test_corruption_and_incomplete_reference_are_never_accepted(self):
        for mutation in ('display','previous_display','intermediate','wrong_previous_shade','missing'):
            with self.subTest(mutation=mutation):
                previous,current=self.fixture()
                if mutation=='display': current[0x1c01]^=1
                if mutation=='previous_display': previous[0x1c01]^=1
                if mutation=='intermediate': current[0x347]=0x40
                if mutation=='wrong_previous_shade': previous[0x347]=0
                if mutation=='missing': previous=None
                differences,generation=return_map_generation(current,previous)
                self.assertTrue(differences)
                self.assertIsNone(generation)

    def test_current_source_match_remains_accepted(self):
        previous,_=self.fixture()
        self.assertEqual(return_map_generation(previous),( [],'current_source'))

    def test_real_flagged_frame_and_scene_failure_remain_distinct(self):
        folder=ROOT/'tmp/current-map-shalamar-phase721-01'
        if not (folder/'frame-1080.ss0').exists():self.skipTest('local replay unavailable')
        result=return_map_readiness(folder,720,540)
        self.assertEqual(result['status'],'PASS')
        terminal=result['observations'][-1]
        self.assertEqual((terminal['frame'],terminal['reference_frame']),(598,597))
        self.assertEqual(len(terminal['mismatches']),8)
        self.assertEqual(terminal['accepted_generation'],'previous_completed_source')
        full=inspect_roundtrips(folder,12,721)
        self.assertEqual(full['status'],'FAIL')
        self.assertTrue(full['scene_route_failures'])
        self.assertEqual([c['status'] for c in full['cycles']],['PASS']*3)
