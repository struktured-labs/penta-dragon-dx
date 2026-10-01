"""#41 execute the actual Lua helper against a banked-memory negative control."""
import ctypes
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class PhysicalAssistance(unittest.TestCase):
    def test_helper_never_writes_selected_scratch_bank(self):
        self.check_helper('probe_stage_speed.lua', 'local ff_scan_hits')

    def test_stage_checkpoint_helper_preserves_scratch_banks(self):
        self.check_helper('probe_stage_integrity.lua', 'local function reg')

    def test_no_bleed_health_preserves_scratch_banks(self):
        self.check_helper('probe_stage1_no_bleed.lua', 'local LIMIT =')

    def test_side_by_side_assistance_preserves_scratch_banks(self):
        self.check_helper('probe_stage_side_by_side.lua', 'local frame, phase, seeded')

    def test_restart_save_fixture_preserves_scratch_banks(self):
        self.check_helper('probe_gameover_restart.lua', 'local function game')

    def test_menu_inventory_fixture_preserves_scratch_banks(self):
        self.check_helper('probe_menu_icon_palettes.lua', 'local LIMIT =')

    def test_side_by_side_counter_validation(self):
        spec = importlib.util.spec_from_file_location('side_by_side',
            ROOT/'scripts/diagnostics/capture_stage_side_by_side.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fields = 'native_assistance_writes=8\n' + ''.join(
            f'native_assistance_svbk_{bank}=1\n' for bank in range(8))
        with patch.object(Path, 'read_text', return_value=fields):
            self.assertEqual(module.assistance_summary(Path('unused'))['writes'], 8)
        with patch.object(Path, 'read_text', return_value=fields.replace('writes=8', 'writes=9')):
            with self.assertRaisesRegex(ValueError, 'inconsistent'):
                module.assistance_summary(Path('unused'))
        with patch.object(Path, 'read_text', return_value=''):
            with self.assertRaises(KeyError):
                module.assistance_summary(Path('unused'))

    def test_side_by_side_fresh_scratch_selection_disclosed(self):
        path = ROOT/'tmp/late-return-side-by-side-physical-01/manifest.json'
        if not path.exists():
            self.skipTest('optional local side-by-side capture unavailable')
        r = json.loads(path.read_text())
        self.assertEqual(r['dx_rom_sha256'],
                         '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
        stage = r['stages']['stage1']
        counts = stage['native_assistance']['dx']
        self.assertEqual(counts['writes'], 2436)
        self.assertEqual(counts['selected_svbk_counts']['3'], 68)
        self.assertEqual(sum(counts['selected_svbk_counts'].values()), counts['writes'])
        # Contact-sheet success is not a Stage1 semantic palette gate.
        self.assertEqual(stage['semantic_palette_audit']['status'], 'not-applicable')

    def test_no_bleed_fresh_run_counts_and_failure_preserved(self):
        path = ROOT/'tmp/late-return-stage1-no-bleed-physical-01/receipt.json'
        if not path.exists():
            self.skipTest('local no-bleed replay unavailable')
        receipt = json.loads(path.read_text())
        self.assertEqual(receipt['rom_sha256'],
                         '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
        probe = receipt['probe']
        counts = [probe[f'native_assistance_svbk_{bank}'] for bank in range(8)]
        self.assertEqual(sum(counts), probe['native_assistance_writes'])
        self.assertEqual(counts, [0,7008,0,312,0,0,0,6])
        # Runtime checks passing must not erase the independent static failure.
        self.assertTrue(all(receipt['checks'].values()))
        self.assertEqual(receipt['status'], 'fail')
        self.assertEqual(len(receipt['failures']), 3)

    def check_helper(self, filename, end_marker):
        source = (ROOT/'scripts/diagnostics'/filename).read_text()
        helper = source[source.index('local native_assistance ='):
                        source.index(end_marker)]
        script = r'''
local selected = 1
local ram = {}
emu = {memory = {wram = {}}}
function emu:read8(address) assert(address == 0xFF70); return selected end
function emu.memory.wram:write8(offset, value) ram[offset] = value end
function emu:write8(address, value)
  ram[(selected == 0 and 1 or selected)*4096 + address-0xD000] = value
end
''' + helper + r'''
for bank=0,7 do
  selected=bank
  ram[0x2CBB]=0x55; ram[0x3CBB]=0x66
  ram[0x2CFD]=0x77; ram[0x3CFD]=0x88
  native_assistance.write(0xDCBB, 0xFF)
  native_assistance.write(0xDCFD, 1)
  assert(ram[0x1CBB]==0xFF and ram[0x1CFD]==1)
  assert(ram[0x2CBB]==0x55 and ram[0x3CBB]==0x66)
  assert(ram[0x2CFD]==0x77 and ram[0x3CFD]==0x88)
end
assert(native_assistance.writes==16)
-- Exercise every inventory/cursor address used by the menu fixture too.
for bank=0,7 do
  selected=bank
  for address=0xDCBD,0xDCDD do
    for physical=2,7 do ram[physical*4096+address-0xD000]=0x5A end
    native_assistance.write(address, 0x11)
    assert(ram[address-0xC000]==0x11)
    for physical=2,7 do
      assert(ram[physical*4096+address-0xD000]==0x5A)
    end
  end
end
-- The previous mapped write demonstrably fails the same scratch invariant.
selected=3
emu:write8(0xDCBB, 0xFF)
assert(ram[0x3CBB]~=0x66)
'''
        try:
            lua = ctypes.CDLL('liblua5.4.so')
        except OSError:
            self.skipTest('Lua 5.4 unavailable')
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
            result = lua.luaL_loadstring(state, script.encode())
            if result == 0:
                result = lua.lua_pcallk(state, 0, 0, 0, 0, None)
            self.assertEqual(result, 0, lua.lua_tolstring(state, -1, None) if result else '')
        finally:
            lua.lua_close(state)
        self.assertNotIn('emu:write8(0xDCBB', source)
        self.assertNotIn('emu:write8(0xDCFD', source)

    def test_fresh_emulator_receipt_discloses_assistance(self):
        path = ROOT/'tmp/arena-stage1-physical-assistance-01/manifest.json'
        if not path.exists():
            self.skipTest('local replay not yet available')
        receipt = json.loads(path.read_text())
        row = receipt['rows'][0]
        self.assertTrue(row['deterministic_replay'])
        for side in ('original', 'dx'):
            result = row[side]
            self.assertEqual(sum(result['native_assistance_svbk_counts'].values()),
                             result['native_assistance_writes'])
            self.assertGreater(result['native_assistance_writes'], 1800)


if __name__ == '__main__':
    unittest.main()
