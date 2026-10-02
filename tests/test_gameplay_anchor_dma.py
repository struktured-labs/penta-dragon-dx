from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/diagnostics')]
from gameplay_anchor_dma import validate_dma_resume,DMA_LOOP,GB_STATE_SIZE
from test_capture_probe_contracts import run_lua


class DmaAnchor(unittest.TestCase):
    def test_only_exact_native_loop_may_be_settled(self):
        raw=bytearray(GB_STATE_SIZE)
        raw[0x17E]=131;raw[0x2A:0x2C]=bytes.fromhex('8DFF')
        raw[0x380:0x391]=DMA_LOOP;raw[0x168]=1
        self.assertTrue(validate_dma_resume(raw))
        raw[0x168]=13
        self.assertTrue(validate_dma_resume(raw))
        raw[0x168]=32
        with self.assertRaises(ValueError):validate_dma_resume(raw)
        raw[0x168]=1
        for offset in range(0x380,0x391):
            mutant=bytearray(raw);mutant[offset]^=1
            with self.assertRaises(ValueError):validate_dma_resume(mutant)
        raw[0x2A:0x2C]=bytes.fromhex('6C01')
        with self.assertRaises(ValueError):validate_dma_resume(raw)
        raw[0x17E]=0
        self.assertFalse(validate_dma_resume(raw))

    def test_capture_lua_compiles_and_no_process_exit(self):
        for name in ('probe_gameplay_obj_palettes.lua','probe_gameplay_dma_boundary.lua'):
            source=(ROOT/'scripts/diagnostics'/name).read_text()
            self.assertNotIn('os.exit(',source)
            run_lua(self,'assert(load([====['+source+']====]))')
        source=(ROOT/'scripts/diagnostics/probe_gameplay_dma_boundary.lua').read_text()
        self.assertLess(source.index('loadStateFile'),source.index('setBreakpoint'))
        self.assertNotIn(':write8(',source)
