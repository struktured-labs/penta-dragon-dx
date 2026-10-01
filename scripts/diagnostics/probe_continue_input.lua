-- #28 assisted diagnostic: one credit and depleted resource, then real keys.
-- Stage1 cold-boots; Stage2 restores an explicitly supplied entry state.
-- No scene, palette, graphics, bank, or controller-register writes.
local out=assert(os.getenv('ENTRY_OUT'))
local button=assert(tonumber(os.getenv('ENTRY_KEYS')))
local stage=tonumber(os.getenv('ENTRY_STAGE') or '1')
local promptRelative=os.getenv('ENTRY_PROMPT_RELATIVE')=='1'
local limit=promptRelative and 6000 or 2400
local firstPoll=nil
local approach= os.getenv('ENTRY_APPROACH_UP')=='1'
local deathSeen=false
assert(not approach or (stage==2 and promptRelative),'approach requires Stage2 prompt-relative replay')
assert(stage==1 or stage==2)
local state=os.getenv('ENTRY_STATE')
if state then assert(emu:loadStateFile(state)~=false,'state load failed') end
assert(button==0 or button==1 or button==8)
local n=0
local wram=assert(emu.memory.wram)
local trace=assert(io.open(out..'/trace.tsv','w'))
local continuation=assert(io.open(out..'/continue.tsv','w'))
local poll=assert(io.open(out..'/continue-poll.tsv','w'))
local resources=assert(io.open(out..'/resources.tsv','w'))
resources:write('frame\tdcbb\tdcdc\tdcdd\tsvbk\tffba\n')
trace:write('frame\tscene\tmode\n')
local damage=assert(io.open(out..'/damage.tsv','w'))
for _,site in ipairs({0x1004,0x1028}) do
 emu:setBreakpoint(function()
  damage:write(string.format('%d\t%04X\t%04X\t%02X\t%02X\n',n,site,
   emu:getRegister('af'),wram:read8(0x1CBB),wram:read8(0x1880)))
  damage:flush()
 end,site)
end
emu:setBreakpoint(function()
 if not firstPoll then firstPoll=n end
 poll:write(string.format('%d\t%02X\t%02X\t%02X\t%02X\n',n,
  emu:read8(0xFF94),emu:read8(0xFF95),emu:read8(0xFF93),emu:read8(0xFF00)))
end,0x4A9C,1)
callbacks:add('frame',function()
 n=n+1
 local keys=0
 if not state then
 if n>=180 and n<186 then keys=0x80 end
 for _,first in ipairs({193,241,291,391}) do
  if n>=first and n<first+6 then keys=1 end
 end
 if n>=341 and n<347 then keys=8 end
 end
 if n==1201 then
  assert(wram:read8(0x1880)==stage+1 and emu:read8(0xFFC1)==1,
         'death stimulus requires requested active stage')
  assert(emu:read8(0xFFBA)==stage-1,'requested stage route expected')
  emu:write8(0xFFE6,1)
  -- Stage2 bank1:4200 decrements before checking zero; zero would wrap.
  wram:write8(0x1CBB,stage==2 and 1 or 0)
 end
 if promptRelative then
  if firstPoll and n>=firstPoll+12 and n<firstPoll+432 and (n-firstPoll-12)%12<6 then keys=button end
 elseif n>=1380 and n<1800 and n%12<6 then keys=button end
 if wram:read8(0x1880)==0x17 then deathSeen=true end
 if approach and n>1201 and not deathSeen then keys=64 end
 emu:setKeys(keys)
 local scene=wram:read8(0x1880)
 resources:write(string.format('%d\t%02X\t%02X\t%02X\t%02X\t%02X\n',n,
  wram:read8(0x1CBB),wram:read8(0x1CDC),wram:read8(0x1CDD),
  emu:read8(0xFF70),emu:read8(0xFFBA)))
 continuation:write(string.format('%d\t%02X\t%02X\t%02X\t%02X\t%02X\n',n,
  scene,emu:read8(0xFFE6),emu:read8(0xFFE7),emu:read8(0xFF94),keys))
 trace:write(string.format('%d\t%02X\t%02X\n',n,scene,emu:read8(0xFFC1)))
 if n==1370 or n==limit then emu:screenshot(string.format('%s/frame-%04d.png',out,n)) end
 if n==limit then
  emu:setKeys(0)
  trace:close();continuation:close();poll:close();resources:close();damage:close()
  os.exit(0)
 end
end)
