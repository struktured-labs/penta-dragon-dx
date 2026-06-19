-- Probe a savestate at frame 68: report all OAM slots with tile in 0x10-0x1F.
-- These are Sara's secondary body sprites per audit (Y=79-87, X=93/101). With
-- iter 31's tile remap, they should be pal D (Sara form palette).
local frame_count = 0
local OUT = os.getenv("PROBE_OUT") or "/tmp/secondary_tiles.json"

callbacks:add("frame", function()
    frame_count = frame_count + 1
    if frame_count == 68 then
        local raw = emu.memory.oam:readRange(0, 0xA0)
        local hits = {}
        for i = 0, 39 do
            local off = i * 4 + 1
            local y = raw:byte(off)
            local x = raw:byte(off + 1)
            local tile = raw:byte(off + 2)
            local pal = raw:byte(off + 3) & 0x07
            local visible = (y > 0 and y < 160 and x > 0 and x < 168)
            if visible and tile >= 0x10 and tile <= 0x1F then
                table.insert(hits, string.format(
                    '{"slot":%d,"tile":%d,"pal":%d,"x":%d,"y":%d}', i, tile, pal, x, y))
            end
        end
        local f = io.open(OUT, "w")
        f:write('{"ffbe":' .. emu:read8(0xFFBE) ..
                ',"d880":' .. emu:read8(0xD880) ..
                ',"hits":[' .. table.concat(hits, ",") .. ']}')
        f:close()
        emu:stop()
    end
end)
