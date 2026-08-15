-- Record Ted's row-major C1A0 publication order beside both physical crowns.
local OUT = assert(os.getenv("TED_PUBLICATION_ORDER_OUT"))
local FRAMES = tonumber(os.getenv("TED_PUBLICATION_ORDER_FRAMES") or "1000")
local out = assert(io.open(OUT, "w"))
local frame, events, done = 0, 0, false
local targets = {
    [0x13]=true, [0x14]=true, [0x1C]=true, [0x1F]=true,
    [0x20]=true, [0x27]=true, [0x28]=true,
}

local function crowns(base)
    local result = {}
    for row=0,31 do
        for col=0,27 do
            local match = true
            for step=0,4 do
                if emu:read8(base + row*32 + col + step) ~= 0x02 + step then
                    match = false
                    break
                end
            end
            if match then result[#result+1] = {row, col} end
        end
    end
    return result
end

callbacks:add("frame", function()
    if done then return end
    frame = frame + 1
    if frame == 1 then emu:write8(0xC5FF, 0) end
    emu:setKeys(0)
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    emu:write8(0xD888, 0)
    emu:write8(0xDD06, 0)
    for offset=0,24*24-1 do
        local tile = emu:read8(0xC1A0 + offset)
        if targets[tile] then
            events = events + 1
            out:write(string.format("S\t%d\t%d\t%d\t%d\t%02X\n",
                frame, offset, math.floor(offset/24), offset%24, tile))
        end
    end
    for _,base in ipairs({0x9800, 0x9C00}) do
        local found = crowns(base)
        if #found == 1 then
            out:write(string.format("F\t%d\t%04X\t%d\t%d\n",
                frame, base, found[1][1], found[1][2]))
        end
    end
    if frame >= FRAMES or emu:read8(0xD880) ~= 0x10 then
        done = true
        out:close()
        local marker = assert(io.open(OUT .. ".done", "w"))
        marker:write(string.format("status=ok frames=%d events=%d\n",
            frame, events))
        marker:close()
        if emu.stop then emu:stop() end
    end
end)
