"""Pre-final capture must witness the route, not exhaust a sample quota."""
from pathlib import Path
import unittest
from test_capture_probe_contracts import run_lua

SOURCE = (Path(__file__).resolve().parents[1] /
          'scripts/diagnostics/probe_ending_inventory_mgba.lua').read_text()


class PreFinalCompletion(unittest.TestCase):
    def test_actual_lua_route_tracker(self):
        tracker = SOURCE.split('local pre_final_sequence = {}', 1)[1].split(
            'local report =', 1)[0]
        run_lua(self, 'local pre_final_sequence = {}\n' + tracker + '''
local function see(art, committed, scene)
  observe_pre_final(scene or 0x19, {dce8=4,dcea=1,dcf0=art,
    dd07=committed and art-1 or 0})
end
assert(not pre_final_complete())
for i=1,100 do see(4,true) end
assert(not pre_final_complete())
for i=1,100 do see(7,true) end
assert(not pre_final_complete())
see(4,false); see(4,true,0x18)
assert(not pre_final_complete())
see(4,true)
assert(pre_final_complete())
see(4,true)
assert(pre_final_complete())
see(7,true)
assert(not pre_final_complete())
''')
        self.assertNotIn('samples >= 43', SOURCE)

    def test_probe_compiles(self):
        run_lua(self, 'assert(load([====[' + SOURCE + ']====]))')
