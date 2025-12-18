-- mGBA Lua script to detect white screen freeze
local frameCount = 0
local maxFrames = 600 -- 10 seconds at 60fps

function onFrame()
    frameCount = frameCount + 1
    
    if frameCount > 120 then -- Wait 2 seconds for splash screen to pass
        local isWhite = true
        -- Check a few points on the screen
        local points = {
            {40, 40}, {80, 72}, {120, 120}, {20, 130}
        }
        
        for _, p in ipairs(points) do
            local r, g, b = emu:readPixel(p[1], p[2])
            -- In mGBA, colors are 0-255. Pure white is 255, 255, 255
            if r < 240 or g < 240 or b < 240 then
                isWhite = false
                break
            end
        end
        
        if not isWhite then
            print("CONTENT_DETECTED")
            os.exit(0)
        end
    end
    
    if frameCount >= maxFrames then
        print("WHITE_SCREEN_FREEZE_DETECTED")
        os.exit(1)
    end
end

emu:addStepCallback(onFrame)

