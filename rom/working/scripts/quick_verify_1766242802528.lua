-- Quick verification script - 5 second capture
local screenshotBase = "/home/struktured/projects/penta-dragon-dx/rom/working/verify_screenshot_"
local frameCount = 0
local screenshotCount = 0
local screenshotInterval = 30  -- Every 0.5 seconds (30 frames)
local startFrame = 60  -- Start after 1 second
local maxFrames = 360  -- 5 seconds total (360 frames = 6s at 60fps, but stops at 5s)

console:log("Quick verification: Capturing screenshots for 5 seconds")

-- Function to log sprite tile IDs and positions (APPEND mode to capture all frames)
local function logSpriteTiles()
    local logFile = io.open(screenshotBase .. "tile_ids.txt", "a")  -- Changed to "a" for append
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
            
            if y > 0 and y < 160 and x > 0 and x < 168 then
                spriteCount = spriteCount + 1
                logFile:write(string.format("  Sprite[%d]: tile=0x%02X (%d) palette=%d pos=(%d,%d)\n", 
                    i, tile, tile, palette, x, y))
            end
        end
        if spriteCount == 0 then
            logFile:write("  No visible sprites\n")
        end
        logFile:write("\n")
        logFile:close()
    end
end

local function takeScreenshot()
    screenshotCount = screenshotCount + 1
    local screenshotPath = screenshotBase .. string.format("%03d", screenshotCount) .. ".png"
    local success = emu:screenshot(screenshotPath)
    local file = io.open(screenshotPath, "r")
    if file then
        file:close()
        console:log("📸 Screenshot " .. screenshotCount .. " saved")
        return true
    else
        console:log("⚠️  Screenshot " .. screenshotCount .. " failed")
        return false
    end
end

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    if frameCount >= startFrame and (frameCount - startFrame) % screenshotInterval == 0 then
        takeScreenshot()
        logSpriteTiles()
    end
    
    if frameCount >= maxFrames then
        console:log("Verification complete. Took " .. screenshotCount .. " screenshots.")
        emu:stop()
    end
end)
