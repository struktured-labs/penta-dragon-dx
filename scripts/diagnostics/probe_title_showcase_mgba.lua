-- Audit the complete cold-boot title/logo/banner cycle through mGBA's CGB
-- pixel pipeline. No input or state injection is used.

local OUT = os.getenv("TITLE_SHOWCASE_OUT")
    or "/tmp/penta-title-showcase"
local MAX_FRAMES = tonumber(os.getenv("TITLE_SHOWCASE_MAX_FRAMES") or "7000")
local EXPECTED_BG0 = {0xFF, 0x7F, 0x94, 0x7E, 0x4A, 0x3D, 0x00, 0x00}
local TITLE_SCENES = {
    [0x01] = true,
    [0x1B] = true,
    [0x1C] = true,
}
local CAPTURE_AT = {
    [0x01] = {[300] = true, [900] = true},
    [0x1C] = {[300] = true, [900] = true, [1500] = true},
    [0x1B] = {[300] = true, [1000] = true, [2000] = true, [3000] = true},
}

local frame, previous_scene, scene_elapsed = 0, -1, 0
local done, entered_attract, screenshot_count = false, false, 0
local transitions = {}
local samples = {[0x01] = 0, [0x1B] = 0, [0x1C] = 0}
local nonzero_total, max_nonzero = 0, 0
local unsafe_total, table_non_neutral_samples = 0, 0
local banner_table_bad_samples, cram_bad_samples = 0, 0
local cram_bad_details = {}

local function visible_attr_counts()
    local lcdc = emu:read8(0xFF40)
    local scy = emu:read8(0xFF42)
    local scx = emu:read8(0xFF43)
    local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local old_vbk = emu:read8(0xFF4F)
    local nonzero, unsafe = 0, 0
    emu:write8(0xFF4F, 1)
    for row = 0, 17 do
        for column = 0, 19 do
            local map_y = ((scy + row * 8) >> 3) & 0x1F
            local map_x = ((scx + column * 8) >> 3) & 0x1F
            local attr = emu:read8(base + map_y * 32 + map_x)
            if (attr & 0x07) ~= 0 then nonzero = nonzero + 1 end
            if (attr & 0xF8) ~= 0 then unsafe = unsafe + 1 end
        end
    end
    emu:write8(0xFF4F, old_vbk)
    return nonzero, unsafe
end

local function active_table_is_neutral()
    for offset = 0, 0xFF do
        if emu:read8(0xC600 + offset) ~= 0 then return false end
    end
    return true
end

local function bg0_is_expected()
    local old_bcps = emu:read8(0xFF68)
    local valid = true
    local actual = {}
    for offset = 0, 7 do
        emu:write8(0xFF68, offset)
        local value = emu:read8(0xFF69)
        actual[#actual + 1] = string.format("%02X", value)
        if value ~= EXPECTED_BG0[offset + 1] then
            valid = false
        end
    end
    emu:write8(0xFF68, old_bcps)
    return valid, table.concat(actual)
end

local function finish(status, message)
    if done then return end
    done = true
    local report = assert(io.open(OUT .. ".report", "w"))
    report:write(string.format("status=%s\n", status))
    report:write(string.format("message=%s\n", message))
    report:write(string.format("frames=%d\n", frame))
    report:write(string.format(
        "transitions=%s\n", table.concat(transitions, ",")
    ))
    report:write(string.format("samples_01=%d\n", samples[0x01]))
    report:write(string.format("samples_1B=%d\n", samples[0x1B]))
    report:write(string.format("samples_1C=%d\n", samples[0x1C]))
    report:write(string.format("nonzero_total=%d\n", nonzero_total))
    report:write(string.format("max_nonzero=%d\n", max_nonzero))
    report:write(string.format("unsafe_total=%d\n", unsafe_total))
    report:write(string.format(
        "table_non_neutral_samples=%d\n", table_non_neutral_samples
    ))
    report:write(string.format(
        "banner_table_bad_samples=%d\n", banner_table_bad_samples
    ))
    report:write(string.format("cram_bad_samples=%d\n", cram_bad_samples))
    report:write(string.format(
        "cram_bad_details=%s\n", table.concat(cram_bad_details, ",")
    ))
    report:write(string.format("screenshots=%d\n", screenshot_count))
    report:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(status .. "\n")
    marker:close()
end

callbacks:add("frame", function()
    if done then return end
    frame = frame + 1
    emu:setKeys(0)

    local scene = emu:read8(0xD880)
    local ffc1 = emu:read8(0xFFC1)
    if scene ~= previous_scene then
        table.insert(
            transitions,
            string.format("%d:%02X>%02X/g%d",
                frame, previous_scene & 0xFF, scene, ffc1)
        )
        previous_scene = scene
        scene_elapsed = 1
    else
        scene_elapsed = scene_elapsed + 1
    end

    if TITLE_SCENES[scene] and ffc1 == 0 then
        if scene_elapsed >= 15 and scene_elapsed % 15 == 0 then
            local nonzero, unsafe = visible_attr_counts()
            samples[scene] = samples[scene] + 1
            nonzero_total = nonzero_total + nonzero
            unsafe_total = unsafe_total + unsafe
            if nonzero > max_nonzero then max_nonzero = nonzero end
            if not active_table_is_neutral() then
                table_non_neutral_samples = table_non_neutral_samples + 1
                if scene == 0x1B then
                    banner_table_bad_samples = banner_table_bad_samples + 1
                end
            end
            local bg0_valid, bg0_actual = bg0_is_expected()
            if not bg0_valid then
                cram_bad_samples = cram_bad_samples + 1
                if #cram_bad_details < 16 then
                    cram_bad_details[#cram_bad_details + 1] = string.format(
                        "f%d/s%02X/e%d:%s",
                        frame, scene, scene_elapsed, bg0_actual
                    )
                end
            end
        end
        if CAPTURE_AT[scene] and CAPTURE_AT[scene][scene_elapsed] then
            screenshot_count = screenshot_count + 1
            emu:screenshot(string.format(
                "%s.%02d.scene%02X.f%d.png",
                OUT, screenshot_count, scene, frame
            ))
        end
    end

    -- The complete idle reel is still a title-mode path, so FFC1 correctly
    -- remains zero throughout 01 -> 1C -> 1B. Requiring FFC1=1 made a clean,
    -- fully captured nine-frame cycle wait until MAX_FRAMES and false-fail.
    if samples[0x01] > 0
        and samples[0x1B] > 0 and samples[0x1C] > 0 then
        entered_attract = true
    end
    if entered_attract and screenshot_count == 9 then
        local clean = (
            nonzero_total == 0
            and unsafe_total == 0
            and banner_table_bad_samples == 0
            and cram_bad_samples == 0
        )
        finish(clean and "ok" or "failed", "complete-title-cycle")
        return
    end
    if frame >= MAX_FRAMES then
        finish("failed", "title-cycle-timeout")
    end
end)
