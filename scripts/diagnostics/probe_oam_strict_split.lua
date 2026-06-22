-- Strict same-sprite-split detector: only flag slot pairs where
-- dx==8 dy==0 (true 8x16-mode horizontal pair) AND tiles in DIFFERENT
-- palette-range buckets. Tile T and T+1 of a 16x16 sprite should always
-- be in the same bucket; if not, that's a real split.
local OUT = os.getenv("OUT") or "/tmp/strict_split.log"
local frame = 0
callbacks:add("frame", function()
    frame = frame + 1
    if frame == 300 then
        local h = io.open(OUT, "w")
        if h then
            local oam = {}
            for slot = 0, 39 do
                local base = 0xFE00 + slot * 4
                oam[slot] = {
                    y = emu:read8(base), x = emu:read8(base + 1),
                    tile = emu:read8(base + 2),
                }
            end
            local function get_bucket(t)
                if t < 0x10 then return "00-0F" end
                if t < 0x20 then return "10-1F" end
                if t < 0x30 then return "20-2F" end
                if t < 0x40 then return "30-3F" end
                if t < 0x50 then return "40-4F" end
                if t < 0x60 then return "50-5F" end
                if t < 0x70 then return "60-6F" end
                if t < 0x80 then return "70-7F" end
                return "80+"
            end
            -- Only CONSECUTIVE OAM slots count as same-sprite pairs:
            -- a real 16x16 sprite in 8x16 mode uses slots N and N+1 at
            -- positions (X, Y) and (X+8, Y), with tiles T and T+1.
            h:write("STRICT same-sprite splits (consecutive slots, dx==8 dy==0):\n")
            local n_splits = 0
            for a = 0, 38 do
                local b = a + 1
                if oam[a].y ~= 0 and oam[b].y ~= 0
                        and oam[b].x == oam[a].x + 8
                        and oam[b].y == oam[a].y then
                    local ba = get_bucket(oam[a].tile)
                    local bb = get_bucket(oam[b].tile)
                    if ba ~= bb then
                        h:write(string.format(
                            "REAL SPLIT: slot %d (X=%d Y=%d tile=0x%02X %s) → slot %d (tile=0x%02X %s)\n",
                            a, oam[a].x, oam[a].y, oam[a].tile, ba,
                            b, oam[b].tile, bb))
                        n_splits = n_splits + 1
                    end
                end
            end
            h:write(string.format("\nTotal strict splits (consecutive): %d\n", n_splits))
            h:close()
        end
        emu:stop()
    end
end)
