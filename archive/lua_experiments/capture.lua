-- mGBA scripting: load currently-running core, wait a few frames, screenshot, then quit

local frames = 60  -- Wait 1 second at 60fps

callbacks:add("frame", function()
    frames = frames - 1
    if frames == 0 then
        console:log("Capturing screenshot...")
        emu:screenshot("rom/working/frame.png")
        emu:quit()
    end
end)
