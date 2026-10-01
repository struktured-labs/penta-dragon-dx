-- Three ordinary Select round trips; no game-memory writes or health aid.
local out = assert(os.getenv('BOSS_MENU_OUT'))
local state = assert(os.getenv('BOSS_MENU_STATE'))
local loaded, done, frame = false, false, 0
local third_entry = tonumber(os.getenv('BOSS_MENU_THIRD_ENTRY') or '720')
assert(third_entry >= 700 and third_entry <= 800)
local third_hold = tonumber(os.getenv('BOSS_MENU_THIRD_HOLD') or '6')
assert(third_hold >= 1 and third_hold <= 6)
local presses = {120, 240, 420, 540, third_entry, 840}
local apu
local input_trace
local loop_trace
local latch_trace
if os.getenv('BOSS_MENU_LATCH_TRACE') then
    latch_trace = assert(io.open(out .. '/latch-writes.tsv', 'w'))
    latch_trace:write('frame\tcycle\taddress\tvalue\tpc\tbank\tie\tsvbk\n')
    emu:setRangeWatchpoint(function(info)
        if not loaded or (emu:read8(0xFF70) & 7) ~= 7 then return end
        latch_trace:write(string.format('%d\t%d\t%04X\t%02X\t%04X\t%02X\t%02X\t%02X\n',
            frame, emu:currentCycle(), info.address & 65535,
            (info.newValue or info.value or 0) & 255, emu:readRegister('PC'),
            emu:read8(0xFF99), emu:read8(0xFFFF), emu:read8(0xFF70)))
    end, 0xDF81, 0xDF83, C.WATCHPOINT_TYPE.WRITE)
end
if os.getenv('BOSS_MENU_INPUT_TRACE') then
    input_trace = assert(io.open(out .. '/input-events.tsv', 'w'))
    input_trace:write('frame\tcycle\taddress\tvalue\tpc\tbank\traw\tedge\theld\n')
    emu:setRangeWatchpoint(function(info)
        if not loaded or frame < 700 or frame > 860 then return end
        input_trace:write(string.format('%d\t%d\t%04X\t%02X\t%04X\t%02X\t%02X\t%02X\t%02X\n',
            frame, emu:currentCycle(), info.address & 65535,
            (info.newValue or info.value or 0) & 255, emu:readRegister('PC'),
            emu:read8(0xFF99), emu:read8(0xFF93), emu:read8(0xFF94), emu:read8(0xFF95)))
    end, 0xFF93, 0xFF96, C.WATCHPOINT_TYPE.WRITE)
    loop_trace = assert(io.open(out .. '/loop-events.tsv', 'w'))
    loop_trace:write('frame\tcycle\tpc\tbank\tsp\treturn\tly\tsvbk\n')
    for _, address in ipairs({0x406F, 0x309B, 0x3136, 0x4295, 0x42A7,
                               0x42AA, 0x028A, 0x028D, 0x6C80, 0x6C85, 0x6D7D,
                               0x6C9E, 0x6CAD, 0x6CC8, 0x6CE2, 0x6CEA, 0x6CF0}) do
        emu:setBreakpoint(function()
            if not loaded or frame < 715 or frame > 735 then return end
            local sp = emu:readRegister('SP')
            loop_trace:write(string.format('%d\t%d\t%04X\t%02X\t%04X\t%04X\t%d\t%02X\n',
                frame, emu:currentCycle(), address, emu:read8(0xFF99), sp,
                emu:read8(sp) | (emu:read8((sp+1)&65535)<<8),
                emu:read8(0xFF44), emu:read8(0xFF70)))
        end, address)
    end
end
local map_trace
if os.getenv('BOSS_MENU_MAP_TRACE') then
    map_trace = assert(io.open(out .. '/map-events.tsv', 'w'))
    map_trace:write('frame\tcycle\tkind\taddress\tvalue\tpc\tbank\tsource\tmap\n')
    local function record(info, kind)
        if not loaded or frame < 540 or frame > 610 then return end
        local source, map = {}, {}
        if kind == 'bgp' then
            local base = (emu:read8(0xFF40) & 8) ~= 0 and 0x1C00 or 0x1800
            for row = 0, 23 do
                for col = 0, 23 do
                    source[#source+1] = string.format('%02X', emu:read8(0xC1A0+row*24+col))
                    map[#map+1] = string.format('%02X', emu.memory.vram:read8(base+row*32+col))
                end
            end
        end
        map_trace:write(string.format('%d\t%d\t%s\t%04X\t%02X\t%04X\t%02X\t%s\t%s\n',
            frame, emu:currentCycle(), kind, info.address & 65535,
            (info.newValue or info.value or 0) & 255, emu:readRegister('PC'),
            emu:read8(0xFF99), table.concat(source), table.concat(map)))
    end
    emu:setWatchpoint(function(info) record(info, 'bgp') end, 0xFF47, C.WATCHPOINT_TYPE.WRITE)
    emu:setRangeWatchpoint(function(info) record(info, 'source') end,
        0xC1A0, 0xC3DF, C.WATCHPOINT_TYPE.WRITE)
end
if os.getenv('BOSS_MENU_APU_TRACE') then
    apu = assert(io.open(out .. '/apu.tsv', 'w'))
    apu:write('frame\tcycle\taddress\tvalue\tpc\n')
    emu:setRangeWatchpoint(function(info)
        if not loaded or frame < 240 or frame > 320 then return end
        apu:write(string.format('%d\t%d\t%04X\t%02X\t%04X\n', frame,
            emu:currentCycle(), info.address & 65535,
            (info.newValue or info.value or 0) & 255, emu:readRegister('PC')))
    end, 0xFF10, 0xFF3F, C.WATCHPOINT_TYPE.WRITE)
end
callbacks:add('frame', function()
    if done then return end
    if not loaded then
        assert(emu:loadStateFile(state) ~= false, 'state load failed')
        loaded = true
        return
    end
    frame = frame + 1
    local pressed = false
    for index, start in ipairs(presses) do
        local hold = index == 5 and third_hold or 6
        if frame >= start and frame < start + hold then pressed = true end
    end
    emu:setKeys(pressed and 4 or 0)
    local prefix = string.format('%s/frame-%04d', out, frame)
    emu:screenshot(prefix .. '.png')
    emu:saveStateFile(prefix .. '.ss0')
    if frame == 1080 then
        done = true
        if apu then apu:close() end
        if input_trace then input_trace:close() end
        if loop_trace then loop_trace:close() end
        if latch_trace then latch_trace:close() end
        if map_trace then map_trace:close() end
        emu:setKeys(0)
        local f = assert(io.open(out .. '/done', 'w'))
        f:write(string.format('1080 captured frames; Select120/240/420/540/%d/840 held6 except third entry held%d; no game-memory writes\n', third_entry, third_hold))
        f:close()
        -- Native tap finalizes synchronously through its exit interposer.
        if os.getenv('PENTA_NATIVE_AV_PREFIX') then os.exit(0) end
        emu:quit()
    end
end)
-- #43: native capture uses Qt's pre-script restoration while the CPU startup
-- gate is held. Never perform a second restoration from the first frame.
if os.getenv('BOSS_MENU_PRELOADED')=='1' then
    local marker=assert(os.getenv('ENTRY_NATIVE_START_GATE'))
    loaded=true
    emu:setKeys(0)
    local ready=assert(io.open(marker,'w'))
    ready:write('boss menu probe initialized after Qt state restore\n')
    ready:close()
end
