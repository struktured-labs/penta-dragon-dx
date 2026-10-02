"""Execute the live Lua geometry function with bounded phase witnesses."""
import subprocess
import unittest
from pathlib import Path


class TranslatedGeometry(unittest.TestCase):
    def test_actual_lua_phase_envelopes_and_outside_controls(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'scripts/diagnostics/probe_low_health_flicker.lua').read_text()
        fn='local function hazard_positions(read_tile)' + source.split('local function hazard_positions(read_tile)',1)[1].split('local function bind_cross_rom_fixture_hazards()',1)[0]
        # System Lua is 5.1; mGBA supports infix bit operations. Replace only
        # the byte mask with its exhaustively equivalent arithmetic spelling.
        self.assertEqual(fn.count('read_tile(column, row) & 0xEF'),1)
        for value in range(256):
            self.assertEqual(value-(value//16%2)*16,value & 0xEF)
        fn=fn.replace('read_tile(column, row) & 0xEF', 'mask(read_tile(column, row))')
        fn='local function mask(v) return v-math.floor(v/16)%2*16 end\n'+fn
        controls='''
for _, witness in ipairs({4,5,6,7,9,10}) do
  for _, tile in ipairs({0x64,0x69,0x74,0x79}) do
    local positions=hazard_positions(function(c,r)
      if r==2 and c==witness then return tile end
      return 0x02
    end)
    local count=0
    for offset,_ in pairs(positions) do
      assert(offset>=68 and offset<=81)
      count=count+1
    end
    assert(count==14)
    assert(positions[71] and positions[79]) -- retracted/moving endpoints
    assert(not positions[67] and not positions[82])
  end
end
-- A stray tooth beyond the envelope must not legitimize a new hazard row.
for _, column in ipairs({18,23,31}) do
  local p=hazard_positions(function(c,r)
    return r==2 and c==column and 0x64 or 0x02
  end)
  assert(next(p)==nil)
end
local p=hazard_positions(function(c,r) return 0x02 end)
assert(next(p)==nil)
for _, column in ipairs({0,1,2,3}) do
  local p=hazard_positions(function(c,r)
    return r==2 and c==column and 0x65 or 0x02
  end)
  local n=0
  for offset,_ in pairs(p) do assert(offset>=64 and offset<=77);n=n+1 end
  assert(n==14 and not p[78])
end
'''
        subprocess.run(['lua','-'],input=fn+controls,text=True,check=True,capture_output=True)
