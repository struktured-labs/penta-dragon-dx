-- Minimal test to verify script execution
local frameCount = 0
local logFile = io.open("test_output/minimal_test.log", "w")

logFile:write("Script loaded successfully\n")
logFile:flush()

-- Set up ONE callback to test
local callback_count = 0
local flags_addr = 0xFE00 + 3  -- First sprite's flags byte

emu:addMemoryCallback(function(addr, value)
    callback_count = callback_count + 1
    logFile:write(string.format("CALLBACK FIRED! Frame %d, Addr=0x%04X, Value=0x%02X\n", frameCount, addr, value))
    logFile:flush()
end, emu.memoryCallback.WRITE, flags_addr, flags_addr)

logFile:write("Callback registered for address 0x" .. string.format("%04X", flags_addr) .. "\n")
logFile:flush()

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    if frameCount == 1 then
        logFile:write("First frame!\n")
        logFile:flush()
    end
    
    if frameCount % 60 == 0 then
        logFile:write(string.format("Frame %d: Callbacks fired: %d\n", frameCount, callback_count))
        logFile:flush()
    end
    
    if frameCount >= 300 then
        logFile:write(string.format("\n=== Summary ===\n"))
        logFile:write(string.format("Total frames: %d\n", frameCount))
        logFile:write(string.format("Callbacks fired: %d\n", callback_count))
        logFile:close()
        emu:stop()
    end
end)

print("Minimal test script loaded")

