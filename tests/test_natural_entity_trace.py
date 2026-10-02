from pathlib import Path
import unittest


class EntityTraceTests(unittest.TestCase):
    def test_observer_is_opt_in_physical_and_read_only(self):
        source = (Path(__file__).resolve().parents[1] /
                  'scripts/diagnostics/probe_stage1_natural_menu_bg.lua').read_text()
        section = source.split('-- Optional physical-bank observer;', 1)[1].split(
            'local frame = 0', 1)[0]
        self.assertIn('os.getenv("STAGE1_NATURAL_ENTITY_TRACE") == "1"', section)
        self.assertIn('0x1C00, 0x1EFF', section)
        self.assertIn('wram:read8(offset)', section)
        self.assertNotIn('emu:write', section)
        self.assertNotIn('setKeys', section)
        self.assertIn('entity_trace:close(); entity_trace = nil', source)
        self.assertLess(source.index('  entity_trace_frame(frame)'),
                        source.index('  emu:setKeys(keys)'))


if __name__ == '__main__':
    unittest.main()
