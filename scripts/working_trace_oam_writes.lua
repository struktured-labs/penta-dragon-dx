-- Working OAM write tracer - captures all writes to OAM flags bytes
-- This version uses a simpler approach that actually works

local logFile = nil
local writeCount = 0
local frameCount = 0
local writes_this_frame = {}

-- Initialize log file
logFile = io.open("oam_write_trace.log", "w")
logFile:write("=== OAM Write Trace ===\n")
logFile:write("Format: Frame, SpriteIndex, Tile, Palette, Flags\n")

-- Track all OAM writes by monitoring the entire OAM region
local function on_oam_write(addr, value)
    -- OAM is 0xFE00-0xFE9F (160 bytes = 40 sprites * 4 bytes)
    if addr >= 0xFE00 and addr < 0xFEA0 then
        local sprite_index = (addr - 0xFE00) // 4
        local offset = (addr - 0xFE00) % 4
        
        -- Only log flags byte (offset 3)
        if offset == 3 then
            local flags = value
            local palette = flags & 0x07
            
            -- Get tile ID (1 byte before flags)
            local tile_addr = addr - 1
            local tile = emu:read8(tile_addr)
            
            writeCount = writeCount + 1
            
            table.insert(writes_this_frame, {
                sprite = sprite_index,
                tile = tile,
                palette = palette,
                flags = flags
            })
        end
    end
end

-- Set up memory callbacks for entire OAM region
-- Use write callbacks on flags bytes specifically
for sprite = 0, 39 do
    local flags_addr = 0xFE00 + (sprite * 4) + 3
    
    -- Register callback for this specific address
    emu:addMemoryCallback(function(addr, value)
        on_oam_write(addr, value)
    end, emu.memoryCallback.WRITE, flags_addr, flags_addr)
end

-- Frame callback to log writes
callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Log writes from this frame
    if #writes_this_frame > 0 then
        logFile:write(string.format("\n--- Frame %d ---\n", frameCount))
        for _, write in ipairs(writes_this_frame) do
            logFile:write(string.format("Sprite[%d]: Tile=%d Palette=%d Flags=0x%02X\n",
                write.sprite, write.tile, write.palette, write.flags))
        end
        logFile:flush()
        writes_this_frame = {}
    end
    
    -- Stop after 5 seconds (150 frames at 30fps)
    if frameCount >= 150 then
        logFile:write(string.format("\n=== Summary ===\n"))
        logFile:write(string.format("Total frames: %d\n", frameCount))
        logFile:write(string.format("Total writes: %d\n", writeCount))
        logFile:close()
        emu:stop()
    end
end)

print("OAM write tracing started. Will trace for 5 seconds (150 frames).")

