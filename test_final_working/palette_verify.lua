-- Palette injection verification script
console:log("=== Palette Verification Script ===")

local frameCount = 0
local screenshotCount = 0
local screenshotDir = "/home/struktured/projects/penta-dragon-dx/test_final_working"

console:log("Screenshot directory: " .. screenshotDir)
console:log("Capturing every 60 frames")

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Capture screenshot every 60 frames
    if frameCount % 60 == 0 then
        screenshotCount = screenshotCount + 1
        local filename = screenshotDir .. "/verify_frame_" .. string.format("%05d", screenshotCount) .. ".png"
        
        -- Use emu:screenshot() - wait a frame after to ensure write completes
        local success = emu:screenshot(filename)
        
        if success then
            console:log(string.format("✅ Captured frame %d: %s", frameCount, filename))
        else
            console:log(string.format("❌ Failed to capture frame %d", frameCount))
        end
    end
    
    -- Stop after 1200 frames (20 seconds at 60fps, but runs faster)
    if frameCount >= 1200 then
        console:log("Verification complete - " .. screenshotCount .. " screenshots")
        -- Wait a moment for final screenshot to be written
        callbacks:add("frame", function()
            emu:quit()
        end)
    end
end)

console:log("Palette verification script loaded")
