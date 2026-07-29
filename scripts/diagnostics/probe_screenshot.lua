-- Take screenshot at gameplay
local frame_count = 0
local KEY_DOWN = 0x80
local KEY_A = 0x01
local KEY_START = 0x08

callbacks:add("frame", function()
    frame_count = frame_count + 1

    if frame_count >= 180 and frame_count <= 185 then
        emu:setKeys(KEY_DOWN)
    elseif frame_count >= 190 and frame_count <= 195 then
        emu:setKeys(KEY_A)
    elseif frame_count >= 200 and frame_count <= 205 then
        emu:setKeys(KEY_START)
    elseif frame_count >= 280 and frame_count <= 285 then
        emu:setKeys(KEY_A)
    elseif frame_count == 400 then
        -- In gameplay by now, take screenshot
        emu:screenshot("/tmp/v303_gameplay.png")
    elseif frame_count == 600 then
        -- Another screenshot
        emu:screenshot("/tmp/v303_gameplay2.png")
        emu:stop()
    else
        emu:setKeys(0)
    end
end)
