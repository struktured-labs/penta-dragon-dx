#!/bin/bash
# Automated test loop for Penta Dragon DX colorization
# Runs ROM in headless mgba with fastforward, captures OAM data and screenshots

set -e

PROJECT_DIR="/home/struktured/projects/penta-dragon-dx-claude"
ROM_PATH="$PROJECT_DIR/rom/working/penta_dragon_dx_FIXED.gb"
TEST_OUTPUT="$PROJECT_DIR/test_output/auto_loop_$(date +%s)"
SCRIPT_PATH="$TEST_OUTPUT/test_script.lua"

mkdir -p "$TEST_OUTPUT/screenshots"
mkdir -p "$TEST_OUTPUT/logs"

# Create Lua test script
cat > "$SCRIPT_PATH" << 'LUAEOF'
-- Auto test loop Lua script
-- Captures OAM state and screenshots during demo sequence

local frameCount = 0
local oamLog = {}
local screenshotDir = os.getenv("SCREENSHOT_DIR") or "test_output"

-- Get OAM state
local function getOAMState()
    local sprites = {}
    for i = 0, 39 do
        local base = 0xFE00 + (i * 4)
        local y = emu:read8(base)
        local x = emu:read8(base + 1)
        local tile = emu:read8(base + 2)
        local flags = emu:read8(base + 3)
        local palette = flags & 0x07

        -- Only log visible sprites
        if y > 0 and y < 160 and x > 0 and x < 168 then
            table.insert(sprites, {
                idx = i,
                y = y,
                x = x,
                tile = tile,
                palette = palette,
                flags = flags
            })
        end
    end
    return sprites
end

-- Frame callback
callbacks:add("frame", function()
    frameCount = frameCount + 1

    -- Wait for demo to start (around frame 8000+)
    -- Capture every 30 frames once sprites appear
    if frameCount >= 8000 and frameCount % 30 == 0 then
        local sprites = getOAMState()

        if #sprites > 0 then
            -- Log OAM state
            table.insert(oamLog, {
                frame = frameCount,
                sprites = sprites
            })

            -- Take screenshot
            local screenshot = emu:takeScreenshot()
            local filename = string.format("%s/frame_%06d.png", screenshotDir, frameCount)
            screenshot:save(filename)
        end
    end

    -- Stop after frame 15000 (demo should be well underway)
    if frameCount >= 15000 then
        -- Write OAM log
        local logFile = io.open(screenshotDir .. "/oam_log.txt", "w")
        logFile:write("# OAM Log - Auto Test Loop\n")
        logFile:write(string.format("# Total frames with sprites: %d\n\n", #oamLog))

        for _, entry in ipairs(oamLog) do
            logFile:write(string.format("Frame %d:\n", entry.frame))
            for _, s in ipairs(entry.sprites) do
                logFile:write(string.format("  Sprite[%d]: tile=0x%02X pal=%d pos=(%d,%d) flags=0x%02X\n",
                    s.idx, s.tile, s.palette, s.x, s.y, s.flags))
            end
            logFile:write("\n")
        end
        logFile:close()

        -- Also write JSON for easier parsing
        local jsonFile = io.open(screenshotDir .. "/oam_log.json", "w")
        jsonFile:write("[\n")
        for i, entry in ipairs(oamLog) do
            jsonFile:write(string.format('  {"frame": %d, "sprites": [', entry.frame))
            for j, s in ipairs(entry.sprites) do
                jsonFile:write(string.format('{"idx":%d,"tile":%d,"pal":%d,"x":%d,"y":%d}',
                    s.idx, s.tile, s.palette, s.x, s.y))
                if j < #entry.sprites then jsonFile:write(",") end
            end
            jsonFile:write("]}")
            if i < #oamLog then jsonFile:write(",") end
            jsonFile:write("\n")
        end
        jsonFile:write("]\n")
        jsonFile:close()

        print(string.format("Test complete. Logged %d frames with sprites.", #oamLog))
        emu:stop()
    end
end)

print("Auto test loop script loaded. Waiting for demo sequence...")
LUAEOF

echo "Test output: $TEST_OUTPUT"
echo "Running mgba with fastforward and test script..."

# Run mgba headlessly with xvfb and fastforward
export SCREENSHOT_DIR="$TEST_OUTPUT/screenshots"
timeout 30 xvfb-run -a mgba-qt --fastforward --script "$SCRIPT_PATH" "$ROM_PATH" 2>&1 || true

echo "Test complete. Results in $TEST_OUTPUT"
ls -la "$TEST_OUTPUT/screenshots/" 2>/dev/null | head -20 || echo "No screenshots dir"
echo "---"
if [ -f "$TEST_OUTPUT/screenshots/oam_log.txt" ]; then
    head -50 "$TEST_OUTPUT/screenshots/oam_log.txt"
fi
