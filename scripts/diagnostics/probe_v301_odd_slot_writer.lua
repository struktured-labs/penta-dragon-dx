-- v3.01 odd-slot probe. After iter 34's partial backport (hwoam_recolor only,
-- no STAT-IRQ WRAM stub), Sara slots 0/2/4/6 read pal 2 but slots 1/3/5/7
-- read pal 4. Theory: STAT IRQ base-game chain at 0x0853 writes pal 4 to
-- odd HW OAM slots. Verify by:
--   (a) Poison slot 1 attr to 0xAB at frame N, watch it drift.
--   (b) Track all CPU writes to 0xFE07 (slot 1 attr).
local frame_count = 0
local fh = io.open("/tmp/v301_oddslot.txt", "w")
local writes = {}

callbacks:add("write", function(addr, val)
    if addr == 0xFE07 or addr == 0xFE03 then
        table.insert(writes, string.format("f%d 0x%04X=0x%02X", frame_count, addr, val))
        if #writes > 80 then table.remove(writes, 1) end
    end
end)

callbacks:add("frame", function()
    frame_count = frame_count + 1
    if frame_count == 30 then
        -- Snapshot pre-poison
        local raw = emu.memory.oam:readRange(0, 0x10)
        fh:write(string.format("f30 pre-poison: slot0 attr=0x%02X, slot1 attr=0x%02X\n",
            raw:byte(4), raw:byte(8)))
        -- Poison slot 1 attr to 0xAB
        emu:write8(0xFE07, 0xAB)
        fh:write("f30: wrote 0xAB to 0xFE07\n")
    end
    if frame_count == 31 or frame_count == 32 or frame_count == 35 or frame_count == 40 then
        local raw = emu.memory.oam:readRange(0, 0x10)
        fh:write(string.format("f%d: slot0 attr=0x%02X, slot1 attr=0x%02X, slot2 attr=0x%02X, slot3 attr=0x%02X\n",
            frame_count, raw:byte(4), raw:byte(8), raw:byte(12), raw:byte(16)))
    end
    if frame_count == 60 then
        local raw = emu.memory.oam:readRange(0, 0x10)
        fh:write(string.format("f60 final: slot0 attr=0x%02X, slot1 attr=0x%02X, slot2 attr=0x%02X, slot3 attr=0x%02X\n",
            raw:byte(4), raw:byte(8), raw:byte(12), raw:byte(16)))
        fh:write("\n=== recent CPU writes to slot 0/1 attr ===\n")
        for _, w in ipairs(writes) do
            fh:write(w .. "\n")
        end
        fh:close()
        emu:stop()
    end
end)
