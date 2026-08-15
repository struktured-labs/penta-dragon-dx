-- Visual prototype for Ted's crown-relative palette containment. This writes
-- only CGB attributes in the emulator and is not evidence of a ROM fix.

local OUT = assert(os.getenv("TED_PROTOTYPE_OUT"))
local FRAMES = tonumber(os.getenv("TED_PROTOTYPE_FRAMES") or "600")
local LIVE = os.getenv("TED_PROTOTYPE_LIVE") == "1"
local MATERIAL = tonumber(os.getenv("TED_PROTOTYPE_MATERIAL") or "5")
local frame = 0
local rows = {
    [0]={0,4}, [1]={-2,5}, [2]={-2,5}, [3]={-2,5}, [4]={-2,5},
    [5]={-2,6}, [6]={-3,6}, [7]={-4,6}, [8]={-4,6}, [9]={-4,6},
    [10]={-3,6}, [11]={-2,5}, [12]={0,5}, [13]={1,4},
}

local function palette(tile)
    if (tile >= 0x02 and tile <= 0x76) or tile == 0x7B or tile == 0x7D or
        tile == 0x80 or (tile >= 0x82 and tile <= 0x86) then
        return MATERIAL
    end
    return 0
end

local function find_crown(base)
    for row=0,31 do
        for col=0,27 do
            local ok=true
            for i=0,4 do
                if emu:read8(base + row*32 + col+i) ~= 0x02+i then ok=false end
            end
            if ok then return row,col end
        end
    end
end

local function apply(base)
    emu:write8(0xFF4F,0)
    local crown_row,crown_col=find_crown(base)
    if crown_row == nil then return false end
    emu:write8(0xFF4F,1)
    for row=0,31 do
        for col=0,31 do
            emu:write8(base + row*32 + col,0)
        end
    end
    emu:write8(0xFF4F,0)
    for relative_row,span in pairs(rows) do
        local row=(crown_row+relative_row) % 32
        for relative_col=span[1],span[2] do
            local col=(crown_col+relative_col) % 32
            local address=base+row*32+col
            local value=palette(emu:read8(address))
            emu:write8(0xFF4F,1)
            emu:write8(address,value)
            emu:write8(0xFF4F,0)
        end
    end
    return true
end

callbacks:add("frame",function()
    frame=frame+1
    emu:setKeys(0)
    emu:write8(0xDCBB,0xF0)
    emu:write8(0xDCDC,0xFF)
    emu:write8(0xDCDD,0xFF)
    emu:write8(0xD888,0)
    emu:write8(0xDD06,0)
    if emu:read8(0xD880) ~= 0x10 then
        if not LIVE then os.exit(1) end
        return
    end
    -- The production candidate's broad Ted LUT is the bug under review. Keep
    -- its normal sweep neutral so it cannot recolor future-frame staging after
    -- this crown-relative mask. A production fix will compile the same
    -- neutrality into Ted's scene LUT rather than writing WRAM every frame.
    for tile=0,255 do emu:write8(0xC600+tile,0) end
    local ok98=apply(0x9800)
    local ok9c=apply(0x9C00)
    emu:write8(0xFF4F,0)
    if frame == 120 or frame == 300 or frame == 540 then
        emu:screenshot(OUT .. string.format("-f%03d.png",frame))
    end
    if not LIVE and frame >= FRAMES then
        local marker=assert(io.open(OUT .. ".done","w"))
        marker:write(string.format("ok crowns98=%s crowns9c=%s\n",tostring(ok98),tostring(ok9c)))
        marker:close()
        os.exit(0)
    end
end)
