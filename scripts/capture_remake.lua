local frame = 0
local phase = 0
callbacks:add("frame", function()
    frame = frame + 1

    if phase == 0 and frame == 120 then
        emu:screenshot("tmp/rm_01_title.png")
        phase = 1
    end

    if phase == 1 then
        if frame == 130 then emu:setKeys(0x80) end
        if frame == 133 then emu:setKeys(0) end
        if frame == 150 then emu:setKeys(0x01) end
        if frame == 153 then emu:setKeys(0) end
        -- Capture stage intro
        if frame == 220 then emu:screenshot("tmp/rm_02_stage_intro.png") end
        -- Press A to skip
        if frame == 250 then emu:setKeys(0x01) end
        if frame == 253 then emu:setKeys(0); phase = 2 end
    end

    if phase == 2 and frame == 500 then
        emu:screenshot("tmp/rm_03_idle.png")
        phase = 3
    end

    if phase == 3 then
        if frame == 510 then emu:setKeys(0x10) end
        if frame == 630 then
            emu:setKeys(0)
            emu:screenshot("tmp/rm_04_right.png")
            phase = 4
        end
    end

    if phase == 4 then
        if frame == 640 then emu:setKeys(0x20) end
        if frame == 700 then
            emu:setKeys(0)
            emu:screenshot("tmp/rm_05_left.png")
            phase = 5
        end
    end

    if phase == 5 then
        if frame == 710 then emu:setKeys(0x40) end
        if frame == 740 then
            emu:setKeys(0)
            emu:screenshot("tmp/rm_06_up.png")
            phase = 6
        end
    end

    if phase == 6 then
        if frame == 750 then emu:setKeys(0x01) end
        if frame == 770 then
            emu:setKeys(0)
            emu:screenshot("tmp/rm_07_shoot.png")
            phase = 7
        end
    end

    if phase == 7 then
        if frame == 780 then emu:setKeys(0x04) end
        if frame == 783 then emu:setKeys(0) end
        if frame == 800 then
            emu:screenshot("tmp/rm_08_dragon.png")
            phase = 8
        end
    end

    if phase == 8 then
        if frame == 810 then emu:setKeys(0x11) end
        if frame == 1110 then
            emu:setKeys(0)
            emu:screenshot("tmp/rm_09_combat.png")
            emu:quit()
        end
    end
end)
