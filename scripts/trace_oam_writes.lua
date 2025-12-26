-- mGBA Lua script to trace where OAM palette bits are written
-- This helps us find where the game assigns palettes to sprites

local logFile = io.open("oam_write_trace.log", "w")
local writeCount = 0

-- Hook writes to OAM (0xFE00-0xFE9F)
-- Each sprite is 4 bytes: Y, X, Tile, Flags (palette bits are in Flags byte)
local function hook_oam_write(addr)
    local spriteIndex = (addr - 0xFE00) // 4
    local offset = (addr - 0xFE00) % 4
    
    -- Only log writes to flags byte (offset 3)
    if offset == 3 then
        local flags = emu:read8(addr)
        local palette = flags & 0x07
        local tile = emu:read8(addr - 1)  -- Tile ID is 1 byte before flags
        
        -- Get call stack to find where this write came from
        local pc = emu:read16(0xFFFC)  -- Program counter (approximate)
        
        writeCount = writeCount + 1
        logFile:write(string.format("Write #%d: Sprite[%d] Flags=0x%02X Palette=%d Tile=%d PC~0x%04X\n",
            writeCount, spriteIndex, flags, palette, tile, pc))
        logFile:flush()
        
        -- Stop after 1000 writes to avoid huge log
        if writeCount >= 1000 then
            emu:stop()
        end
    end
end

-- Set breakpoints on OAM writes
for addr = 0xFE00, 0xFE9F do
    emu:setBreakpoint(addr, function()
        hook_oam_write(addr)
    end)
end

callbacks:add("shutdown", function()
    logFile:write(string.format("\nTotal OAM writes logged: %d\n", writeCount))
    logFile:close()
end)

print("OAM write tracing started. Will log first 1000 writes to flags bytes.")
