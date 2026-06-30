local TITLE = {
    {180, 185, 0x80}, {193, 198, 0x01}, {241, 246, 0x01},
    {291, 296, 0x01}, {341, 346, 0x08}, {391, 396, 0x01},
}
local frame = 0
local count_s0 = {0,0,0,0,0,0,0,0}  -- pal counts per slot
local count_s1 = {0,0,0,0,0,0,0,0}
local count_s2 = {0,0,0,0,0,0,0,0}
local count_s3 = {0,0,0,0,0,0,0,0}
callbacks:add("keysRead", function()
    local keys = 0
    for _, seq in ipairs(TITLE) do
        if frame >= seq[1] and frame <= seq[2] then keys = seq[3]; break end
    end
    emu:setKeys(keys)
end)
callbacks:add("frame", function()
    frame = frame + 1
    if frame >= 400 and frame <= 1500 then
        local p0 = emu:read8(0xFE03) & 7
        local p1 = emu:read8(0xFE07) & 7
        local p2 = emu:read8(0xFE0B) & 7
        local p3 = emu:read8(0xFE0F) & 7
        count_s0[p0+1] = count_s0[p0+1] + 1
        count_s1[p1+1] = count_s1[p1+1] + 1
        count_s2[p2+1] = count_s2[p2+1] + 1
        count_s3[p3+1] = count_s3[p3+1] + 1
    end
    if frame == 1500 then
        local h = io.open("/home/struktured/projects/penta-dragon-dx-claude/tmp/fresh_boot_sara_counts.log", "w")
        h:write("slot0 ")
        for i = 1, 8 do h:write(count_s0[i] .. " ") end
        h:write("\nslot1 ")
        for i = 1, 8 do h:write(count_s1[i] .. " ") end
        h:write("\nslot2 ")
        for i = 1, 8 do h:write(count_s2[i] .. " ") end
        h:write("\nslot3 ")
        for i = 1, 8 do h:write(count_s3[i] .. " ") end
        h:write("\n")
        h:close()
        emu:stop()
    end
end)
