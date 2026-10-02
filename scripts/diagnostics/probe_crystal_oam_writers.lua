-- Identify the stock routine that elects to emit Crystal Dragon sprites.
-- This is read-only evidence: it traces calls into the central sprite emitter
-- and records their banked callers, then samples the resulting body count.
-- #41: native assistance writes physical WRAM bank1 regardless of the SVBK
-- bank a graphics routine selected. #37: never write DCDC/DCDD (inventory /
-- ten-slot cursor) as fake health; DCBB is the health byte.
local native_assistance = {writes = 0, bank_shadow_counts = {}}
function native_assistance.write(address, value)
  local svbk = emu:read8(0xFF70) & 7
  native_assistance.writes = native_assistance.writes + 1
  native_assistance.bank_shadow_counts[svbk] =
    (native_assistance.bank_shadow_counts[svbk] or 0) + 1
  assert(emu.memory and emu.memory.wram, "physical WRAM required for assistance")
    :write8(address - 0xC000, value)
end

local OUT = assert(os.getenv("CRYSTAL_OAM_WRITER_OUT"),
    "CRYSTAL_OAM_WRITER_OUT required")
local FRAMES = tonumber(os.getenv("CRYSTAL_OAM_WRITER_FRAMES") or "120")
local EXPECTED_SCENE = tonumber(
    os.getenv("CRYSTAL_FLICKER_EXPECTED_SCENE") or "14")
local frame = 0
local trace = assert(io.open(OUT .. ".tsv", "w"))
trace:write("kind\tframe\tbank\tcaller\ty\tx\ttile\tffd4\tbody\n")

local function register(name)
    local readers = {
        function() return emu:getRegister(string.lower(name)) end,
        function() return emu:getRegister(string.upper(name)) end,
        function() return emu:readRegister(string.lower(name)) end,
        function() return emu:readRegister(string.upper(name)) end,
    }
    for _, reader in ipairs(readers) do
        local ok, value = pcall(reader)
        if ok and value ~= nil then return value & 0xFFFF end
    end
    return 0xFFFF
end

local function read16(address)
    return emu:read8(address) | (emu:read8((address + 1) & 0xFFFF) << 8)
end

local function four_sprite_emitter()
    if emu:read8(0xD880) ~= EXPECTED_SCENE then return end
    local sp, hl = register("sp"), register("hl")
    trace:write(string.format(
        "emit\t%d\t%02X\t%04X\t%02X\t%02X\t%02X\t%02X\t-\n",
        frame, emu:read8(0xFF99), read16(sp), register("b") & 0xFF,
        register("c") & 0xFF, emu:read8(hl), emu:read8(0xFFD4)))
end

pcall(function()
    emu:setBreakpoint(four_sprite_emitter, 0x021A)
end)

local function body_count()
    local count = 0
    for slot = 4, 19 do
        local address = 0xFE00 + slot * 4
        local y, x, tile = emu:read8(address), emu:read8(address + 1),
            emu:read8(address + 2)
        if y >= 16 and y < 160 and x >= 8 and x < 168 and
            tile >= 0x40 and tile <= 0x66 then
            count = count + 1
        end
    end
    return count
end

local function finish(status)
    trace:write(string.format("complete\t%s\t%d\n", status, frame))
    trace:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(status .. "\n")
    marker:close()
    os.exit(status == "ok" and 0 or 2)
end

callbacks:add("frame", function()
    frame = frame + 1
    emu:setKeys(0)
    native_assistance.write(0xDCBB, 0xF0)
    if emu:read8(0xD880) ~= EXPECTED_SCENE then
        finish("wrong-scene")
        return
    end
    trace:write(string.format(
        "frame\t%d\t-\t-\t-\t-\t-\t%02X\t%d\n",
        frame, emu:read8(0xFFD4), body_count()))
    trace:flush()
    if frame >= FRAMES then finish("ok") end
end)
