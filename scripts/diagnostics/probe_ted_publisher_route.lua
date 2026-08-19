-- Diagnose the fixed Ted caller and its WRAM/native publication route.
local OUT = assert(os.getenv("TED_ROUTE_OUT"))
local FRAMES = tonumber(os.getenv("TED_ROUTE_FRAMES") or "600")
local counts = {}
local events = assert(io.open(OUT .. ".events", "w"))
local frame = 0
local function reg(name)
  for _, reader in ipairs({
    function() return emu:getRegister(name) end,
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:readRegister(name) end,
    function() return emu:readRegister(string.lower(name)) end,
  }) do
    local ok, value = pcall(reader)
    if ok and value ~= nil then return value & 0xFFFF end
  end
  return 0xFFFF
end
local sites = {0x028A, 0x028D, 0xDB87, 0xDB8A, 0x4295, 0x42A7,
               0x578C, 0x58E0, 0x5910, 0x5940, 0x5970, 0x5E5C,
               0x57BC}
for _, site in ipairs(sites) do
  counts[site] = 0
  -- Some mGBA builds reject WRAM breakpoints while accepting ROM sites.
  -- Keep those counts at zero instead of aborting the entire route receipt;
  -- the fixed-bank $4295/$42A7 hooks remain authoritative publications.
  pcall(function() emu:setBreakpoint(function()
    counts[site] = counts[site] + 1
    if site == 0x028D or site == 0x4295 or site == 0x5E5C or site == 0x57BC or site == 0x5910 then
      events:write(string.format("frame=%d site=%04X bank=%02X a=%02X f=%02X bc=%04X de=%04X hl=%04X sp=%04X\n",
        frame, site, emu:read8(0xFF70), reg("a") & 0xFF,
        reg("f") & 0xFF, reg("bc"), reg("de"), reg("hl"), reg("sp")))
      events:flush()
    end
  end, site) end)
end
callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)
  emu:write8(0xDCBB, 0xF0)
  emu:write8(0xDCDC, 0xFF); emu:write8(0xDCDD, 0xFF)
  if frame == FRAMES then
    local out = assert(io.open(OUT, "w"))
    out:write(string.format("frames=%d scene=%02X bank=%02X\n",
      frame, emu:read8(0xD880), emu:read8(0xFF70)))
    for _, site in ipairs(sites) do
      out:write(string.format("site=%04X count=%d\n", site, counts[site]))
    end
    out:write("db87=")
    for address = 0xDB87, 0xDB9D do
      out:write(string.format("%02X", emu:read8(address)))
    end
    out:write("\n")
    out:close()
    events:close()
    local done = assert(io.open(OUT .. ".done", "w")); done:write("ok\n"); done:close()
    emu:stop()
  end
end)
