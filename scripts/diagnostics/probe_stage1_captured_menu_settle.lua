-- Advance the hash-pinned operator capture on its own ABI ancestor with no
-- input, saving one keyframe state per frame. The verifier picks the first
-- frame whose CPU/stack lie outside every release-lock rewrite.
local OUT = assert(os.getenv("PENTA_CAPTURED_MENU_SETTLE_OUT"))
local STATE = assert(os.getenv("PENTA_CAPTURED_MENU_STATE"))
local FRAMES = tonumber(os.getenv("PENTA_CAPTURED_MENU_SETTLE_FRAMES") or "24")
local loaded, frame = false, 0
callbacks:add("frame", function()
  if not loaded then
    local ok, result = pcall(function() return emu:loadStateFile(STATE) end)
    assert(ok and result ~= false, "operator state failed to load")
    loaded = true
    emu:setKeys(0)
    return
  end
  frame = frame + 1
  emu:setKeys(0)
  assert(emu:saveStateFile(string.format("%s/settle-%02d.ss0", OUT, frame)) ~= false)
  if frame == FRAMES then
    local done = assert(io.open(OUT .. "/done.txt", "w"))
    done:write("complete\n"); done:close()
    os.exit(0)
  end
end)
