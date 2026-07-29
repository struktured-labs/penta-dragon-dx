-- mGBA pixel-pipeline probe for the stock pre/post-final story paths.
--
-- This patches the emulated bank-0 title entry in memory only. The stub maps
-- bank 1 and jumps to the original pre-final 0x54C0 or post-final 0x5513
-- routine. The ROM file is never modified.

local ENTRY = os.getenv("FINAL_SCENE_ENTRY") or "post-final"
local OUT = os.getenv("FINAL_SCENE_OUT") or "/tmp/penta_final_scene.txt"
local SCREENSHOT = os.getenv("FINAL_SCENE_SCREENSHOT")
    or "/tmp/penta_final_scene.png"
local MAX_FRAMES = tonumber(os.getenv("FINAL_SCENE_MAX_FRAMES") or "5000")
local STATE_OUT = os.getenv("FINAL_SCENE_STATE_OUT")
local CAPTURE_STABLE = tonumber(
    os.getenv("FINAL_SCENE_CAPTURE_STABLE") or "240"
)
local ART_TARGET = tonumber(os.getenv("FINAL_SCENE_ART_ID") or "")
local TRACE_LAYOUT = os.getenv("FINAL_SCENE_TRACE_LAYOUT") == "1"
local TRACE = io.open(OUT .. ".trace", "w")
local function trace(message)
    if TRACE then TRACE:write(message .. "\n"); TRACE:flush() end
end

local KEY_A = 0x01
local expected_scene = (ENTRY == "pre-final") and 0x19 or 0x1A
local expected_sequence = (ENTRY == "pre-final") and 0x04 or 0x05
-- 0x5513 is the required PUSH AF paired with the POP AF at 0x5519. Entering
-- at 0x5514 corrupts the diagnostic caller's stack and stalls on the final
-- Sara page instead of returning into the credits.
local target = (ENTRY == "pre-final") and 0x54C0 or 0x5513
local initial_ffba = (ENTRY == "pre-final") and 0x06 or 0x08
local initial_ffe4 = (ENTRY == "pre-final") and 0x00 or 0x01
local WRAM_STUB = 0xDF60

local function emit16(code, value)
    table.insert(code, value & 0xFF)
    table.insert(code, (value >> 8) & 0xFF)
end

local function emit_ld_a16_a(code, address)
    table.insert(code, 0xEA)
    emit16(code, address)
end

local function build_entry_stub()
    local code = {}
    table.insert(code, 0xAF)                  -- XOR A
    emit_ld_a16_a(code, 0xFFC1)              -- gameplay flag = 0
    emit_ld_a16_a(code, 0xDD09)              -- title input block = 0
    emit_ld_a16_a(code, 0x6000)              -- MBC1 mode 0
    emit_ld_a16_a(code, 0x4000)              -- MBC1 upper bits 0
    table.insert(code, 0x3E)
    table.insert(code, initial_ffba)
    table.insert(code, 0xE0)
    table.insert(code, 0xBA)                  -- FFBA
    table.insert(code, 0x3E)
    table.insert(code, initial_ffe4)
    table.insert(code, 0xE0)
    table.insert(code, 0xE4)                  -- FFE4
    table.insert(code, 0x3E)
    table.insert(code, 0x01)
    table.insert(code, 0xE0)
    table.insert(code, 0x99)                  -- FF99 bank shadow
    emit_ld_a16_a(code, 0x2100)              -- map ROM bank 1
    table.insert(code, 0xC3)                  -- JP target
    emit16(code, target)
    return code
end

local stub = build_entry_stub()
local stub_installed = false

local frame = 0
local previous_scene = -1
local transitions = {}
local samples = 0
local contaminated_total = 0
local max_contaminated = 0
local layout_mismatch_total = 0
local max_layout_mismatch = 0
local table_bad_samples = 0
local reached = false
local screenshot_taken = false
local stable_scene_frames = 0
local state_saved = false
local previous_layout_key = -1
local layout_stable_frames = 0
local previous_mismatch_signature = nil

local function visible_attr_layout()
    local lcdc = emu:read8(0xFF40)
    local scy = emu:read8(0xFF42)
    local scx = emu:read8(0xFF43)
    local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local old_vbk = emu:read8(0xFF4F)
    local art = emu:read8(0xDCF0)
    local committed_art = (
        emu:read8(0xD880) == expected_scene
        and emu:read8(0xDCE8) == expected_sequence
        and emu:read8(0xDCEA) == 0x01
        and art >= 1 and art <= 7
        and ((emu:read8(0xDD07) + 1) & 0xFF) == art
    ) and art or 0
    local viewport_bit = ((scy | scx) & 0x08) << 1
    local expected_key = (
        0x80 | committed_art | (lcdc & 0x08) | viewport_bit
    )
    if (
        committed_art == 0
        or emu:read8(0xDF49) ~= expected_key
        or emu:read8(0xDF4A) < 0x22
    ) then
        emu:write8(0xFF4F, old_vbk)
        return 0, 0, false
    end
    local contaminated, mismatch = 0, 0
    local mismatch_cells = {}
    emu:write8(0xFF4F, 1)
    for row = 0, 17 do
        for column = 0, 19 do
            local map_y = ((scy + row * 8) >> 3) & 0x1F
            local map_x = ((scx + column * 8) >> 3) & 0x1F
            local attr = emu:read8(base + map_y * 32 + map_x)
            local expected = (row <= 7) and committed_art or 0
            if attr ~= 0 then contaminated = contaminated + 1 end
            if attr ~= expected then
                mismatch = mismatch + 1
                if TRACE_LAYOUT then
                    table.insert(
                        mismatch_cells,
                        string.format("%d,%d:%02X", row, column, attr)
                    )
                end
            end
        end
    end
    emu:write8(0xFF4F, old_vbk)
    return contaminated, mismatch, true, table.concat(mismatch_cells, ";")
end

local function active_table_is_neutral()
    for offset = 0, 0xFF do
        if emu:read8(0xCC00 + offset) ~= 0 then return false end
    end
    return true
end

local function finish(status)
    local out = io.open(OUT, "w")
    out:write(string.format("status=%s\n", status))
    out:write(string.format("entry=%s\n", ENTRY))
    out:write(string.format("frames=%d\n", frame))
    out:write(string.format("expected_scene=%02X\n", expected_scene))
    out:write(string.format("reached=%s\n", tostring(reached)))
    out:write(string.format("samples=%d\n", samples))
    out:write(string.format("contaminated_total=%d\n", contaminated_total))
    out:write(string.format("max_contaminated=%d\n", max_contaminated))
    out:write(string.format(
        "layout_mismatch_total=%d\n", layout_mismatch_total
    ))
    out:write(string.format(
        "max_layout_mismatch=%d\n", max_layout_mismatch
    ))
    out:write(string.format("table_bad_samples=%d\n", table_bad_samples))
    out:write(string.format("stable_scene_frames=%d\n", stable_scene_frames))
    out:write(string.format("state_saved=%s\n", tostring(state_saved)))
    out:write(string.format("art_target=%s\n", tostring(ART_TARGET)))
    out:write(string.format("dce8=%02X\n", emu:read8(0xDCE8)))
    out:write(string.format("dcea=%02X\n", emu:read8(0xDCEA)))
    out:write(string.format("dcf0=%02X\n", emu:read8(0xDCF0)))
    out:write(string.format("dd07=%02X\n", emu:read8(0xDD07)))
    out:write("transitions=" .. table.concat(transitions, ",") .. "\n")
    out:close()
    if STATE_OUT then
        local marker = assert(io.open(OUT .. ".done", "w"))
        marker:write(status .. "\n")
        marker:close()
    end
    os.exit(status == "ok" and 0 or 1)
end

callbacks:add("frame", function()
    frame = frame + 1
    local scene = emu:read8(0xD880)

    -- The first trip through 0x39C3 has already begun when Lua receives its
    -- first frame callback. Install after that trip, then let the untouched
    -- title/attract sequence initialize VRAM, CRAM, WRAM, and the DX hook.
    -- The stock title loop naturally re-enters 0x39C3 around frame 2,046 and
    -- takes this diagnostic-only branch in a fully initialized context.
    if frame == 30 and not stub_installed then
        -- Only replace the already-executed first instruction with JP. The
        -- rest of the still-running first title pass must remain untouched.
        emu.memory.cart0:write8(0x39C3, 0xC3)
        emu.memory.cart0:write8(0x39C4, WRAM_STUB & 0xFF)
        emu.memory.cart0:write8(0x39C5, (WRAM_STUB >> 8) & 0xFF)
        stub_installed = true
        trace(string.format(
            "installed JP %04X; %d-byte %s stub -> %04X",
            WRAM_STUB, #stub, ENTRY, target
        ))
    end
    if stub_installed and not reached then
        -- Keep the diagnostic landing pad intact until the title loop takes
        -- the JP. DF60-DF7E is above the DX control/sweep scratch allocation
        -- and is used only in the emulator process.
        for index, byte in ipairs(stub) do
            emu:write8(WRAM_STUB + index - 1, byte)
        end
    end

    local requested_art_committed = (
        ART_TARGET
        and scene == expected_scene
        and emu:read8(0xDCE8) == expected_sequence
        and emu:read8(0xDCEA) == 0x01
        and emu:read8(0xDCF0) == ART_TARGET
        and emu:read8(0xDD07) + 1 == ART_TARGET
    )
    local current_art = emu:read8(0xDCF0)
    local current_art_committed = (
        scene == expected_scene
        and emu:read8(0xDCE8) == expected_sequence
        and emu:read8(0xDCEA) == 0x01
        and current_art >= 1 and current_art <= 7
        and ((emu:read8(0xDD07) + 1) & 0xFF) == current_art
    )
    local current_viewport_bit = (
        (emu:read8(0xFF42) | emu:read8(0xFF43)) & 0x08
    ) << 1
    local current_layout_key = current_art_committed
        and (
            0x80 | current_art | (emu:read8(0xFF40) & 0x08)
            | current_viewport_bit
        ) or -1
    if current_layout_key >= 0 then
        if current_layout_key == previous_layout_key then
            layout_stable_frames = layout_stable_frames + 1
        else
            previous_layout_key = current_layout_key
            layout_stable_frames = 1
        end
    else
        previous_layout_key = -1
        layout_stable_frames = 0
    end

    if TRACE_LAYOUT and current_art_committed then
        local _, mismatch, classified, cells = visible_attr_layout()
        if classified then
            local signature = string.format("%d|%s", mismatch, cells)
            if signature ~= previous_mismatch_signature then
                trace(string.format(
                    "layout-change f%d n=%d art=%02X key=%02X row=%02X " ..
                    "cells=%s",
                    frame, mismatch, current_art, emu:read8(0xDF49),
                    emu:read8(0xDF4A), cells
                ))
                previous_mismatch_signature = signature
            end
        else
            previous_mismatch_signature = nil
        end
    end

    -- Advance dialogue with short, released A pulses. Once a requested art
    -- panel is committed, release A and hold that stock frame for capture.
    if reached and not requested_art_committed and (frame % 90) < 4 then
        emu:setKeys(KEY_A)
    else
        emu:setKeys(0)
    end

    if scene ~= previous_scene then
        table.insert(
            transitions,
            string.format("%d:%02X>%02X", frame, previous_scene & 0xFF, scene)
        )
        trace(string.format(
            "f%d D880=%02X FFC1=%d FFBA=%02X FFE4=%d FF99=%02X",
            frame, scene, emu:read8(0xFFC1), emu:read8(0xFFBA),
            emu:read8(0xFFE4), emu:read8(0xFF99)
        ))
        previous_scene = scene
    end

    if scene == expected_scene then
        reached = true
        local art_committed = (
            not ART_TARGET
            or requested_art_committed
        )
        if STATE_OUT then
            stable_scene_frames = art_committed
                and (stable_scene_frames + 1) or 0
        else
            stable_scene_frames = stable_scene_frames + 1
        end
        if (
            frame >= 60
            and frame % 120 == 0
            and layout_stable_frames >= 120
        ) then
            local contaminated, mismatch, classified = visible_attr_layout()
            if classified then
                if mismatch > 0 then
                    trace(string.format(
                        "layout-mismatch f%d n=%d art=%02X key=%02X row=%02X " ..
                        "LCDC=%02X SCY=%02X SCX=%02X",
                        frame, mismatch, emu:read8(0xDCF0),
                        emu:read8(0xDF49), emu:read8(0xDF4A),
                        emu:read8(0xFF40), emu:read8(0xFF42),
                        emu:read8(0xFF43)
                    ))
                end
                samples = samples + 1
                contaminated_total = contaminated_total + contaminated
                layout_mismatch_total = layout_mismatch_total + mismatch
                if contaminated > max_contaminated then
                    max_contaminated = contaminated
                end
                if mismatch > max_layout_mismatch then
                    max_layout_mismatch = mismatch
                end
                if not active_table_is_neutral() then
                    table_bad_samples = table_bad_samples + 1
                end
                if not screenshot_taken and frame >= 600 then
                    emu:screenshot(SCREENSHOT)
                    screenshot_taken = true
                end
            end
        end
        if STATE_OUT and stable_scene_frames == CAPTURE_STABLE then
            emu:screenshot(SCREENSHOT)
            screenshot_taken = true
            local ok, result = pcall(function()
                return emu:saveStateFile(STATE_OUT)
            end)
            state_saved = ok and result ~= false
            if not state_saved then
                trace("saveStateFile failed: " .. tostring(result))
            end
            finish(state_saved and "ok" or "failed")
            return
        end
    elseif reached and STATE_OUT then
        stable_scene_frames = 0
    end

    local finished_pre = (
        ENTRY == "pre-final"
        and reached
        and scene >= 0x0C
        and scene <= 0x14
    )
    local enough_post = (
        ENTRY == "post-final"
        and reached
        and frame >= MAX_FRAMES
    )
    if finished_pre or enough_post then
        local ok = (
            samples > 0
            and layout_mismatch_total == 0
            and table_bad_samples == 0
        )
        finish(ok and "ok" or "failed")
    end

    if frame >= MAX_FRAMES then
        local ok = (
            reached
            and samples > 0
            and layout_mismatch_total == 0
            and table_bad_samples == 0
        )
        finish(ok and "ok" or "failed")
    end
end)
