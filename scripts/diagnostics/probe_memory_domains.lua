local out = assert(os.getenv("MEMORY_DOMAINS_OUT"))
local handle = assert(io.open(out, "w"))
for key, value in pairs(emu.memory) do
  handle:write(tostring(key) .. "\t" .. tostring(value) .. "\n")
end
for _, key in ipairs({"vram", "vram0", "vram1", "videoRam", "cgbVram"}) do
  local ok, value = pcall(function() return emu.memory[key] end)
  handle:write(string.format("probe:%s\t%s\t%s\n", key, tostring(ok), tostring(value)))
end
handle:close()
os.exit(0)
