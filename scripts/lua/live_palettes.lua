-- Test if we can poll a file and inject CRAM in real time
local f = 0
local last_mtime = 0
local PAL_FILE = os.getenv("PAL_FILE") or "/tmp/live_palettes.txt"

local function parse_color(s)
    -- Parse "RRGGBB" hex (6 chars) or 4-digit BGR555 hex
    if #s == 6 then
        local r = tonumber(s:sub(1,2), 16) or 0
        local g = tonumber(s:sub(3,4), 16) or 0
        local b = tonumber(s:sub(5,6), 16) or 0
        local r5 = math.floor(r * 31 / 255)
        local g5 = math.floor(g * 31 / 255)
        local b5 = math.floor(b * 31 / 255)
        return (b5 << 10) | (g5 << 5) | r5
    elseif #s == 4 then
        return tonumber(s, 16) or 0
    end
    return 0
end

local function load_palettes(path)
    local fh = io.open(path, "r")
    if not fh then return nil end
    local txt = fh:read("*all")
    fh:close()

    local writes = {}
    -- Lines format: "BG0:0=7FFF,1=7E94,2=3D4A,3=0000"
    --               "OBJ1:0=0000,1=03E0,2=01C0,3=0000"
    for line in txt:gmatch("[^\r\n]+") do
        local kind, pal_idx, colors = line:match("^(BG?O?B?J?)(%d):(.+)$")
        if not kind then
            kind, pal_idx, colors = line:match("^([BO][GJ]B?)(%d):(.+)$")
        end
        if kind and pal_idx then
            local is_obj = kind:sub(1,1) == "O"
            pal_idx = tonumber(pal_idx)
            local color_idx_max = -1
            for entry in colors:gmatch("[^,]+") do
                local ci, cv = entry:match("^%s*(%d+)=(%w+)%s*$")
                if ci and cv then
                    ci = tonumber(ci)
                    local val15 = parse_color(cv)
                    -- CRAM byte index: pal*8 + color*2 (lo), +1 (hi)
                    local base = pal_idx * 8 + ci * 2
                    table.insert(writes, {
                        is_obj = is_obj,
                        idx = base,
                        lo = val15 & 0xFF,
                        hi = (val15 >> 8) & 0xFF,
                    })
                end
            end
        end
    end
    return writes
end

local function apply_writes(writes)
    if not writes or #writes == 0 then return end
    for _, w in ipairs(writes) do
        if w.is_obj then
            emu:write8(0xFF6A, w.idx)
            emu:write8(0xFF6B, w.lo)
            emu:write8(0xFF6A, w.idx + 1)
            emu:write8(0xFF6B, w.hi)
        else
            emu:write8(0xFF68, w.idx)
            emu:write8(0xFF69, w.lo)
            emu:write8(0xFF68, w.idx + 1)
            emu:write8(0xFF69, w.hi)
        end
    end
end

callbacks:add("frame", function()
    f = f + 1
    -- Poll file mtime every 30 frames (~0.5 sec)
    if f % 30 == 0 then
        local fh = io.open(PAL_FILE, "r")
        if fh then
            -- io.open doesn't give us mtime, but we can read+hash content
            local content = fh:read("*all")
            fh:close()
            local hash = 0
            for i = 1, #content do
                hash = (hash * 31 + content:byte(i)) & 0xFFFFFFFF
            end
            if hash ~= last_mtime then
                last_mtime = hash
                local writes = load_palettes(PAL_FILE)
                if writes then
                    apply_writes(writes)
                    print(string.format("Applied %d palette writes from %s", #writes, PAL_FILE))
                end
            end
        end
    end
end)
