-- Dump BG palette RAM (CGB) at a given frame.
-- Output: hex dump of all 64 bytes of BG palette RAM (8 palettes × 8 bytes each).
-- Method: write BCPS=0x80 (auto-increment from index 0), read BCPD 64 times.
local OUT = os.getenv("STATE_PATH") or "/tmp/penta_bg_pal.txt"
local FRAME_AT = tonumber(os.getenv("FRAME_AT") or "600")

local fired = false

callbacks:add("frame", function()
    local f = emu:currentFrame()
    if not fired and f >= FRAME_AT then
        fired = true
        local fh = io.open(OUT, "w")
        -- CGB BCPS auto-inc fires only on WRITES to BCPD, not reads.
        -- So set the index explicitly for each read.
        local bytes = {}
        for i = 0, 63 do
            emu:write8(0xFF68, i)
            local b = emu:read8(0xFF69)
            bytes[#bytes+1] = string.format("%02X", b)
        end
        fh:write("# BG palette RAM (64 bytes, 8 palettes × 4 colors × 2 bytes BGR555)\n")
        for p = 0, 7 do
            local line = string.format("pal%d:", p)
            for c = 0, 3 do
                local off = (p * 8) + (c * 2) + 1
                line = line .. " " .. bytes[off] .. bytes[off+1]
            end
            fh:write(line .. "\n")
        end
        fh:write("# raw=" .. table.concat(bytes, "") .. "\n")
        fh:close()
        console:log("dump_bg_palette wrote " .. OUT .. " at frame " .. f)
        os.exit(0)
    end
end)
