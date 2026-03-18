-- Systematic verification of every game mechanic
-- Each phase tests one specific thing and captures proof
local frame = 0
local phase = 0
local caps = 0

local function cap(name)
    emu:screenshot("tmp/verify_" .. name .. ".png")
    caps = caps + 1
end

callbacks:add("frame", function()
    frame = frame + 1

    -- 1. Title screen renders
    if frame == 120 then cap("01_title"); phase = 1 end

    -- 2. Cursor on OPENING START (default)
    if phase == 1 and frame == 125 then cap("02_cursor_default") end

    -- 3. Move cursor DOWN to GAME START
    if phase == 1 and frame == 130 then emu:setKeys(0x80) end -- DOWN
    if phase == 1 and frame == 133 then emu:setKeys(0); cap("03_cursor_game") end

    -- 4. Press A to start
    if phase == 1 and frame == 140 then emu:setKeys(0x01); phase = 2 end
    if phase == 2 and frame == 143 then emu:setKeys(0) end

    -- 5. Stage intro appears
    if phase == 2 and frame == 220 then cap("04_stage_intro"); phase = 3 end

    -- 6. Skip stage intro
    if phase == 3 and frame == 250 then emu:setKeys(0x01) end
    if phase == 3 and frame == 253 then emu:setKeys(0); phase = 4 end

    -- 7. Gameplay starts - Sara visible, dungeon tiles loaded
    if phase == 4 and frame == 500 then cap("05_gameplay_start"); phase = 5 end

    -- 8. Auto-scroll: capture same spot 60 frames later (should shift)
    if phase == 5 and frame == 560 then cap("06_autoscroll_proof"); phase = 6 end

    -- 9. Move RIGHT
    if phase == 6 and frame == 570 then emu:setKeys(0x10) end -- RIGHT
    if phase == 6 and frame == 600 then emu:setKeys(0); cap("07_move_right"); phase = 7 end

    -- 10. Move LEFT
    if phase == 7 and frame == 610 then emu:setKeys(0x20) end -- LEFT
    if phase == 7 and frame == 640 then emu:setKeys(0); cap("08_move_left"); phase = 8 end

    -- 11. Move UP
    if phase == 8 and frame == 650 then emu:setKeys(0x40) end -- UP
    if phase == 8 and frame == 680 then emu:setKeys(0); cap("09_move_up"); phase = 9 end

    -- 12. Move DOWN
    if phase == 9 and frame == 690 then emu:setKeys(0x80) end -- DOWN
    if phase == 9 and frame == 720 then emu:setKeys(0); cap("10_move_down"); phase = 10 end

    -- 13. Shoot A (witch form)
    if phase == 10 and frame == 730 then emu:setKeys(0x01) end
    if phase == 10 and frame == 750 then emu:setKeys(0); cap("11_shoot_witch"); phase = 11 end

    -- 14. Toggle form (SELECT)
    if phase == 11 and frame == 760 then emu:setKeys(0x04) end -- SELECT
    if phase == 11 and frame == 763 then emu:setKeys(0) end
    if phase == 11 and frame == 775 then cap("12_dragon_form"); phase = 12 end

    -- 15. Shoot A (dragon form - should be different projectile)
    if phase == 12 and frame == 780 then emu:setKeys(0x01) end
    if phase == 12 and frame == 800 then emu:setKeys(0); cap("13_shoot_dragon"); phase = 13 end

    -- 16. Open menu (START)
    if phase == 13 and frame == 810 then emu:setKeys(0x08) end -- START
    if phase == 13 and frame == 813 then emu:setKeys(0) end
    if phase == 13 and frame == 820 then cap("14_menu_open"); phase = 14 end

    -- 17. Close menu (A)
    if phase == 14 and frame == 830 then emu:setKeys(0x01) end
    if phase == 14 and frame == 833 then emu:setKeys(0); phase = 15 end

    -- 18. Use flash bomb (B)
    if phase == 15 and frame == 850 then emu:setKeys(0x02) end -- B
    if phase == 15 and frame == 853 then emu:setKeys(0); cap("15_flash_bomb"); phase = 16 end

    -- 19. Get hit by enemy (walk into danger, verify HP drops)
    -- Just wait for enemies and don't dodge
    if phase == 16 and frame >= 860 and frame < 1200 then
        emu:setKeys(0x10) -- Walk right into enemies
    end
    if phase == 16 and frame == 1200 then
        emu:setKeys(0)
        cap("16_after_damage")
        phase = 17
    end

    -- 20. HUD shows on damage (should be visible briefly)
    if phase == 17 and frame == 1210 then cap("17_hud_visible"); phase = 18 end

    -- 21. HUD auto-hides (wait 4 seconds = 240 frames)
    if phase == 18 and frame == 1450 then cap("18_hud_hidden"); phase = 19 end

    -- 22. Terrain collision: walk into wall (should stop)
    if phase == 19 then
        if frame == 1460 then emu:setKeys(0x20) end -- LEFT toward wall
        if frame == 1520 then emu:setKeys(0); cap("19_wall_collision"); phase = 20 end
    end

    -- 23. Continue playing, verify enemies spawn from multiple directions
    if phase == 20 then
        if frame >= 1530 then emu:setKeys(0x01) end -- Shoot
        if frame == 1800 then emu:setKeys(0); cap("20_enemy_density"); phase = 21 end
    end

    -- Done
    if phase == 21 and frame == 1810 then
        console:log("Verification complete: " .. caps .. " captures")
        emu:quit()
    end
end)
