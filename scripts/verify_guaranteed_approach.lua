-- Guaranteed Approach Verification Script
-- Verifies each step of palette injection is working correctly

local frameCount = 0
local boot_loader_addr = 0x0150  -- Boot hook address
local oam_dma_ret = 0x4197       -- OAM DMA completion
local logFile = nil

-- Expected palette values (Palette 1: SARA_W)
local expected_palette_1 = {
    0x0000,  -- transparent
    0x03E0,  -- green
    0x021F,  -- orange
    0x0280   -- dark green
}

function log(message)
    if logFile then
        logFile:write(message .. "\n")
    end
    console:log(message)
end

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Initialize log file on first frame
    if frameCount == 1 then
        logFile = io.open("guaranteed_approach_verification.log", "w")
        log("=== Guaranteed Approach Verification ===")
        log("Frame: " .. frameCount)
    end
    
    -- Check 1: Boot hook is installed
    if frameCount == 1 then
        local boot_hook = emu:read8(boot_loader_addr)
        if boot_hook == 0xCD then
            log("✅ CHECK 1: Boot hook installed at 0x0150 (CALL instruction)")
        else
            log("❌ CHECK 1: Boot hook NOT installed (found 0x" .. string.format("%02X", boot_hook) .. ")")
        end
    end
    
    -- Check 2: OAM DMA hook is installed
    if frameCount == 1 then
        local oam_hook = emu:read8(oam_dma_ret)
        if oam_hook == 0xCD then
            log("✅ CHECK 2: OAM DMA hook installed at 0x4197 (CALL instruction)")
        else
            log("❌ CHECK 2: OAM DMA hook NOT installed (found 0x" .. string.format("%02X", oam_hook) .. ")")
        end
    end
    
    -- Check 3: Palettes loaded (check after boot, around frame 10)
    if frameCount == 10 then
        log("\n--- CHECK 3: Palette Loading Verification ---")
        local all_loaded = true
        
        -- Check OBJ Palette 1
        log("Checking OBJ Palette 1:")
        for colorIdx = 0, 3 do
            -- Set palette index
            emu:write8(0xFF6A, 0x80 + (1 * 8) + (colorIdx * 2))
            local lo = emu:read8(0xFF6B)
            emu:write8(0xFF6A, 0x80 + (1 * 8) + (colorIdx * 2) + 1)
            local hi = emu:read8(0xFF6B)
            local color = lo + (hi * 256)
            local expected = expected_palette_1[colorIdx + 1]
            
            if color == expected then
                log(string.format("  Color %d: 0x%04X ✅", colorIdx, color))
            else
                log(string.format("  Color %d: 0x%04X ❌ (expected 0x%04X)", colorIdx, color, expected))
                all_loaded = false
            end
        end
        
        if all_loaded then
            log("✅ CHECK 3: Palettes loaded correctly")
        else
            log("❌ CHECK 3: Palettes NOT loaded correctly")
        end
    end
    
    -- Check 4: Sprite assignment (check around frame 200, when sprites are visible)
    if frameCount == 200 then
        log("\n--- CHECK 4: Sprite Assignment Verification ---")
        local sara_w_sprites = 0
        local correct_palette = 0
        
        -- Check OAM for SARA_W sprites (tiles 4-7)
        for spriteIdx = 0, 39 do
            local oam_addr = 0xFE00 + (spriteIdx * 4)
            local y = emu:read8(oam_addr)
            local tile = emu:read8(oam_addr + 2)
            local flags = emu:read8(oam_addr + 3)
            local palette = flags & 0x07
            
            if y > 0 and y < 144 and tile >= 4 and tile < 8 then
                sara_w_sprites = sara_w_sprites + 1
                if palette == 1 then
                    correct_palette = correct_palette + 1
                    log(string.format("  Sprite %d: tile=%d, palette=%d ✅", spriteIdx, tile, palette))
                else
                    log(string.format("  Sprite %d: tile=%d, palette=%d ❌ (expected 1)", spriteIdx, tile, palette))
                end
            end
        end
        
        if sara_w_sprites > 0 then
            log(string.format("Found %d SARA_W sprites, %d with correct palette", sara_w_sprites, correct_palette))
            if correct_palette == sara_w_sprites then
                log("✅ CHECK 4: All SARA_W sprites have correct palette")
            else
                log("❌ CHECK 4: Some SARA_W sprites have wrong palette")
            end
        else
            log("⚠️  CHECK 4: No SARA_W sprites found (may not be visible yet)")
        end
    end
    
    -- Check 5: DMG palette patches (verify patches are applied)
    if frameCount == 1 then
        log("\n--- CHECK 5: DMG Palette Patch Verification ---")
        -- Check a few known DMG palette write locations
        local known_dmg_writes = {0x41C1, 0x41D3, 0x41D5, 0x41E6, 0x41EA}
        local patched_count = 0
        
        for _, addr in ipairs(known_dmg_writes) do
            if addr < emu:getMemorySize() then
                local opcode = emu:read8(addr)
                local reg = emu:read8(addr + 1)
                
                if opcode == 0xE0 and reg == 0x00 then
                    patched_count = patched_count + 1
                    log(string.format("  Address 0x%04X: Patched ✅", addr))
                elseif opcode == 0xE0 and (reg == 0x47 or reg == 0x48 or reg == 0x49) then
                    log(string.format("  Address 0x%04X: NOT patched ❌ (writes to FF%02X)", addr, reg))
                end
            end
        end
        
        if patched_count > 0 then
            log(string.format("✅ CHECK 5: %d DMG palette writes patched", patched_count))
        else
            log("⚠️  CHECK 5: Could not verify DMG patches (may need different addresses)")
        end
    end
    
    -- Stop after checks complete
    if frameCount >= 250 then
        log("\n=== Verification Complete ===")
        if logFile then
            logFile:close()
        end
        emu:quit()
    end
end)

console:log("Guaranteed approach verification script loaded")

