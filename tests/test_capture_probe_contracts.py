"""Exercise capture code without an emulator or generated ROM fixtures."""
import ctypes
import ctypes.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
sys.path.insert(0, str(ROOT / "scripts/probes"))

import verify_title_showcase_mgba as title_showcase  # noqa: E402
import verify_title_visual_receipts as title_visual  # noqa: E402
import verify_title_color as title_color  # noqa: E402
import verify_title_animation_frames as title_animation  # noqa: E402
import verify_live_palette_session as live_palette  # noqa: E402


def run_lua(case, code):
    library = ctypes.util.find_library('lua5.4')
    if not library:
        case.skipTest('Lua 5.4 unavailable')
    lua = ctypes.CDLL(library)
    lua.luaL_newstate.restype = ctypes.c_void_p
    lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
    lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lua.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_longlong, ctypes.c_void_p]
    lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    lua.lua_tolstring.restype = ctypes.c_char_p
    lua.lua_close.argtypes = [ctypes.c_void_p]
    state = lua.luaL_newstate()
    try:
        lua.luaL_openlibs(state)
        result = lua.luaL_loadstring(state, code.encode())
        if not result:
            result = lua.lua_pcallk(state, 0, 0, 0, 0, None)
        case.assertEqual(result, 0, lua.lua_tolstring(state, -1, None))
    finally:
        lua.lua_close(state)


class CaptureContracts(unittest.TestCase):
    def test_title_emulator_probes_use_clean_private_runtime_roms(self):
        (ROOT / "tmp").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="title-runtime-contract-", dir=ROOT / "tmp"
        ) as directory:
            scratch = Path(directory)
            source = scratch / "source.gb"
            source.write_bytes(b"candidate")

            visual_out = scratch / "visual"
            visual_out.mkdir()
            visual_rom, visual_runtime = title_visual.prepare_runtime_rom(
                source, visual_out
            )
            visual_command = title_visual.probe_command(
                Path("launcher"), visual_rom, visual_runtime
            )

            showcase_out = scratch / "showcase" / "title"
            showcase_rom, showcase_runtime = title_showcase.prepare_runtime_rom(
                source, showcase_out
            )
            showcase_command = title_showcase.probe_command(
                "launcher", showcase_rom, showcase_runtime
            )

            animation_runtime = scratch / "animation-runtime"
            animation_runtime.mkdir()
            animation_rom = title_animation.prepare_runtime_rom(
                source, animation_runtime
            )

            live_rom, live_runtime = live_palette.prepare_title_runtime_rom(
                source, scratch / "live"
            )
            live_command = live_palette.title_capture_command(
                "launcher", live_rom, live_runtime
            )
            live_deck_command = live_palette.live_palette_command(
                "launcher", live_rom, live_runtime
            )

            color_runtime = scratch / "color-runtime"
            color_runtime.mkdir()
            with mock.patch.object(
                title_color.subprocess, "run"
            ) as run:
                run.return_value.returncode = 0
                run.return_value.stdout = b""
                run.return_value.stderr = b""
                (color_runtime / "title.png").write_bytes(b"x" * 101)
                color_rom = title_color.capture_title(
                    str(source), 600, "probe.lua", color_runtime
                )
            color_command = run.call_args.args[0]

            for runtime_rom, runtime, command in (
                (visual_rom, visual_runtime, visual_command),
                (showcase_rom, showcase_runtime, showcase_command),
                (color_runtime / "candidate.gb", color_runtime, color_command),
                (live_rom, live_runtime, live_command),
                (live_rom, live_runtime, live_deck_command),
            ):
                self.assertEqual(runtime_rom.read_bytes(), source.read_bytes())
                self.assertIn(str(runtime_rom), command)
                self.assertIn(f"savegamePath={runtime}", command)
                self.assertIn(f"savestatePath={runtime}", command)
                self.assertNotIn(str(source), command)
            self.assertEqual(color_rom, color_runtime / "title.png")
            self.assertEqual(animation_rom.read_bytes(), source.read_bytes())
            self.assertNotEqual(animation_rom.parent, source.parent)

    def test_live_loader_rejects_false_and_exceptions(self):
        source = (ROOT / 'scripts/lua/live_palettes.lua').read_text()
        helper = source[source.index('local function load_state('):source.index('local function game_read(')]
        run_lua(self, helper + '''
emu={loadStateFile=function() return false end}
assert(load_state('state')==false)
emu.loadStateFile=function() error('missing') end
assert(load_state('state')==false)
emu.loadStateFile=function() return true end
assert(load_state('state')==true)
emu.loadStateFile=function() return nil end
assert(load_state('state')==true)
''')

    def test_opening_reads_bank_one_and_restores_selector(self):
        source = (ROOT / 'scripts/diagnostics/probe_opening_inventory_mgba.lua').read_text()
        stub = '''
local callback, vbk, raw_reads, attr_reads, exited = nil, 0, 0, 0, false
local lines={}
os.getenv=function(k) if k=='OPENING_INVENTORY_OUT' then return 'unused' else return '1' end end
os.exit=function() exited=true end
io.open=function() return {write=function(self,s) lines[#lines+1]=s end,
 flush=function() end,close=function() end} end
callbacks={add=function(self,k,fn) callback=fn end}
emu={memory={wram={read8=function(self,a) if a==0x1880 then return 0x15 end return 0 end},
 vram={read8=function(self,a) assert(a>=0x1800 and a<0x2000);raw_reads=raw_reads+1;return 0 end}},
 read8=function(self,a)
   if a==0xFF4F then return vbk end
   if a==0xFF40 then return 0x83 end
   if a>=0x9800 and a<0xA000 then assert(vbk==1);attr_reads=attr_reads+1;return 1 end
   assert(a>=0xFF00, 'banked WRAM bus alias read')
   return 0
 end,
 write8=function(self,a,v) assert(a==0xFF4F);vbk=v end,
 setKeys=function() end,screenshot=function() assert(vbk==0) end}
'''
        run_lua(self, stub + source + '''
callback()
assert(not exited and vbk==0)
assert(raw_reads==360 and attr_reads==360)
assert(table.concat(lines):find(string.rep('01',360),1,true))
assert(table.concat(lines):find('complete',1,true))
callback()
assert(raw_reads==360 and attr_reads==360)
''')

    def test_title_does_not_decimate_visible_boss_frames(self):
        source = (ROOT / 'scripts/diagnostics/probe_title_visual_receipts_mgba.lua').read_text()
        sample = source.split('local function sample_demo()', 1)[1].split('local function ', 1)[0]
        self.assertNotIn('frame %', sample)
        self.assertIn('demo_samples = demo_samples + 1', sample)
        self.assertIn('demo_mismatches = demo_mismatches + 1', sample)


if __name__ == '__main__':
    unittest.main()
