-- Issue #23: cold boot -> position-assisted doorway -> native secret entry.
-- No scene, cache, palette, graphics, mapper, or game-code writes.
local out=assert(os.getenv('SECRET_CHR_OUT'))
local wram=assert(emu.memory.wram)
local vram=assert(emu.memory.vram)
local frame,hits=0,0
local trace=assert(io.open(out..'/frames.tsv','w'))
trace:write('frame\tscene\tstage\tmain_loop_hits\n')
emu:setBreakpoint(function() hits=hits+1 end,0x016C)
callbacks:add('frame',function()
 frame=frame+1
 local keys=0
 if frame>=180 and frame<186 then keys=128 end
 if (frame>=193 and frame<199) or (frame>=241 and frame<247)
  or (frame>=291 and frame<297) or (frame>=391 and frame<397) then keys=1 end
 if frame>=341 and frame<347 then keys=8 end
 if frame==1201 then
  assert(wram:read8(0x1880)==2 and emu:read8(0xFFBA)==0,'no Stage-1 baseline')
  wram:write8(0x1C00,0xD8);wram:write8(0x1C01,4)
  wram:write8(0x1C02,0x40);wram:write8(0x1C03,5)
 end
 if frame>1200 then
  -- #37: health only; DCDD is the native menu cursor.
  wram:write8(0x1CBB,255)
  if frame<=1320 then keys=129 end
 end
 emu:setKeys(keys)
 trace:write(string.format('%d\t%d\t%d\t%d\n',frame,wram:read8(0x1880),emu:read8(0xFFBA),hits))
 if frame==1200 or frame==1500 or frame==3600 then
  emu:screenshot(string.format('%s/frame-%04d.png',out,frame))
 end
 if frame==3600 then
  assert(emu:saveStateFile(out..'/final.ss0')~=false,'final state capture failed')
  local file=assert(io.open(out..'/secret-chr.bin','wb'))
  for i=0x1000,0x17FF do file:write(string.char(vram:read8(i))) end
  file:close();trace:close();os.exit(0)
 end
end)
