-- Dump CGB VRAM bank 0 plus hardware OAM from a loaded gameplay savestate.
-- Used to match title-reel resource graphics against the same monster art in
-- ordinary gameplay, where the YAML-compiled tile palette is authoritative.

local PREFIX = assert(
    os.getenv("VRAM_OBJ_PREFIX"), "VRAM_OBJ_PREFIX is required")
local frame = 0

local function byte_string(first, last)
    local chunks = {}
    local chunk = {}
    for address = first, last do
        chunk[#chunk + 1] = string.char(emu:read8(address))
        if #chunk == 256 then
            chunks[#chunks + 1] = table.concat(chunk)
            chunk = {}
        end
    end
    if #chunk > 0 then chunks[#chunks + 1] = table.concat(chunk) end
    return table.concat(chunks)
end

callbacks:add("frame", function()
    frame = frame + 1
    emu:setKeys(0)
    if frame ~= 1 then return end

    local old_vbk = emu:read8(0xFF4F)
    emu:write8(0xFF4F, 0)

    local vram = assert(io.open(PREFIX .. ".vram0.bin", "wb"))
    vram:write(byte_string(0x8000, 0x97FF))
    vram:close()

    local oam = assert(io.open(PREFIX .. ".oam.bin", "wb"))
    oam:write(byte_string(0xFE00, 0xFE9F))
    oam:close()

    local entities = assert(io.open(PREFIX .. ".entities.bin", "wb"))
    entities:write(byte_string(0xDC85, 0xDCAC))
    entities:close()

    local meta = assert(io.open(PREFIX .. ".meta", "w"))
    meta:write(string.format(
        "D880=%02X FFC1=%02X FFBA=%02X FFBE=%02X FFBF=%02X "
            .. "old_VBK=%02X\n",
        emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xFFBA),
        emu:read8(0xFFBE), emu:read8(0xFFBF), old_vbk))
    meta:close()

    emu:write8(0xFF4F, old_vbk)
    os.exit(0)
end)
