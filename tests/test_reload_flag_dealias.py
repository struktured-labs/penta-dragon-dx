from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_stage1_spike_palettes import publication_boundary


class ReloadFlagTests(unittest.TestCase):
    def test_title_composition_preserves_gameplay_reload_and_isr(self):
        import build_title_color_prototype as title
        base=(ROOT/'tmp/reload-flag-dealias-r443e3/candidate.gb').read_bytes()
        rom=(ROOT/'tmp/title-nightfall-port/r443e3-v5/candidate.gb').read_bytes()
        # Gameplay palette image, reload body, and pending-flag cave survive.
        for start,end in ((0x36800,0x36840),(0x37407,0x37464),(0x37701,0x3771E)):
            self.assertEqual(rom[start:end],base[start:end])
        body=base[0x66C80:0x66CC9]
        v5_head=bytes.fromhex('F0 40 CB 7F CA 00 6D CD 00 6D')
        self.assertEqual(rom[0x66C80:0x66C80+len(v5_head)],v5_head)
        start=0x66C80+len(v5_head)
        self.assertEqual(rom[start:start+len(body)],body)
        palettes=title.build_palette_block(title.SCHEMES['Nightfall'])
        self.assertEqual(rom[0x66240:0x66240+len(palettes)],palettes)

    def test_cleaner_and_its_branch_join_are_unchanged(self):
        old=(ROOT/'tmp/later-stage-deferred-dma-r443d/candidate.gb').read_bytes()
        new=(ROOT/'tmp/reload-flag-dealias-r443e3/candidate.gb').read_bytes()
        self.assertEqual(new[0x36E00:0x36E60],old[0x36E00:0x36E60])
        self.assertEqual(new[0x36E0B:0x36E0D],bytes.fromhex('28 1D'))
        self.assertEqual(new[0x36E2A:0x36E2D],bytes(3))
        for address,size in ((0x11C3,0x30),(0x07A0,0x12),(0x0AF0,0x0C)):
            self.assertEqual(new[address:address+size],old[address:address+size])

    def test_guard_precedes_request_read_and_identity_is_exact(self):
        rom=(ROOT/'tmp/reload-flag-dealias-r443e3/candidate.gb').read_bytes()
        self.assertEqual(rom[0x37701:0x3770C],bytes.fromhex('FA 80 D8 FE 02 C2 2D 74 FA 5D DF'))
        self.assertEqual(publication_boundary(rom)['pc'],0x7457)
        for address in (0x36E2A,0x37701,0x37D18):
            changed=bytearray(rom);changed[address]^=1
            with self.assertRaises(RuntimeError):publication_boundary(changed)


if __name__=='__main__':unittest.main()
