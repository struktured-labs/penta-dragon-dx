-- Lua script for mgba to verify palette injection
-- Extracts OBJ palette data and OAM sprite attributes after game initializes

local frameCount = 0
local targetFrame = 120  -- ~2 seconds at 60fps for game to stabilize
local outputFile = "rom/working/palette_verification.txt"

function onFrame()
    frameCount = frameCount + 1
    
    if frameCount == targetFrame then
        local file = io.open(outputFile, "w")
        
        file:write("=== Palette Verification Report ===\n\n")
        
        -- Read OBJ palette data from CGB palette RAM
        file:write("--- OBJ Palettes (CGB Palette RAM) ---\n")
        for palIdx = 0, 7 do
            file:write(string.format("OBJ Palette %d: ", palIdx))
            local colors = {}
            for colorIdx = 0, 3 do
                -- Each palette is 8 bytes (4 colors × 2 bytes)
                local addr = 0xFF6B  -- OCPD register (read-only access)
                -- Set palette index via OCPS (0xFF6A)
                emu:write8(0xFF6A, 0x80 + (palIdx * 8) + (colorIdx * 2))
                local lo = emu:read8(0xFF6B)
                emu:write8(0xFF6A, 0x80 + (palIdx * 8) + (colorIdx * 2) + 1)
                local hi = emu:read8(0xFF6B)
                local color = lo + (hi * 256)
                table.insert(colors, string.format("%04X", color))
            end
            file:write(table.concat(colors, " ") .. "\n")
        end
        
        file:write("\n--- OAM Sprite Data (First 16 sprites) ---\n")
        -- OAM is at 0xFE00-0xFE9F (40 sprites × 4 bytes)
        for spriteIdx = 0, 15 do
            local oamBase = 0xFE00 + (spriteIdx * 4)
            local y = emu:read8(oamBase + 0)
            local x = emu:read8(oamBase + 1)
            local tile = emu:read8(oamBase + 2)
            local attr = emu:read8(oamBase + 3)
            
            -- Only report visible sprites
            if y > 0 and y < 160 and x > 0 and x < 168 then
                -- Extract palette number from attributes (bits 0-2 in CGB mode)
                local paletteNum = attr & 0x07
                local priority = (attr & 0x80) ~= 0
                local flipY = (attr & 0x40) ~= 0
                local flipX = (attr & 0x20) ~= 0
                local bank = (attr & 0x08) ~= 0
                
                file:write(string.format(
                    "Sprite %02d: Pos(%3d,%3d) Tile=%02X Palette=%d Bank=%d FlipX=%s FlipY=%s Pri=%s\n",
                    spriteIdx, x-8, y-16, tile, paletteNum, bank and 1 or 0,
                    flipX and "Y" or "N", flipY and "Y" or "N", priority and "Y" or "N"
                ))
            end
        end
        
        file:write("\n=== Analysis ===\n")
        file:write("- Check which sprites use palette 0 (MainCharacter)\n")
        file:write("- Check which sprites use palettes 1-7 (Enemies/monsters)\n")
        file:write("- Compare OBJ Palette 0 colors to YAML definition\n")
        
        file:close()
        
        console:log("✓ Palette verification written to " .. outputFile)
        
        -- Take a screenshot
        emu:screenshot("rom/working/palette_verification.png")
        console:log("✓ Screenshot saved to rom/working/palette_verification.png")
        
        -- Exit after capturing data
        emu:stop()
    end
end

callbacks:add("frame", onFrame)
console:log("Palette verification script loaded. Will capture data at frame " .. targetFrame)
