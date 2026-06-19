-- Probe: at title screen + force DCFD=1 + force D880=0x00, dump BG pal 0
-- (which the level-select letters use) and check readability against itself.
local frame_count = 0
local OUT = "/tmp/levelselect_palette.json"
local INPUT_SEQ = {
    -- DOWN to select GAME START (which checks DCFD)
    {f=180, key=0x80, dur=6}, -- DOWN
    {f=193, key=0x01, dur=6}, -- A
    {f=241, key=0x01, dur=6}, -- A
    {f=291, key=0x01, dur=6}, -- A
    {f=341, key=0x08, dur=6}, -- START
    {f=391, key=0x01, dur=6}, -- A
}
local last_key = 0

callbacks:add("frame", function()
    frame_count = frame_count + 1
    -- Force DCFD=1 early so GAME START dispatches to level-select
    if frame_count == 60 then
        emu:write8(0xDCFD, 0x01)
    end
    local key = 0
    for _, ev in ipairs(INPUT_SEQ) do
        if frame_count >= ev.f and frame_count < ev.f + ev.dur then
            key = ev.key
            break
        end
    end
    emu:setKeys(key)

    if frame_count == 500 then
        -- Dump BG palette 0 (CGB BG palette RAM via FF68/FF69)
        emu:write8(0xFF68, 0x80)  -- auto-increment, addr 0
        local pal0 = {}
        for i = 1, 8 do
            pal0[i] = emu:read8(0xFF69)
        end
        -- Dump all 8 BG palettes
        local all_pal = {}
        emu:write8(0xFF68, 0x80)
        for i = 1, 64 do
            all_pal[i] = emu:read8(0xFF69)
        end
        -- Dump D880, FFC1, DCFD state
        local d880 = emu:read8(0xD880)
        local ffc1 = emu:read8(0xFFC1)
        local dcfd = emu:read8(0xDCFD)
        local lcdc = emu:read8(0xFF40)
        emu:screenshot("/tmp/levelselect_state.png")

        local f = io.open(OUT, "w")
        f:write(string.format(
            '{"frame":%d,"d880":%d,"ffc1":%d,"dcfd":%d,"lcdc":%d,"bg_pal0":[%d,%d,%d,%d,%d,%d,%d,%d],"all_bg_pal":[',
            frame_count, d880, ffc1, dcfd, lcdc,
            pal0[1], pal0[2], pal0[3], pal0[4], pal0[5], pal0[6], pal0[7], pal0[8]))
        for i = 1, 64 do
            if i > 1 then f:write(",") end
            f:write(tostring(all_pal[i]))
        end
        f:write("]}")
        f:close()
        emu:stop()
    end
end)
