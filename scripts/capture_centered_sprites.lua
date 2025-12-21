-- Capture centered sprites with their names
-- Detects when sprites are centered and captures screenshots

local frameCount = 0
local capturedSprites = {}
local lastCaptureFrame = {}
local centerX = 80  -- Screen center X (160/2)
local centerY = 72  -- Screen center Y (144/2)
local centerThreshold = 30  -- Pixels from center to consider "centered" (more lenient)

-- Known sprite tile ranges and names
local spriteInfo = {
    [0] = {name = "Dragonfly", tiles = {0, 1, 2, 3}},
    [4] = {name = "Sara_W", tiles = {4, 5, 6, 7}},
    [100] = {name = "Monster_100_103", tiles = {100, 101, 102, 103}},
    [104] = {name = "Monster_104_107", tiles = {104, 105, 106, 107}},
    [108] = {name = "Monster_108_111", tiles = {108, 109, 110, 111}},
    [112] = {name = "Monster_112_115", tiles = {112, 113, 114, 115}},
    [116] = {name = "Monster_116_119", tiles = {116, 117, 118, 119}},
    [120] = {name = "Monster_120_123", tiles = {120, 121, 122, 123}},
}

-- Function to get sprite name from tile ID
local function getSpriteName(tile)
    for baseTile, info in pairs(spriteInfo) do
        for _, t in ipairs(info.tiles) do
            if t == tile then
                return info.name
            end
        end
    end
    return "Unknown_" .. tostring(tile)
end

-- Function to check if sprite is centered
local function isCentered(x, y)
    local dx = math.abs(x - centerX)
    local dy = math.abs(y - centerY)
    return dx < centerThreshold and dy < centerThreshold
end

-- Function to extract text from screen (simple OCR attempt)
-- Look for text in common text areas
local function extractSpriteName()
    -- Try to read text from common name display areas
    -- This is a simplified approach - real OCR would be more complex
    
    -- Check tilemap for text patterns (simplified)
    -- For now, return nil and we'll use tile-based naming
    return nil
end

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Check every 10 frames for performance
    if frameCount % 10 == 0 then
        -- Scan OAM for centered sprites
        for spriteIndex = 0, 39 do
            local oamBase = 0xFE00 + (spriteIndex * 4)
            local y = emu:read8(oamBase)
            local x = emu:read8(oamBase + 1)
            local tile = emu:read8(oamBase + 2)
            local flags = emu:read8(oamBase + 3)
            
            -- Check if sprite is visible and centered
            if y > 0 and y < 144 and x > 0 and x < 168 then
                if isCentered(x, y) then
                    local spriteName = getSpriteName(tile)
                    local key = spriteName .. "_" .. tile
                    
                    -- Only capture if we haven't captured this sprite recently (avoid duplicates)
                    if not lastCaptureFrame[key] or (frameCount - lastCaptureFrame[key]) > 180 then
                        -- Capture screenshot
                        local success, screenshot = pcall(function() return emu:takeScreenshot() end)
                        if success and screenshot then
                            local filename = string.format("sprite_%s_tile%d_frame%05d.png", 
                                spriteName, tile, frameCount)
                            
                            -- Try to save with full path
                            local fullPath = filename
                            local saveSuccess, err = pcall(function() 
                                screenshot:save(fullPath)
                            end)
                            
                            if saveSuccess then
                                print(string.format("✅ Captured: %s (tile %d) at frame %d, pos (%d,%d) -> %s", 
                                    spriteName, tile, frameCount, x, y, filename))
                                
                                capturedSprites[key] = {
                                    name = spriteName,
                                    tile = tile,
                                    frame = frameCount,
                                    x = x,
                                    y = y
                                }
                                lastCaptureFrame[key] = frameCount
                            else
                                print(string.format("❌ Failed to save: %s (error: %s)", filename, tostring(err)))
                            end
                        else
                            print(string.format("❌ Failed to take screenshot at frame %d", frameCount))
                        end
                    end
                end
            end
        end
    end
    
    -- Stop after 15 seconds (900 frames at 60fps)
    if frameCount >= 900 then
        print("\n=== Capture Summary ===")
        print(string.format("Total frames: %d", frameCount))
        print(string.format("Unique sprites captured: %d", #capturedSprites))
        
        for key, info in pairs(capturedSprites) do
            print(string.format("  - %s (tile %d) at frame %d", 
                info.name, info.tile, info.frame))
        end
        
        emu:stop()
    end
end)

print("Centered sprite capture script loaded")
print("Will capture sprites when they appear near screen center")

