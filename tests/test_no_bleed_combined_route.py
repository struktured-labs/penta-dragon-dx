import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CombinedRoute(unittest.TestCase):
    def test_actual_lua_movement_schedule(self):
        source = (ROOT/'scripts/diagnostics/probe_stage1_no_bleed.lua').read_text()
        self.assertIn('local BOX_LEG_FRAMES = 100', source)
        self.assertIn('route_frame % (4 * BOX_LEG_FRAMES)', source)
        block = source[
            source.index('  local route_mode, route_frame'):
            source.index('  -- Fire periodically')
        ]
        lua = ('local KEY_RIGHT,KEY_LEFT,KEY_UP,KEY_DOWN=16,32,64,128\n'
               'local BOX_LEG_FRAMES=100\n'
               'local function movement_at(INPUT_MODE,play_frames)\n'
               '  local movement\n'+block+
               '\nreturn movement\nend\n'
               'for f=1,3599 do assert(movement_at("vertical-box",f)==movement_at("vertical",f)) end\n'
               'for f=3600,7200 do assert(movement_at("vertical-box",f)==movement_at("box",f-3600)) end\n')
        subprocess.run(['lua','-'], input=lua, text=True, check=True)
