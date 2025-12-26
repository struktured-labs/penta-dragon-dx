-- mGBA Lua script to verify render status
local frameCount = 0
local maxFrames = 600

function onFrame()
    frameCount = frameCount + 1
    
    if frameCount > 180 then -- After 3 seconds
        local isWhite = true
        local points = {
            {40, 40}, {80, 72}, {120, 120}, {20, 130}
        }
        
        for _, p in ipairs(points) do
            local r, g, b = emu:readPixel(p[1], p[2])
            if r < 240 or g < 240 or b < 240 then
                isWhite = false
                break
            end
        end
        
        local f = io.open("/tmp/penta_verify.txt", "w")
        if not isWhite then
            f:write("SUCCESS: Content Detected\n")
        else
            f:write("FAILURE: White Screen Detected\n")
        end
        f:close()
        
        if not isWhite then
            emu:log("Verification successful!")
            os.exit(0)
        end
    end
    
    if frameCount >= maxFrames then
        local f = io.open("/tmp/penta_verify.txt", "w")
        f:write("FAILURE: Freeze Timeout\n")
        f:close()
        os.exit(1)
    end
end

emu:addStepCallback(onFrame)
