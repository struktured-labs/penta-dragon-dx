"""Reject retired flags and prove the exact packed request/consumer boundary."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'scripts/diagnostics')]
from menu_commit_protocol import authenticate, expected_parts, NAME
from test_capture_probe_contracts import run_lua


class CompletedMapProtocol(unittest.TestCase):
    def test_every_owned_byte_is_authenticated(self):
        rom = bytearray(b'\xff'*0x80000)
        offsets = []
        for bank, address, code in expected_parts():
            start = bank*0x4000+address-(0x4000 if bank else 0)
            rom[start:start+len(code)] = code
            offsets.extend(range(start,start+len(code)))
        self.assertEqual(authenticate(rom)['name'], NAME)
        self.assertEqual(authenticate(rom)['post_pc'], 0x7459)
        for offset in offsets:
            rom[offset] ^= 1
            with self.assertRaises(ValueError, msg=hex(offset)): authenticate(rom)
            rom[offset] ^= 1

    def test_request_and_consumption_require_real_paired_store(self):
        text = (ROOT/'scripts/diagnostics/probe_menu_window_order.lua').read_text()
        functions = text.split('local function inject_completed_map()',1)[1].split('\nif FORCE_COMMIT_FRAME >= 0 then',1)[0]
        run_lua(self, '''
local COMMIT_PROTOCOL='ffc4-absolute-ready-page-scy-df5c-scx-r443'
local forced_commit,forced_commit_consumed=false,false
local forced_commit_target,forced_commit_scx,forced_commit_scy
local mem,writes={},{}
emu={read8=function(self,a) return mem[a] or 0 end,
 write8=function(self,a,v) assert(a==0xFFC4 or a==0xDF5C);mem[a]=v;writes[a]=v end,
 memory={wram={read8=function(self,a) return mem[a] or 0 end}}}
local function inject_completed_map()''' + functions + '''
for page=0,1 do for x=0,15 do for y=0,15 do
 mem={[0xFF40]=page*0x40,[0x1C00]=x,[0x1C02]=y,[0xFF99]=13}
 forced_commit_consumed=false; inject_completed_map()
 assert(mem[0xFFC4]==0xC0+page*0x10+y and mem[0xDF5C]==x)
 observe_completed_map(); assert(not forced_commit_consumed)
 mem[0xFFC4]=0;mem[0xFF42]=y;mem[0xFF43]=x
 mem[0xFF40]=0x48;observe_completed_map();assert(not forced_commit_consumed)
 mem[0xFF40]=page==1 and 0x08 or 0x40
 mem[0xFF99]=1;observe_completed_map();assert(not forced_commit_consumed)
 mem[0xFF99]=13;mem[0xFF42]=(y+1)%16
 observe_completed_map();assert(not forced_commit_consumed)
 mem[0xFF42]=y;mem[0xFF43]=(x+1)%16
 observe_completed_map();assert(not forced_commit_consumed)
 mem[0xFF43]=x;observe_completed_map();assert(forced_commit_consumed)
 for _,pending in ipairs({0x20,0x40,0xC0}) do
  mem[0xFFC4]=pending;assert(not pcall(inject_completed_map))
 end
end end end
COMMIT_PROTOCOL='retired';mem[0xFFC4]=0;assert(not pcall(inject_completed_map))
''')


if __name__=='__main__': unittest.main()
