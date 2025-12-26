-- mGBA Lua script to diagnose OAM and palette state
local logFile = nil
local frameCount = 0

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Initialize log file on first frame
    if not logFile then
        logFile = io.open("oam_diagnosis.log", "w")
        logFile:write("=== OAM and Palette Diagnosis ===\n")
        logFile:write("Frame, SpriteIndex, Y, X, Tile, Flags, Palette, IsSaraW\n")
    end
    
    -- Log every 30 frames (once per second at 30fps)
    if frameCount % 30 == 0 then
        local oamBase = 0xFE00
        local saraWTiles = {[4] = true, [5] = true, [6] = true, [7] = true}
        
        logFile:write(string.format("\n--- Frame %d ---\n", frameCount))
        
        -- Check OBJ palettes
        local objPal0 = emu:read16(0xFF68)  -- OBJ palette 0 index
        logFile:write(string.format("OBJ Palette 0 index: 0x%02X\n", objPal0))
        
        -- Check all 40 sprites
        local saraWCount = 0
        for i = 0, 39 do
            local addr = oamBase + (i * 4)
            local y = emu:read8(addr)
            local x = emu:read8(addr + 1)
            local tile = emu:read8(addr + 2)
            local flags = emu:read8(addr + 3)
            local palette = flags & 0x07
            
            local isSaraW = saraWTiles[tile] and y > 0 and y < 144
            
            if isSaraW then
                saraWCount = saraWCount + 1
            end
            
            if isSaraW or (y > 0 and y < 144) then
                logFile:write(string.format("Sprite %d: Y=%d X=%d Tile=%d Flags=0x%02X Pal=%d %s\n",
                    i, y, x, tile, flags, palette, isSaraW and "***SARA W***" or ""))
            end
        end
        
        logFile:write(string.format("Sara W sprites found: %d\n", saraWCount))
        logFile:flush()
    end
    
    -- Stop after 5 seconds (150 frames at 30fps)
    if frameCount >= 150 then
        if logFile then
            logFile:close()
        end
        emu:stop()
    end
end)

