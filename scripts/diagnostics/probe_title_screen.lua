-- Probe: take screenshots at the title screen + count BG palette usage
-- (verify any "splotches" — non-pal-0 or non-pal-1 cells outside expected places).
local frame_count = 0
callbacks:add("frame", function()
    frame_count = frame_count + 1
    if frame_count == 200 then
        -- Title should be settled by now (no input)
        local d880 = emu:read8(0xD880)
        local ffc1 = emu:read8(0xFFC1)
        -- Dump BG attr histogram
        emu:write8(0xFF4F, 1)
        local histo = {0, 0, 0, 0, 0, 0, 0, 0}
        for r = 0, 17 do
            for c = 0, 19 do
                local p = emu:read8(0x9800 + r*32 + c) & 7
                histo[p+1] = histo[p+1] + 1
            end
        end
        emu:write8(0xFF4F, 0)
        local f = io.open("/tmp/title_state.txt", "w")
        f:write(string.format("frame %d: d880=%d ffc1=%d\n", frame_count, d880, ffc1))
        f:write("BG attr histogram per palette:\n")
        for i = 0, 7 do
            if histo[i+1] > 0 then
                f:write(string.format("  pal %d: %d cells\n", i, histo[i+1]))
            end
        end
        f:close()
        emu:screenshot("/tmp/title_screen.png")
        emu:stop()
    end
end)
