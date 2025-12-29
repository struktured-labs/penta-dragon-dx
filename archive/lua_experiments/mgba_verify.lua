-- mgba_verify.lua
local MAX_FRAMES = 600
local frame_count = 0
local white_frames = 0
local log_file = io.open("boot_trace.txt", "w")

function on_frame()
    frame_count = frame_count + 1
    local pc = emu:getReg("PC")
    local bank = emu:read8(0x2000) -- This might not work for all MBCs, but let's try
    
    log_file:write(string.format("Frame %d: PC=%04X, Bank=%02X\n", frame_count, pc, bank))

    local is_white = true
    for i = 0, 10 do
        if emu:readVideoPixel(math.random(0,159), math.random(0,143)) ~= 0x7FFF then
            is_white = false
            break
        end
    end

    if is_white then white_frames = white_frames + 1 else white_frames = 0 end

    if white_frames > 120 then
        log_file:write("FAILURE: White screen detected.\n")
        log_file:close()
        emu:exit()
    end

    if frame_count > MAX_FRAMES then
        log_file:write("SUCCESS: Reached end of test.\n")
        log_file:close()
        emu:exit()
    end
end

callbacks:add("frame", on_frame)
