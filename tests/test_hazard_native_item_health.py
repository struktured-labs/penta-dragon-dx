"""#37/#41: execute the hazard fixture helpers, including broken controls."""
import ctypes
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / 'scripts/diagnostics/probe_stage1_spike_palettes.lua'


def run_lua(source, execute=True):
    lua = ctypes.CDLL('liblua5.4.so')
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
        result = lua.luaL_loadstring(state, source.encode())
        if result == 0 and execute:
            result = lua.lua_pcallk(state, 0, 0, 0, 0, None)
        if result:
            raise RuntimeError(lua.lua_tolstring(state, -1, None).decode())
    finally:
        lua.lua_close(state)


STUB = '''
local selected, canonical, stage = 1, 2, 0
local ram = {}
emu = {memory={wram={}}}
function emu:read8(a)
  if a == 0xFF70 then return selected end
  if a == 0xFFB7 then return canonical end
  if a == 0xFFBA then return stage end
  error('unexpected CPU read')
end
function emu:write8(a,v)
  ram[(selected == 0 and 1 or selected)*4096+a-0xD000] = v
end
function emu.memory.wram:write8(a,v) ram[a]=v end
function emu.memory.wram:read8(a) return ram[a] or 0 end
'''
CHECKS = '''
for bank=0,7 do
  selected=bank; ram={}
  for p=2,7 do for a=0xCBD,0xCDD do ram[p*4096+a]=0x5A end end
  native_assistance.seed_item()
  assert(ram[0x1CBD]==1 and ram[0x1CDB]==0)
  assert(ram[0x1CDC]==0x0C and ram[0x1CDD]==0)
  for _,phase in ipairs({'item','healthy','warning'}) do
    native_assistance.set_health(phase)
    local expected=({item=0xC0,healthy=0xFF,warning=0x40})[phase]
    assert(ram[0x1CBB]==expected)
    assert(ram[0x1CBD]==1 and ram[0x1CDB]==0)
    assert(ram[0x1CDC]==0x0C and ram[0x1CDD]==0)
  end
  for p=2,7 do for a=0xCBD,0xCDD do assert(ram[p*4096+a]==0x5A) end end
  ram[0x1D06]=1; ram[0x1880]=0x0B
  assert(native_assistance.warning_observed())
  for _,entry in ipairs({{0x1CBB,0xFF},{0x1D06,0},{0x1880,2}}) do
    local old=ram[entry[1]]; ram[entry[1]]=entry[2]
    assert(not native_assistance.warning_observed()); ram[entry[1]]=old
  end
  canonical=3; assert(not native_assistance.warning_observed()); canonical=2
  stage=1; assert(not native_assistance.warning_observed()); stage=0
end
assert(not pcall(function() native_assistance.set_health('invalid') end))
'''


class HazardNativeItemHealth(unittest.TestCase):
    def setUp(self):
        self.source = PROBE.read_text()
        self.helper = self.source.split('local OUT =', 1)[0]

    def test_full_probe_stays_within_lua_limits(self):
        run_lua(self.source, execute=False)

    def test_real_helpers_preserve_cursor_and_scratch_for_all_banks(self):
        run_lua(STUB + self.helper + CHECKS)

    def test_mapped_inventory_seed_negative_control_fails(self):
        broken = self.helper.replace('native_assistance.write(0xDCBD, 1)',
                                     'emu:write8(0xDCBD, 1)')
        self.assertNotEqual(broken, self.helper)
        with self.assertRaisesRegex(RuntimeError, 'assertion failed'):
            run_lua(STUB + broken + CHECKS)

    def test_legacy_cursor_as_health_negative_control_fails(self):
        broken = self.helper.replace('native_assistance.write(0xDCBB, assert',
                                     'native_assistance.write(0xDCDD, assert')
        self.assertNotEqual(broken, self.helper)
        with self.assertRaisesRegex(RuntimeError, 'assertion failed'):
            run_lua(STUB + broken + CHECKS)

    def test_live_driver_uses_helpers_and_real_selected_slot(self):
        body = self.source.split('local OUT =', 1)[1]
        self.assertEqual(body.count('native_assistance.seed_item()'), 1)
        self.assertNotIn('write8(0xDCBD', body)
        self.assertNotIn('native_assistance.write(0xDCDD', body)
        self.assertNotIn('native_assistance.write(0xDCDC', body)
        self.assertIn('0xDCBD + 10 * native_assistance.read(0xDCDB)', body)
        self.assertIn('if native_assistance.warning_observed() then', body)

    def test_receipt_cannot_substitute_stimulus_counts_for_native_warning(self):
        sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
        from verify_stage1_hazard_menu import replay_is_clean
        receipt = dict.fromkeys((
            'floor_mismatch_frames', 'transient_mismatch_frames',
            'unsafe_map_flip_events', 'palette_mismatch_frames',
            'endpoint_mismatch_frames', 'visible_attr_mismatch_frames',
            'post_menu_transient_mismatch_frames', 'post_menu_palette_mismatch_frames',
            'post_menu_floor_mismatch_frames', 'post_menu_endpoint_mismatch_frames',
            'post_menu_visible_attr_mismatch_frames', 'active_hazard_attr_write_hits',
            'post_menu_active_hazard_attr_write_hits', 'rendered_wrong_palette0_tooth_cells',
            'menu_map_alias_frames'), 0)
        receipt.update(passed=True, menu_anchor_frame=181, menu_open_frames=241,
                       menu_closed_frame=427, post_menu_closed_frames=224,
                       menu_close_repair_hits=1, menu_close_native_tail_hits=1,
                       map_flip_events=82, menu_use_input_frames=6,
                       menu_a_handler_hits=1, menu_item_dispatch_hits=1,
                       menu_selected_item_trace='f266:g00:i01:c00',
                       low_health_forced_frames=195, low_health_scene_frames=180)
        self.assertTrue(replay_is_clean(receipt, 426, 266, 456))
        for count in (0, 119):
            self.assertFalse(replay_is_clean(dict(receipt, low_health_scene_frames=count),
                                            426, 266, 456))
        del receipt['low_health_scene_frames']
        self.assertFalse(replay_is_clean(receipt, 426, 266, 456))


if __name__ == '__main__':
    unittest.main()
