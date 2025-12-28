-- Press SELECT when hazard is on screen to capture BG tiles
-- Output: tmp/hazard_capture.log

print("=== HAZARD TILE CAPTURE ===")
print("Press SELECT when spike log hazard is visible!")
print("Output will be in tmp/hazard_capture.log")

local captured = false
local select_was_pressed = false

callbacks:add("frame", function()
    if captured then return end

    -- Read joypad register - check if SELECT is pressed
    -- We'll check the game's internal button state at common RAM locations
    -- Or just use a simple frame-based approach with user pressing Start to capture

    -- Try reading button state from RAM (common location)
    local buttons = emu:read8(0xFF00)

    -- SELECT button check - when P14 is low and bit 2 is low
    -- This is tricky, let's try a different approach
    -- Check if SELECT+A is pressed by reading common game button buffer
    local joy = emu:read8(0xFFF8) -- Common joypad mirror location

    -- Simple approach: capture after pressing Start (bit 3)
    -- Actually let's just do timed capture - press nothing, just wait
end)

-- Alternative: Just capture on a timer after user signals ready
local frame_count = 0
local ready = false

print("")
print("Auto-capture in 70 seconds")
print("Navigate to hazard...")

callbacks:add("frame", function()
    if captured then return end

    frame_count = frame_count + 1

    -- Capture after 4200 frames (~70 seconds)
    if frame_count == 4200 then
        captured = true

        local log = io.open("tmp/hazard_capture.log", "w")
        local scx = emu:read8(0xFF43)
        local scy = emu:read8(0xFF42)

        log:write("HAZARD TILE CAPTURE\n")
        log:write(string.format("SCX=%d, SCY=%d\n\n", scx, scy))

        -- Screenshot
        emu:screenshot("tmp/hazard_capture.png")

        -- Dump visible BG tiles
        local start_col = math.floor(scx / 8)
        local start_row = math.floor(scy / 8)

        log:write("Visible BG tiles (20x18):\n")
        for row = 0, 17 do
            local line = string.format("R%02d: ", row)
            for col = 0, 19 do
                local map_col = (start_col + col) % 32
                local map_row = (start_row + row) % 32
                local addr = 0x9800 + map_row * 32 + map_col
                local tile = emu:read8(addr)
                line = line .. string.format("%02X ", tile)
            end
            log:write(line .. "\n")
        end

        log:write("\nCaptured! Check tmp/hazard_capture.log and tmp/hazard_capture.png\n")
        log:close()

        print("")
        print("=== CAPTURED! ===")
        print("Check tmp/hazard_capture.log")
        print("Check tmp/hazard_capture.png")
    end

    -- Progress indicator every 10 seconds
    if frame_count % 600 == 0 and frame_count < 4200 then
        print(string.format("Capturing in %d seconds...", (4200 - frame_count) / 60))
    end
end)
