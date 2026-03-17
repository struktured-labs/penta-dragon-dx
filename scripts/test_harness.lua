-- Penta Dragon DX Remake - Headless Test Harness
-- Key bitmask: A=0x01, B=0x02, SELECT=0x04, START=0x08, RIGHT=0x10, LEFT=0x20, UP=0x40, DOWN=0x80

local frame = 0
local phase = 0
local screenshots = 0

-- Offset: stage intro adds ~180 frames after game start
-- Press A at frame 200 to skip it faster
local GAME_START = 500  -- gameplay active by this frame

callbacks:add("frame", function()
    frame = frame + 1

    -- Phase 0: Title screen
    if phase == 0 and frame == 120 then
        emu:screenshot("tmp/h_title.png")
        screenshots = screenshots + 1
        phase = 1
    end

    -- Phase 1: DOWN + A to select GAME START
    if phase == 1 then
        if frame == 130 then emu:setKeys(0x80) end  -- DOWN
        if frame == 135 then emu:setKeys(0) end
        if frame == 140 then emu:setKeys(0x01) end   -- A to confirm
        if frame == 145 then emu:setKeys(0) end
        -- Skip stage intro by pressing A again
        if frame == 250 then emu:setKeys(0x01) end   -- A to skip stage screen
        if frame == 253 then emu:setKeys(0); phase = 2 end
    end

    -- Phase 2: Gameplay captured
    if phase == 2 and frame == GAME_START then
        emu:screenshot("tmp/h_gameplay.png")
        screenshots = screenshots + 1
        phase = 3
    end

    -- Phase 3: Hold RIGHT 120 frames
    if phase == 3 then
        if frame == GAME_START + 10 then emu:setKeys(0x10) end
        if frame == GAME_START + 130 then
            emu:setKeys(0)
            emu:screenshot("tmp/h_scrolled.png")
            screenshots = screenshots + 1
            phase = 4
        end
    end

    -- Phase 4: LEFT 60 frames
    if phase == 4 then
        if frame == GAME_START + 140 then emu:setKeys(0x20) end
        if frame == GAME_START + 200 then
            emu:setKeys(0)
            emu:screenshot("tmp/h_left.png")
            screenshots = screenshots + 1
            phase = 5
        end
    end

    -- Phase 5: UP 30 frames
    if phase == 5 then
        if frame == GAME_START + 210 then emu:setKeys(0x40) end
        if frame == GAME_START + 240 then
            emu:setKeys(0)
            emu:screenshot("tmp/h_up.png")
            screenshots = screenshots + 1
            phase = 6
        end
    end

    -- Phase 6: Shoot (A 20 frames)
    if phase == 6 then
        if frame == GAME_START + 250 then emu:setKeys(0x01) end
        if frame == GAME_START + 270 then
            emu:setKeys(0)
            emu:screenshot("tmp/h_shoot.png")
            screenshots = screenshots + 1
            phase = 7
        end
    end

    -- Phase 7: SELECT toggle dragon form
    if phase == 7 then
        if frame == GAME_START + 275 then emu:setKeys(0x04) end
        if frame == GAME_START + 278 then emu:setKeys(0) end
        if frame == GAME_START + 290 then
            emu:screenshot("tmp/h_dragon.png")
            screenshots = screenshots + 1
            phase = 8
        end
    end

    -- Phase 8: Shoot only (A) for 200 frames, let auto-scroll advance
    if phase == 8 then
        if frame == GAME_START + 300 then emu:setKeys(0x01) end  -- A only
        if frame == GAME_START + 500 then
            emu:setKeys(0)
            emu:screenshot("tmp/h_combat.png")
            screenshots = screenshots + 1
            phase = 9
        end
    end

    -- Phase 9: START for menu
    if phase == 9 then
        if frame == GAME_START + 510 then emu:setKeys(0x08) end
        if frame == GAME_START + 513 then emu:setKeys(0) end
        if frame == GAME_START + 520 then
            emu:screenshot("tmp/h_menu.png")
            screenshots = screenshots + 1
            phase = 10
        end
    end

    -- Done
    if phase == 10 and frame == GAME_START + 525 then
        console:log("Test complete: " .. screenshots .. " screenshots")
        emu:quit()
    end
end)
