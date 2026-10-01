"""#40 combined Sara helper observer: exact layout and retained gate failures."""
import ctypes
import json
from pathlib import Path
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from build_sara_doorway_priority import helper


class CombinedObserver(unittest.TestCase):
    def test_lua_compiles_without_executing_emulator(self):
        try:
            lua=ctypes.CDLL('liblua5.4.so')
        except OSError:
            self.skipTest('Lua 5.4 library unavailable')
        lua.luaL_newstate.restype=ctypes.c_void_p
        lua.luaL_loadfilex.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_char_p]
        lua.lua_tolstring.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p]
        lua.lua_tolstring.restype=ctypes.c_char_p
        lua.lua_close.argtypes=[ctypes.c_void_p]
        state=lua.luaL_newstate()
        try:
            result=lua.luaL_loadfilex(state,str(ROOT/'scripts/diagnostics/probe_stage_speed.lua').encode(),None)
            self.assertEqual(result,0,lua.lua_tolstring(state,-1,None) if result else '')
        finally:
            lua.lua_close(state)

    def test_authenticates_complete_combined_helper_and_callsite(self):
        source=(ROOT/'scripts/diagnostics/probe_stage_speed.lua').read_text()
        signatures=dict((int(a,16),bytes.fromhex(b)) for a,b in
                        re.findall(r"matches\(0x([A-F0-9]+), '([A-F0-9]+)'\)",source))
        self.assertEqual(signatures[0xDB40],helper(combined=True))
        self.assertEqual(signatures[0xDA41],bytes.fromhex('2ACD40DB000000E6F8B11213'))
        rom_path=ROOT/'tmp/arena-completion-safe-trial-01/candidate.gb'
        if rom_path.exists():
            rom=rom_path.read_bytes()
            self.assertEqual(rom[0x37b41:0x37b41+len(signatures[0xDA41])],signatures[0xDA41])
            self.assertEqual(rom[33*0x4000+0x40:33*0x4000+0x40+len(signatures[0xDB40])],signatures[0xDB40])

    def test_retained_missing_telemetry_is_not_accepted(self):
        base=ROOT/'tmp/arena-completion-safe-stage1-speed-01/receipt.json'
        if not (base/'manifest.json').exists():
            self.skipTest('local failing run unavailable')
        result=json.loads((base/'stage1-dx-a-loop-patrol/result.json').read_text())
        self.assertEqual(result['central_x_entry_11a2'],0)
        self.assertEqual(result['central_x_entry_11a5'],0)
        self.assertEqual(result['central_attr_samples'],0)
        manifest=json.loads((base/'manifest.json').read_text())
        self.assertNotEqual(manifest['status'],'pass')

    def test_fresh_observer_recovers_samples_without_hiding_route_failure(self):
        before=ROOT/'tmp/arena-completion-safe-stage1-speed-01/receipt.json'
        after=ROOT/'tmp/arena-completion-safe-stage1-speed-03'
        if not (after/'manifest.json').exists():
            self.skipTest('fresh observer replay unavailable')
        old=json.loads((before/'stage1-dx-a-loop-patrol/result.json').read_text())
        new=json.loads((after/'stage1-dx-a-loop-patrol/result.json').read_text())
        self.assertEqual(new['central_x_entry_db40'],12213)
        self.assertEqual(new['central_attr_samples'],12213)
        for field in ('main_loop_hits','central_emitter_hits','central_tile_counts','central_palette_counts'):
            self.assertEqual(new[field],old[field])
        manifest=json.loads((after/'manifest.json').read_text())
        self.assertNotEqual(manifest['status'],'pass')
        self.assertEqual((after/'stage1-dx-a-loop-patrol/attr-events.tsv').read_bytes(),
                         (before/'stage1-dx-a-loop-patrol/attr-events.tsv').read_bytes())


if __name__=='__main__':unittest.main()
