-- Official #81 gate: Select 2 frames after every FFBD change; dump watch frames.
local out=assert(os.getenv('CAP_OUT'))
local wram=assert(emu.memory.wram)
local stop=tonumber(os.getenv('CAP_STOP') or '2000')
local delay=tonumber(os.getenv('SEL_DELAY') or '2')
local frame=0
local prev_room=-1
local phase='boot'
local t=0
local n=0
local log=assert(io.open(out..'/trans.tsv','w'))
log:write('frame\tphase\troom\tscene\twy\tlcdc\tevent\n')
local function rec(ev)
  log:write(string.format('%d\t%s\t%d\t%d\t%d\t%02x\t%s\n',
    frame,phase,emu:read8(0xFFBD),wram:read8(0x1880),emu:read8(0xFF4A),emu:read8(0xFF40),ev or ''))
end
callbacks:add('frame',function()
  frame=frame+1
  local keys=0
  local room=emu:read8(0xFFBD)
  local scene=wram:read8(0x1880)
  if frame<500 then
    if frame>=180 and frame<186 then keys=0x80 end
    if (frame>=193 and frame<199) or (frame>=241 and frame<247)
      or (frame>=291 and frame<297) or (frame>=391 and frame<397) then keys=0x01 end
    if frame>=341 and frame<347 then keys=0x08 end
    if scene==2 then phase='walk' end
  else
    wram:write8(0x1CBB,255)
    if phase=='walk' then
      keys=0x10+0x01
      local p=(frame//40)%8
      if p==2 or p==3 then keys=keys+0x40 end
      if p==6 or p==7 then keys=keys+0x80 end
      if prev_room>=0 and room~=prev_room and scene==2 then
        n=n+1
        phase='delay'
        t=0
        rec('room_change_'..prev_room..'_to_'..room)
      end
    elseif phase=='delay' then
      t=t+1
      if t>=delay then phase='open'; t=0 end
    elseif phase=='open' then
      t=t+1
      if t<=6 then keys=0x04 end
      if t>=6 then phase='watch'; t=0 end
    elseif phase=='watch' then
      t=t+1
      if t==1 or t==40 then
        emu:screenshot(string.format('%s/w%02d_t%02d_f%05d.png',out,n,t,frame))
        rec('watch')
      end
      if t>=50 then phase='close'; t=0 end
    elseif phase=='close' then
      t=t+1
      if t<=6 then keys=0x04 end
      if t>=40 then phase='walk'; rec('resumed') end
    end
  end
  emu:setKeys(keys)
  prev_room=room
  if frame>=stop then rec('done'); log:close(); os.exit(0) end
end)
