import os
from pathlib import Path
import ctypes
import ctypes.util
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class BossReceiptLoadFailure(unittest.TestCase):
    @unittest.skipUnless(ctypes.util.find_library("lua5.4"), "Lua 5.4 unavailable")
    def test_failed_load_terminates_without_retry_or_rendered_receipt(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            prefix = Path(directory) / "boss"
            env = dict(os.environ, BOSS_RECEIPT_OUT=str(prefix),
                       PENTA_STATE_FILE="missing.ss0", BOSS_TARGET="8",
                       BOSS_RECEIPT_BREAKPOINTS="0")
            code = '''
local frame, loads = nil, 0
callbacks = {add=function(self, name, fn) frame=fn end}
emu = {loadStateFile=function() loads=loads+1; return false end}
dofile("scripts/diagnostics/probe_boss_state_receipt.lua")
for i=1,100 do frame() end
assert(loads == 1, "invalid savestate retried")
'''
            # mGBA uses Lua 5.4; the system `lua` CLI may still be Lua 5.1,
            # which cannot parse the probe's native bitwise operators.
            lua = ctypes.CDLL(ctypes.util.find_library("lua5.4"))
            lua.luaL_newstate.restype = ctypes.c_void_p
            lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
            lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            lua.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_longlong, ctypes.c_void_p]
            lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            lua.lua_tolstring.restype = ctypes.c_char_p
            lua.lua_close.argtypes = [ctypes.c_void_p]
            state = lua.luaL_newstate()
            self.assertTrue(state)
            try:
                with patch.dict(os.environ, env):
                    lua.luaL_openlibs(state)
                    result = lua.luaL_loadstring(state, code.encode())
                    if result == 0:
                        result = lua.lua_pcallk(state, 0, 0, 0, 0, None)
                    self.assertEqual(result, 0, lua.lua_tolstring(state, -1, None))
            finally:
                lua.lua_close(state)
            self.assertEqual(Path(str(prefix) + ".audit.done").read_text(),
                             "error-state-load\n")
            self.assertFalse(Path(str(prefix) + ".audit.report").exists())
            self.assertFalse(prefix.with_suffix(".ss0").exists())
