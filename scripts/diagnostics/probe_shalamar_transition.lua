-- #60 diagnostic: one boss-HP stimulus, then the native defeat/card path.
local out=assert(os.getenv('ENTRY_OUT'))
local frame=0
local defeat_frame=tonumber(os.getenv('TRANSITION_DEFEAT_FRAME') or '180')
local score_poll=false
local event_injected=false
local function native_shalamar_scene(scene,native_scene)
 -- #59: the broken control intentionally retains cached scene0A. Never
 -- require the graphics cache under test to be repaired before delivering
 -- the boss-HP stimulus. Native scene identity alone owns this decision.
 return scene==0x0C or (scene==0x0B and native_scene==0x0C)
end
local edges=assert(io.open(out..'/score-edges.tsv','w'))
edges:write('frame\tpc\tbank\n')
if os.getenv('TRANSITION_NATIVE_EVENT')=='1' then
 emu:setBreakpoint(function()
  if not event_injected and frame>=120 and emu:read8(0xFFBA)==0 and emu:read8(0xFFBF)==0 then
   emu:writeRegister('a',0x29)
   assert(emu:readRegister('A')==0x29,'event register write failed')
   event_injected=true
   edges:write(string.format('%d\t13F4_EVENT29\t%02X\n',frame,emu:read8(0xFF99)));edges:flush()
  end
 end,0x13F4)
end
if os.getenv('TRANSITION_LIVE_ENTRY')=='1' then
 emu:setBreakpoint(function()
  if not event_injected and frame>=120 and emu:read8(0xFFBA)==0 and emu:read8(0xFFBF)==0 then
   local sp=emu:readRegister('SP')&65535
   assert(sp>=0xDF80 and sp<=0xDFFF,'unexpected mainloop stack')
   assert(emu:read8(0xFF70)&7==1,'unexpected stack bank')
   emu:write8(sp-2,0x6C);emu:write8(sp-1,0x01)
   emu:writeRegister('sp',sp-2);emu:writeRegister('pc',0x1A2B)
   assert(emu:readRegister('SP')==sp-2 and emu:readRegister('PC')==0x1A2B,'native call register write failed')
   event_injected=true
   edges:write(string.format('%d\t016C_CALL1A2B\t%02X\n',frame,emu:read8(0xFF99)));edges:flush()
  end
 end,0x016C)
end
for _,pc in ipairs({0x1A81,0x7569,0x756F,0x7575,0x7589,0x758C,0x7598}) do
 emu:setBreakpoint(function()
  edges:write(string.format('%d\t%04X\t%02X\n',frame,pc,emu:read8(0xFF99)));edges:flush()
 end,pc)
end
emu:setBreakpoint(function() score_poll=true end,0x758C,1)
emu:setBreakpoint(function() score_poll=false end,0x7598,1)
-- #60 experimental relocated score poll; absent in the parent ROM.
emu:setBreakpoint(function() score_poll=true end,0x4603,63)
emu:setBreakpoint(function() score_poll=false end,0x460A,63)
local trace=assert(io.open(out..'/transition.tsv','w'))
trace:write('frame\tscene\tstage\tboss_hp\tlcdc\tvisible_oam\tshadow_oam\tscore_poll\tnative_scene\n')
local function visible(base)
 local count=0
 for i=0,39 do
  local y=emu:read8(base+i*4); local x=emu:read8(base+i*4+1)
  if y>0 and y<160 and x>0 and x<168 then count=count+1 end
 end
 return count
end
callbacks:add('frame',function()
 frame=frame+1
 local w=assert(emu.memory.wram)
 if frame==defeat_frame then
  -- Native bank2:406F..4079 checks DDA3/4 for zero before JP4244.
  -- Do not touch Sara health DCBB, scene, palette, OAM or code.
  local scene=w:read8(0x1880)
  assert(native_shalamar_scene(scene,emu:read8(0xFFB7)), 'must stimulate live Shalamar, not another scene')
  w:write8(0x1DA3,0); w:write8(0x1DA4,0)
 end
 trace:write(string.format('%d\t%02X\t%02X\t%d\t%02X\t%d\t%d\t%d\t%02X\n',
  frame,w:read8(0x1880),emu:read8(0xFFBA),
  w:read8(0x1DA3)+256*w:read8(0x1DA4),emu:read8(0xFF40),visible(0xFE00),visible(0xC000),score_poll and 1 or 0,emu:read8(0xFFB7)))
 trace:flush()
end)
dofile(assert(os.getenv('SECRET_REPLAY_PROBE')))
-- Override the replay's fire pulse after the defeat stimulus so the score
-- card remains visible for inspection; resume its native A pulses at1600.
callbacks:add('frame',function()
 if frame>=defeat_frame and frame<defeat_frame+1420 then emu:setKeys(0) end
 local close_at=tonumber(os.getenv('TRANSITION_CLOSE_MENU_FRAME') or '-1000')
 if frame==close_at then
  edges:write(string.format('%d\tSELECT_CLOSE_INPUT\t%02X\n',frame,emu:read8(0xFF99)));edges:flush()
 end
 if frame>=close_at and frame<close_at+6 then emu:setKeys(4) end
end)
-- #67: the outer probe owns the barrier, including the final input override.
-- The shared replay must not release the CPU before this callback is installed.
local startup_gate=os.getenv('ENTRY_NATIVE_START_GATE')
if startup_gate then
 assert(os.getenv('ENTRY_NATIVE_DEFER_START')=='1','outer probe must own startup')
 local ready=assert(io.open(startup_gate,'w'))
 ready:write('transition probe and final input override installed\n')
 ready:close()
end
