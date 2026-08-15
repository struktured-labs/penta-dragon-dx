-- Dump Ted's lazily installed WRAM helper and CPU state from a saved frame.
local OUT = assert(os.getenv("TED_RUNTIME_OUT"))
local done = false

local function reg(name)
    local ok, value = pcall(function() return emu:getRegister(name) end)
    if ok and value ~= nil then return value & 0xFFFF end
    return 0xFFFF
end

callbacks:add("frame", function()
    if done then return end
    done = true
    local handle = assert(io.open(OUT, "w"))
    handle:write(string.format(
        "pc=%04X sp=%04X bc=%04X de=%04X hl=%04X scene=%02X sentinel=%02X phase=%02X ie=%02X if=%02X\n",
        reg("PC"), reg("SP"), reg("BC"), reg("DE"), reg("HL"),
        emu:read8(0xD880), emu:read8(0xC5FF), emu:read8(0xC5F3),
        emu:read8(0xFFFF), emu:read8(0xFF0F)))
    for row=0,15 do
        local address = 0xC500 + row * 16
        handle:write(string.format("%04X:", address))
        for offset=0,15 do
            handle:write(string.format("%02X", emu:read8(address + offset)))
        end
        handle:write("\n")
    end
    handle:write("stack_DFE0:")
    for address=0xDFE0,0xE01F do
        handle:write(string.format("%02X", emu:read8(address)))
    end
    handle:write("\n")
    handle:close()
    emu:stop()
end)
