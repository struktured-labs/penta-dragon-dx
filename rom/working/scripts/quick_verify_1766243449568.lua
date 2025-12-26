-- Quick verification script - screenshot-based (Python controls wall clock time)
local screenshotBase = "/home/struktured/projects/penta-dragon-dx/rom/working/verify_screenshot_"
local screenshotCount = 0
local frameCount = 0
local screenshotIntervalFrames = 400  -- Frames between screenshots

console:log("Quick verification: Taking screenshots every " .. screenshotIntervalFrames .. " frames")
console:log("Note: Fast forward enabled - Python will kill after 5 seconds")

-- Function to log ALL sprite tile IDs (for monster identification)
local function logSpriteTiles()
    -- Log ALL visible sprites to identify all monster types
    local logFile = io.open(screenshotBase .. "tile_ids.txt", "a")
    if logFile then
        logFile:write(string.format("Screenshot %d (frame %d):\n", screenshotCount, frameCount))
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
    
    -- Take screenshots periodically (Python controls wall clock timing)
    if frameCount % screenshotIntervalFrames == 0 then
        takeScreenshot()
        -- Log tile IDs after taking screenshot
        logSpriteTiles()
    end
end)
