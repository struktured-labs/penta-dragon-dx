-- Verify OBJ cap fix: load enemy save states, run frames, dump every visible OAM
-- sprite's tile + OBJ palette index over CONSECUTIVE frames. Enemies should hold
-- a non-0 OBJ palette stably (not flicker to pal0=blue). Also confirm no freeze
-- (D880 stays sane, frames advance).
local STATE = os.getenv("STATE") or "save_states_for_claude/level1_cat_fish_moth_spike_hazard_orb_item.ss0"
local OUT = os.getenv("OUT") or "/tmp/objv"
local f, done = 0, false
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("objverify "..STATE.."\n");h:close() end end
local function dumpOAM(tag)
  -- group by (tile-range bucket) -> palette to summarize; list distinct sprites
  local s={}
  for sp=0,39 do
    local y=emu:read8(0xFE00+sp*4); local t=emu:read8(0xFE00+sp*4+2); local a=emu:read8(0xFE00+sp*4+3)&7
    if y~=0 and y<160 then s[#s+1]=string.format("t%02X:p%d",t,a) end
  end
  log(tag.." D880="..string.format("%02X",emu:read8(0xD880)).." n="..#s.." ["..table.concat(s," ").."]")
end
callbacks:add("frame", function()
  if done then return end
  f=f+1
  emu:setKeys(0)
  if f==10 then pcall(function() return emu:loadStateFile(STATE) end) end
  if f>=140 and f<=145 then dumpOAM("f"..f) end   -- consecutive frames -> stability
  if f==145 then
    emu:screenshot(OUT..".png")
    -- OBJ CRAM check (palettes loaded, not white)
    local ob=""; for p=0,7 do local i=p*8+2; emu:write8(0xFF6A,i); local lo=emu:read8(0xFF6B); emu:write8(0xFF6A,i+1); local hi=emu:read8(0xFF6B); ob=ob..string.format(" o%d=%04X",p,(hi<<8)|lo) end
    log("OBJ CRAM c1:"..ob)
    done=true; emu:stop()
  end
end)
