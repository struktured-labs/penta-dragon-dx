-- Dump live Stage 1 tile graphics, tilemaps, attributes, and BG CRAM after a
-- normal cold-boot GAME START route. Used to prove whether a pickup-only
-- palette can preserve every surrounding floor pixel.

local OUT = assert(os.getenv("PICKUP_ART_OUT"))
local KEY_A, KEY_START, KEY_DOWN = 0x01, 0x08, 0x80
local frame, stable, done = 0, 0, false

local function keys()
    local schedule = {
        {180, 185, KEY_DOWN},
        {201, 206, KEY_A},
        {261, 266, KEY_A},
        {321, 326, KEY_A},
        {381, 386, KEY_START},
        {431, 436, KEY_A},
    }
    for _, row in ipairs(schedule) do
        if frame >= row[1] and frame <= row[2] then return row[3] end
    end
    return 0
end

local function dump_range(path, first, last)
    local handle = assert(io.open(path, "wb"))
    for address = first, last do
        handle:write(string.char(emu:read8(address)))
    end
    handle:close()
end

local function dump()
    local old_vbk = emu:read8(0xFF4F)
    for bank = 0, 1 do
        emu:write8(0xFF4F, bank)
        dump_range(
            string.format("%s.vram%d.bin", OUT, bank),
            0x8000, 0x9FFF
        )
    end
    emu:write8(0xFF4F, old_vbk)

    local old_bcps = emu:read8(0xFF68)
    local cram = assert(io.open(OUT .. ".bg-cram.bin", "wb"))
    for index = 0, 63 do
        emu:write8(0xFF68, index)
        cram:write(string.char(emu:read8(0xFF69)))
    end
    cram:close()
    emu:write8(0xFF68, old_bcps)

    local state = assert(io.open(OUT .. ".state.txt", "w"))
    state:write(string.format(
        "frame=%d\nD880=%02X\nFFC1=%02X\nLCDC=%02X\nSCX=%02X\nSCY=%02X\n",
        frame, emu:read8(0xD880), emu:read8(0xFFC1),
        emu:read8(0xFF40), emu:read8(0xFF43), emu:read8(0xFF42)
    ))
    state:close()
    emu:screenshot(OUT .. ".png")
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write("ok\n")
    marker:close()
    done = true
    os.exit(0)
end

callbacks:add("frame", function()
    if done then return end
    frame = frame + 1
    emu:setKeys(keys())
    if emu:read8(0xD880) == 0x02 and emu:read8(0xFFC1) == 1 then
        stable = stable + 1
        if stable >= 180 then dump() end
    else
        stable = 0
    end
end)
