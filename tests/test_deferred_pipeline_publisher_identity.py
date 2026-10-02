from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_stage1_spike_palettes import publication_boundary, semantic_expansion_is_exact
from verify_stage1_north_integrity import detect_publication_boundary


class PipelineIdentityTests(unittest.TestCase):
    def test_r453_spike_probe_matches_python_identity(self):
        rom = (ROOT / 'tmp/title-nightfall-port/d82-r453-title-attract-recovery/candidate.gb').read_bytes()
        boundary = publication_boundary(rom)
        self.assertTrue(semantic_expansion_is_exact(rom))
        self.assertEqual(boundary, {'variant': 'r449f-title-v6-15ab73c3', 'pc': 0x7457})
        probe = (ROOT / 'scripts/diagnostics/probe_stage1_spike_palettes.lua').read_text()
        selection = probe.split('PENTA_R449F_PREHELPER_PUBLICATION =', 1)[1].split('PENTA_R351_PUBLICATION =', 1)[0]
        self.assertIn('"' + boundary['variant'] + '"', selection)
        for offset in (0x12E0, 0x37457, 0x37462, 0x77777):
            changed = bytearray(rom)
            changed[offset] ^= 1
            with self.assertRaises(RuntimeError):
                publication_boundary(changed)
            self.assertFalse(semantic_expansion_is_exact(changed))

    def test_r445c_v6_exact_identity(self):
        rom=(ROOT/'tmp/title-nightfall-port/r443e3f2-v6-r445c/candidate.gb').read_bytes()
        self.assertEqual(detect_publication_boundary(rom)['publication_pc'],0x7457)
        for offset in (0x37457,0x37462,0x5EC80,0x66C80,0x37703,0x72C80,0x77777):
            changed=bytearray(rom);changed[offset]^=1
            with self.assertRaises(RuntimeError): publication_boundary(changed)

    def test_combined_title_v5_exact_identity(self):
        rom=(ROOT/'tmp/title-nightfall-port/r443e3-v5/candidate.gb').read_bytes()
        self.assertEqual(detect_publication_boundary(rom)['publication_pc'],0x7457)
        self.assertEqual(rom[0x12F4:0x12FC],bytes.fromhex('F0 40 EE 08 E0 40 18 05'))
        for offset in (0x37457,0x37462):
            self.assertEqual(rom[offset:offset+2],bytes.fromhex('E0 40'))
        for offset in (0x37457,0x37462,0x5EC80,0x66C80,0x37701,0x77777):
            changed=bytearray(rom);changed[offset]^=1
            with self.assertRaises(RuntimeError): publication_boundary(changed)

    def test_r443d_exact_identity(self):
        rom=(ROOT/'tmp/later-stage-deferred-dma-r443d/candidate.gb').read_bytes()
        self.assertEqual(detect_publication_boundary(rom)['publication_pc'],0x7457)
        changed=bytearray(rom);changed[0x3770E]^=1
        with self.assertRaises(RuntimeError): publication_boundary(changed)

    def test_reload_dealias_exact_identity(self):
        rom=(ROOT/'tmp/reload-flag-dealias-r443e/candidate.gb').read_bytes()
        self.assertEqual(detect_publication_boundary(rom)['publication_pc'],0x7457)
        for offset in (0x37457,0x37462,0x3770E,0x37D18,0x77777):
            changed=bytearray(rom);changed[offset]^=1
            with self.assertRaises(RuntimeError): publication_boundary(changed)

    def test_title_v4_exact_identity(self):
        rom=(ROOT/'tmp/title-nightfall-port/r442-v4/candidate.gb').read_bytes()
        self.assertEqual(detect_publication_boundary(rom)['publication_pc'],0x7457)
        for offset in (0x37457,0x37462,0x5EC80,0x77777):
            changed=bytearray(rom);changed[offset]^=1
            with self.assertRaises(RuntimeError): publication_boundary(changed)

    def test_corrected_map_source_identity_and_delta(self):
        old=(ROOT/'tmp/deferred-dma-pipeline-r397/candidate.gb').read_bytes()
        rom=(ROOT/'tmp/deferred-dma-pipeline-r397b/candidate.gb').read_bytes()
        offset=19*0x4000+0x2CCF
        self.assertEqual(old[offset],0xC4)
        self.assertEqual(rom[offset],0x01)
        self.assertTrue({i for i,(x,y) in enumerate(zip(old,rom)) if x!=y} <= {offset,0x14D,0x14E,0x14F})
        self.assertEqual(publication_boundary(rom)['variant'],'r397b-deferred-pipeline-7f1dcd6e')
        self.assertEqual(detect_publication_boundary(rom)['publication_pc'],0x7457)

    def test_exact_pipeline_lcdc_site(self):
        rom=(ROOT/'tmp/deferred-dma-pipeline-r397/candidate.gb').read_bytes()
        self.assertEqual(publication_boundary(rom),
                         {'variant':'r397-deferred-pipeline-1aeb2e66','pc':0x7457})
        self.assertEqual(detect_publication_boundary(rom)['publication_pc'],0x7457)

    def test_changes_anywhere_fail_closed(self):
        rom=(ROOT/'tmp/deferred-dma-pipeline-r397/candidate.gb').read_bytes()
        for offset in (0x13B3,0x42C6,0x3746D,26*0x4000+0x2C80,
                       28*0x4000+0x2C80,24*0x4000+0x2E00,0x77777):
            changed=bytearray(rom);changed[offset]^=1
            with self.assertRaises(RuntimeError): publication_boundary(changed)


if __name__=='__main__': unittest.main()
