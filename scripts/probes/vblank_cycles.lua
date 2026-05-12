-- Measure VBlank handler T-cycle duration by stamping at entry (0x0040) and
-- exit (0x081D per project memory) and reading DIV (CPU/256 timer).
--
-- A handler that runs longer than the VBlank period (~4560 T-cycles) can
-- cause palette writes to land in LCD Mode 3, producing scroll tearing.
--
-- Output: tmp/vblank_cycles_<label>.txt with histogram of cycle counts.

local OUT = os.getenv("STATE_PATH") or "/tmp/penta_vblank.txt"
local TOTAL_FRAMES = tonumber(os.getenv("TOTAL_FRAMES") or "600")
local START_AT = tonumber(os.getenv("START_AT") or "120")

local entry_div = nil
local entry_frame = nil
local durations = {}
local f = 0
local fired = false

-- mgba's exec watchpoint fires on instruction at the given PC.
-- Use the VBlank vector (0x0040) and the RETI at 0x081D.
if callbacks.execute then
    -- newer mgba scripting (5+)
    -- not always present; fall back to frame-based sampling
end

-- Simpler approach: use the 'frame' callback (fires once per video frame
-- after rendering completes). Between frames, we can read DIV to see how
-- many cycles passed. If the modded handler dominates, the FF04 delta
-- between frame callbacks is consistent — but doesn't tell us VBlank-only
-- duration.
--
-- Real measurement: sample LY (FF44) inside frame callback. LY=0 means
-- we just exited VBlank and started a new frame. If our handler is slow,
-- LY may have wrapped well past 0 by the time the callback fires (mgba
-- batches frames at end of vertical sync). This is approximate.

callbacks:add("frame", function()
    if fired then return end
    f = f + 1
    if f < START_AT then return end

    local div = emu:read8(0xFF04)
    local ly = emu:read8(0xFF44)
    -- LY between 144 and 153 = VBlank window
    -- We sample at frame-end (start of next VBlank). LY should be ~0 if
    -- rendering completed normally. LY > 0 here indicates the previous
    -- VBlank handler overran enough that we missed the VBlank start
    -- detection (rare but observable when VBlank work is huge).
    table.insert(durations, {f=f, div=div, ly=ly})

    if #durations >= TOTAL_FRAMES - START_AT then
        fired = true
        local fh = io.open(OUT, "w")
        fh:write("# VBlank cycle approximation: DIV/LY samples at frame-end\n")
        -- DIV diffs between consecutive samples ≈ M-cycles since last sample
        -- (DIV ticks at 16384 Hz = clock/256, so each unit = 256 T-cycles)
        local div_diffs = {}
        local prev_div = nil
        for _, s in ipairs(durations) do
            if prev_div ~= nil then
                local diff = s.div - prev_div
                if diff < 0 then diff = diff + 256 end  -- wrap
                table.insert(div_diffs, diff)
            end
            prev_div = s.div
        end
        -- Stats
        local sum, max_d, ge17 = 0, 0, 0
        for _, d in ipairs(div_diffs) do
            sum = sum + d
            if d > max_d then max_d = d end
            -- 1 frame ≈ 70224 T = 274 DIV ticks. But DIV is 8-bit so wraps.
            -- A delta > 17 (≈4500 T) inside a frame would indicate an
            -- abnormally heavy VBlank handler.
            if d >= 17 then ge17 = ge17 + 1 end
        end
        fh:write(string.format("samples=%d\n", #div_diffs))
        if #div_diffs > 0 then
            fh:write(string.format("mean_div_delta=%.2f\n", sum / #div_diffs))
        end
        fh:write(string.format("max_div_delta=%d\n", max_d))
        fh:write(string.format("samples_ge_17=%d\n", ge17))
        fh:close()
        console:log(string.format("vblank_cycles: %d samples, max delta %d",
            #div_diffs, max_d))
        os.exit(0)
    end
end)
