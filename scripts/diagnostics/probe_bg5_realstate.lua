-- Load a real stage-1 dungeon save state, run frames so the colorizer reloads
-- palettes, then dump all 8 BG palettes + pal5 fully. Confirms whether the
-- palette system loads BG5 as lava (03FF/001F) in genuine gameplay (vs the
-- degenerate level-select hacked state where palette loading is unreliable).
local PATH = os.getenv("STATE") or "save_states_for_claude/level1_sara_d_alone.ss0"
local OUT = os.getenv("OUT") or "/tmp/bg5_real"
local f, done = 0, false
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("bg5 realstate "..PATH.."\n");h:close() end end
local function rdbg(p,c) local i=p*8+c*2; emu:write8(0xFF68,i); local lo=emu:read8(0xFF69)
  emu:write8(0xFF68,i+1); local hi=emu:read8(0xFF69); return (hi<<8)|lo end
callbacks:add("frame", function()
  if done then return end
  f = f + 1
  emu:setKeys(0)
  if f == 10 then pcall(function() return emu:loadStateFile(PATH) end) end
  -- Force MY ROM's colorizer to reload palettes from bank-13 bg_data (the save
  -- state carries the OLD build's CRAM + a matching DF00 hash, so cond_pal would
  -- otherwise cache-skip). DF02=0 -> cold-boot path resets DF00=0 -> cond_pal
  -- reloads. Hold for a few frames so the reload definitely lands.
  if f >= 12 and f <= 40 then emu:write8(0xDF02, 0x00); emu:write8(0xDF00, 0x00) end
  if f == 160 then
    done = true
    log(string.format("D880=%02X FFC1=%d FFBA=%02X FFBD=%02X",
      emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xFFBA), emu:read8(0xFFBD)))
    for p=0,7 do
      log(string.format("BG pal%d: %04X %04X %04X %04X", p, rdbg(p,0),rdbg(p,1),rdbg(p,2),rdbg(p,3)))
    end
    emu:screenshot(OUT..".png")
    log("DONE")
    emu:stop()
  end
end)
