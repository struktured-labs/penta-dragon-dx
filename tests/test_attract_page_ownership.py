"""Exercise the actual Lua ownership callbacks, not a rewritten Python model."""
from pathlib import Path
import unittest
from test_capture_probe_contracts import run_lua

SOURCE=(Path(__file__).resolve().parents[1]/'scripts/diagnostics/probe_attract_pickup_palettes.lua').read_text()


class PageOwnership(unittest.TestCase):
    def test_copy_entry_owner_survives_logical_room_change(self):
        start=SOURCE.index('local pending_owners, page_owners')
        end=SOURCE.index('local function snapshot_range',start)
        stub='''
local hooks, stage, owner, hl, lcdc = {},0,1,0x9800,0x83
os.getenv=function(k) return k=='ATTRACT_PUBLICATION_PC' and '7457' or '0D' end
emu={setBreakpoint=function(self,fn,pc,bank) hooks[pc]=fn;return 1 end,
 read8=function(self,a) if a==0xFFBA then return stage end assert(a==0xFFE5);return owner end,
 readRegister=function(self,k) return k=='HL' and hl or lcdc end}
'''
        run_lua(self,stub+SOURCE[start:end]+'''
hooks[0x42A7]()
assert(page_owners[0x9800]==nil)
owner=3
hooks[0x7457]()
assert(page_owners[0x9800]==1 and owner_publications==1)
hooks[0x7457]()
assert(owner_publications==1)
hl=0x9C00;hooks[0x42A7]();lcdc=0x8B;hooks[0x7457]()
assert(page_owners[0x9C00]==3 and page_owners[0x9800]==1)
stage=1;owner=8;hooks[0x42A7]();hooks[0x7457]()
assert(page_owners[0x9C00]==3 and owner_publications==2)
stage=0;hl=0x8000;hooks[0x42A7]();lcdc=0;hooks[0x7457]()
assert(owner_invalid_events==2)
''')

    def test_white_exception_is_exact_and_only_before_first_publication(self):
        start=SOURCE.index('  local white_entry = false')
        end=SOURCE.index('  local cells = {}',start)
        block=SOURCE[start:end]
        run_lua(self,'''
local page_owners,base,owner_publications,owner_missing_frames,blank_entry_frames={},0x9800,0,0,0
local index,bad=0xBC,false
emu={read8=function(self,a) if a==0xFF68 then return index end
 assert(a==0xFF69);return bad and 0 or (index%2==0 and 255 or 127) end,
 write8=function(self,a,v) assert(a==0xFF68);index=v end}
local function sample()
'''+block+'''
 return white_entry
end
assert(sample() and blank_entry_frames==1 and index==0xBC)
bad=true;assert(not sample() and blank_entry_frames==1 and index==0xBC)
bad=false;owner_publications=1
assert(not sample() and owner_missing_frames==1 and blank_entry_frames==1)
page_owners[base]=1
assert(not sample() and owner_missing_frames==1)
''')


if __name__=='__main__':unittest.main()
