-- Item 8: verify the powerup cheat + warp to the final boss (Penta Dragon).
-- Load dungeon state, set FFBA=7, pulse SELECT+START to teleport to FFBA=8 /
-- D880=0x14 (Penta Dragon arena), apply the cheat bytes every frame (FFBE=1
-- Dragon, FFC0=3 Turbo, DCDD/DCDC=FF HP), screenshot + log state.
local OUT="/tmp/finalboss"; local f,done=0,false
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("finalboss\n");h:close() end end
callbacks:add("frame",function()
  if done then return end
  f=f+1
  if f==10 then pcall(function() return emu:loadStateFile("save_states_for_claude/level1_sara_d_alone.ss0") end) end
  if f==30 then emu:write8(0xFFBA,7) end  -- so next teleport INC -> 8 (Penta Dragon)
  -- pulse SELECT+START to fire the teleport
  if f>=40 and f<70 and (f%8<4) then emu:setKeys(0x0C) else emu:setKeys(0) end
  -- cheat: force powerups every gameplay frame
  if f>20 then
    emu:write8(0xFFBE,1); emu:write8(0xFFC0,3); emu:write8(0xDCDD,0xFF); emu:write8(0xDCDC,0xFF)
  end
  if f==200 then
    log(string.format("f%d D880=%02X FFBA=%02X FFBE(form)=%d FFC0(powerup)=%d HP=%02X",
      f, emu:read8(0xD880), emu:read8(0xFFBA), emu:read8(0xFFBE), emu:read8(0xFFC0), emu:read8(0xDCDD)))
    emu:screenshot(OUT..".png"); done=true; emu:stop()
  end
end)
