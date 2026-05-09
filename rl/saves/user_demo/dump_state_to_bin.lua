-- Dump WRAM/HRAM/OAM/VRAM from current state to raw bin files.
-- Args: pass as `--script dump_state_to_bin.lua` AFTER -t <state.ss>
-- Outputs: <state>_wram.bin, <state>_hram.bin, <state>_oam.bin, <state>_vram.bin
-- Plus <state>_meta.txt with key game state values.

local function out_path(suffix)
    -- Use STATE_PATH env var or default
    local base = os.getenv("STATE_PATH") or "current_state"
    return base .. suffix
end

callbacks:add("start", function()
    -- Wait one frame for state to load fully
end)

callbacks:add("frame", function()
    -- After 5 frames, dump. State has loaded by now.
    if emu:currentFrame() < 5 then return end

    local function dump_range(start_addr, end_addr, fname)
        local f = io.open(fname, "wb")
        if not f then
            console:log("ERROR: cannot open " .. fname)
            return
        end
        for a = start_addr, end_addr do
            f:write(string.char(emu:read8(a)))
        end
        f:close()
        console:log(string.format("dumped %s (%d bytes)", fname, end_addr - start_addr + 1))
    end

    -- WRAM: 0xC000-0xDFFF (8KB visible; bank-switched in CGB)
    -- We dump only bank 1 visible (D000-DFFF) + bank 0 (C000-CFFF)
    -- For game-state reconstruction, that's what matters
    dump_range(0xC000, 0xDFFF, out_path("_wram.bin"))
    -- HRAM: 0xFF80-0xFFFE
    dump_range(0xFF80, 0xFFFE, out_path("_hram.bin"))
    -- OAM: 0xFE00-0xFE9F
    dump_range(0xFE00, 0xFE9F, out_path("_oam.bin"))
    -- VRAM: 0x8000-0x9FFF
    dump_range(0x8000, 0x9FFF, out_path("_vram.bin"))
    -- IO regs: 0xFF00-0xFF7F (timing, banking, palettes)
    dump_range(0xFF00, 0xFF7F, out_path("_io.bin"))

    -- Meta: write key game state values as ASCII
    local meta = io.open(out_path("_meta.txt"), "w")
    meta:write(string.format("FFBA=%d\n", emu:read8(0xFFBA)))
    meta:write(string.format("FFBD=%d\n", emu:read8(0xFFBD)))
    meta:write(string.format("FFBF=%d\n", emu:read8(0xFFBF)))
    meta:write(string.format("FFC0=%d\n", emu:read8(0xFFC0)))
    meta:write(string.format("D880=0x%02x\n", emu:read8(0xD880)))
    meta:write(string.format("DCB8=%d\n", emu:read8(0xDCB8)))
    meta:write(string.format("DCBB=0x%02x\n", emu:read8(0xDCBB)))
    meta:write(string.format("DCDC=0x%02x\n", emu:read8(0xDCDC)))
    meta:write(string.format("DCDD=0x%02x\n", emu:read8(0xDCDD)))
    meta:write(string.format("FE04=%d\n", emu:read8(0xFE04)))  -- Sara X
    meta:write(string.format("FE05=%d\n", emu:read8(0xFE05)))  -- Sara Y
    meta:write(string.format("FFE9=0x%02x\n", emu:read8(0xFFE9)))
    meta:close()
    console:log("meta written: " .. out_path("_meta.txt"))

    -- Exit after dumping
    os.exit(0)
end)
