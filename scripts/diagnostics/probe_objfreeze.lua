-- Freeze/progress check for the HW-OAM recolor: cold-boot, auto-start into the
-- dungeon, run long, confirm D880 progresses + frame counter advances (no hang).
local OUT=os.getenv("OUT") or "/tmp/objfreeze"
local f,done=0,false
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("objfreeze\n");h:close() end end
local function press(lo,hi,m) return (f>=lo and f<hi) and m or 0 end
callbacks:add("frame", function()
  if done then return end
  f=f+1
  local k=press(180,186,0x80)|press(193,199,0x01)|press(241,247,0x01)|press(291,297,0x01)|press(341,347,0x08)|press(391,397,0x01)
  if f>430 then k=0x10|((f%4<2) and 0x01 or 0) end  -- walk+fire in dungeon
  emu:setKeys(k)
  if f%400==0 then log(string.format("f%d D880=%02X FFC1=%d FFBA=%02X",f,emu:read8(0xD880),emu:read8(0xFFC1),emu:read8(0xFFBF))) end
  if f==2400 then emu:screenshot(OUT..".png"); log("reached f2400 D880="..string.format("%02X",emu:read8(0xD880))); done=true; emu:stop() end
end)
