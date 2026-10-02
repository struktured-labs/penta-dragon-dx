-- Minimal frame-liveness probe for the deterministic Stage-1 miniboss switch.
-- Unlike the full spike verifier this installs no instruction breakpoints, so
-- a missing post-switch frame proves a game-side stall rather than trace cost.
-- #41: native assistance writes physical WRAM bank1 regardless of the SVBK
-- bank a graphics routine selected. #37: never write DCDC/DCDD (inventory /
-- ten-slot cursor) as fake health; DCBB is the health byte.
local native_assistance = {writes = 0, bank_shadow_counts = {}}
function native_assistance.write(address, value)
  local svbk = emu:read8(0xFF70) & 7
  native_assistance.writes = native_assistance.writes + 1
  native_assistance.bank_shadow_counts[svbk] =
    (native_assistance.bank_shadow_counts[svbk] or 0) + 1
  assert(emu.memory and emu.memory.wram, "physical WRAM required for assistance")
    :write8(address - 0xC000, value)
end

local out = assert(os.getenv("STAGE1_MINIBOSS_OUT"))
local force_frame = tonumber(os.getenv("STAGE1_MINIBOSS_FORCE_FRAME") or "200")
local finish_frame = tonumber(os.getenv("STAGE1_MINIBOSS_FINISH_FRAME") or "240")
local frame = 0

local function reg(name)
  local ok, value = pcall(function() return emu:getRegister(name) end)
  if ok and value then return value & 0xFFFF end
  return 0xFFFF
end

local function record()
  local handle = assert(io.open(out .. ".heartbeat", "a"))
  handle:write(string.format(
    "f%d pc=%04X sp=%04X scene=%02X room=%02X boss=%02X kind=%02X bank=%02X lcdc=%02X\n",
    frame, reg("PC"), reg("SP"), emu:read8(0xD880), emu:read8(0xFFBD),
    emu:read8(0xFFBF), emu:read8(0xDCB8), emu:read8(0xFF99),
    emu:read8(0xFF40)))
  handle:close()
end

callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)
  if frame == force_frame then
    emu:write8(0xD880, 0x0A)
    emu:write8(0xFFBF, 0x01)
    native_assistance.write(0xDCB8, 0x02)
  end
  record()
  if frame >= finish_frame then
    emu:screenshot(out .. ".png")
    local done = assert(io.open(out .. ".done", "w"))
    done:write("OK\n")
    done:close()
    os.exit(0)
  end
end)
