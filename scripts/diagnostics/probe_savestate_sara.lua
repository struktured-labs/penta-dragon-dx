-- Probe a savestate: dump Sara slots 0-3 pal + scene state at frame 68.
-- Args via env: PROBE_OUT (output JSON path)
local frame_count = 0
local OUT = os.getenv("PROBE_OUT") or "/tmp/probe_savestate.json"
callbacks:add("frame", function()
    frame_count = frame_count + 1
    if frame_count == 68 then
        local raw = emu.memory.oam:readRange(0, 0x10)
        local function pal(off)
            return raw:byte(off + 4) & 0x07
        end
        local function tile(off)
            return raw:byte(off + 3)
        end
        local f = io.open(OUT, "w")
        if f then
            f:write(string.format(
                '{"d880":%d,"ffba":%d,"ffbe":%d,"ffbf":%d,"ffc1":%d,"df1f":%d,' ..
                '"slot0":{"tile":%d,"pal":%d},"slot1":{"tile":%d,"pal":%d},' ..
                '"slot2":{"tile":%d,"pal":%d},"slot3":{"tile":%d,"pal":%d}}',
                emu:read8(0xD880), emu:read8(0xFFBA), emu:read8(0xFFBE),
                emu:read8(0xFFBF), emu:read8(0xFFC1), emu:read8(0xDF1F),
                tile(0), pal(0), tile(4), pal(4),
                tile(8), pal(8), tile(12), pal(12)
            ))
            f:close()
        end
        emu:stop()
    end
end)
