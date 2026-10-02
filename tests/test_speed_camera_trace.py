from pathlib import Path
import unittest

class CameraTraceTests(unittest.TestCase):
    def test_constant_cardinal_routes_only_set_normal_keys(self):
        root = Path(__file__).resolve().parents[1]
        source = (root/'scripts/diagnostics/probe_stage_speed.lua').read_text()
        cli = (root/'scripts/diagnostics/verify_stage_speed_matrix.py').read_text()
        for direction in ('left', 'up', 'down'):
            branch = source.split('  elseif INPUT_MODE == "'+direction+'" then\n', 1)[1].split('  elseif', 1)[0]
            self.assertEqual(branch.strip(), 'emu:setKeys(KEY_'+direction.upper()+')')
            self.assertIn('"'+direction+'"', cli.split('"--input-mode"', 1)[1].split('default=', 1)[0])

    def test_pc_sampling_is_opt_in_and_read_only(self):
        s=(Path(__file__).resolve().parents[1]/'scripts/diagnostics/probe_stage_speed.lua').read_text()
        self.assertIn('os.getenv("STAGE_SPEED_PC_TRACE") == "1"',s)
        trace=s.split('  if pc_trace and phase == "play" then',1)[1].split('  if camera_trace then',1)[0]
        self.assertIn('emu:readRegister("PC")',trace)
        self.assertIn('read8(0x1880)',trace)
        self.assertNotIn('write8',trace)
        self.assertNotIn('setKeys',trace)

    def test_opt_in_read_only_frame_observer(self):
        s=(Path(__file__).resolve().parents[1]/'scripts/diagnostics/probe_stage_speed.lua').read_text()
        self.assertIn('os.getenv("STAGE_SPEED_CAMERA_TRACE") == "1"',s)
        section=s.split('  frame = frame + 1\n',1)[1].split('  emu:write8(0xDCFD',1)[0]
        self.assertIn('if camera_trace then',section)
        self.assertIn('main_loop_hits, tile_copy_hits',section)
        for address in ('0x1880','0x1C00','0x1C02','0x1CB8'):
            self.assertIn('wram:read8('+address+')',section)
        self.assertIn('section_cycle', s)
        self.assertNotIn('emu:write',section)
        self.assertNotIn('setKeys',section)
        self.assertIn('if camera_trace then camera_trace:close(); camera_trace = nil end',s)

    def test_loop_routes_are_separate_and_cpu_anchored(self):
        root = Path(__file__).resolve().parents[1]
        s = (root/'scripts/diagnostics/probe_stage_speed.lua').read_text()
        anchor = s.split('main_loop_hits = main_loop_hits + 1', 1)[1].split('last_main_loop_frame = play_frames', 1)[0]
        for mode in ('loop-patrol', 'loop-vertical-patrol'):
            self.assertIn('INPUT_MODE == "' + mode + '"', anchor)
        self.assertEqual(anchor.count('(main_loop_hits - 1) % 30 < 15'), 2)
        self.assertIn('if play_frames % 120 < 60 then emu:setKeys(KEY_RIGHT)', s)
        self.assertIn('if play_frames % 120 < 60 then emu:setKeys(KEY_UP)', s)
        self.assertIn('The loop breakpoint owns these keys', s)

    def test_loop_trace_reads_full_positions_and_polled_input(self):
        root = Path(__file__).resolve().parents[1]
        s = (root/'scripts/diagnostics/probe_stage_speed.lua').read_text()
        trace = s.split('      if loop_trace then', 1)[1].split('      -- Separate diagnostic routes:', 1)[0]
        for addr in ('0x1C00', '0x1C01', '0x1C02', '0x1C03', '0x1CB8'):
            self.assertIn('wram:read8(' + addr + ')', trace)
        self.assertIn('emu:read8(0xFF93)', trace)
        self.assertIn('emu:read8(0xFFBF)', trace)
        for addr in ('0xFFC8', '0xFFC9', '0xFFCA', '0xFFD3', '0xFFEB', '0xFFE4'):
            self.assertIn('emu:read8(' + addr + ')', trace)
        self.assertNotIn('setKeys', trace)
        self.assertNotIn('write8', trace)
        self.assertIn('if loop_trace then loop_trace:close(); loop_trace = nil end', s)

if __name__=='__main__':unittest.main()
