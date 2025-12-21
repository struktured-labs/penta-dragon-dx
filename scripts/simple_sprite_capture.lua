-- Simple sprite capture - capture every N frames and log sprite info
local frameCount = 0
local captureInterval = 60  -- Capture every 60 frames (1 second at 60fps)
local outputDir = "sprite_captures"

print("=== Simple Sprite Capture Script ===")
print("Will capture screenshots every " .. captureInterval .. " frames")
print("Output directory: " .. outputDir)

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Capture every N frames
    if frameCount % captureInterval == 0 then
        -- Log current sprite state
        local spriteInfo = {}
        for i = 0, 39 do
            local oamBase = 0xFE00 + (i * 4)
            local y = emu:read8(oamBase)
            local x = emu:read8(oamBase + 1)
            local tile = emu:read8(oamBase + 2)
            local flags = emu:read8(oamBase + 3)
            
            if y > 0 and y < 144 and x > 0 and x < 168 then
                table.insert(spriteInfo, {
                    index = i,
                    x = x,
                    y = y,
                    tile = tile,
                    palette = flags & 0x07
                })
            end
        end
        
        -- Find Sara W sprites (tiles 4-7)
        local saraWSprites = {}
        for _, sprite in ipairs(spriteInfo) do
            if sprite.tile >= 4 and sprite.tile <= 7 then
                table.insert(saraWSprites, sprite)
            end
        end
        
        -- Capture screenshot
        local success, screenshot = pcall(function() return emu:takeScreenshot() end)
        if success and screenshot then
            local filename = string.format("%s/frame_%05d.png", outputDir, frameCount)
            local saveSuccess, err = pcall(function() screenshot:save(filename) end)
            
            if saveSuccess then
                print(string.format("Frame %d: Captured %s (%d sprites visible, %d Sara W)", 
                    frameCount, filename, #spriteInfo, #saraWSprites))
                
                -- Log Sara W positions
                for _, sara in ipairs(saraWSprites) do
                    print(string.format("  Sara W: tile %d at (%d,%d) palette %d", 
                        sara.tile, sara.x, sara.y, sara.palette))
                end
            else
                print(string.format("Frame %d: Failed to save screenshot: %s", frameCount, tostring(err)))
            end
        else
            print(string.format("Frame %d: Failed to take screenshot", frameCount))
        end
    end
    
    -- Stop after 20 seconds
    if frameCount >= 1200 then
        print("\n=== Capture Complete ===")
        print(string.format("Total frames: %d", frameCount))
        emu:stop()
    end
end)

print("Script loaded - starting capture...")
