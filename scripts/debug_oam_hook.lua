-- Debug script to check if OAM DMA hook is working
local frameCount = 0
local logFile = nil
local hookCallCount = 0

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    if frameCount == 1 then
        logFile = io.open("oam_hook_debug.txt", "w")
        logFile:write("=== OAM DMA Hook Debug ===\n")
    end
    
    if not logFile then return end
    
    -- Log every 60 frames
    if frameCount % 60 == 0 then
        logFile:write(string.format("\n=== Frame %d ===\n", frameCount))
        
        -- Check OBJ Palette 1 (SARA_W)
        logFile:write("OBJ Palette 1:\n")
        for i = 0, 3 do
            emu:write8(0xFF6A, 0x80 + (1 * 8) + (i * 2))
            local lo = emu:read8(0xFF6B)
            emu:write8(0xFF6A, 0x80 + (1 * 8) + (i * 2) + 1)
            local hi = emu:read8(0xFF6B)
            local color = lo | (hi << 8)
            logFile:write(string.format("  Color %d: %04X\n", i, color))
        end
        
        -- Check SARA_W sprites
        logFile:write("\nSARA_W sprites (tiles 4-7):\n")
        local sara_w_found = false
        for sprite = 0, 39 do
            local oam = 0xFE00 + (sprite * 4)
            local y = emu:read8(oam)
            local x = emu:read8(oam + 1)
            local tile = emu:read8(oam + 2)
            local flags = emu:read8(oam + 3)
            local palette = flags & 0x07
            
            if y > 0 and y < 144 and tile >= 4 and tile < 8 then
                sara_w_found = true
                logFile:write(string.format("  Sprite %d: tile=%d, palette=%d, pos=(%d,%d)\n", 
                    sprite, tile, palette, x, y))
            end
        end
        
        if not sara_w_found then
            logFile:write("  (No SARA_W sprites found)\n")
        end
        
        -- Check current bank
        local current_bank = emu:read8(0x2000) & 0x1F
        logFile:write(string.format("\nCurrent bank: %d\n", current_bank))
        
        logFile:flush()
    end
    
    -- Stop after 5 seconds (300 frames at 60fps)
    if frameCount >= 300 then
        logFile:close()
        emu:quit()
    end
end)

-- Try to hook OAM DMA register write to detect when DMA happens
local last_dma_value = 0
callbacks:add("read", function(addr, value)
    -- Monitor FF46 (OAM DMA register)
    if addr == 0xFF46 then
        if value ~= last_dma_value and value ~= 0 then
            hookCallCount = hookCallCount + 1
            if logFile then
                logFile:write(string.format("\n[Frame %d] OAM DMA triggered! Value: 0x%02X (count: %d)\n", 
                    frameCount, value, hookCallCount))
                logFile:flush()
            end
            last_dma_value = value
        end
    end
end)

print("OAM DMA hook debug script loaded")

