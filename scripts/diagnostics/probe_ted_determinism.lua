-- Deterministic full-plane Ted trace. Capture both 32x32 physical BG maps on
-- every consecutive frame; Python owns all interpretation and comparison.

local OUT = assert(os.getenv("TED_DETERMINISM_OUT"))
local FRAMES = tonumber(os.getenv("TED_DETERMINISM_FRAMES") or "900")
-- Serialized boss fixtures can resume just before the inactive-map rebuild.
-- Exclude that fixture-only handoff; all requested samples remain consecutive.
local WARMUP = tonumber(os.getenv("TED_DETERMINISM_WARMUP") or "36")
local SCENE = 0x10
local REINSTALL_RUNTIME = os.getenv("TED_DETERMINISM_REINSTALL") == "1"
local frame, samples, finished = 0, 0, false
local trace = assert(io.open(OUT .. ".bin", "wb"))

local function byte(value) return string.char(value & 0xFF) end

local function sample()
    local old_vbk = emu:read8(0xFF4F)
    trace:write(byte(emu:read8(0xFF40)))
    trace:write(byte(emu:read8(0xFF42)))
    trace:write(byte(emu:read8(0xFF43)))
    trace:write(byte(emu:read8(0xFF91)))
    trace:write(byte(emu:read8(0xC4FA)))
    trace:write(byte(emu:read8(0xC4FB)))
    trace:write(byte(emu:read8(0xDC0B)))
    for _, base in ipairs({0x9800, 0x9C00}) do
        emu:write8(0xFF4F, 0)
        for offset=0,0x3FF do trace:write(byte(emu:read8(base+offset))) end
        emu:write8(0xFF4F, 1)
        for offset=0,0x3FF do
            trace:write(byte(emu:read8(base+offset) & 0x07))
        end
    end
    emu:write8(0xFF4F, old_vbk)
    samples = samples + 1
end

local function finish(status)
    if finished then return end
    finished = true
    trace:close()
    local done = assert(io.open(OUT .. ".done", "w"))
    done:write(string.format("status=%s frames=%d samples=%d scene=%02X\n",
        status, frame, samples, emu:read8(0xD880)))
    done:close()
    emu:stop()
end

callbacks:add("frame", function()
    if finished then return end
    frame = frame + 1
    -- Savestates retain the lazily installed C500 helper from the ROM that
    -- created them. Force the current candidate to reinstall its own runtime
    -- before the next publication; otherwise a byte-identical old WRAM blob
    -- can make materially different ROM candidates produce identical traces.
    if frame == 1 and REINSTALL_RUNTIME then emu:write8(0xC5FF, 0) end
    emu:setKeys(0)
    local svbk = emu:read8(0xFF70) & 0x07
    if svbk ~= 0 and svbk ~= 1 then return end
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    emu:write8(0xD888, 0)
    emu:write8(0xDD06, 0)
    if emu:read8(0xD880) ~= SCENE then finish("wrong-scene"); return end
    if frame > WARMUP then sample() end
    if samples >= FRAMES then finish("ok") end
end)
