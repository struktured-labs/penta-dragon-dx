"""Run actual probe callbacks with inaccessible banked Dxxx bus memory."""
import ast
import ctypes
import ctypes.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class LiveProbeWram(unittest.TestCase):
    @unittest.skipUnless(ctypes.util.find_library("lua5.4"), "Lua 5.4 unavailable")
    def test_probes_use_physical_game_bank_without_touching_bus_alias(self):
        tree = ast.parse((ROOT / "scripts/probes/verify_miniboss_color.py").read_text())
        miniboss = next(ast.literal_eval(node.value) for node in tree.body
                        if isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "PROBE" for t in node.targets))
        gameplay = (ROOT / "scripts/diagnostics/probe_gameplay_obj_palettes.lua").read_text()
        lua = ctypes.CDLL(ctypes.util.find_library("lua5.4"))
        lua.luaL_newstate.restype = ctypes.c_void_p
        lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
        lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lua.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_longlong, ctypes.c_void_p]
        lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        lua.lua_tolstring.restype = ctypes.c_char_p
        lua.lua_close.argtypes = [ctypes.c_void_p]
        stub = '''
local callback, exited, writes = nil, false, 0
callbacks={add=function(self, name, fn) callback=fn end}
os.exit=function() exited=true end
local function bus(address)
  assert(address < 0xD000 or address > 0xDFFF, "banked bus alias accessed")
  if address == 0xFFC1 or address == 0xFFBF then return 1 end
  return 0
end
emu={read8=function(self,a) return bus(a) end,
 readRegister=function(self,name) assert(name=='PC');return 0x100 end,
 write8=function(self,a,v) bus(a) end, setKeys=function() end,
 screenshot=function() end, memory={wram={
 read8=function(self,a)
   assert(a>=0x1000 and a<0x2000)
   if a==0x1880 then return 0x0A end
   if a==0x1CB8 then return 2 end
   return 0
 end,
 write8=function(self,a,v)
   assert(a==0x1CDD or a==0x1CDC or a==0x1CBB or a==0x1CB8)
   writes=writes+1
 end}}}
'''
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            root = Path(directory)
            lut = root / "lut.bin"
            lut.write_bytes(bytes(256))
            for name, probe in (("miniboss", miniboss), ("gameplay", gameplay)):
                with self.subTest(name=name):
                    report = root / (name + ".txt")
                    env = {"STATE_PATH": str(report), "STATE_LOADED": "1",
                           "GAMEPLAY_OBJ_OUT": str(report), "GAMEPLAY_OBJ_LUT": str(lut),
                           "GAMEPLAY_OBJ_DONE": str(root / "gameplay.done")}
                    code = stub + probe + '''
for i=1,302 do if not exited then callback() end end
local marker=io.open(os.getenv("GAMEPLAY_OBJ_DONE"))
assert(exited or (marker and marker:read("*a")=="complete"), "probe did not finish")
if marker then marker:close() end
assert(writes > 0, "survival fixture was not exercised")
'''
                    state = lua.luaL_newstate()
                    try:
                        with patch.dict(os.environ, env):
                            lua.luaL_openlibs(state)
                            result = lua.luaL_loadstring(state, code.encode())
                            if result == 0:
                                result = lua.lua_pcallk(state, 0, 0, 0, 0, None)
                            self.assertEqual(result, 0, lua.lua_tolstring(state, -1, None))
                    finally:
                        lua.lua_close(state)
                    self.assertIn("D880=", report.read_text())
