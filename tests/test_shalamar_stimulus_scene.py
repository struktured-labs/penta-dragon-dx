"""#59: execute the Lua stimulus predicate, including the stale-cache control."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeBossStimulus(unittest.TestCase):
    def test_actual_lua_predicate_requires_native_boss_not_repaired_cache(self):
        lua = shutil.which('lua')
        if lua is None:
            self.skipTest('Lua interpreter unavailable (no emulator needed)')
        source = (ROOT / 'scripts/diagnostics/probe_shalamar_transition.lua').read_text()
        predicate = re.search(r'local function native_shalamar_scene\(.*?\nend',
                              source, re.S).group(0)
        script = predicate + '''
for scene=0,255 do
 for native=0,255 do
  local expected = scene==12 or (scene==11 and native==12)
  assert(native_shalamar_scene(scene,native)==expected)
 end
end
-- Retained failing control at frame900: raw0B/native0C/cache0A/armed0.
-- The cache is deliberately not an input to the stimulus decision.
assert(native_shalamar_scene(11,12))
assert(not native_shalamar_scene(11,3))
'''
        result = subprocess.run([lua, '-e', script], capture_output=True, text=True,
                                timeout=10, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
