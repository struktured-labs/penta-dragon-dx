-- Cold-boot title capture: no scene or machine-memory writes.
local path = assert(os.getenv("CAPTURE_TITLE_STATE"))
local frames, stable = 0, 0
callbacks:add("frame", function()
    frames = frames + 1
    emu:setKeys(0)
    local title = emu.memory.wram:read8(0x1880) == 1
        and emu:read8(0xFFC1) == 0
    if title then stable = stable + 1 else stable = 0 end
    if stable == 45 then
        assert(emu:saveStateFile(path) ~= false, "title save failed")
        os.exit(0)
    end
    if frames > 1800 then error("cold title not reached") end
end)
