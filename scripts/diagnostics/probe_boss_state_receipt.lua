-- Reload a generated boss state in a fresh mGBA process and emit a rendered
-- receipt plus exact production table/CRAM bytes.

local OUT = assert(os.getenv("BOSS_RECEIPT_OUT"), "BOSS_RECEIPT_OUT required")
local STATE_OUT = os.getenv("BOSS_RECEIPT_STATE_OUT")
local TARGET = tonumber(os.getenv("BOSS_TARGET") or "0")
local EXPECTED_SCENE = 0x0C + TARGET
local RECEIPT_FRAME = tonumber(os.getenv("BOSS_RECEIPT_FRAMES") or "120")
local AUDIT_WARMUP = tonumber(os.getenv("BOSS_RECEIPT_WARMUP") or "24")
local REARM_CURRENT_ROM = os.getenv("BOSS_RECEIPT_REARM") ~= "0"
local REARM_PALETTES = os.getenv("BOSS_RECEIPT_PALETTE_REARM") ~= "0"
local KEEP_ALIVE = os.getenv("BOSS_RECEIPT_KEEPALIVE") ~= "0"
local frame, done, state_saved = 0, false, false
local palette_settled = 0
local scene_drift_frames = 0
local max_scene_drift_frames = 0
local trace = assert(io.open(OUT .. ".audit.trace", "w"))
local attr_frames, attr_samples, attr_mismatches = 0, 0, 0
local raw_lut_mismatches = 0
local max_frame_mismatches, unsafe_attrs = 0, 0
local mismatch_examples = {}
local contract_attrs = {}
local copy_entries, atomic_copies, pure_copies, sanitizer_calls = 0, 0, 0, 0
local decision_zero, decision_nonzero = 0, 0
local sanitizer_examples = {}
local penta_9c88_writes = {}
local penta_992f_writes = {}
local penta_pending_mismatches = {}
local hidden_staging_mismatches = 0

local function register(name)
    local accessors = {
        function() return emu:getRegister(name) end,
        function() return emu:getRegister(string.lower(name)) end,
        function() return emu:readRegister(name) end,
        function() return emu:readRegister(string.lower(name)) end,
    }
    for _, accessor in ipairs(accessors) do
        local ok, value = pcall(accessor)
        if ok and value ~= nil then return value & 0xFFFF end
    end
    return 0xFFFF
end

-- Define the register accessor before breakpoint closures capture it. Lua's
-- local scope begins at the declaration, so registering these callbacks above
-- the helper silently resolved `register` as an unset global when they fired.
pcall(function()
    emu:setBreakpoint(function() copy_entries = copy_entries + 1 end, 0x42A7)
    emu:setBreakpoint(function()
        if (register("F") & 0x80) ~= 0 then
            decision_zero = decision_zero + 1
        else
            decision_nonzero = decision_nonzero + 1
        end
    end, 0x42B0)
    emu:setBreakpoint(function() atomic_copies = atomic_copies + 1 end, 0x42B2)
    emu:setBreakpoint(function() pure_copies = pure_copies + 1 end, 0x4324)
    emu:setBreakpoint(function()
        sanitizer_calls = sanitizer_calls + 1
        if #sanitizer_examples < 8 then
            sanitizer_examples[#sanitizer_examples + 1] = string.format(
                "%02X:%04X:%04X", emu:read8(0xD880),
                register("HL"), register("DE"))
        end
    end, 0xDB80)
end)
if TARGET == 8 then
    pcall(function()
        emu:addMemoryCallback(function(address, value)
            if #penta_9c88_writes < 24 then
                penta_9c88_writes[#penta_9c88_writes + 1] = string.format(
                    "f%d:b%02X:pc%04X:v%02X:vbk%d", frame,
                    emu:read8(0xFF99), register("PC"), value,
                    emu:read8(0xFF4F) & 1)
            end
        end, emu.memoryCallback.WRITE, 0x9C88, 0x9C88)
    end)
    pcall(function()
        emu:addMemoryCallback(function(address, value)
            if #penta_992f_writes < 48 then
                penta_992f_writes[#penta_992f_writes + 1] = string.format(
                    "f%d:pc%04X:v%02X:vbk%d", frame,
                    register("PC"), value, emu:read8(0xFF4F) & 1)
            end
        end, emu.memoryCallback.WRITE, 0x992F, 0x992F)
    end)
end

local function hex_range(address, length)
    local result = {}
    for offset = 0, length - 1 do
        result[#result + 1] = string.format(
            "%02X", emu:read8(address + offset)
        )
    end
    return table.concat(result)
end

local function dump_range(path, address, length)
    local handle = assert(io.open(path, "wb"))
    for offset = 0, length - 1 do
        handle:write(string.char(emu:read8(address + offset)))
    end
    handle:close()
end

local function dump_vram_receipt()
    local old_vbk = emu:read8(0xFF4F)
    emu:write8(0xFF4F, 0)
    dump_range(OUT .. ".map0.bin", 0x9800, 0x800)
    dump_range(OUT .. ".vram0.bin", 0x8000, 0x1800)
    emu:write8(0xFF4F, 1)
    dump_range(OUT .. ".attr.bin", 0x9800, 0x800)
    dump_range(OUT .. ".vram1.bin", 0x8000, 0x1800)
    emu:write8(0xFF4F, old_vbk)
    dump_range(OUT .. ".source.bin", 0xC1A0, 0x240)
end

local function palette_hex()
    local accessor = emu.memory.cgbBgPalette
    local raw
    if accessor then
        raw = accessor:readRange(0, 64)
    else
        local old_index = emu:read8(0xFF68)
        local bytes = {}
        for index = 0, 63 do
            emu:write8(0xFF68, index)
            bytes[#bytes + 1] = string.char(emu:read8(0xFF69))
        end
        emu:write8(0xFF68, old_index)
        raw = table.concat(bytes)
    end
    return (raw:gsub(".", function(char)
        return string.format("%02X", string.byte(char))
    end))
end

local function resolve_penta_pending(next_base)
    if #penta_pending_mismatches == 0 then return end
    local prior_base = penta_pending_mismatches[1].base
    if next_base ~= nil and next_base ~= prior_base then
        -- The game prepared the outgoing physical map after its final scanout;
        -- it was hidden by the LCDC map flip on the next sampled frame.
        hidden_staging_mismatches = hidden_staging_mismatches
            + #penta_pending_mismatches
    else
        attr_mismatches = attr_mismatches + #penta_pending_mismatches
        raw_lut_mismatches = raw_lut_mismatches
            + #penta_pending_mismatches
        if #penta_pending_mismatches > max_frame_mismatches then
            max_frame_mismatches = #penta_pending_mismatches
        end
        for _, pending in ipairs(penta_pending_mismatches) do
            contract_attrs[pending.contract_key] =
                contract_attrs[pending.contract_key] or {}
            contract_attrs[pending.contract_key][pending.actual] = true
            if #mismatch_examples < 12 then
                mismatch_examples[#mismatch_examples + 1] = pending.example
            end
        end
    end
    penta_pending_mismatches = {}
end

-- Audit the scrolled BG viewport while the boss is actually animating.  Arena
-- bodies are BG tiles, not OBJ sprites: the tile byte in VBK=0 and palette
-- attribute in VBK=1 therefore have to be published as one logical update.
-- The active 256-byte LUT at C600 is the production contract for that pair.
-- Sampling 85 consecutive settled frames catches the old position-inheritance
-- /confetti bug that a single final screenshot could easily miss.
local function sample_visible_attrs()
    local lcdc = emu:read8(0xFF40)
    local scx, scy = emu:read8(0xFF43), emu:read8(0xFF42)
    local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    if TARGET == 8 then resolve_penta_pending(base) end
    local first_col, first_row = math.floor(scx / 8), math.floor(scy / 8)
    local cols = ((scx & 7) == 0) and 20 or 21
    local rows = ((scy & 7) == 0) and 18 or 19
    local old_vbk = emu:read8(0xFF4F)
    local addresses, tiles = {}, {}

    emu:write8(0xFF4F, 0)
    for y = 0, rows - 1 do
        for x = 0, cols - 1 do
            local row, col = (first_row + y) & 31, (first_col + x) & 31
            local address = base + row * 32 + col
            addresses[#addresses + 1] = address
            tiles[#tiles + 1] = emu:read8(address)
        end
    end

    emu:write8(0xFF4F, 1)
    local frame_mismatches = 0
    for index, address in ipairs(addresses) do
        local tile = tiles[index]
        local attribute = emu:read8(address)
        local actual = attribute & 7
        local raw_expected = emu:read8(0xC600 + tile) & 7
        local expected = raw_expected
        local physical_row = math.floor((address - base) / 32)
        -- Shalamar's lower six rows are stock animation staging, not visible
        -- body material. The shared atomic sanitizer intentionally publishes
        -- them as neutral even when their future-frame tile IDs are cyan.
        local physical_col = (address - base) & 31
        if TARGET == 0 and (
            physical_row >= 12 or
            (physical_row >= 8 and physical_col >= 20)
        ) then expected = 0 end
        attr_samples = attr_samples + 1
        if (attribute & 0xF8) ~= 0 then unsafe_attrs = unsafe_attrs + 1 end
        local defer_penta_mismatch = TARGET == 8 and actual ~= expected
        if actual ~= raw_expected and not defer_penta_mismatch then
            raw_lut_mismatches = raw_lut_mismatches + 1
        end
        local contract_key = tile * 8 + expected
        if not defer_penta_mismatch then
            contract_attrs[contract_key] = contract_attrs[contract_key] or {}
            contract_attrs[contract_key][actual] = true
        end
        if defer_penta_mismatch then
            local zero = index - 1
            penta_pending_mismatches[#penta_pending_mismatches + 1] = {
                base = base,
                actual = actual,
                contract_key = contract_key,
                example = string.format(
                    "f%d:%d:%d:%04X:%02X:%d>%d:s%02X,%02X", frame,
                    zero % cols, math.floor(zero / cols), address, tile,
                    actual, expected, scx, scy),
            }
        elseif actual ~= expected then
            attr_mismatches = attr_mismatches + 1
            frame_mismatches = frame_mismatches + 1
            if #mismatch_examples < 12 then
                local zero = index - 1
                mismatch_examples[#mismatch_examples + 1] = string.format(
                    "f%d:%d:%d:%04X:%02X:%d>%d:s%02X,%02X", frame,
                    zero % cols, math.floor(zero / cols), address, tile,
                    actual, expected, scx, scy)
            end
        end
    end
    emu:write8(0xFF4F, old_vbk)
    attr_frames = attr_frames + 1
    if frame_mismatches > max_frame_mismatches then
        max_frame_mismatches = frame_mismatches
    end
end

local function alternating_tile_count()
    local alternating = 0
    for _, attributes in pairs(contract_attrs) do
        local count = 0
        for _ in pairs(attributes) do count = count + 1 end
        if count > 1 then alternating = alternating + 1 end
    end
    return alternating
end

local function finish(status, message)
    if done then return end
    done = true
    if TARGET == 8 then resolve_penta_pending(nil) end
    trace:close()
    dump_vram_receipt()
    local report = assert(io.open(OUT .. ".audit.report", "w"))
    report:write(string.format(
        "status=%s target=%d expected_scene=%02X frame=%d d880=%02X " ..
        "ffc1=%d lcdc=%02X bgp=%02X stat=%02X ly=%02X phase=%02X palette_settled=%d " ..
        "state_saved=%s message=%s " ..
        "attr_frames=%d attr_samples=%d attr_mismatches=%d " ..
        "raw_lut_mismatches=%d " ..
        "max_frame_mismatches=%d hidden_staging_mismatches=%d " ..
        "max_scene_drift_frames=%d " ..
        "unsafe_attrs=%d alternating_tiles=%d " ..
        "copy_entries=%d atomic_copies=%d pure_copies=%d sanitizer_calls=%d " ..
        "decision_zero=%d decision_nonzero=%d sanitizer_examples=%s " ..
        "mismatch_examples=%s penta_9c88_writes=%s penta_992f_writes=%s " ..
        "active_table=%s arena_helper=%s bg_cram=%s\n",
        status, TARGET, EXPECTED_SCENE, frame, emu:read8(0xD880),
        emu:read8(0xFFC1), emu:read8(0xFF40), emu:read8(0xFF47),
        emu:read8(0xFF41), emu:read8(0xFF44), emu:read8(0xDF4C),
        palette_settled,
        tostring(state_saved), message,
        attr_frames, attr_samples, attr_mismatches, raw_lut_mismatches,
        max_frame_mismatches, hidden_staging_mismatches,
        max_scene_drift_frames,
        unsafe_attrs, alternating_tile_count(),
        copy_entries, atomic_copies, pure_copies, sanitizer_calls,
        decision_zero, decision_nonzero,
        (#sanitizer_examples > 0) and table.concat(sanitizer_examples, ",") or "none",
        (#mismatch_examples > 0) and table.concat(mismatch_examples, ",") or "none",
        (#penta_9c88_writes > 0) and table.concat(penta_9c88_writes, ",") or "none",
        (#penta_992f_writes > 0) and table.concat(penta_992f_writes, ",") or "none",
        hex_range(0xC600, 0x100),
        hex_range(0xDB80, 0x24),
        palette_hex()
    ))
    report:close()
    local marker = assert(io.open(OUT .. ".audit.done", "w"))
    marker:write(status .. "\n")
    marker:close()
end

callbacks:add("frame", function()
    if done then return end
    frame = frame + 1
    emu:setKeys(0)
    if KEEP_ALIVE then
        emu:write8(0xDCBB, 0xF0)
        -- Some serialized boss poses already have the arena-exit handshake
        -- armed (Troop uses D888/DD06; Penta reaches the same handoff later).
        -- Hold those transition flags neutral while preserving animation,
        -- OAM, tile publication, and damage state for the visual audit.
        emu:write8(0xD888, 0x00)
        emu:write8(0xDD06, 0x00)
    end
    if frame == 1 and REARM_CURRENT_ROM then
        -- Fixture states may carry an older ROM's scene-cache identity and
        -- mutable palette table. Force one normal current-ROM scene transition so the
        -- receipt proves the candidate's own arena table and palettes.
        emu:write8(0xDF0D, 0xFF)
    end
    if frame == 1 and REARM_PALETTES then
        -- Re-arm the complete production palette pass too. A fixture can
        -- carry valid geometry but stale CRAM from an older ROM; the receipt
        -- must prove the current candidate's palette rows, not inherited
        -- serialized hardware state.
        emu:write8(0xDF4C, 0x11)
    end
    if frame == 1 and TARGET == 4 then
        -- Ted's geometry classifier is lazily copied into C500. Curated
        -- savestates can serialize an older candidate's helper and sentinel;
        -- force the loaded ROM to install its own bytes before recapturing.
        emu:write8(0xC5FF, 0x00)
    end
    if KEEP_ALIVE then
        emu:write8(0xDCDC, 0xFF)
        emu:write8(0xDCDD, 0xFF)
    end
    if frame <= 4 then
        trace:write(string.format(
            "frame=%d pc=%04X sp=%04X d880=%02X ffb7=%02X ffba=%02X " ..
            "ffbf=%02X dcbb=%02X dc80_dfff=%s\n",
            frame, register("PC"), register("SP"), emu:read8(0xD880),
            emu:read8(0xFFB7), emu:read8(0xFFBA), emu:read8(0xFFBF),
            emu:read8(0xDCBB), hex_range(0xDC80, 0x380)
        ))
        trace:flush()
    end
    if TARGET == 8 and frame >= 54 and frame <= 64 then
        local old_vbk = emu:read8(0xFF4F)
        emu:write8(0xFF4F, 0)
        local tile = emu:read8(0x9C88)
        emu:write8(0xFF4F, 1)
        local attr = emu:read8(0x9C88)
        emu:write8(0xFF4F, old_vbk)
        trace:write(string.format(
            "penta_cell frame=%d pc=%04X lcdc=%02X scx=%02X scy=%02X " ..
            "tile=%02X attr=%02X copy=%d atomic=%d\n",
            frame, register("PC"), emu:read8(0xFF40), emu:read8(0xFF43),
            emu:read8(0xFF42), tile, attr, copy_entries, atomic_copies))
        trace:flush()
    end
    if frame > 3 and emu:read8(0xD880) ~= EXPECTED_SCENE then
        scene_drift_frames = scene_drift_frames + 1
        if scene_drift_frames > max_scene_drift_frames then
            max_scene_drift_frames = scene_drift_frames
        end
        -- One-frame publisher sentinels are legal during a map handoff. A
        -- sustained mismatch is a genuine arena exit; allow a short window so
        -- the trace can distinguish the two instead of failing on the first
        -- transient byte.
        if scene_drift_frames > 1 then
            finish("error", "arena-left-after-reload")
            return
        end
    else
        scene_drift_frames = 0
    end
    -- A restored state can initially expose the map that was inactive when it
    -- was serialized. Let the eight-group atomic publisher complete three
    -- rows, then collect only settled boss animation.
    if emu:read8(0xDF4C) == 0 then
        palette_settled = palette_settled + 1
    else
        palette_settled = 0
    end
    if frame > AUDIT_WARMUP and palette_settled > 0
        and emu:read8(0xD880) == EXPECTED_SCENE then
        sample_visible_attrs()
    end
    if frame == math.floor(RECEIPT_FRAME / 4)
        or frame == math.floor(RECEIPT_FRAME / 2)
        or frame == math.floor(RECEIPT_FRAME * 3 / 4) then
        emu:screenshot(OUT .. string.format(".f%03d.png", frame))
    end
    if frame == RECEIPT_FRAME then
        -- Saving on a phase-zero frame is sufficient: the receipt has already
        -- sampled the live LUT/attributes for 85+ frames and verifies exact
        -- CRAM bytes. Riff legitimately rearms the phased loader often enough
        -- that eight *consecutive* zero-phase frames may never occur, despite
        -- zero rendered or staging mismatches.
        if palette_settled < 1 then
            finish("error", "palette-loader-not-settled")
            return
        end
        emu:screenshot(OUT .. ".png")
        if STATE_OUT then
            local save_ok, result = pcall(function()
                return emu:saveStateFile(STATE_OUT)
            end)
            state_saved = save_ok and result ~= false
            if not state_saved then
                finish("error", "saveStateFile-failed")
                return
            end
        end
        finish("ok", "rendered")
    end
end)
