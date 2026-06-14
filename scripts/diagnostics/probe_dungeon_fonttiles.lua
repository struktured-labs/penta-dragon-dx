-- Do tiles 0x80-0x87 (font letters A-H, also potential dungeon BG/item tiles)
-- appear in a real dungeon room? If NOT, we can safely extend the item palette
-- down to 0x80 in the dungeon table (one-line global font fix). Loads a dungeon
-- save state and histograms tile IDs 0x80-0x9F in the active tilemap.
local function log(m) local h=io.open("/tmp/dft.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/dft.log","w"); if h then h:write("dungeon font tiles\n");h:close() end end
local PATH=nil
do local h=io.open("/tmp/state_path.txt","r"); if h then PATH=h:read("*l"); h:close() end end
local f=0;local done=false
callbacks:add("frame",function()
 f=f+1
 if f==10 and PATH then pcall(function() return emu:loadStateFile(PATH) end) end
 if f>=90 and not done then
   done=true
   local base=((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
   local cnt={}
   for r=0,17 do for c=0,19 do local t=emu:read8(base+r*32+c); cnt[t]=(cnt[t] or 0)+1 end end
   local s="tiles 0x80-0x9F present:"
   for t=0x80,0x9F do if cnt[t] then s=s..string.format(" %02X(%d)",t,cnt[t]) end end
   log(s)
   log(string.format("D880=0x%02X FFC1=%d base=0x%04X",emu:read8(0xD880),emu:read8(0xFFC1),base))
   log("DONE")
 end
end)
