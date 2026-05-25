-- Live palette editor — polls /tmp/live_palettes.txt and writes CGB CRAM
local f = 0
local last_hash = 0
local PAL_FILE = "/tmp/live_palettes.txt"
local SENTINEL = "/tmp/live_palettes_lua.log"

-- Log to sentinel file (since mGBA print may not go to stdout)
local function log(msg)
    local fh = io.open(SENTINEL, "a")
    if fh then
        fh:write(msg .. "\n")
        fh:close()
    end
end

-- Reset log on startup
local fh = io.open(SENTINEL, "w")
if fh then fh:write("live_palettes.lua loaded at start\n"); fh:close() end

local function parse_color(s)
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
    for line in txt:gmatch("[^\r\n]+") do
        local kind, pal_idx, colors = line:match("^(OBJ)(%d):(.+)$")
        if not kind then
            kind, pal_idx, colors = line:match("^(BG)(%d):(.+)$")
        end
        if kind and pal_idx then
            local is_obj = kind == "OBJ"
            pal_idx = tonumber(pal_idx)
            for entry in colors:gmatch("[^,]+") do
                local ci, cv = entry:match("^%s*(%d+)=(%w+)%s*$")
                if ci and cv then
                    ci = tonumber(ci)
                    local val15 = parse_color(cv)
                    local base = pal_idx * 8 + ci * 2
                    table.insert(writes, {
                        is_obj = is_obj, idx = base,
                        lo = val15 & 0xFF, hi = (val15 >> 8) & 0xFF,
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

-- Cached parsed writes — applied EVERY frame so the game's cond_pal
-- can't override our changes when it triggers a palette reload on
-- state change (room transition, miniboss spawn, etc.)
local cached_writes = nil

callbacks:add("frame", function()
    f = f + 1
    if f == 30 then log("Lua frame=30, polling /tmp/live_palettes.txt") end

    -- Check for file changes every 30 frames (~0.5s).
    if f % 30 == 0 then
        local fh = io.open(PAL_FILE, "r")
        if fh then
            local content = fh:read("*all")
            fh:close()
            local hash = 0
            for i = 1, #content do
                hash = (hash * 31 + content:byte(i)) & 0xFFFFFFFF
            end
            if hash ~= last_hash then
                last_hash = hash
                cached_writes = load_palettes(PAL_FILE)
                log(string.format("f%d: Loaded %d palette writes from file", f, cached_writes and #cached_writes or 0))
            end
        end
    end

    -- Apply cached writes EVERY frame — this is the override mechanism.
    -- The game's cond_pal calls palette_loader on state changes (room
    -- transition, miniboss spawn, etc.), which would otherwise restore
    -- ROM palettes. Re-applying every frame keeps our edits visible.
    apply_writes(cached_writes)
end)
