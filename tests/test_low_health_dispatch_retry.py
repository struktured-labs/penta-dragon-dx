"""Execute the actual observer predicate, including interrupt negative controls."""
import subprocess
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
from verify_low_health_flicker import compiler_mapper_sample


class DispatchRetry(unittest.TestCase):
    def test_mapper_requires_exact_return_bank_and_register(self):
        row = dict(pc='09C0', cpu_a='01', stack_return='4324',
                   rom_bank='01', wram_bank='03')
        self.assertTrue(compiler_mapper_sample(row))
        for key in row:
            self.assertFalse(compiler_mapper_sample(dict(row, **{key: '0000'})))
            self.assertFalse(compiler_mapper_sample({k:v for k,v in row.items() if k != key}))

    def test_completion_observation_is_bounded(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / 'scripts/diagnostics/probe_low_health_flicker.lua').read_text()
        block = 'local function observation_done' + source.split(
            'local function observation_done', 1)[1].split('\nend', 1)[0] + '\nend\n'
        code = block + '''
for n=1,1199 do
  assert(not observation_done(n,1200,false))
  assert(not observation_done(n,1200,true))
end
assert(observation_done(1200,1200,false))
for n=1200,1207 do assert(not observation_done(n,1200,true)) end
assert(observation_done(1208,1200,true)) -- terminate; pending counters still fail
assert(observation_done(1201,1200,false))
'''
        subprocess.run(['lua', '-'], input=code, text=True, check=True, capture_output=True)

    def test_retry_requires_unexecuted_entry_and_exact_interrupt(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / 'scripts/diagnostics/probe_low_health_flicker.lua').read_text()
        block = source.split('local function dispatch_interrupt_retry', 1)[1]
        block = 'local function dispatch_interrupt_retry' + block.split(
            'local function finish_publication_route', 1)[0]
        code = block + '''
local function snapshot()
  return {frame=721, af=4992, bc=768, de=12, hl=99, sp=57333,
    scene=2, room=3, effective_room=3, owner=156, svbk=249, ie=7, flags=242}
end
local old, new = snapshot(), snapshot()
new.flags=240
assert(dispatch_interrupt_retry(old,new))
assert(not dispatch_interrupt_retry(nil,new)) -- next instruction cleared eligibility
assert(not dispatch_interrupt_retry(old,old)) -- genuine duplicate, no interrupt
for _, key in ipairs({'frame','af','bc','de','hl','sp','scene','room',
    'effective_room','owner','svbk','ie'}) do
  local bad=snapshot();bad.flags=240;bad[key]=bad[key]+1
  assert(not dispatch_interrupt_retry(old,bad),key)
end
old.ie=4;new.ie=4
assert(not dispatch_interrupt_retry(old,new)) -- disabled interrupt
old=snapshot();new=snapshot();new.flags=241
assert(not dispatch_interrupt_retry(old,new)) -- changed, not consumed flag
old.flags=247;new.flags=240
assert(not dispatch_interrupt_retry(old,new)) -- multiple flags, not one service
'''
        subprocess.run(['lua', '-'], input=code, text=True, check=True,
                       capture_output=True)
        self.assertIn('function() dispatch_entry = nil end,\n        0x6CD0, 19)', source)
