"""Per-arena BG palette rows: YAML parse/save, editor bridge, and Lua scoping.

No emulator and no ROM are used. Scratch files live under the repo-local
tmp/ directory (AGENTS.md: never the system /tmp).
"""
from __future__ import annotations

import ctypes
import ctypes.util
import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import arena_bg_palettes as abp  # noqa: E402

YAML_SOURCE = ROOT / "palettes" / "penta_palettes_v097.yaml"
LUA_SOURCE = ROOT / "scripts" / "lua" / "live_palettes.lua"


def scratch_dir(prefix: str) -> tempfile.TemporaryDirectory:
    (ROOT / "tmp").mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=prefix, dir=ROOT / "tmp")


class ArenaYamlParse(unittest.TestCase):
    def test_absent_or_empty_section_means_no_overrides(self):
        self.assertEqual(abp.parse_arena_bg_palettes(None), {})
        self.assertEqual(abp.parse_arena_bg_palettes({}), {})
        self.assertEqual(abp.parse_arena_bg_palettes({"arena_bg_palettes": None}), {})
        self.assertEqual(abp.parse_arena_bg_palettes({"arena_bg_palettes": {}}), {})
        self.assertEqual(
            abp.parse_arena_bg_palettes({"arena_bg_palettes": {"Ted": None}}), {}
        )
        document = yaml.safe_load(YAML_SOURCE.read_text())
        self.assertEqual(abp.parse_arena_bg_palettes(document), {})

    def test_valid_rows_normalize_and_order(self):
        document = {
            "arena_bg_palettes": {
                "Ted": {"BG5": ["7fff", "03ff", "001f", "0000"],
                        "Dungeon": {"colors": ["7FFF", "7E94", "3D4A", "0000"]}},
                "Shalamar": {"BG4": ["7FFF", "001F", "3D80", "0000"]},
            }
        }
        parsed = abp.parse_arena_bg_palettes(document)
        self.assertEqual(list(parsed), ["Shalamar", "Ted"])  # ARENAS order
        self.assertEqual(list(parsed["Ted"]), [0, 5])
        self.assertEqual(parsed["Ted"][5], ["7FFF", "03FF", "001F", "0000"])

    def test_malformed_sections_fail_closed(self):
        bad = [
            {"arena_bg_palettes": ["Ted"]},
            {"arena_bg_palettes": {"Tedd": {"BG1": ["7FFF"] * 4}}},
            {"arena_bg_palettes": {"Ted": {"BG8": ["7FFF"] * 4}}},
            {"arena_bg_palettes": {"Ted": {"BG1": ["7FFF"] * 3}}},
            {"arena_bg_palettes": {"Ted": {"BG1": ["8000", "7FFF", "7FFF", "7FFF"]}}},
            {"arena_bg_palettes": {"Ted": {"BG1": ["FF0000", "7FFF", "7FFF", "7FFF"]}}},
            {"arena_bg_palettes": {"Ted": {"BG1": [0x7FFF, "7FFF", "7FFF", "7FFF"]}}},
            {"arena_bg_palettes": {"Ted": {"BG0": ["7FFF"] * 4, "Dungeon": ["7FFF"] * 4}}},
        ]
        for document in bad:
            with self.subTest(document=document):
                with self.assertRaises(abp.ArenaPaletteError):
                    abp.parse_arena_bg_palettes(document)

    def test_rows_used_match_arena_tables(self):
        expected = {
            "Shalamar": [0, 4], "Riff": [0, 2], "CrystalDragon": [0, 4],
            "Cameo": [0, 1], "Ted": [0, 1, 2, 5, 6, 7], "Troop": [0, 7],
            "Faze": [0, 2], "Angela": [0, 2], "PentaDragon": [0, 1],
        }
        self.assertEqual(
            {key: abp.arena_rows_used(key) for key in abp.ARENA_KEYS}, expected
        )

    def test_d880_ids_follow_builder_table_order(self):
        self.assertEqual(
            [abp.ARENA_D880[key] for key in abp.ARENA_KEYS],
            list(range(0x0C, 0x15)),
        )


class ArenaYamlSection(unittest.TestCase):
    TEXT = YAML_SOURCE.read_text()

    def test_no_overrides_leaves_text_identical(self):
        self.assertEqual(abp.replace_section(self.TEXT, {}), self.TEXT)

    def test_add_replace_and_empty_round_trip(self):
        first = {"Shalamar": {4: ["7FFF", "001F", "3D80", "0000"]}}
        added = abp.replace_section(self.TEXT, first)
        self.assertTrue(added.startswith(self.TEXT))
        document = yaml.safe_load(added)
        self.assertEqual(abp.parse_arena_bg_palettes(document), first)
        self.assertEqual(document["bg_palettes"], yaml.safe_load(self.TEXT)["bg_palettes"])

        second = {
            "Riff": {2: ["7FFF", "7C1F", "294A", "0000"]},
            "Ted": {1: ["7FFF", "001F", "294A", "0000"], 6: ["7FFF", "7F1B", "3D08", "0000"]},
        }
        replaced = abp.replace_section(added, second)
        self.assertEqual(abp.parse_arena_bg_palettes(yaml.safe_load(replaced)), second)
        self.assertEqual(replaced.count("arena_bg_palettes:"), 1)
        self.assertTrue(replaced.startswith(self.TEXT))

        emptied = abp.replace_section(replaced, {})
        self.assertEqual(abp.parse_arena_bg_palettes(yaml.safe_load(emptied)), {})
        self.assertIn("arena_bg_palettes: {}", emptied)

    def test_block_in_middle_preserves_following_sections(self):
        text = (
            "bg_palettes:\n  Dungeon:\n    colors: [\"7FFF\", \"7E94\", \"3D4A\", \"0000\"]\n"
            "\narena_bg_palettes:\n  Ted:\n    BG5: [\"7FFF\", \"03FF\", \"001F\", \"0000\"]\n"
            "\n# trailing comment owned by next section\nnext_section:\n  a: 1\n"
        )
        out = abp.replace_section(text, {"Cameo": {1: ["7FFF", "001F", "294A", "0000"]}})
        self.assertTrue(out.startswith("bg_palettes:\n  Dungeon:\n"))
        self.assertTrue(
            out.endswith("\n# trailing comment owned by next section\nnext_section:\n  a: 1\n")
        )
        document = yaml.safe_load(out)
        self.assertEqual(document["next_section"], {"a": 1})
        self.assertEqual(list(abp.parse_arena_bg_palettes(document)), ["Cameo"])


def load_editor(tmp: Path):
    yaml_copy = tmp / "palettes.yaml"
    yaml_copy.write_bytes(YAML_SOURCE.read_bytes())
    os.environ["PENTA_LIVE_PALETTE_FILE"] = str(tmp / "live_palettes.txt")
    os.environ["PENTA_PALETTE_YAML"] = str(yaml_copy)
    os.environ["PENTA_PALETTE_BACKUP_DIR"] = str(tmp / "backups")
    spec = importlib.util.spec_from_file_location(
        f"live_palette_editor_{abs(hash(str(tmp)))}",
        ROOT / "scripts" / "live_palette_editor.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, yaml_copy


class EditorArenaBridge(unittest.TestCase):
    def setUp(self):
        self._saved_env = {
            key: os.environ.get(key)
            for key in ("PENTA_LIVE_PALETTE_FILE", "PENTA_PALETTE_YAML",
                        "PENTA_PALETTE_BACKUP_DIR")
        }
        self._tmp = scratch_dir("arena-editor-")
        self.tmp = Path(self._tmp.name)
        self.editor, self.yaml_path = load_editor(self.tmp)

    def tearDown(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def live_lines(self) -> list[str]:
        return (self.tmp / "live_palettes.txt").read_text().splitlines()

    def test_startup_without_arena_section_emits_nothing_new(self):
        self.assertEqual(self.editor.STATE["ARENA"], {})
        self.assertEqual(self.live_lines(), ["# Auto-generated by live_palette_editor.py"])

    def test_boss_preview_slots_match_builder_slot_table(self):
        document = yaml.safe_load(YAML_SOURCE.read_text())
        for ffbf, key, slot in self.editor.BOSS_PAL_ENTRIES:
            with self.subTest(key=key):
                self.assertEqual(slot, document["boss_palettes"][key].get("slot", 6))
        self.assertIn((7, "Boss7_Knight", 6), self.editor.BOSS_PAL_ENTRIES)
        self.assertIn((8, "Angela", 7), self.editor.BOSS_PAL_ENTRIES)

    def test_arena_edit_is_scoped_and_after_global_rows(self):
        ed = self.editor
        with ed.STATE_LOCK:
            ed.STATE["BG"][4][1] = "03E0"
            ed.DIRTY["BG"].add(4)
            ed.update_arena_color("Shalamar", 4, 1, "001F")
            ed.write_live_file(ed.STATE, ed.DIRTY)
        lines = self.live_lines()
        global_line = "BG4:0=7FFF,1=03E0,2=3D80,3=0000"
        # The new arena row starts from the (edited) global row.
        arena_line = "ARENA0C.BG4:0=7FFF,1=001F,2=3D80,3=0000"
        self.assertIn(global_line, lines)
        self.assertIn(arena_line, lines)
        self.assertLess(lines.index(global_line), lines.index(arena_line))
        self.assertFalse(any(line.startswith("ARENA0E") for line in lines))

    def test_save_round_trip_backup_and_clear(self):
        ed = self.editor
        original = self.yaml_path.read_bytes()
        with ed.STATE_LOCK:
            ed.update_arena_color("Ted", 5, 1, "0000")
            ed.update_arena_color("Shalamar", 4, 2, "1234")
            changed, backup = ed.Handler.save_to_yaml(None)
        self.assertTrue(changed)
        self.assertEqual(backup.read_bytes(), original)
        saved = self.yaml_path.read_text()
        self.assertTrue(saved.startswith(original.decode()))
        reloaded = ed.load_yaml_palettes()
        self.assertEqual(reloaded["ARENA"], {
            "Shalamar": {4: ["7FFF", "7FE0", "1234", "0000"]},
            "Ted": {5: ["7FFF", "0000", "001F", "0000"]},
        })
        # Global rows are unchanged by arena-only edits.
        for index in range(8):
            self.assertEqual(reloaded["BG"][index], ed.STATE["BG"][index])

        with ed.STATE_LOCK:
            unchanged, _ = ed.Handler.save_to_yaml(None)
        self.assertFalse(unchanged)

        with ed.STATE_LOCK:
            cleared = ed.clear_arena_rows("Ted", None)
            ed.clear_arena_rows("Shalamar", 4)
        self.assertEqual(cleared, [5])
        self.assertIn(5, ed.DIRTY["BG"])
        with ed.STATE_LOCK:
            changed, _ = ed.Handler.save_to_yaml(None)
        self.assertTrue(changed)
        self.assertEqual(ed.load_yaml_palettes()["ARENA"], {})
        self.assertIn("arena_bg_palettes: {}", self.yaml_path.read_text())

    def test_global_only_save_does_not_add_arena_section(self):
        ed = self.editor
        with ed.STATE_LOCK:
            ed.STATE["BG"][3][1] = "1111"
            changed, _ = ed.Handler.save_to_yaml(None)
        self.assertTrue(changed)
        text = self.yaml_path.read_text()
        self.assertNotIn("arena_bg_palettes", text)
        self.assertIn('BG3:\n    colors: ["7FFF", "1111", "2143", "0000"]', text)

    def test_http_update_clear_and_render(self):
        ed = self.editor
        server = ed.PaletteHTTPServer(("127.0.0.1", 0), ed.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def post(path, payload):
            request = urllib.request.Request(
                base + path, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    return response.status
            except urllib.error.HTTPError as error:
                return error.code

        try:
            self.assertEqual(post("/update", {"kind": "ARENA", "arena": "CrystalDragon",
                                              "pal": 4, "color": 1, "bgr": "7C00"}), 200)
            self.assertEqual(post("/update", {"kind": "ARENA", "arena": "Nobody",
                                              "pal": 4, "color": 1, "bgr": "7C00"}), 400)
            self.assertEqual(post("/update", {"kind": "ARENA", "arena": "Ted",
                                              "pal": 8, "color": 1, "bgr": "7C00"}), 400)
            self.assertEqual(post("/update", {"kind": "ARENA", "arena": "Ted",
                                              "pal": 1, "color": 1, "bgr": "FFFF"}), 400)
            self.assertIn("ARENA0E.BG4:0=7FFF,1=7C00,2=3D80,3=0000", self.live_lines())
            with urllib.request.urlopen(base + "/", timeout=5) as response:
                html = response.read().decode()
            self.assertIn("Boss Arena BG Palettes (per arena)", html)
            self.assertIn("D880=$0E", html)
            self.assertIn('data-arena="CrystalDragon" data-pal="4"', html)
            self.assertIn("FFBF 7: Boss7_Knight → OBJ6", html)
            self.assertIn("FFBF 8: Angela → OBJ7", html)
            self.assertEqual(post("/arena_clear", {"arena": "CrystalDragon", "pal": 4}), 200)
            lines = self.live_lines()
            self.assertFalse(any(line.startswith("ARENA") for line in lines))
            self.assertIn("BG4:0=7FFF,1=7FE0,2=3D80,3=0000", lines)
        finally:
            server.shutdown()
            server.server_close()


def lua_library():
    name = ctypes.util.find_library("lua5.4")
    return ctypes.CDLL(name) if name else None


LUA_HARNESS = r'''
local ENV = ...
os.getenv = function(key) return ENV[key] end
local d880 = 0x02
local cram = {}
local bg_index = 0
local frame_cb = nil
callbacks = {add = function(self, name, fn) if name == "frame" then frame_cb = fn end end}
emu = {
  memory = {wram = {read8 = function(self, off)
    if off == 0xD880 - 0xC000 then return d880 end
    return 0 end}},
  read8 = function(self, addr) if addr == 0xFF68 then return bg_index end return 0 end,
  write8 = function(self, addr, value)
    if addr == 0xFF68 then bg_index = value
    elseif addr == 0xFF69 then cram[bg_index] = value end
  end,
  loadStateFile = function() return true end,
  screenshot = function() end, setKeys = function() end,
}
local chunk = assert(load(SCRIPT, "@" .. CHUNK_NAME))
chunk()
assert(frame_cb, "frame callback registered")
local function run(n) for _ = 1, n do frame_cb() end end
local function color(pal, ci)
  local lo, hi = cram[pal * 8 + ci * 2], cram[pal * 8 + ci * 2 + 1]
  if lo == nil then return nil end
  return string.format("%04X", lo | (hi << 8))
end
'''


class LuaArenaScoping(unittest.TestCase):
    def setUp(self):
        self.lua = lua_library()
        if self.lua is None:
            self.skipTest("Lua 5.4 unavailable")
        self._tmp = scratch_dir("arena-lua-")
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_lua(self, body: str, env: dict[str, str], chunk_name: str):
        lua = self.lua
        lua.luaL_newstate.restype = ctypes.c_void_p
        lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
        lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lua.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_longlong, ctypes.c_void_p]
        lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        lua.lua_tolstring.restype = ctypes.c_char_p
        lua.lua_close.argtypes = [ctypes.c_void_p]

        def quote(text: str) -> str:
            return "[==[" + text + "]==]"

        env_table = "{" + ",".join(
            f"[ {quote(k)} ]={quote(v)}" for k, v in env.items()
        ) + "}"
        code = (
            f"SCRIPT = {quote(LUA_SOURCE.read_text())}\n"
            f"CHUNK_NAME = {quote(chunk_name)}\n"
            f"local run_harness = assert(load({quote(LUA_HARNESS + body)}))\n"
            f"run_harness({env_table})\n"
        )
        state = lua.luaL_newstate()
        try:
            lua.luaL_openlibs(state)
            result = lua.luaL_loadstring(state, code.encode())
            if not result:
                result = lua.lua_pcallk(state, 0, 0, 0, 0, None)
            self.assertEqual(result, 0, lua.lua_tolstring(state, -1, None))
        finally:
            lua.lua_close(state)

    def test_script_compiles(self):
        self.run_lua("", {"LIVE_PALETTE_LOG": str(self.tmp / "log.txt"),
                          "LIVE_PALETTE_FILE": str(self.tmp / "missing.txt")},
                     "/nowhere/scripts/lua/live_palettes.lua")

    def test_root_detection(self):
        log = self.tmp / "log.txt"
        self.run_lua("", {"LIVE_PALETTE_LOG": str(log),
                          "LIVE_PALETTE_FILE": str(self.tmp / "missing.txt")},
                     "/srv/wt/scripts/lua/live_palettes.lua")
        self.assertIn("root=/srv/wt\n", log.read_text())
        self.run_lua("", {"LIVE_PALETTE_LOG": str(log),
                          "LIVE_PALETTE_FILE": str(self.tmp / "missing.txt"),
                          "PWD": "/home/x/checkout"},
                     "scripts/lua/live_palettes.lua")
        self.assertIn("root=/home/x/checkout\n", log.read_text())
        self.run_lua("", {"LIVE_PALETTE_LOG": str(log),
                          "LIVE_PALETTE_FILE": str(self.tmp / "missing.txt"),
                          "PENTA_PROJECT_DIR": "/explicit/root/"},
                     "/srv/wt/scripts/lua/live_palettes.lua")
        self.assertIn("root=/explicit/root\n", log.read_text())
        self.run_lua("", {"LIVE_PALETTE_LOG": str(log),
                          "LIVE_PALETTE_FILE": str(self.tmp / "missing.txt")},
                     "=stdin")
        self.assertIn("root=/home/struktured/projects/penta-dragon-dx-claude\n",
                      log.read_text())

    def test_arena_rows_apply_only_in_matching_d880(self):
        live = self.tmp / "live.txt"
        live.write_text(
            "# Auto-generated by live_palette_editor.py\n"
            "BG4:0=7FFF,1=03E0,2=3D80,3=0000\n"
            "ARENA0C.BG4:0=7FFF,1=001F,2=3D80,3=0000\n"
            "ARENA10.BG5:0=7FFF,1=1234,2=001F,3=0000\n"
        )
        body = r'''
d880 = 0x0E  -- Crystal Dragon shares BG4 with Shalamar
run(30)
assert(color(4, 1) == "03E0", "global BG4 outside Shalamar: " .. tostring(color(4, 1)))
assert(color(5, 1) == nil, "Ted row must not be written outside Ted")
d880 = 0x0C
run(1)
assert(color(4, 1) == "001F", "Shalamar arena BG4: " .. tostring(color(4, 1)))
assert(color(5, 1) == nil)
d880 = 0x10
run(1)
assert(color(5, 1) == "1234", "Ted arena BG5")
assert(color(4, 1) == "03E0", "global BG4 re-asserted after leaving Shalamar")
d880 = 0x16  -- post-boss reload: no arena row applies
cram = {}
run(1)
assert(color(5, 1) == nil and color(4, 1) == "03E0")
'''
        self.run_lua(body, {"LIVE_PALETTE_LOG": str(self.tmp / "log.txt"),
                            "LIVE_PALETTE_FILE": str(live)},
                     "/srv/wt/scripts/lua/live_palettes.lua")

    def test_legacy_lines_still_parse(self):
        live = self.tmp / "live.txt"
        live.write_text("BG3:0=7FFF,1=001F,2=2143,3=0000\nBOSS1@6:0=0000,1=601F,2=03E0,3=0000\n")
        body = r'''
d880 = 0x02
run(30)
assert(color(3, 1) == "001F")
'''
        self.run_lua(body, {"LIVE_PALETTE_LOG": str(self.tmp / "log.txt"),
                            "LIVE_PALETTE_FILE": str(live)},
                     "/srv/wt/scripts/lua/live_palettes.lua")


if __name__ == "__main__":
    unittest.main()
