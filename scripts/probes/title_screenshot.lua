-- Title screen capture harness.
-- Boots ROM, waits N frames for title to render, screenshots once, exits.
-- Output path read from env STATE_PATH (full path including extension).
-- Frame target read from env FRAME_AT (default 200).

local OUT = os.getenv("STATE_PATH") or "/tmp/penta_title.png"
local FRAME_AT = tonumber(os.getenv("FRAME_AT") or "200")

local fired = false

callbacks:add("frame", function()
    local f = emu:currentFrame()
    if not fired and f >= FRAME_AT then
        fired = true
        emu:screenshot(OUT)
        console:log("title_screenshot wrote " .. OUT .. " at frame " .. f)
        os.exit(0)
    end
end)
