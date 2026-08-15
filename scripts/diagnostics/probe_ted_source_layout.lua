-- Capture Ted's complete 24x24 source publications for sanitizer diagnosis.
-- Read-only apart from deterministic boss-idle inputs used by every boss probe.

local OUT = assert(os.getenv("TED_SOURCE_LAYOUT_OUT"), "TED_SOURCE_LAYOUT_OUT required")
local LIMIT = tonumber(os.getenv("TED_SOURCE_LAYOUT_COPIES") or "32")
local SOURCE, SIZE, SCENE = 0xC1A0, 24 * 24, 0x10
local copies, frames, finished = 0, 0, false
local out = assert(io.open(OUT, "w"))

local function finish(status)
    if finished then return end
    finished = true
    out:write(string.format("status=%s frames=%d copies=%d\n", status, frames, copies))
    out:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write("status=" .. status .. "\n")
    marker:close()
    os.exit(status == "ok" and 0 or 1)
end

local function capture()
    if emu:read8(0xD880) ~= SCENE then return end
    copies = copies + 1
    out:write(string.format("copy=%d frame=%d\n", copies, frames))
    for row = 0, 23 do
        for col = 0, 23 do
            out:write(string.format("%02X", emu:read8(SOURCE + row * 24 + col)))
            if col ~= 23 then out:write(" ") end
        end
        out:write("\n")
    end
    if copies >= LIMIT then finish("ok") end
end

callbacks:add("frame", function()
    frames = frames + 1
    local svbk = emu:read8(0xFF70) & 0x07
    if svbk ~= 0 and svbk ~= 1 then return end
    capture()
    emu:setKeys(0)
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    emu:write8(0xD888, 0x00)
    emu:write8(0xDD06, 0x00)
    if emu:read8(0xD880) ~= SCENE then finish("wrong-scene") end
    if frames >= 600 then finish(copies > 0 and "ok" or "no-copies") end
end)
