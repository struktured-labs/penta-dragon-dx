-- iter 246: dump the HRAM OAM DMA routine at 0xFF80
local logged = false
callbacks:add("frame", function()
  if logged then return end
  logged = true
  local out = io.open("tmp/hram_dma.txt", "w")
  if not out then return end
  out:write("HRAM 0xFF80-FF9F: ")
  for i = 0, 31 do
    out:write(string.format("%02X ", emu:read8(0xFF80 + i)))
  end
  out:write("\n")
  out:close()
  emu:stop()
end)
