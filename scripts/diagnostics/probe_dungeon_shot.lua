-- Boot to the dungeon and screenshot (regression gate for the neutralized hook
-- + repointed sweep call: dungeon/title must be unchanged since neutralize only
-- affects arenas, D880 0x0C..0x14). Output: /tmp/dungeon.png
local TITLE={{180,185,0x80},{193,198,0x01},{241,246,0x01},{291,296,0x01},{341,346,0x08},{391,396,0x01}}
local f=0;local fid=0;local done=false
local function log(m) local h=io.open("/tmp/dungeon.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/dungeon.log","w"); if h then h:write("dungeon shot\n");h:close() end end
callbacks:add("frame",function()
 f=f+1
 if done then return end
 if f<=500 then local k=0;for _,e in ipairs(TITLE) do if f>=e[1] and f<=e[2] then k=e[3];break end end;emu:setKeys(k);return end
 emu:setKeys(0)
 if emu:read8(0xD880)==0x02 and emu:read8(0xFFC1)==1 then
   fid=fid+1
   if fid>=120 then
     emu:screenshot("/tmp/dungeon.png")
     log(string.format("f%d dungeon shot saved D880=0x%02X FFC1=%d",f,emu:read8(0xD880),emu:read8(0xFFC1)))
     log("DONE"); done=true
   end
 end
end)
