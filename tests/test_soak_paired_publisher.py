"""Negative controls execute the actual Lua idempotent-store predicate."""
import subprocess
import unittest
from pathlib import Path


class PairedPublisher(unittest.TestCase):
    def test_only_same_frame_exact_repeat_is_exempt_from_hidden_target(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'scripts/diagnostics/probe_later_stage_soak.lua').read_text()
        expression=source.split('local repeat_store=',1)[1].split('trace_flip(site,base',1)[0].strip()
        code='''
local function repeat_allowed(site,primary_frame,primary_lcdc,play_frame,next_lcdc,actual)
  local emu={read8=function(self,address) assert(address==0xFF40);return actual end}
  return '''+expression+'''
end
assert(repeat_allowed(0x7462,12,0x8B,12,0x8B,0x8B))
assert(not repeat_allowed(0x7457,12,0x8B,12,0x8B,0x8B))
assert(not repeat_allowed(0x7462,nil,nil,12,0x8B,0x8B))
assert(not repeat_allowed(0x7462,11,0x8B,12,0x8B,0x8B))
assert(not repeat_allowed(0x7462,12,0x83,12,0x8B,0x8B))
assert(not repeat_allowed(0x7462,12,0x8B,12,0x8B,0x83))
'''
        subprocess.run(['lua','-'],input=code,text=True,check=True,capture_output=True)
        self.assertIn('else primary_frame,primary_lcdc=nil,nil end',source)
