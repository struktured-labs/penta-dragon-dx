-- Capture screenshots during demo
local frameCount = 0

callbacks:add("frame", function()
    frameCount = frameCount + 1

    -- Capture at key moments during demo
    if frameCount == 9500 or frameCount == 10000 or frameCount == 13000 then
        emu:screenshot("tmp/demo_" .. frameCount .. ".png")
    end

    if frameCount >= 14000 then
        emu:stop()
    end
end)
