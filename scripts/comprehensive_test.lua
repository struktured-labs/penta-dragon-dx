-- Comprehensive testing script for ROM colorization
-- Based on working_trace_oam_writes.lua pattern
-- Logs OAM state, palette state, performance metrics, and captures screenshots

local logFile = nil
local frameCount = 0
local startTime = 0
local oamWrites = {}
local paletteWrites = {}
local performanceData = {}
local writes_this_frame = {}

-- Initialize on first frame
callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Initialize on first frame
    if frameCount == 1 then
        logFile = io.open("test_output/latest/logs/comprehensive_test.log", "w")
        if not logFile then
            print("ERROR: Could not open log file!")
            return
        end
        logFile:write("=== Comprehensive Test Log ===\n")
        startTime = emu:time()
        
        -- Set up OAM write callbacks
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
        
        -- Set up palette write callbacks
        emu:addMemoryCallback(function(addr, value)
            table.insert(paletteWrites, {
                frame = frameCount,
                register = string.format("0x%04X", addr),
                value = value,
                pc = emu:getRegister("PC")
            })
        end, emu.memoryCallback.WRITE, 0xFF68, 0xFF6B)
    end
    
    if not logFile then return end
    
    -- Capture screenshot every 60 frames
    if frameCount % 60 == 0 then
        local screenshot = emu:takeScreenshot()
        screenshot:save(string.format("test_output/latest/screenshots/frame_%05d.png", frameCount))
    end
    
    -- Log performance every 10 frames
    if frameCount % 10 == 0 then
        local currentTime = emu:time()
        local elapsed = currentTime - startTime
        local fps = frameCount / elapsed
        table.insert(performanceData, {
            frame = frameCount,
            elapsed = elapsed,
            fps = fps
        })
    end
    
    -- Log OAM state every 60 frames
    if frameCount % 60 == 0 then
        logFile:write(string.format("\n=== Frame %d ===\n", frameCount))
        
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
        
        -- Log OBJ palettes
        logFile:write("OBJ Palettes:\n")
        for pal = 0, 7 do
            emu:write8(0xFF6A, 0x80 | (pal * 8))
            local colors = {}
            for i = 0, 3 do
                emu:write8(0xFF6A, 0x80 | (pal * 8) | (i * 2))
                local lo = emu:read8(0xFF6B)
                emu:write8(0xFF6A, 0x80 | (pal * 8) | (i * 2) | 1)
                local hi = emu:read8(0xFF6B)
                colors[i + 1] = lo | (hi << 8)
            end
            logFile:write(string.format("  Palette %d: %04X %04X %04X %04X\n",
                pal, colors[1], colors[2], colors[3], colors[4]))
        end
        logFile:flush()
    end
    
    -- Stop after 5 seconds (300 frames at 60fps)
    if frameCount >= 300 then
        -- Write summary
        logFile:write(string.format("\n=== Summary ===\n"))
        logFile:write(string.format("Total frames: %d\n", frameCount))
        logFile:write(string.format("OAM writes: %d\n", #oamWrites))
        logFile:write(string.format("Palette writes: %d\n", #paletteWrites))
        logFile:write(string.format("Average FPS: %.2f\n", frameCount / (emu:time() - startTime)))
        logFile:close()
        
        -- Write OAM writes to JSON
        local oamFile = io.open("test_output/latest/logs/oam_writes.json", "w")
        oamFile:write("[\n")
        for i, write in ipairs(oamWrites) do
            oamFile:write(string.format('  {"frame":%d,"sprite":%d,"tile":%d,"palette":%d,"flags":%d,"pc":%d}',
                write.frame, write.sprite, write.tile, write.palette, write.flags, write.pc))
            if i < #oamWrites then oamFile:write(",") end
            oamFile:write("\n")
        end
        oamFile:write("]\n")
        oamFile:close()
        
        -- Write palette writes to JSON
        local palFile = io.open("test_output/latest/logs/palette_writes.json", "w")
        palFile:write("[\n")
        for i, write in ipairs(paletteWrites) do
            palFile:write(string.format('  {"frame":%d,"register":"%s","value":%d,"pc":%d}',
                write.frame, write.register, write.value, write.pc))
            if i < #paletteWrites then palFile:write(",") end
            palFile:write("\n")
        end
        palFile:write("]\n")
        palFile:close()
        
        -- Write performance data to JSON
        local perfFile = io.open("test_output/latest/logs/performance.json", "w")
        perfFile:write("[\n")
        for i, perf in ipairs(performanceData) do
            perfFile:write(string.format('  {"frame":%d,"elapsed":%.3f,"fps":%.2f}',
                perf.frame, perf.elapsed, perf.fps))
            if i < #performanceData then perfFile:write(",") end
            perfFile:write("\n")
        end
        perfFile:write("]\n")
        perfFile:close()
        
        emu:stop()
    end
end)

print("Comprehensive test script loaded")

