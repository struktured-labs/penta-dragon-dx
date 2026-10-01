"""Issue #6: negative controls and bounded emitter transform contracts."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts/diagnostics'), str(ROOT/'scripts')]
import build_sara_atomic_pose as builder
import verify_sara_pose as verifier

def execute_tail(code, a, flags, c, e):
    """Execute the landed tail bytes, not a reimplementation of its branch."""
    stack, pc, enabled, writes = [(0,c)], 0, False, []
    for _ in range(32):
        op = code[pc]
        pc += 1
        if op == 0xF5: stack.append((a,flags))
        elif op == 0xAF: a,flags = 0,0x80
        elif op == 0xEA:
            addr = int.from_bytes(code[pc:pc+2],'little'); pc += 2
            writes.append((addr,a))
        elif op == 0x7B: a = e
        elif op == 0xFE:
            value = code[pc]; pc += 1
            flags = 0x40 | (0x80 if a == value else 0) | (0x10 if a < value else 0)
        elif op == 0x38:
            rel = code[pc]; pc += 1
            if flags & 0x10: pc += rel if rel < 128 else rel-256
        elif op == 0xFB: enabled = True
        elif op == 0xF1: a,flags = stack.pop()
        elif op == 0xC1: _,c = stack.pop()
        elif op == 0x79: a = c
        elif op == 0x4F: c = a
        elif op == 0xC6:
            value = code[pc]; pc += 1
            total = a+value
            flags = (0x80 if total&255 == 0 else 0) | (0x20 if (a&15)+(value&15)>15 else 0) | (0x10 if total>255 else 0)
            a = total&255
        elif op == 0xC9: return a,flags,enabled,writes,stack
        else: raise AssertionError(f'unexpected opcode {op:02X}')
    raise AssertionError('tail did not return')

def rows():
    result = []
    for i in range(720):
        base = 0x20+4*((i//45)%4)
        oam = ','.join(f'{j}:{80+(j//2)*8}:{80+(j%2)*8}:{base+j:02X}:02' for j in range(4))
        result.append(dict(sample=str(i+1),frame=str(i+523),ffbe='00',visible_oam=oam))
    return result

class SaraAtomicPoseTests(unittest.TestCase):
    def test_complete_animated_quartets_pass(self):
        self.assertEqual(verifier.check_rows(rows(),720)['status'],'pass')

    def test_observed_three_new_one_old_pose_fails(self):
        data = rows()
        data[138]['visible_oam'] = '0:80:80:2D:22,1:80:88:2C:22,2:88:80:2F:22,3:88:88:2A:22'
        report = verifier.check_rows(data,720)
        self.assertEqual(report['status'],'fail')
        self.assertEqual(report['failures'][0]['sample'],139)

    def test_two_old_two_new_fails(self):
        data = rows()
        data[0]['visible_oam'] = '0:80:80:2D:22,1:80:88:2C:22,2:88:80:2B:22,3:88:88:2A:22'
        self.assertEqual(verifier.check_rows(data,720)['status'],'fail')

    def test_complete_tiles_with_displaced_quadrant_fail(self):
        # The old tile-set/raster checks both accept a faithfully rendered
        # displaced quadrant. Coherent position is an independent requirement.
        for y, x in ((89, 88), (88, 89)):
            data = rows()
            data[0]['visible_oam'] = (
                f'0:80:80:20:02,1:80:88:21:02,2:88:80:22:02,3:{y}:{x}:23:02')
            result = verifier.check_rows(data, 720)
            self.assertEqual(result['status'], 'fail')
            self.assertEqual(result['failures'][0]['reason'], 'split walking geometry')

    def test_missing_tile_or_duplicate_tile_fails(self):
        for replacement in ('0:80:80:20:02,1:80:88:21:02,2:88:80:22:02',
                            '0:80:80:20:02,1:80:88:21:02,2:88:80:22:02,3:88:88:22:02'):
            data = rows()
            data[0]['visible_oam'] = replacement
            self.assertEqual(verifier.check_rows(data,720)['status'],'fail')

    def test_no_evidence_or_frozen_pose_cannot_pass(self):
        self.assertEqual(verifier.check_rows([],720)['status'],'fail')
        data = rows()
        for row in data: row['visible_oam'] = data[0]['visible_oam']
        self.assertEqual(verifier.check_rows(data,720)['status'],'fail')

    def test_missing_or_reordered_samples_fail(self):
        data = rows()
        self.assertEqual(verifier.check_rows(data[:-1],720)['status'],'fail')
        data[0],data[1] = data[1],data[0]
        self.assertEqual(verifier.check_rows(data,720)['status'],'fail')

    def test_builder_rejects_unknown_parent_and_preserves_width(self):
        with self.assertRaises(ValueError): builder.build(b'unknown')
        self.assertEqual(len(builder.body()),len(builder.OLD))
        self.assertEqual(len(builder.body()),60)

    def test_palette_and_priority_folds_exhaustive(self):
        for form in range(256):
            self.assertEqual(1+int(form < 1),2 if form == 0 else 1)
        for attr in range(256):
            for palette in range(8):
                self.assertEqual((attr & ~128 & 248)|palette,(attr & 120)|palette)

    def test_landed_tail_preserves_flags_stack_and_only_defers_first_three(self):
        tail = builder.body()[0xDA4D-0xDA21:]
        for c in range(256):
            for flags in range(0,256,16):
                for slot in range(40):
                    expected_flags = (0x80 if (c+8)&255 == 0 else 0) | (0x20 if (c&15)+8>15 else 0) | (0x10 if c+8>255 else 0)
                    self.assertEqual(execute_tail(tail,c,flags,c,4*(slot+1)),
                                     ((c+8)&255,expected_flags,slot >= 3,[(0x1FFF,0)],[]))

    def test_unknown_tail_instruction_is_not_silently_accepted(self):
        with self.assertRaises(AssertionError): execute_tail(b'\0',0,0,0,4)

    def test_exact_candidate_changes_only_both_emitter_images_and_checksum(self):
        parent = ROOT/'tmp/spike-death-trial-05/candidate.gb'
        if not parent.exists(): self.skipTest('retained parent unavailable')
        source = parent.read_bytes()
        candidate = builder.build(source)
        self.assertEqual(builder.authenticated_parent(candidate),source)
        corrupted = bytearray(candidate)
        corrupted[0x20000] ^= 1
        with self.assertRaises(ValueError): builder.authenticated_parent(corrupted)
        allowed = {0x14E,0x14F}
        for bank in (13,16):
            start = bank*0x4000+0x3B21
            allowed.update(range(start,start+60))
            self.assertEqual(candidate[start:start+60],builder.body())
        self.assertLessEqual({i for i,(a,b) in enumerate(zip(source,candidate)) if a != b},allowed)
        self.assertEqual(candidate[0x20000:0x20300],source[0x20000:0x20300])

    def test_release_matrix_includes_both_ordinary_input_routes(self):
        from verify_release_candidate import build_gates
        gates = {gate.name:gate for gate in build_gates(Path('absent.gb'),ROOT/'tmp/unit-only')}
        walking = gates['sara_walking_pose_atomicity'].command
        firing = gates['sara_firing_pose_atomicity'].command
        self.assertIn('absent.gb',walking)
        self.assertIn('--fire',firing)
        self.assertIn('17',firing)

    def test_raster_missing_pixel_negative_control(self):
        from PIL import Image
        image = Image.new('RGB',(160,144),(0,0,0))
        expected = {(80,80):(255,128,0)}
        self.assertEqual(len(verifier.missing_pixels(image,expected)),1)
        image.putpixel((80,80),expected[(80,80)])
        self.assertEqual(verifier.missing_pixels(image,expected),[])

    def test_inherited_component_contracts_authenticate_exact_successor(self):
        import menu_commit_protocol
        from verify_stage1_spike_palettes import publication_boundary, semantic_expansion_is_exact
        from verify_menu_icon_palettes import menu_oracle
        from stage_card_palette_handoff import inspect_stage_card_palette_handoff
        parent = ROOT/'tmp/spike-death-trial-05/candidate.gb'
        if not parent.exists(): self.skipTest('retained parent unavailable')
        source = parent.read_bytes()
        candidate = builder.build(source)
        for inspect in (menu_commit_protocol.authenticate, publication_boundary,
                        semantic_expansion_is_exact, menu_oracle,
                        inspect_stage_card_palette_handoff):
            with self.subTest(component=inspect.__name__):
                self.assertEqual(inspect(candidate),inspect(source))
        unknown = bytearray(candidate)
        unknown[25*0x4000] ^= 1
        with self.assertRaises(ValueError): menu_commit_protocol.authenticate(unknown)

    def test_hazard_contract_authenticates_successor_and_rejects_changed_hazard_code(self):
        from verify_stage1_spike_palettes import semantic_expansion_is_exact, SEMANTIC_HELPER_ENTRY
        parent = ROOT/'tmp/spike-death-trial-05/candidate.gb'
        if not parent.exists(): self.skipTest('retained parent unavailable')
        candidate = builder.build(parent.read_bytes())
        self.assertTrue(semantic_expansion_is_exact(candidate))
        corrupted = bytearray(candidate)
        corrupted[20*0x4000 + SEMANTIC_HELPER_ENTRY-0x4000] ^= 1
        self.assertFalse(semantic_expansion_is_exact(corrupted))

if __name__ == '__main__': unittest.main()
