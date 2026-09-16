"""Exercise the real Lua probe with a frame/raster stub, without an emulator."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CursorCaptureTiming(unittest.TestCase):
    @unittest.skipUnless(shutil.which("lua"), "Lua interpreter unavailable")
    def test_capture_waits_for_complete_visible_frame(self):
        code = r'''
local callback, captures, present = nil, 0, true
callbacks = {add=function(self, name, fn) callback=fn end}
emu = {
  setKeys=function() end,
  read8=function(self, address)
    if address == 0xD880 then return 1 end
    if address == 0x9924 and present then return 0x73 end
    return 0
  end,
  screenshot=function() captures=captures+1 end,
}
dofile("scripts/diagnostics/probe_title_cursor_mgba.lua")
for i=1,300 do callback() end
callback()
assert(captures == 0, "captured before a whole visible frame")
present=false
callback()
present=true
callback()
assert(captures == 0, "nonconsecutive visibility incorrectly accepted")
callback()
assert(captures == 1, "stable visible selector not captured")
callback()
assert(captures == 1, "capture should be once per position")
'''
        env = dict(os.environ, PENTA_TITLE_CURSOR_OUT="unused",
                   PENTA_TITLE_CURSOR_SETTLE="300")
        result = subprocess.run(["lua", "-"], input=code, text=True,
                                capture_output=True, cwd=ROOT, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
