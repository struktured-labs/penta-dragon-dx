"""Native observer reads cannot accidentally consume a staging-bank alias."""
from pathlib import Path
import unittest
from test_capture_probe_contracts import run_lua

SOURCE=(Path(__file__).resolve().parents[1]/'scripts/diagnostics/probe_later_stage_soak.lua').read_text()


class PhysicalSoak(unittest.TestCase):
    def test_accessor_reads_physical_bank_without_bus_or_writes(self):
        block=SOURCE.split('local function game_read(address)',1)[1].split('\nend',1)[0]
        run_lua(self, '''
local calls=0
local game_wram={read8=function(self,a) calls=calls+1;assert(a==0x1880 or a==0x1F4C);return a==0x1880 and 5 or 0 end}
local function game_read(address)
'''+block+'''
end
for bank=0,7 do
  assert(game_read(0xD880)==5)
  assert(game_read(0xDF4C)==0)
end
assert(calls==16)
assert(not pcall(game_read,0xC880))
assert(not pcall(game_read,0xE880))
''')
        self.assertNotIn('emu:read8(0xD880)',SOURCE)
        self.assertNotIn('emu:read8(0xDF4C)',SOURCE)
        # Keep the separate CPU-bus accessibility guard for the old audit.
        self.assertIn('emu:read8(0xDF51) ~= 0xA8',SOURCE)
        self.assertIn('wram:read8(0x3280)',SOURCE)

    def test_whole_probe_compiles(self):
        self.assertNotIn(']====]', SOURCE)
        run_lua(self, 'assert(load([====['+SOURCE+']====]))')
