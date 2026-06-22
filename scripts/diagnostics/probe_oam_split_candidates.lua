-- iter 160: identify split-prone OAM slots (multi-tile enemies whose
-- tiles cross hwoam_recolor's tile-range palette buckets).
--
-- Outputs adjacency analysis at f=300. SPLIT lines flag slot pairs
-- that are visually close (dx<=8, dy<=16) AND have tiles in different
-- range buckets, which would render with different palettes when
-- hwoam_recolor B=40 stamps them.
--
-- Caveat: dx<=8 dy<=16 is a loose adjacency filter — produces false
-- positives for two distinct sprites that happen to overlap (e.g.
-- Sara's blue projectile passing through an orange Hornet at the same
-- X,Y). For a strict same-sprite check, filter to dx EXACTLY 8 and
-- dy EXACTLY 0 (the typical 8x16-mode horizontal split).
--
-- Usage:
--   OUT=tmp/oam_split.log xvfb-run -a mgba-qt ROM -t SAVESTATE.ss0 \
--     --script scripts/diagnostics/probe_oam_split_candidates.lua -l 0
-- (defaults to /tmp/oam_split.log if OUT env var unset)

-- Dump OAM at f=300 + report adjacent-slot tile ranges (potential split spots)
local OUT = os.getenv("OUT") or "/tmp/oam_split.log"
local frame = 0
callbacks:add("frame", function()
    frame = frame + 1
    if frame == 300 then
        local h = io.open(OUT, "w")
        if h then
            h:write("OAM dump at f=300:\n")
            h:write("slot |  X  |  Y  | tile | attr | pal\n")
            local oam = {}
            for slot = 0, 39 do
                local base = 0xFE00 + slot * 4
                local y = emu:read8(base)
                local x = emu:read8(base + 1)
                local tile = emu:read8(base + 2)
                local attr = emu:read8(base + 3)
                local pal = attr & 7
                oam[slot] = {y=y, x=x, tile=tile, attr=attr, pal=pal}
                if y ~= 0 or x ~= 0 then  -- only show active slots
                    h:write(string.format("  %2d | %3d | %3d | 0x%02X | 0x%02X | %d\n",
                        slot, x, y, tile, attr, pal))
                end
            end
            -- Find adjacent OAM slots that share an X/Y region (multi-tile sprite)
            -- and check if their tiles cross a tile-range boundary
            h:write("\nADJACENCY ANALYSIS:\n")
            local boundaries = {0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80}
            local function get_range(t)
                if t < 0x10 then return "0x00-0x0F" end
                if t < 0x20 then return "0x10-0x1F" end
                if t < 0x30 then return "0x20-0x2F" end
                if t < 0x40 then return "0x30-0x3F" end
                if t < 0x50 then return "0x40-0x4F" end
                if t < 0x60 then return "0x50-0x5F" end
                if t < 0x70 then return "0x60-0x6F" end
                if t < 0x80 then return "0x70-0x7F" end
                return "0x80+"
            end
            for a = 0, 38 do
                if oam[a].y ~= 0 then
                    for b = a + 1, 39 do
                        if oam[b].y ~= 0 then
                            -- Check if visually adjacent: same y or y+/-16, x within 8 px
                            local dx = math.abs(oam[a].x - oam[b].x)
                            local dy = math.abs(oam[a].y - oam[b].y)
                            if dx <= 8 and dy <= 16 then
                                if get_range(oam[a].tile) ~= get_range(oam[b].tile) then
                                    h:write(string.format("SPLIT: slot %d (tile 0x%02X %s) ↔ slot %d (tile 0x%02X %s) — dx=%d dy=%d\n",
                                        a, oam[a].tile, get_range(oam[a].tile),
                                        b, oam[b].tile, get_range(oam[b].tile), dx, dy))
                                end
                            end
                        end
                    end
                end
            end
            h:close()
        end
        emu:stop()
    end
end)
