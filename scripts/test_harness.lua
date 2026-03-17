-- Penta Dragon DX Remake - Headless Test Harness
-- Exercises: title screen, game start, scrolling (R/L/U/D), shooting, form toggle
-- Key bitmask: A=0x01, B=0x02, SELECT=0x04, START=0x08, RIGHT=0x10, LEFT=0x20, UP=0x40, DOWN=0x80

local frame = 0
local phase = 0
local screenshots = 0

callbacks:add("frame", function()
    frame = frame + 1

    -- Phase 0: Title screen (wait 120 frames for boot)
    if phase == 0 and frame == 120 then
        emu:screenshot("tmp/h_title.png")
        screenshots = screenshots + 1
        phase = 1
    end

    -- Phase 1: Navigate to GAME START (DOWN then A)
    if phase == 1 then
        if frame == 130 then emu:setKeys(0x80) end  -- DOWN
        if frame == 135 then emu:setKeys(0) end
        if frame == 140 then emu:setKeys(0x01) end   -- A
        if frame == 145 then emu:setKeys(0); phase = 2 end
    end

    -- Phase 2: Wait for gameplay, capture initial state
    if phase == 2 and frame == 300 then
        emu:screenshot("tmp/h_gameplay.png")
        screenshots = screenshots + 1
        phase = 3
    end

    -- Phase 3: Hold RIGHT for 120 frames
    if phase == 3 then
        if frame == 310 then emu:setKeys(0x10) end
        if frame == 430 then
            emu:setKeys(0)
            emu:screenshot("tmp/h_scrolled.png")
            screenshots = screenshots + 1
            phase = 4
        end
    end

    -- Phase 4: Hold LEFT for 60 frames
    if phase == 4 then
        if frame == 440 then emu:setKeys(0x20) end
        if frame == 500 then
            emu:setKeys(0)
            emu:screenshot("tmp/h_left.png")
            screenshots = screenshots + 1
            phase = 5
        end
    end

    -- Phase 5: Hold UP for 30 frames
    if phase == 5 then
        if frame == 510 then emu:setKeys(0x40) end
        if frame == 540 then
            emu:setKeys(0)
            emu:screenshot("tmp/h_up.png")
            screenshots = screenshots + 1
            phase = 6
        end
    end

    -- Phase 6: Press A to shoot
    if phase == 6 then
        if frame == 550 then emu:setKeys(0x01) end
        if frame == 570 then
            emu:setKeys(0)
            emu:screenshot("tmp/h_shoot.png")
            screenshots = screenshots + 1
            phase = 7
        end
    end

    -- Phase 7: SELECT to toggle dragon form
    if phase == 7 then
        if frame == 575 then emu:setKeys(0x04) end
        if frame == 578 then emu:setKeys(0) end
        if frame == 590 then
            emu:screenshot("tmp/h_dragon.png")
            screenshots = screenshots + 1
            phase = 8
        end
    end

    -- Phase 8: Hold RIGHT+A for combat, wait for enemies
    if phase == 8 then
        if frame == 600 then emu:setKeys(0x11) end  -- RIGHT + A
        if frame == 900 then
            emu:setKeys(0)
            emu:screenshot("tmp/h_combat.png")
            screenshots = screenshots + 1
            phase = 9
        end
    end

    -- Phase 9: Press START to open menu
    if phase == 9 then
        if frame == 910 then emu:setKeys(0x08) end  -- START
        if frame == 913 then emu:setKeys(0) end
        if frame == 920 then
            emu:screenshot("tmp/h_menu.png")
            screenshots = screenshots + 1
            phase = 10
        end
    end

    -- Done
    if phase == 10 and frame == 925 then
        console:log("Test complete: " .. screenshots .. " screenshots")
        emu:quit()
    end
end)
