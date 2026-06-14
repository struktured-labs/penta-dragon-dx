-- Try to reach the victory ending (bank1:0x54C0) for capture. From the title
-- screen bank 1 is mapped, so set FFBA=6 and redirect execution to 0x54C0.
-- Probe several mechanisms and log which works. Capture screenshots through the
-- ending scenes (D880 0x19 -> 0x1A -> 0x16).
local OUT = os.getenv("OUT") or "/tmp/ending"
local f, fired, shots = 0, false, 0
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("ending trigger probe\n");h:close() end end

-- discover available register API once
local function tryReg()
  local ok = pcall(function() return emu:setRegister("pc", emu:readRegister("pc")) end)
  log("setRegister/readRegister available: "..tostring(ok))
  return ok
end

local haveReg = nil
callbacks:add("frame", function()
  f = f + 1
  emu:setKeys(0)
  if haveReg == nil then haveReg = tryReg() end
  -- let the title settle (bank 1 mapped here)
  if f == 400 and not fired then
    fired = true
    emu:write8(0xFFBA, 0x06)
    -- map ROM bank 1 (MBC1) so 0x54C0 is the ending code
    emu:write8(0x2100, 0x01)
    if haveReg then
      pcall(function() emu:setRegister("pc", 0x54C0) end)
      log(string.format("f%d fired setRegister pc=0x54C0 FFBA=6 d880=%02X", f, emu:read8(0xD880)))
    else
      log("no setRegister; cannot redirect PC")
    end
  end
  if fired and f > 400 and f % 40 == 0 and shots < 12 then
    shots = shots + 1
    emu:screenshot(string.format("%s_%02d.png", OUT, shots))
    log(string.format("f%d shot%d D880=%02X FFC1=%d FFBA=%02X", f, shots,
      emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xFFBA)))
  end
  if f > 1000 then log("DONE"); emu:stop() end
end)
