"""#66 preserve mismatched encounters; never promote sampled equality to parity."""
import importlib.util
import ctypes
import ctypes.util
import os
import subprocess
import sys
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'scripts/diagnostics/verify_stage_speed_matrix.py'
SPEC = importlib.util.spec_from_file_location('speed_initial', PATH)
speed = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(speed)


class InitialEncounter(unittest.TestCase):
    def test_state_patrol_wrapper_rewrites_and_compiles_without_emulator(self):
        library = ctypes.util.find_library('lua5.4') or ctypes.util.find_library('lua5.3')
        if not library:
            self.skipTest('Lua 5.3+ library unavailable')
        lua = ctypes.CDLL(library)
        lua.luaL_newstate.restype = ctypes.c_void_p
        lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
        lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lua.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_longlong, ctypes.c_void_p]
        lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        lua.lua_tolstring.restype = ctypes.c_char_p
        lua.lua_close.argtypes = [ctypes.c_void_p]
        # Execute only wrapper transformations. Compile the generated probe,
        # but replace its execution with a no-op: no emulator or Lua emu API.
        import json
        script = ('local real_load=load; local getenv=os.getenv; '
                  'os.getenv=function(k) if k=="STAGE7_STATE_PATROL_BASE_PROBE" then return '
                  + json.dumps(str(speed.PROBE)) + ' end return getenv(k) end; '
                  'load=function(s,n) assert(real_load(s,n)); return function() end end; '
                  'dofile(' + json.dumps(str(speed.PROBE.with_name('probe_stage7_state_patrol.lua'))) + ')')
        state = lua.luaL_newstate()
        self.assertTrue(state)
        try:
            lua.luaL_openlibs(state)
            status = lua.luaL_loadstring(state, script.encode())
            if status == 0:
                status = lua.lua_pcallk(state, 0, 0, 0, 0, None)
            self.assertEqual(status, 0, lua.lua_tolstring(state, -1, None) if status else None)
        finally:
            lua.lua_close(state)

    def test_invalid_start_policies_fail_before_emulator_launch(self):
        for policy, health, message in (
                ('invalid', '109', 'unsupported STAGE_SPEED_START_POLICY'),
                ('first-lowhealth-loop', '255', 'requires --health 109')):
            result = subprocess.run(
                [sys.executable, str(PATH), '--health', health,
                 '--output', str(PATH.parents[2] / 'tmp/unused-policy-test')],
                env=dict(os.environ, STAGE_SPEED_START_POLICY=policy),
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn(message, result.stderr)

    def test_probe_compiles_without_launching_emulator(self):
        library = ctypes.util.find_library('lua5.4') or ctypes.util.find_library('lua5.3')
        if not library:
            self.skipTest('Lua 5.3+ library unavailable')
        lua = ctypes.CDLL(library)
        lua.luaL_newstate.restype = ctypes.c_void_p
        lua.luaL_loadfilex.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        lua.lua_tolstring.restype = ctypes.c_char_p
        lua.lua_close.argtypes = [ctypes.c_void_p]
        state = lua.luaL_newstate()
        self.assertTrue(state)
        try:
            status = lua.luaL_loadfilex(state, str(speed.PROBE).encode(), None)
            error = lua.lua_tolstring(state, -1, None) if status else None
            self.assertEqual(status, 0, error)
        finally:
            lua.lua_close(state)

    def setUp(self):
        self.sample = dict(slots_dc80_dcaf='00' * 48, rng_ffd1=42, stride_ffc1=1)

    def compare(self, other):
        return speed.compare_initial_encounters(
            {'initial_encounter': self.sample}, {'initial_encounter': other})

    def test_equal_samples_are_not_matched_work_qualification(self):
        result = self.compare(dict(self.sample))
        self.assertEqual(result['status'], 'SAMPLED_FIELDS_EQUAL')
        self.assertTrue(result['sampled_state_equal'])
        self.assertFalse(result['matched_work_qualified'])

    def test_each_native_difference_is_visible(self):
        for key, value in dict(slots_dc80_dcaf='11' + '00' * 47,
                               rng_ffd1=43, stride_ffc1=0).items():
            result = self.compare(dict(self.sample, **{key: value}))
            self.assertEqual(result['status'], 'DIFFERENT')
            self.assertEqual(result['differing_fields'], [key])
            self.assertFalse(result['sampled_state_equal'])

    def test_missing_and_malformed_evidence_is_unknown(self):
        for bad in (None, {}, [], dict(self.sample, rng_ffd1=True),
                    dict(self.sample, rng_ffd1=100),
                    dict(self.sample, slots_dc80_dcaf='00'),
                    dict(self.sample, slots_dc80_dcaf='zz' * 48)):
            result = self.compare(bad)
            self.assertEqual(result['status'], 'UNKNOWN')
            self.assertFalse(result['sampled_state_equal'])
        self.assertEqual(speed.compare_initial_encounters({}, {})['status'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
