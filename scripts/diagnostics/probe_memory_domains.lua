local OUT = assert(os.getenv("MEMORY_DOMAINS_OUT"))
callbacks:add("frame", function()
  local out = assert(io.open(OUT, "w"))
  for key, value in pairs(emu.memory or {}) do
    out:write(string.format("%s=%s\n", tostring(key), tostring(value)))
  end
  out:close()
  local done = assert(io.open(OUT .. ".done", "w")); done:write("ok\n"); done:close()
  emu:stop()
end)
