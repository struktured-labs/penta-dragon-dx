-- Minimal pre-frame receipt for diagnosing ROMs that never reach frame 1.
local OUT = assert(os.getenv("BOOT_PROGRESS_OUT"))
local hits = {}

local function flush(tag)
  local fh = assert(io.open(OUT, "w"))
  fh:write("tag=" .. tag .. "\n")
  for _, value in ipairs(hits) do fh:write("hit=" .. value .. "\n") end
  fh:close()
end

for _, entry in ipairs({
  {0x0100, "entry"}, {0x0061, "mapper"}, {0x0824, "vblank_hook"},
  {0x6F1D, "vblank_wrapper"}, {0x6FE4, "ted_private_entry"},
  {0x028A, "ted_caller"}, {0x4295, "stock_map_copy"},
}) do
  pcall(function()
    emu:setBreakpoint(function()
      if #hits < 128 then
        hits[#hits + 1] = string.format("%s:%04X", entry[2], entry[1])
        flush("breakpoint")
      end
    end, entry[1])
  end)
end

callbacks:add("frame", function()
  hits[#hits + 1] = "frame"
  flush("frame")
  os.exit(0)
end)
