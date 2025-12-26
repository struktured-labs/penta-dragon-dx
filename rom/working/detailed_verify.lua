-- Detailed color verification script
local frameCount = 0
local screenshotCount = 0
local logFile = io.open("rom/working/detailed_verify.txt", "w")

-- Function to read OBJ palette from palette RAM
local function readOBJPalette(palIndex)
    local colors = {}
    for colorIdx = 0, 3 do
        emu:write8(0xFF6A, 0x80 + (palIndex * 8) + (colorIdx * 2))
        local lo = emu:read8(0xFF6B)
        emu:write8(0xFF6A, 0x80 + (palIndex * 8) + (colorIdx * 2) + 1)
        local hi = emu:read8(0xFF6B)
        local color = lo + (hi * 256)
        table.insert(colors, string.format("%04X", color))
    end
    return colors
end

-- Function to log OAM sprite data
local function logOAM()
    logFile:write(string.format("\n=== Frame %d ===\n", frameCount))
    
    -- Read OBJ palettes
    logFile:write("OBJ Palettes:\n")
    for pal = 0, 7 do
        local colors = readOBJPalette(pal)
        logFile:write(string.format("  Palette %d: %s\n", pal, table.concat(colors, " ")))
    end
    
    -- Read OAM sprites
    logFile:write("\nVisible Sprites:\n")
    local spriteCount = 0
    for i = 0, 39 do
        local oamBase = 0xFE00 + (i * 4)
        local y = emu:read8(oamBase)
        local x = emu:read8(oamBase + 1)
        local tile = emu:read8(oamBase + 2)
        local attr = emu:read8(oamBase + 3)
        local palette = attr & 0x07
        
        if y > 0 and y < 160 and x > 0 and x < 168 then
            spriteCount = spriteCount + 1
            logFile:write(string.format("  Sprite[%d]: tile=%d palette=%d pos=(%d,%d)\n", 
                i, tile, palette, x, y))
        end
    end
    logFile:write(string.format("Total visible sprites: %d\n", spriteCount))
    logFile:flush()
end

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Log every 300 frames (~5 seconds at 60fps)
    if frameCount % 300 == 0 then
        logOAM()
    end
    
    -- Take screenshots every 600 frames (~10 seconds)
    if frameCount % 600 == 0 and frameCount >= 600 then
        screenshotCount = screenshotCount + 1
        local path = string.format("rom/working/detailed_screenshot_%03d.png", screenshotCount)
        emu:screenshot(path)
        console:log("📸 Screenshot " .. screenshotCount .. ": " .. path)
    end
    
    -- Stop after 10 screenshots
    if screenshotCount >= 10 then
        logFile:close()
        console:log("✓ Verification complete")
        emu:stop()
    end
end)

console:log("Detailed verification script loaded")
