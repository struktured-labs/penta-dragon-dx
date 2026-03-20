-- GB Game Verifier — State dumper for mGBA
-- Dumps memory + screenshot every N frames
-- Config via env vars: VERIFY_DUMP_DIR, VERIFY_INTERVAL, VERIFY_MAX_FRAMES, VERIFY_INPUT_FILE

local DUMP_DIR = os.getenv("VERIFY_DUMP_DIR") or "tmp/verify_dump"
local INTERVAL = tonumber(os.getenv("VERIFY_INTERVAL") or "60")
local MAX_FRAMES = tonumber(os.getenv("VERIFY_MAX_FRAMES") or "1800")
local INPUT_FILE = os.getenv("VERIFY_INPUT_FILE") or ""

-- Memory addresses to track (Penta Dragon)
local ADDRS = {
    {0xFF43, "SCX"},
    {0xFF42, "SCY"},
    {0xFF40, "LCDC"},
    {0xFFBD, "room"},
    {0xFFBE, "form"},
    {0xFFBF, "boss"},
    {0xFFC0, "powerup"},
    {0xFFC1, "gameplay"},
    {0xFFD0, "stage"},
}

-- Load recorded inputs
local inputs = {}
if INPUT_FILE ~= "" then
    local f = io.open(INPUT_FILE, "r")
    if f then
        for line in f:lines() do
            local fr, keys = line:match("(%d+),(%d+)")
            if fr then inputs[tonumber(fr)] = tonumber(keys) end
        end
        f:close()
    end
end

-- Open state log
local state_file = io.open(DUMP_DIR .. "/state.csv", "w")
if not state_file then
    console:log("ERROR: cannot write to " .. DUMP_DIR .. "/state.csv")
    return
end

-- Write header
local hdr = "frame,keys"
for _, a in ipairs(ADDRS) do hdr = hdr .. "," .. a[2] end
state_file:write(hdr .. "\n")

local frame = 0

callbacks:add("frame", function()
    frame = frame + 1

    -- Apply recorded inputs
    if inputs[frame] then
        emu:setKeys(inputs[frame])
    end

    -- Dump state
    if frame % INTERVAL == 0 then
        local keys = 0
        if inputs[frame] then keys = inputs[frame] end

        local line = frame .. "," .. keys
        for _, a in ipairs(ADDRS) do
            line = line .. "," .. emu:read8(a[1])
        end
        state_file:write(line .. "\n")
        state_file:flush()

        emu:screenshot(DUMP_DIR .. "/frame_" .. string.format("%06d", frame) .. ".png")
    end

    if frame >= MAX_FRAMES then
        state_file:close()
        console:log("Verifier done: " .. frame .. " frames")
        emu:quit()
    end
end)
