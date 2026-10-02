import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
import verify_stage2_flip_attributes as v


class Stage2FlipAttributes(unittest.TestCase):
    def test_later_stage_saved_publications_reject_wrong_attributes(self):
        directory=ROOT/'tmp/astra-r441-later-stage-soaks'
        for stage in range(3,8):
            with self.subTest(stage=stage):
                fields=(directory/f'stage{stage}.flip-events.tsv').read_text().splitlines()[0].split('\t')
                site=int(fields[2],16);base=int(fields[5],16)
                state=v.serialized_state(directory/(f'stage{stage}.'+fields[13]))
                v.audit_state(state,site,base,stage)
                for row,col in ((0,0),(12,12),(23,23)):
                    bad=bytearray(state)
                    bad[v.VRAM1+base-0x8000+row*32+col]^=1
                    with self.assertRaises(ValueError):v.audit_state(bad,site,base,stage)
                with self.assertRaises(ValueError):v.audit_state(state,site,base,2)

    def test_stage_specific_semantics(self):
        for stage,tile,expected in ((2,0xAE,2),(3,0x88,1),(4,1,4),
                (4,0x2D,2),(5,2,5),(5,0x12,5),(6,0x88,1),
                (7,0x19,5),(7,0xA0,4),(7,0xAE,2),
                (2,0x19,0),(3,0xAE,0),(6,0xA0,0),(5,0x18,0)):
            with self.subTest(stage=stage,tile=tile):
                self.assertEqual(v.expected_attr(stage,tile),expected)
        with self.assertRaises(ValueError):v.expected_attr(8,0)

    def test_saved_publication_and_machine_mutations(self):
        directory=ROOT/'tmp/astra-r441-stage2-flip-states'
        fields=(directory/'stage2.flip-events.tsv').read_text().splitlines()[0].split('\t')
        site=int(fields[2],16);base=int(fields[5],16)
        state=v.serialized_state(directory/('stage2.'+fields[13]))
        v.audit_state(state,site,base)
        for offset in (v.CPU_PC,v.CPU_A,v.MEMORY_CURRENT_ROM_BANK,
                v.MEMORY_CURRENT_WRAM_BANK,v.WRAM1+0x880,
                v.VRAM0+base-0x8000,v.VRAM1+base-0x8000,
                v.VRAM1+base-0x8000+23*32+23):
            bad=bytearray(state);bad[offset]^=8 if offset==v.CPU_A else 1
            with self.assertRaises(ValueError):v.audit_state(bad,site,base)
        with self.assertRaises(ValueError):v.audit_state(state,site,0x9A00)
