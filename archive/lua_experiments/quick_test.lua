-- Quick test script - captures OAM state
local frameCount = 0

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Check OAM every 100 frames after demo starts
    if frameCount >= 8500 and frameCount % 100 == 0 then
        local visible = {}
        for i = 0, 39 do
            local base = 0xFE00 + (i * 4)
            local y = emu:read8(base)
            local x = emu:read8(base + 1)
            local tile = emu:read8(base + 2)
            local flags = emu:read8(base + 3)
            local pal = flags & 0x07
            
            if y > 0 and y < 160 and x > 0 and x < 168 then
                table.insert(visible, string.format("S%d:t%02X,p%d", i, tile, pal))
            end
        end
        
        if #visible > 0 then
            print(string.format("F%d: %s", frameCount, table.concat(visible, " ")))
        end
    end
    
    if frameCount >= 12000 then
        print("Test complete")
        emu:stop()
    end
end)

print("Quick test loaded...")
