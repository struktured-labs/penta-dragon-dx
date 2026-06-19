-- Probe iter 43 v3.01 ROM: dump HW OAM slots 0-3 across frames 50-70
local frame_count = 0
local fh = io.open("/tmp/v301_iter43_slots.txt", "w")

callbacks:add("frame", function()
    frame_count = frame_count + 1
    if frame_count >= 50 and frame_count <= 72 then
        local raw = emu.memory.oam:readRange(0, 0x10)
        fh:write(string.format("f%d slot0 attr=0x%02X tile=0x%02X | slot1 attr=0x%02X tile=0x%02X | slot2 attr=0x%02X tile=0x%02X | slot3 attr=0x%02X tile=0x%02X\n",
            frame_count,
            raw:byte(4), raw:byte(3),
            raw:byte(8), raw:byte(7),
            raw:byte(12), raw:byte(11),
            raw:byte(16), raw:byte(15)))
    end
    if frame_count == 80 then
        -- Also dump WRAM stub at 0xDB50 to verify it was installed
        fh:write("WRAM 0xDB50 first 16 bytes: ")
        for i = 0, 15 do
            fh:write(string.format("%02X ", emu:read8(0xDB50 + i)))
        end
        fh:write("\n")
        fh:write(string.format("Sentinel DF03 = 0x%02X (expect 0x5A)\n", emu:read8(0xDF03)))
        fh:close()
        emu:stop()
    end
end)
