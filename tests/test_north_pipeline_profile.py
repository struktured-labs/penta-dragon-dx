"""Keep optional timing observation separate from normal release execution."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProfileTests(unittest.TestCase):
    def test_deferred_trace_is_exact_variant_gated_and_read_only(self):
        source=(ROOT/'scripts/diagnostics/probe_stage1_north_integrity.lua').read_text()
        section=source.split('local deferred_profile = nil',1)[1].split('pipeline_profile = assert',1)[0]
        self.assertIn('STAGE1_NORTH_PROFILE',section)
        self.assertIn('r397b-deferred-pipeline-7f1dcd6e',section)
        self.assertIn('emu:read8(sp + 8)',section)
        self.assertIn('latch & 0x60',section)
        self.assertNotIn('emu:write',section)
        self.assertIn('if deferred_profile then deferred_profile:close() end',source)

    def test_explicit_default_off_and_all_routes_wired(self):
        path = ROOT / 'scripts/diagnostics/verify_stage1_north_integrity.py'
        tree = ast.parse(path.read_text())
        function = next(n for n in tree.body
                        if isinstance(n, ast.FunctionDef) and n.name == 'run_route')
        self.assertEqual(function.args.args[-1].arg, 'profile_pipeline')
        self.assertIs(function.args.defaults[-1].value, False)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == 'run_route']
        self.assertEqual(len(calls), 3)
        for call in calls:
            self.assertEqual(sum(k.arg == 'profile_pipeline' for k in call.keywords), 1)

    def test_trace_uses_distinct_native_exit_and_does_not_write_game_memory(self):
        source = (ROOT / 'scripts/diagnostics/probe_stage1_north_integrity.lua').read_text()
        section = source.split('local pipeline_profile = nil', 1)[1].split(
            'local initial_room', 1)[0]
        self.assertIn('local points = CGB_ROM and', section)
        self.assertIn('{"tiles_end", 0x42ED, 1}', section)
        self.assertIn('{"tiles_end", 0x436D, 1}', section)
        self.assertIn('emu:currentCycle()', section)
        self.assertNotIn('emu:write', section)

    def test_profile_observes_relative_flips_and_queue_without_mutation(self):
        source = (ROOT / 'scripts/diagnostics/probe_stage1_north_integrity.lua').read_text()
        section = source.split('local pipeline_profile = nil', 1)[1].split(
            'local initial_room', 1)[0]
        self.assertIn('{"relative_commit", 0x745F, 13}', section)
        self.assertIn('tonumber(os.getenv("STAGE1_NORTH_PUBLICATION_PC"), 16) == 0x7457', section)
        self.assertIn('tonumber(os.getenv("STAGE1_NORTH_PUBLICATION_SEGMENT"), 16) == 13', section)
        for read in ('emu:read8(0xFF40)', 'emu:read8(0xFFC4)', 'wram:read8(0x1F5C)'):
            self.assertIn(read, section)
        self.assertNotIn('write8', section)
        self.assertNotIn('write16', section)

    def test_source_census_reads_fixed_wram_only_at_copy_entry(self):
        source = (ROOT / 'scripts/diagnostics/probe_stage1_north_integrity.lua').read_text()
        section = source.split('local pipeline_profile = nil', 1)[1].split(
            'local initial_room', 1)[0]
        self.assertIn('if label == "tiles_begin" then', section)
        self.assertIn('for index = 0, 575 do', section)
        self.assertIn('emu:read8(0xC1A0 + index)', section)
        self.assertIn('pipeline_sources:write(table.concat(source))', section)
        self.assertNotIn('emu:write', section)


if __name__ == '__main__':
    unittest.main()
