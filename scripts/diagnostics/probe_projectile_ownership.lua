-- #57: inspect simultaneous native player/enemy shots, not palette edits.
local out=assert(os.getenv('PROJECTILE_OUT'))
local power=assert(tonumber(os.getenv('PROJECTILE_POWER')))
assert(power>=0 and power<=2)
local frame=0
local restored=false
local trace=assert(io.open(out..'/oam.tsv','w'))
trace:write('frame\tpower_before\tpower_requested\tform\tscene\toam\n')
callbacks:add('frame',function()
 if not restored then
  -- Qt can advance before attaching Lua. Establish an explicit own-ROM
  -- restore epoch, excluding that uncontrolled startup from the 240 frames.
  assert(emu:loadStateFile(assert(os.getenv('PROJECTILE_STATE')))~=false)
  restored=true
  emu:setKeys(0)
  emu:saveStateFile(out..'/restored.ss0')
  return
 end
 frame=frame+1
 local before=emu:read8(0xFFC0)
 -- Explicit diagnostic weapon selection, maintained because native item
 -- duration is not seeded. No inventory/cursor/scene/cache/graphics writes.
 emu:write8(0xFFC0,power)
 local w=assert(emu.memory.wram)
 emu:setKeys(frame%12<6 and 1 or 0)
 local bytes={}
 for i=0,159 do bytes[#bytes+1]=string.format('%02X',emu:read8(0xFE00+i)) end
 trace:write(string.format('%d\t%d\t%d\t%d\t%02X\t%s\n',
  frame,before,power,emu:read8(0xFFBE),w:read8(0x1880),table.concat(bytes)))
 if frame%30==0 then
  emu:screenshot(string.format('%s/frame-%04d.png',out,frame))
  emu:saveStateFile(string.format('%s/frame-%04d.ss0',out,frame))
 end
 if frame==240 then trace:close();emu:setKeys(0);os.exit(0) end
end)
