-- Capture more screenshots at different times
local frameCount = 0

callbacks:add("frame", function()
    frameCount = frameCount + 1

    -- Capture at various moments
    if frameCount == 9000 or frameCount == 9300 or frameCount == 11000 or frameCount == 12500 then
        emu:screenshot("tmp/demo_" .. frameCount .. ".png")
    end

    if frameCount >= 13000 then
        emu:stop()
    end
end)
