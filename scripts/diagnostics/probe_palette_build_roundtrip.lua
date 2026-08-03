-- Prove tuned YAML palettes survive the title-safe boot mask and that Stage 1
-- selects its independently tuned hazard BG7 after GAME START.

local OUT = os.getenv("PENTA_ROUNDTRIP_OUT")
    or "/tmp/penta-palette-build-roundtrip"
local MAX_FRAMES = tonumber(
    os.getenv("PENTA_ROUNDTRIP_MAX_FRAMES") or "2000"
)
local KEY_DOWN, KEY_A, KEY_START = 0x80, 0x01, 0x08

local function parse_bytes(name)
    local result = {}
    local raw = assert(os.getenv(name), name .. " is required")
    for byte in string.gmatch(raw, "[^,]+") do
        table.insert(result, tonumber(byte, 16))
    end
    assert(#result == 8, name .. " must contain eight bytes")
    return result
end

local EXPECTED_BG0 = parse_bytes("PENTA_EXPECTED_BG0")
local EXPECTED_BG7 = parse_bytes("PENTA_EXPECTED_BG7")
local EXPECTED_OBJ2 = parse_bytes("PENTA_EXPECTED_OBJ2")

local function read_palette(index_register, data_register, slot)
    local result = {}
    local old_index = emu:read8(index_register)
    for offset = 0, 7 do
        emu:write8(index_register, slot * 8 + offset)
        result[offset + 1] = emu:read8(data_register)
    end
    emu:write8(index_register, old_index)
    return result
end

local function equal(left, right)
    for index = 1, 8 do
        if left[index] ~= right[index] then return false end
    end
    return true
end

local function encode(values)
    local result = {}
    for index = 1, 8 do
        table.insert(result, string.format("%02X", values[index]))
    end
    return table.concat(result, ",")
end

local function scheduled_keys(frame)
    local schedule = {
        {180, 185, KEY_DOWN},
        {201, 206, KEY_A},
        {261, 266, KEY_A},
        {321, 326, KEY_A},
        {381, 386, KEY_START},
        {431, 436, KEY_A},
    }
    for _, entry in ipairs(schedule) do
        if frame >= entry[1] and frame <= entry[2] then
            return entry[3]
        end
    end
    return 0
end

local frame = 0
local title_checked = false
local title_bg0, title_bg7
local gameplay_at = -1
local finished = false
local phase_trace = {}
local last_phase_signature = ""

local function finish(status, message, gameplay_bg0, gameplay_bg7, gameplay_obj2)
    if finished then return end
    finished = true
    local report = assert(io.open(OUT .. ".report", "w"))
    report:write(string.format("status=%s\n", status))
    report:write(string.format("message=%s\n", message))
    report:write(string.format("frame=%d\n", frame))
    report:write(string.format("d880=%02X\n", emu:read8(0xD880)))
    report:write(string.format("ffc1=%d\n", emu:read8(0xFFC1)))
    report:write(string.format("df00=%02X\n", emu:read8(0xDF00)))
    report:write(string.format("df02=%02X\n", emu:read8(0xDF02)))
    report:write(string.format("df4c=%02X\n", emu:read8(0xDF4C)))
    report:write("phase_trace=" .. table.concat(phase_trace, ";") .. "\n")
    report:write(string.format(
        "title_bg0_match=%d\n",
        title_bg0 and equal(title_bg0, EXPECTED_BG0) and 1 or 0
    ))
    report:write(string.format(
        "title_bg7_masked=%d\n",
        title_bg7 and equal(title_bg7, EXPECTED_BG0) and 1 or 0
    ))
    report:write(string.format(
        "gameplay_bg0_match=%d\n",
        gameplay_bg0 and equal(gameplay_bg0, EXPECTED_BG0) and 1 or 0
    ))
    report:write(string.format(
        "gameplay_bg7_match=%d\n",
        gameplay_bg7 and equal(gameplay_bg7, EXPECTED_BG7) and 1 or 0
    ))
    report:write(string.format(
        "gameplay_obj2_match=%d\n",
        gameplay_obj2 and equal(gameplay_obj2, EXPECTED_OBJ2) and 1 or 0
    ))
    report:write("title_bg0=" .. (title_bg0 and encode(title_bg0) or "") .. "\n")
    report:write("title_bg7=" .. (title_bg7 and encode(title_bg7) or "") .. "\n")
    report:write(
        "gameplay_bg7="
        .. (gameplay_bg7 and encode(gameplay_bg7) or "")
        .. "\n"
    )
    report:write(
        "gameplay_obj2="
        .. (gameplay_obj2 and encode(gameplay_obj2) or "")
        .. "\n"
    )
    report:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(status .. "\n")
    marker:close()
end

callbacks:add("frame", function()
    if finished then return end
    frame = frame + 1
    emu:setKeys(scheduled_keys(frame))

    local scene = emu:read8(0xD880)
    local gameplay = emu:read8(0xFFC1)
    local phase_signature = string.format(
        "%02X/%d/%02X/%02X/%02X",
        scene, gameplay, emu:read8(0xDF00), emu:read8(0xDF02),
        emu:read8(0xDF4C)
    )
    if phase_signature ~= last_phase_signature then
        table.insert(
            phase_trace,
            string.format("f%d:%s", frame, phase_signature)
        )
        last_phase_signature = phase_signature
    end
    if not title_checked and frame >= 150 and scene == 0x01 and gameplay == 0 then
        title_bg0 = read_palette(0xFF68, 0xFF69, 0)
        title_bg7 = read_palette(0xFF68, 0xFF69, 7)
        title_checked = true
    end

    if scene == 0x02 and gameplay == 1 and gameplay_at < 0 then
        gameplay_at = frame
    end
    if gameplay_at > 0 and frame >= gameplay_at + 60 then
        local gameplay_bg0 = read_palette(0xFF68, 0xFF69, 0)
        local gameplay_bg7 = read_palette(0xFF68, 0xFF69, 7)
        local gameplay_obj2 = read_palette(0xFF6A, 0xFF6B, 2)
        local clean = (
            title_checked
            and equal(title_bg0, EXPECTED_BG0)
            and equal(title_bg7, EXPECTED_BG0)
            and equal(gameplay_bg0, EXPECTED_BG0)
            and equal(gameplay_bg7, EXPECTED_BG7)
            and equal(gameplay_obj2, EXPECTED_OBJ2)
        )
        finish(
            clean and "ok" or "failed",
            "title-mask-to-stage1-hazard-roundtrip",
            gameplay_bg0,
            gameplay_bg7,
            gameplay_obj2
        )
        return
    end

    if frame >= MAX_FRAMES then
        finish("failed", "timeout", nil, nil, nil)
    end
end)
