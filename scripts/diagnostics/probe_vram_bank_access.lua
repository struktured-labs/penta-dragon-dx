local out = assert(os.getenv("VRAM_BANK_OUT"))
local raw = assert(emu.memory.vram)
callbacks:add("frame", function()
  local address = tonumber(os.getenv("VRAM_BANK_ADDRESS") or "38912")
  local offset = address - 0x8000
  local old = emu:read8(0xFF4F)
  local values = {old = old, raw_before = raw:read8(offset)}
  emu:write8(0xFF4F, 0)
  values.cpu0 = emu:read8(address)
  values.raw0 = raw:read8(offset)
  emu:write8(0xFF4F, 1)
  values.cpu1 = emu:read8(address)
  values.raw1 = raw:read8(offset)
  values.raw_plus = raw:read8(0x2000 + offset)
  emu:write8(0xFF4F, old)
  local handle = assert(io.open(out, "w"))
  for key, value in pairs(values) do
    handle:write(string.format("%s=%02X\n", key, value))
  end
  handle:close()
  os.exit(0)
end)
