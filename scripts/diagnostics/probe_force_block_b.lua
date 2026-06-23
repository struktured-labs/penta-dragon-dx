-- iter 247 v2: patch HRAM 0xFF87 = 0x3E (LD A immediate) so A = 0xC1 always.
-- Forces DMA source to ALWAYS read block B (0xC100), not alternate.
local OUT = os.getenv("OUT") or "tmp/force_block_b"
local f = 0
local patched = false
local h = io.open(OUT .. ".log", "w")
if h then h:write("# force-block-B DMA test v2 (iter 247)\n"); h:close() end
local function log(msg)
  local h = io.open(OUT .. ".log", "a")
  if h then h:write(msg .. "\n"); h:close() end
end

callbacks:add("frame", function()
  f = f + 1
  if not patched then
    local pre_op = emu:read8(0xFF87)
    local pre_v  = emu:read8(0xFF88)
    -- Replace `C6 C0` (ADD A, 0xC0) with `3E C1` (LD A, 0xC1)
    emu:write8(0xFF87, 0x3E)
    emu:write8(0xFF88, 0xC1)
    local post_op = emu:read8(0xFF87)
    local post_v  = emu:read8(0xFF88)
    log(string.format("# patched HRAM: 0xFF87 0x%02X->0x%02X, 0xFF88 0x%02X->0x%02X",
      pre_op, post_op, pre_v, post_v))
    patched = true
  end
  if f > 300 then log("DONE"); emu:stop(); return end
  if f < 1 then return end
  if f > 30 and (f % 20) ~= 0 then return end

  local ffcb = emu:read8(0xFFCB)
  local hw0  = emu:read8(0xFE03)
  local hw2  = emu:read8(0xFE0B)
  log(string.format("f%d FFCB=%02X | HW0=%02X(p%d) HW2=%02X(p%d)",
    f, ffcb, hw0, hw0&7, hw2, hw2&7))
end)
