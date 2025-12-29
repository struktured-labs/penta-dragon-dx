-- mGBA Lua script to trace boot sequence
local log = io.open("boot_trace.txt", "w")

-- Hook key addresses
emu:setBreakpoint(0x0152, function()
    log:write(string.format("0x0152: About to CALL 0x0067 (VBlank wait)\n"))
    log:flush()
end)

emu:setBreakpoint(0x006D, function()
    local ly = emu:read8(0xFF44)
    log:write(string.format("0x006D: LY check loop, LY=%d\n", ly))
    log:flush()
end)

emu:setBreakpoint(0x0155, function()
    log:write("0x0155: Returned from 0x0067, setting up stack\n")
    log:flush()
end)

emu:setBreakpoint(0x015B, function()
    log:write("0x015B: About to CALL 0x00C8 (LCD on)\n")
    log:flush()
end)

emu:setBreakpoint(0x015E, function()
    log:write("0x015E: Returned from 0x00C8, enabling interrupts\n")
    log:flush()
end)

emu:setBreakpoint(0x015F, function()
    log:write("0x015F: About to enter main loop at 0x3B77\n")
    log:flush()
end)

callbacks:add("frame", function()
    -- Check every frame
end)

callbacks:add("shutdown", function()
    log:close()
end)
