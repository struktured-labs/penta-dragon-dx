-- Round 7: CGB boot palette trace + entity AI table comparison (gargoyle vs boss 16)
local OUT_DIR = "/home/struktured/projects/penta-dragon-dx-claude/tmp/probes/"
local frame = 0
local results = {bg_palette={}, obj_palette={}, palette_ram={}, ai_compare={}}

local function r8(a) return emu:read8(a) end
local function w8(a, v) emu:write8(a, v) end
local function rom_w8(a, v) emu.memory.cart0:write8(a, v) end

local function logf(name, txt)
    local f = io.open(OUT_DIR .. name, "a")
    if f then f:write(txt .. "\n"); f:close() end
end

-- Capture initial palette RAM via BCPS auto-increment read
-- BCPS = FF68, BCPD = FF69 (BG palette)
-- OCPS = FF6A, OCPD = FF6B (OBJ palette)
-- 8 palettes × 4 colors × 2 bytes = 64 bytes each

local function read_palette_ram(bcps_reg, bcpd_reg)
    -- Set auto-increment + start at index 0
    w8(bcps_reg, 0x80)
    local out = {}
    for i = 0, 63 do table.insert(out, r8(bcpd_reg)) end
    return out
end

local snapshots_taken = {}

callbacks:add("frame", function()
    frame = frame + 1
    -- Snapshot palette RAM at specific boot frames
    local checkpoints = {1, 5, 10, 30, 60, 100, 200, 400}
    for _, cp in ipairs(checkpoints) do
        if frame == cp and not snapshots_taken[cp] then
            snapshots_taken[cp] = true
            results.palette_ram["bg_f"..cp] = read_palette_ram(0xFF68, 0xFF69)
            results.palette_ram["obj_f"..cp] = read_palette_ram(0xFF6A, 0xFF6B)
            results.palette_ram["meta_f"..cp] = {
                BCPS=r8(0xFF68), BGP=r8(0xFF47), LCDC=r8(0xFF40),
                D880=r8(0xD880), FFC1=r8(0xFFC1), FF99=r8(0xFF99)
            }
            logf("trace7.txt", string.format("snapshot at f=%d D880=0x%02X FFC1=0x%02X", cp, r8(0xD880), r8(0xFFC1)))
        end
    end
    if frame == 410 then
        -- Compare entity AI table entries gargoyle vs boss 16
        results.ai_compare.gargoyle_entry_1 = {} -- entry 1 (FFBF=1 = gargoyle, idx 0)
        results.ai_compare.boss16_entry_16 = {}
        -- Table base 0x2C8F, entry size 16
        -- FFBF=1 → entry 0 → 0x2C8F
        -- FFBF=16 → entry 15 → 0x2C8F + 15*16 = 0x2D7F
        for i = 0, 15 do
            results.ai_compare.gargoyle_entry_1[i+1] = emu.memory.cart0:read8(0x2C8F + i)
            results.ai_compare.boss16_entry_16[i+1] = emu.memory.cart0:read8(0x2D7F + i)
        end
        -- Also compare boss 15 (entry 14) since it's the closest valid
        results.ai_compare.boss15_entry_14 = {}
        for i = 0, 15 do
            results.ai_compare.boss15_entry_14[i+1] = emu.memory.cart0:read8(0x2C8F + 14*16 + i)
        end

        -- Emit JSON
        local function emit(o, ind)
            local pad = string.rep("  ", ind)
            local r = ""
            if type(o) == "table" then
                local is_arr = (#o > 0)
                if is_arr then
                    r = "[\n"
                    for i, v in ipairs(o) do r = r .. pad .. "  " .. emit(v, ind+1) .. (i<#o and "," or "") .. "\n" end
                    r = r .. pad .. "]"
                else
                    r = "{\n"
                    local ks={}
                    for k in pairs(o) do table.insert(ks, k) end
                    table.sort(ks, function(a,b) return tostring(a)<tostring(b) end)
                    for i, k in ipairs(ks) do r = r .. pad .. "  \"" .. tostring(k) .. "\": " .. emit(o[k], ind+1) .. (i<#ks and "," or "") .. "\n" end
                    r = r .. pad .. "}"
                end
            elseif type(o) == "number" then r = tostring(o)
            elseif type(o) == "string" then r = "\"" .. o:gsub('"','\\"') .. "\""
            else r = "null" end
            return r
        end
        local f = io.open(OUT_DIR .. "results7.json", "w")
        if f then f:write(emit(results, 0)); f:write("\n"); f:close() end
        logf("trace7.txt", "ALL DONE")
        os.exit(0)
    end
end)

logf("trace7.txt", "probe7 started")
