-- Long play test: auto-play for ~5 minutes to test boss encounters
-- Just hold A (shoot) and let auto-scroll + enemies do their thing
local frame = 0
local phase = 0
local cap = 0

callbacks:add("frame", function()
    frame = frame + 1

    -- Start game
    if frame == 130 then emu:setKeys(0x80) end  -- DOWN
    if frame == 133 then emu:setKeys(0) end
    if frame == 150 then emu:setKeys(0x01) end  -- A
    if frame == 153 then emu:setKeys(0) end
    -- Skip stage intro
    if frame == 250 then emu:setKeys(0x01) end
    if frame == 253 then emu:setKeys(0) end

    -- From frame 500: hold A to auto-fire, occasionally move
    if frame >= 500 then
        local pattern = (frame / 120) % 4
        if pattern < 1 then
            emu:setKeys(0x01)  -- A only (shoot)
        elseif pattern < 2 then
            emu:setKeys(0x41)  -- UP + A
        elseif pattern < 3 then
            emu:setKeys(0x81)  -- DOWN + A
        else
            emu:setKeys(0x01)  -- A only
        end
    end

    -- Capture every 30 seconds (~1800 frames)
    if frame == 2300 then emu:screenshot("tmp/lp_30s.png"); cap = cap + 1 end
    if frame == 4100 then emu:screenshot("tmp/lp_60s.png"); cap = cap + 1 end
    if frame == 5900 then emu:screenshot("tmp/lp_90s.png"); cap = cap + 1 end
    if frame == 7700 then emu:screenshot("tmp/lp_120s.png"); cap = cap + 1 end
    if frame == 9500 then emu:screenshot("tmp/lp_150s.png"); cap = cap + 1 end
    if frame == 11300 then emu:screenshot("tmp/lp_180s.png"); cap = cap + 1 end
    if frame == 13100 then emu:screenshot("tmp/lp_210s.png"); cap = cap + 1 end
    if frame == 14900 then emu:screenshot("tmp/lp_240s.png"); cap = cap + 1 end
    if frame == 16700 then emu:screenshot("tmp/lp_270s.png"); cap = cap + 1 end
    if frame == 18000 then
        emu:screenshot("tmp/lp_300s.png")
        console:log("Long play complete: " .. cap + 1 .. " captures over 5 min")
        emu:quit()
    end
end)
