-- Inspect title-screen text coloring: for each title text row, dump per-cell
-- (tile, palette) so we can see if a single word has mixed palettes (the
-- 0x80-0x87 pal0 vs 0x88-0x99 pal1 two-tone). Also dump BG CRAM pal0/1/5.
local function log(m) local h=io.open("/tmp/titleattr.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/titleattr.log","w"); if h then h:write("title attr\n");h:close() end end
local f=0;local done=false
local function rdbg(p,c) local i=p*8+c*2; emu:write8(0xFF68,i); local lo=emu:read8(0xFF69)
  emu:write8(0xFF68,i+1); local hi=emu:read8(0xFF69); return (hi<<8)|lo end
callbacks:add("frame",function()
 f=f+1; emu:setKeys(0)
 if f~=400 or done then return end
 done=true
 local base = ((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
 log("active tilemap base=0x"..string.format("%04X",base).." LCDC=0x"..string.format("%02X",emu:read8(0xFF40)))
 for _,r in ipairs({1,2,3,6,8,10,15,17}) do
   emu:write8(0xFF4F,0); local tiles={}
   for c=0,19 do tiles[c]=emu:read8(base+r*32+c) end
   emu:write8(0xFF4F,1); local at={}
   for c=0,19 do at[c]=emu:read8(base+r*32+c)&7 end
   emu:write8(0xFF4F,0)
   local s="row"..r..":"
   for c=0,19 do if tiles[c]~=0x00 then s=s..string.format(" %02X/p%d",tiles[c],at[c]) end end
   log(s)
 end
 log(string.format("CRAM pal0c1=%04X pal1c1=%04X pal5c1=%04X pal6c1=%04X",rdbg(0,1),rdbg(1,1),rdbg(5,1),rdbg(6,1)))
 log("DONE")
end)
