-- Remake capture - same timing as original for comparison
-- Remake: A at frame 140 goes directly to gameplay (no long stage screen)
local frame = 0
local phase = 0

callbacks:add("frame", function()
    frame = frame + 1

    if phase == 0 and frame == 120 then
        emu:screenshot("tmp/rm_01_title.png")
        phase = 1
    end

    -- DOWN + A to select GAME START
    if phase == 1 then
        if frame == 130 then emu:setKeys(0x80) end
        if frame == 133 then emu:setKeys(0) end
        if frame == 150 then emu:setKeys(0x01) end
        if frame == 153 then emu:setKeys(0); phase = 2 end
    end

    -- Gameplay starts much sooner in remake
    if phase == 2 and frame == 350 then
        emu:screenshot("tmp/rm_02_gameplay_start.png")
        phase = 3
    end

    -- Idle
    if phase == 3 and frame == 450 then
        emu:screenshot("tmp/rm_03_idle.png")
        phase = 4
    end

    -- RIGHT 120 frames
    if phase == 4 then
        if frame == 460 then emu:setKeys(0x10) end
        if frame == 580 then
            emu:setKeys(0)
            emu:screenshot("tmp/rm_04_right.png")
            phase = 5
        end
    end

    -- LEFT 60 frames
    if phase == 5 then
        if frame == 590 then emu:setKeys(0x20) end
        if frame == 650 then
            emu:setKeys(0)
            emu:screenshot("tmp/rm_05_left.png")
            phase = 6
        end
    end

    -- UP 30 frames
    if phase == 6 then
        if frame == 660 then emu:setKeys(0x40) end
        if frame == 690 then
            emu:setKeys(0)
            emu:screenshot("tmp/rm_06_up.png")
            phase = 7
        end
    end

    -- DOWN 30 frames
    if phase == 7 then
        if frame == 700 then emu:setKeys(0x80) end
        if frame == 730 then
            emu:setKeys(0)
            emu:screenshot("tmp/rm_07_down.png")
            phase = 8
        end
    end

    -- Shoot A
    if phase == 8 then
        if frame == 740 then emu:setKeys(0x01) end
        if frame == 760 then
            emu:setKeys(0)
            emu:screenshot("tmp/rm_08_shoot.png")
            phase = 9
        end
    end

    -- SELECT toggle
    if phase == 9 then
        if frame == 770 then emu:setKeys(0x04) end
        if frame == 773 then emu:setKeys(0) end
        if frame == 790 then
            emu:screenshot("tmp/rm_09_dragon.png")
            phase = 10
        end
    end

    -- Combat RIGHT+A 300 frames
    if phase == 10 then
        if frame == 800 then emu:setKeys(0x11) end
        if frame == 1100 then
            emu:setKeys(0)
            emu:screenshot("tmp/rm_10_combat.png")
            emu:quit()
        end
    end
end)
