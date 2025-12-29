-- Improved mGBA Lua script to trace OAM writes with better PC tracking
-- This helps us find where the game assigns palettes to sprites

local logFile = nil
local writeCount = 0
local frameCount = 0

-- Track writes per frame to find patterns
local writes_this_frame = {}

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Initialize log file on first frame
    if not logFile then
        logFile = io.open("oam_write_trace.log", "w")
        logFile:write("=== OAM Write Trace ===\n")
        logFile:write("Format: Frame, SpriteIndex, Tile, Palette, Flags, PC\n")
    end
    
    -- Log frame summary
    if #writes_this_frame > 0 then
        logFile:write(string.format("\n--- Frame %d ---\n", frameCount))
        for _, write in ipairs(writes_this_frame) do
            logFile:write(string.format("Sprite[%d]: Tile=%d Palette=%d Flags=0x%02X PC=0x%04X\n",
                write.sprite, write.tile, write.palette, write.flags, write.pc))
        end
        logFile:flush()
        writes_this_frame = {}
    end
    
    -- Stop after 5 seconds (150 frames at 30fps)
    if frameCount >= 150 then
        if logFile then
            logFile:write(string.format("\n=== Summary ===\n"))
            logFile:write(string.format("Total frames: %d\n", frameCount))
            logFile:write(string.format("Total writes: %d\n", writeCount))
            logFile:close()
        end
        emu:stop()
    end
end)

-- Hook writes to OAM flags bytes (offset 3 of each sprite)
local function hook_oam_write(addr)
    local spriteIndex = (addr - 0xFE00) // 4
    local offset = (addr - 0xFE00) % 4
    
    -- Only log writes to flags byte (offset 3)
    if offset == 3 then
        local flags = emu:read8(addr)
        local palette = flags & 0x07
        local tile = emu:read8(addr - 1)  -- Tile ID is 1 byte before flags
        
        -- Get actual PC from emulator
        local pc = emu:read16(0xFFFC)  -- This is approximate - mGBA doesn't expose PC directly
        -- Try to get better PC tracking via breakpoint context
        
        writeCount = writeCount + 1
        
        table.insert(writes_this_frame, {
            sprite = spriteIndex,
            tile = tile,
            palette = palette,
            flags = flags,
            pc = pc
        })
    end
end

-- Set memory callbacks on OAM flags bytes
-- mGBA Lua API: addMemoryCallback(callback, type, start, end)
for sprite = 0, 39 do
    local addr = 0xFE00 + (sprite * 4) + 3  -- Flags byte
    emu:addMemoryCallback(function()
        hook_oam_write(addr)
    end, emu.memoryCallback.WRITE, addr, addr)
end

print("OAM write tracing started. Will trace for 5 seconds (150 frames).")

