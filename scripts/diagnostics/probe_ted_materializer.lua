-- Read results produced by the savestate-injected Ted materializer harness.
local OUT = assert(os.getenv("TED_MATERIALIZER_OUT"))
local RESULTS, MARKER = 0xCC00, 0xCD00
local frames = 0

callbacks:add("frame", function()
    frames = frames + 1
    if emu:read8(MARKER) ~= 0xA5 then
        if frames >= 30 then
            local done = assert(io.open(OUT .. ".done", "w"))
            done:write("status=timeout\n")
            done:close()
            emu:stop()
        end
        return
    end
    local out = assert(io.open(OUT, "w"))
    for test = 0, 31 do
        local base = RESULTS + test * 3
        out:write(string.format("%d %02X %02X %02X\n", test,
            emu:read8(base), emu:read8(base + 1), emu:read8(base + 2)))
    end
    out:close()
    local done = assert(io.open(OUT .. ".done", "w"))
    done:write("status=ok tests=32\n")
    done:close()
    emu:stop()
end)
