-- Save a candidate-native mGBA state after a bounded uninstrumented run.

local STATE_OUT = assert(os.getenv("PENTA_SNAPSHOT_STATE_OUT"),
  "PENTA_SNAPSHOT_STATE_OUT required")
local RECEIPT_OUT = assert(os.getenv("PENTA_SNAPSHOT_RECEIPT_OUT"),
  "PENTA_SNAPSHOT_RECEIPT_OUT required")
local TARGET_FRAME = tonumber(os.getenv("PENTA_SNAPSHOT_FRAME") or "500")
assert(TARGET_FRAME > 0, "PENTA_SNAPSHOT_FRAME must be positive")

local frame = 0
callbacks:add("frame", function()
  frame = frame + 1
  if frame < TARGET_FRAME then return end

  local ok, result = pcall(function()
    return emu:saveStateFile(STATE_OUT)
  end)
  assert(ok and result ~= false, "saveStateFile failed")

  local receipt = assert(io.open(RECEIPT_OUT, "w"))
  receipt:write(string.format(
    "status=pass\nframes=%d\nscene=%02X\nroom=%02X\nlcdc=%02X\n",
    frame, emu:read8(0xD880), emu:read8(0xFFBD), emu:read8(0xFF40)))
  receipt:close()
  os.exit(0)
end)
