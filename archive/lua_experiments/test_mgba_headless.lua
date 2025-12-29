-- Simple test script for mgba-headless
-- Based on working_trace_oam_writes.lua pattern

local logFile = nil
local frameCount = 0
local oamWrites = {}

-- Initialize on first frame
callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Initialize on first frame
    if frameCount == 1 then
        logFile = io.open("test_output/latest/logs/mgba_headless_test.log", "w")
        if not logFile then
            print("ERROR: Could not open log file!")
            return
        end
        logFile:write("=== mgba-headless Test Log ===\n")
        logFile:write("Frame, SpriteIndex, Tile, Palette, Flags, PC\n")
        
        -- Set up OAM write callbacks (flags bytes only)
        for sprite = 0, 39 do
            local flagsAddr = 0xFE00 + (sprite * 4) + 3
            emu:addMemoryCallback(function(addr, value)
                local spriteIndex = math.floor((addr - 0xFE00) / 4)
                local tileAddr = addr - 1
                local tile = emu:read8(tileAddr)
                local pc = emu:getRegister("PC")
                
                table.insert(oamWrites, {
                    frame = frameCount,
                    sprite = spriteIndex,
                    tile = tile,
                    palette = value & 0x07,
                    flags = value,
                    pc = pc
                })
            end, emu.memoryCallback.WRITE, flagsAddr, flagsAddr)
        end
    end
    
    if not logFile then return end
    
    -- Log OAM writes every frame (for debugging)
    if #oamWrites > 0 then
        for _, write in ipairs(oamWrites) do
            logFile:write(string.format("%d, %d, %d, %d, 0x%02X, 0x%04X\n",
                write.frame, write.sprite, write.tile, write.palette, write.flags, write.pc))
        end
        oamWrites = {}  -- Clear after logging
    end
    
    -- Log OAM state every 60 frames
    if frameCount % 60 == 0 then
        logFile:write(string.format("\n=== Frame %d OAM State ===\n", frameCount))
        
        -- Log visible sprites
        for i = 0, 39 do
            local oamBase = 0xFE00 + (i * 4)
            local y = emu:read8(oamBase)
            local x = emu:read8(oamBase + 1)
            local tile = emu:read8(oamBase + 2)
            local flags = emu:read8(oamBase + 3)
            local palette = flags & 0x07
            
            if y > 0 and y < 144 then  -- Visible sprite
                logFile:write(string.format("Sprite %2d: Y=%3d X=%3d Tile=%3d Palette=%d Flags=0x%02X\n",
                    i, y, x, tile, palette, flags))
            end
        end
        logFile:flush()
    end
    
    -- Stop after 5 seconds (300 frames at 60fps)
    if frameCount >= 300 then
        logFile:write(string.format("\n=== Summary ===\n"))
        logFile:write(string.format("Total frames: %d\n", frameCount))
        logFile:close()
        emu:stop()
    end
end)

print("mgba-headless test script loaded")

