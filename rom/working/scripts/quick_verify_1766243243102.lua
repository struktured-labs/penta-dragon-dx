-- Quick verification script - screenshot-based (fast test)
local screenshotBase = "/home/struktured/projects/penta-dragon-dx/rom/working/verify_screenshot_"
local frameCount = 0
local screenshotCount = 0
local screenshotInterval = 30  -- Every 0.5 seconds (30 frames) - capture frequently in short test
local startFrame = 60  -- Start after 1 second (60 frames = 1s at 60fps)
local maxScreenshots = 5  -- Stop after 5 screenshots

console:log("Quick verification: Taking screenshots every 0.5 seconds (mgba-qt)")
console:log("Note: Fast forward enabled - stopping after 5 screenshots")

-- Log frame count periodically to verify fast forward is working
local lastLogFrame = 0

-- Function to log ALL sprite tile IDs (for monster identification)
local function logSpriteTiles()
    -- Log ALL visible sprites to identify all monster types
    local logFile = io.open(screenshotBase .. "tile_ids.txt", "a")
    if logFile then
        logFile:write(string.format("Frame %d (screenshot %d):\n", frameCount, screenshotCount))
        local spriteCount = 0
        for i = 0, 39 do
            local oamBase = 0xFE00 + (i * 4)
            local y = emu:read8(oamBase)
            local x = emu:read8(oamBase + 1)
            local tile = emu:read8(oamBase + 2)
            local attr = emu:read8(oamBase + 3)
            local palette = attr & 0x07
            
            -- Log ALL visible sprites (not just center area)
            if y > 0 and y < 160 and x > 0 and x < 168 then
                spriteCount = spriteCount + 1
                logFile:write(string.format("  Sprite[%d]: tile=0x%02X (%d) palette=%d pos=(%d,%d)\n", 
                    i, tile, tile, palette, x, y))
            end
        end
        if spriteCount == 0 then
            logFile:write("  (no visible sprites)\n")
        end
        logFile:write("\n")
        logFile:close()
    end
end

local function takeScreenshot()
    screenshotCount = screenshotCount + 1
    local screenshotPath = screenshotBase .. string.format("%03d", screenshotCount) .. ".png"
    
    -- Try screenshot - check return value and also verify file exists
    local success = emu:screenshot(screenshotPath)
    
    -- Verify file was actually created
    local file = io.open(screenshotPath, "r")
    if file then
        file:close()
        console:log("📸 Screenshot " .. screenshotCount .. " saved: " .. screenshotPath)
        return true
    else
        console:log("⚠️  Screenshot " .. screenshotCount .. " failed - file not created: " .. screenshotPath)
        console:log("   emu:screenshot returned: " .. tostring(success))
        return false
    end
end

-- Frame callback - take screenshots periodically
callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Log frame count every 60 frames to verify speed
    if frameCount - lastLogFrame >= 60 then
        console:log("Frame: " .. frameCount)
        lastLogFrame = frameCount
    end
    
    -- Take screenshots periodically after start frame
    if frameCount >= startFrame and (frameCount - startFrame) % screenshotInterval == 0 then
        takeScreenshot()
        -- Log tile IDs after taking screenshot
        logSpriteTiles()
        
        -- Stop after max screenshots
        if screenshotCount >= maxScreenshots then
            console:log("Verification complete. Took " .. screenshotCount .. " screenshots.")
            emu:stop()
            return
        end
    end
end)
