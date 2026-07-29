-- Trace every stock LDH [BGP],A site during the title-screen gameplay demo.

local OUT = assert(os.getenv("BGP_TRACE_OUT"), "BGP_TRACE_OUT is required")
local frame, demo_seen, return_frame, done = 0, false, nil, false

local sites = {
    {0x06FD, 0x00}, {0x0721, 0x00},
    {0x0949, 0x00}, {0x0956, 0x00}, {0x0963, 0x00},
    {0x0970, 0x00}, {0x097D, 0x00}, {0x098A, 0x00},
    {0x0997, 0x00}, {0x0A0F, 0x00},
    {0x0F5E, 0x00}, {0x0F90, 0x00}, {0x0FB3, 0x00},
    {0x281E, 0x00}, {0x2823, 0x00}, {0x2828, 0x00},
    {0x29BF, 0x00},
    {0x41C1, 0x01}, {0x41D3, 0x01}, {0x41EE, 0x01},
    {0x5021, 0x01}, {0x502F, 0x01},
    {0x55D3, 0x02},
    {0x78DE, 0x02}, {0x78EF, 0x02},
    {0x59BD, 0x0C},
}
local fade_call_sites = {
    {0x0259, 0x00}, {0x15DF, 0x00}, {0x3B16, 0x00},
    {0x4A7E, 0x01}, {0x73BA, 0x01}, {0x74F1, 0x01},
}

local trace = assert(io.open(OUT .. ".tsv", "w"))
trace:write(
    "frame\tsite\tbank\tmapped_bank\td880\tbgp\twrite_a\tstat\tly\tsp\tcaller" ..
    "\tmapped_4353\n"
)
trace:close()

local function read_register(name)
    local readers = {
        function() return emu:getRegister(string.lower(name)) end,
        function() return emu:getRegister(string.upper(name)) end,
        function() return emu:readRegister(string.lower(name)) end,
        function() return emu:readRegister(string.upper(name)) end,
    }
    for _, reader in ipairs(readers) do
        local ok, value = pcall(reader)
        if ok and value then return value end
    end
    return nil
end

local function record(site, bank)
    if not demo_seen then return end
    if bank ~= 0 and emu:read8(0xFF99) ~= bank then return end
    local sp = read_register("sp")
    local write_a = read_register("a")
    local caller = 0xFFFF
    if sp and site == 0x0F5E then
        local return_address =
            emu:read8(sp + 4) | (emu:read8(sp + 5) << 8)
        caller = (return_address - 3) & 0xFFFF
    end
    local handle = assert(io.open(OUT .. ".tsv", "a"))
    handle:write(string.format(
        "%d\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%04X\t%04X" ..
        "\t%02X\n",
        frame, site, bank, emu:read8(0xFF99),
        emu:read8(0xD880), emu:read8(0xFF47),
        (write_a or 0xFF) & 0xFF, emu:read8(0xFF41), emu:read8(0xFF44),
        sp or 0xFFFF, caller, emu:read8(0x4353)
    ))
    handle:close()
end

for _, row in ipairs(sites) do
    local site, bank = row[1], row[2]
    emu:setBreakpoint(function() record(site, bank) end, site + 2)
end
for _, row in ipairs(fade_call_sites) do
    local site, bank = row[1], row[2]
    emu:setBreakpoint(function() record(site, bank) end, site)
end

callbacks:add("frame", function()
    if done then return end
    frame = frame + 1
    emu:setKeys(0)
    if emu:read8(0xD880) == 0x0A then demo_seen = true end
    if demo_seen and not return_frame and emu:read8(0xD880) == 0x01 then
        return_frame = frame
    end
    if (return_frame and frame - return_frame >= 80) or frame >= 12000 then
        done = true
        local marker = assert(io.open(OUT .. ".done", "w"))
        marker:write(return_frame and "ok\n" or "timeout\n")
        marker:close()
    end
end)
