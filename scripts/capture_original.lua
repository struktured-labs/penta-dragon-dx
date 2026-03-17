-- Original Penta Dragon reference capture - with stage screen skip
local frame = 0
local phase = 0

callbacks:add("frame", function()
    frame = frame + 1

    -- Title
    if phase == 0 and frame == 120 then
        emu:screenshot("tmp/og_01_title.png")
        phase = 1
    end

    -- DOWN + A to select GAME START
    if phase == 1 then
        if frame == 130 then emu:setKeys(0x80) end
        if frame == 133 then emu:setKeys(0) end
        if frame == 150 then emu:setKeys(0x01) end
        if frame == 153 then emu:setKeys(0); phase = 2 end
    end

    -- Stage screen - try pressing START/A to skip
    if phase == 2 then
        if frame == 400 then emu:screenshot("tmp/og_02_stage.png") end
        if frame == 500 then emu:setKeys(0x01) end  -- A to skip
        if frame == 503 then emu:setKeys(0) end
        if frame == 600 then emu:setKeys(0x08) end  -- START to skip
        if frame == 603 then emu:setKeys(0) end
        if frame == 700 then emu:setKeys(0x01) end  -- A again
        if frame == 703 then emu:setKeys(0) end
        -- Wait for gameplay
        if frame == 1000 then emu:screenshot("tmp/og_03_pre_gameplay.png") end
        if frame == 1400 then
            emu:screenshot("tmp/og_04_gameplay_check.png")
            phase = 3
        end
    end

    -- Now in gameplay - idle
    if phase == 3 and frame == 1500 then
        emu:screenshot("tmp/og_05_idle.png")
        phase = 4
    end

    -- RIGHT 120 frames
    if phase == 4 then
        if frame == 1510 then emu:setKeys(0x10) end
        if frame == 1630 then
            emu:setKeys(0)
            emu:screenshot("tmp/og_06_right.png")
            phase = 5
        end
    end

    -- LEFT 60 frames
    if phase == 5 then
        if frame == 1640 then emu:setKeys(0x20) end
        if frame == 1700 then
            emu:setKeys(0)
            emu:screenshot("tmp/og_07_left.png")
            phase = 6
        end
    end

    -- UP 30 frames
    if phase == 6 then
        if frame == 1710 then emu:setKeys(0x40) end
        if frame == 1740 then
            emu:setKeys(0)
            emu:screenshot("tmp/og_08_up.png")
            phase = 7
        end
    end

    -- DOWN 30 frames
    if phase == 7 then
        if frame == 1750 then emu:setKeys(0x80) end
        if frame == 1780 then
            emu:setKeys(0)
            emu:screenshot("tmp/og_09_down.png")
            phase = 8
        end
    end

    -- Shoot A
    if phase == 8 then
        if frame == 1790 then emu:setKeys(0x01) end
        if frame == 1810 then
            emu:setKeys(0)
            emu:screenshot("tmp/og_10_shoot.png")
            phase = 9
        end
    end

    -- SELECT toggle
    if phase == 9 then
        if frame == 1820 then emu:setKeys(0x04) end
        if frame == 1823 then emu:setKeys(0) end
        if frame == 1840 then
            emu:screenshot("tmp/og_11_dragon.png")
            phase = 10
        end
    end

    -- Combat RIGHT+A 300 frames
    if phase == 10 then
        if frame == 1850 then emu:setKeys(0x11) end
        if frame == 2150 then
            emu:setKeys(0)
            emu:screenshot("tmp/og_12_combat.png")
            emu:quit()
        end
    end
end)
