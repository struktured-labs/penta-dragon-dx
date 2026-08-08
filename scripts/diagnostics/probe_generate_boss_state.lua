-- Capture one mGBA boss-arena state after native diagnostic entry.
--
-- generate_stream_boss_states.py starts from a real Stage 1 gameplay state.
-- Its throwaway ROM copy enters the game's original boss routine at 0x1A2B;
-- the release ROM is never patched or shipped with navigation code. This Lua
-- side observes the transition, keeps Sara alive, and captures the arena.
--
-- Environment:
--   BOSS_TARGET     0..8 (Shalamar through Penta Dragon)
--   BOSS_STATE_OUT  output .ss0 path
--   BOSS_OUT        output prefix for .report/.png
--   BOSS_STABLE_FRAMES frames to render after the arena appears (default 240)

local TARGET = tonumber(os.getenv("BOSS_TARGET") or "0")
local STATE_OUT = assert(os.getenv("BOSS_STATE_OUT"), "BOSS_STATE_OUT required")
local OUT = os.getenv("BOSS_OUT") or "/tmp/penta-stream-boss"
local STABLE_TARGET = tonumber(os.getenv("BOSS_STABLE_FRAMES") or "240")
local ENTRY_TIMEOUT = tonumber(os.getenv("BOSS_ENTRY_TIMEOUT") or "1200")
local EXPECTED_SCENE = 0x0C + TARGET
local f, reached, stable, done = 0, false, 0, false
local trace = assert(io.open(OUT .. ".trace", "w"))

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

local function hex_range(address, length)
    local result = {}
    for offset = 0, length - 1 do
        result[#result + 1] = string.format(
            "%02X", emu:read8(address + offset)
        )
    end
    return table.concat(result)
end

local function palette_hex(accessor_name, index_port, data_port)
    local accessor = emu.memory[accessor_name]
    local raw
    if accessor then
        raw = accessor:readRange(0, 64)
    else
        local old_index = emu:read8(index_port)
        local bytes = {}
        for index = 0, 63 do
            emu:write8(index_port, index)
            bytes[#bytes + 1] = string.char(emu:read8(data_port))
        end
        emu:write8(index_port, old_index)
        raw = table.concat(bytes)
    end
    return (raw:gsub(".", function(char)
        return string.format("%02X", string.byte(char))
    end))
end

local function finish(status, message)
    if done then return end
    done = true
    trace:close()
    local report = assert(io.open(OUT .. ".report", "w"))
    report:write(string.format(
        "status=%s target=%d expected_scene=%02X frame=%d d880=%02X " ..
        "ffc1=%d ff91=%02X df0d=%02X ffba=%02X ffbf=%02X stable=%d message=%s " ..
        "pc=%04X sp=%04X ie=%02X lcdc=%02X " ..
        "active_table=%s bg_cram=%s\n",
        status, TARGET, EXPECTED_SCENE, f, emu:read8(0xD880),
        emu:read8(0xFFC1), emu:read8(0xFF91), emu:read8(0xDF0D),
        emu:read8(0xFFBA), emu:read8(0xFFBF),
        stable, message, register("PC"), register("SP"),
        emu:read8(0xFFFF), emu:read8(0xFF40),
        hex_range(0xC600, 0x100),
        palette_hex("cgbBgPalette", 0xFF68, 0xFF69)
    ))
    report:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(status .. "\n")
    marker:close()
end

callbacks:add("frame", function()
    if done then return end
    f = f + 1
    emu:setKeys(0)

    -- Keep Sara alive while the arena settles.
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    -- The synthetic Stage-1 dispatcher route can inherit an attack phase that
    -- decrements DCBB before serialization (Troop arms D888/DD06; Ted and
    -- Penta can leave for the splash shortly after reload). Keep every visual
    -- fixture in its arena; boss-exit behavior has a separate death/game-over
    -- gate.
    emu:write8(0xDCBB, 0xF0)

    local scene = emu:read8(0xD880)
    if f <= ENTRY_TIMEOUT and (not reached or stable < 80) then
        trace:write(string.format(
            "frame=%d pc=%04X d880=%02X ff91=%02X df0d=%02X ffb7=%02X ffba=%02X " ..
            "dcbb=%02X d888=%02X dd06=%02X\n",
            f, register("PC"), scene, emu:read8(0xFF91),
            emu:read8(0xDF0D), emu:read8(0xFFB7),
            emu:read8(0xFFBA), emu:read8(0xDCBB),
            emu:read8(0xD888), emu:read8(0xDD06)
        ))
        trace:flush()
    end
    if not reached then
        if scene == EXPECTED_SCENE then
            -- The serialized diagnostic landing waits in Stage 1 before
            -- calling the stock boss dispatcher and can consume the pending
            -- scene transition during that artificial wait. Rearm only after
            -- the dispatcher publishes the real target; the unmodified ROM
            -- then selects and renders its own arena table on the next VBlank.
            emu:write8(0xFF91, 0x01)
            emu:write8(0xDF0D, 0xFF)
            reached = true
        elseif f > ENTRY_TIMEOUT then
            finish("error", "arena-entry-timeout")
            return
        end
    end
    if reached then
        if emu:read8(0xD880) ~= EXPECTED_SCENE then
            finish("error", "arena-left-before-save")
            return
        end
        stable = stable + 1
        if stable == STABLE_TARGET then
            emu:screenshot(OUT .. ".png")
            local save_ok, result = pcall(function()
                return emu:saveStateFile(STATE_OUT)
            end)
            local saved = save_ok and result ~= false
            if not saved then
                finish("error", "saveStateFile-failed")
                return
            end
            finish("ok", "saved")
        end
    end
end)
