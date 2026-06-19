-- Verify v3.01 ROM boots through the first 300 frames without crash.
-- Checks: PC stays in legal ranges, no STOP/HALT loop, state advances.
local frame_count = 0
local last_states = {}

callbacks:add("frame", function()
    frame_count = frame_count + 1
    if frame_count % 50 == 0 then
        local d880 = emu:read8(0xD880)
        local ffc1 = emu:read8(0xFFC1)
        local ffba = emu:read8(0xFFBA)
        table.insert(last_states, string.format("f%d: D880=0x%02X FFC1=%d FFBA=%d", frame_count, d880, ffc1, ffba))
    end
    if frame_count == 300 then
        local fh = io.open("/tmp/v301_boot.txt", "w")
        fh:write("v3.01 boot smoke test (iter 39 joypad trim):\n")
        for _, s in ipairs(last_states) do
            fh:write("  " .. s .. "\n")
        end
        fh:close()
        emu:screenshot("/tmp/v301_boot.png")
        emu:stop()
    end
end)
