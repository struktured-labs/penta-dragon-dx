-- Trace the experimental block-major Ted writer/publication contract.
local OUT = assert(os.getenv("TED_BLOCK_TRACE_OUT"))
local FRAMES = tonumber(os.getenv("TED_BLOCK_TRACE_FRAMES") or "360")
local report = assert(io.open(OUT, "w"))
local frame, finished = 0, false

local function reg(name)
  for _, candidate in ipairs({name, string.lower(name)}) do
    local ok, value = pcall(function() return emu:getRegister(candidate) end)
    if ok and value ~= nil then return value & 0xFFFF end
  end
  return 0xFFFF
end

local function line(kind)
  local bank = emu:read8(0xFF70) & 7
  report:write(string.format(
    "%s frame=%d pc=%04X svbk=%d rombank=%02X ready=%02X cand=%02X%02X key=%02X de=%04X hl=%04X bc=%04X sp=%04X ie=%02X lcdc=%02X scene=%02X\n",
    kind, frame, reg("PC"), bank, emu:read8(0xFF99), emu:read8(0xC5FF),
    emu:read8(0xD842), emu:read8(0xD841), emu:read8(0xD578),
    reg("DE"), reg("HL"), reg("BC"), reg("SP"), emu:read8(0xFFFF),
    emu:read8(0xFF40), emu:read8(0xD880)))
  report:flush()
end

local function bp(address, name, segment)
  assert(pcall(function()
    local callback = function() if not finished then line(name) end end
    if segment then emu:setBreakpoint(callback, address, segment)
    else emu:setBreakpoint(callback, address) end
  end))
end

-- $028D is in the fixed ROM window and is the safe publication observation
-- point. Breakpoints in $4000-$7FFF are bank-relative; installing them without
-- an explicit segment made an earlier diagnostic perturb execution itself.
bp(0x028D, "publish-fixed")
for _, site in ipairs({
  {0x5940, "install-entry"}, {0x5970, "install-middle"},
  {0x5E48, "private-copy"}, {0x6140, "private-setup"},
  {0x5890, "expand"}, {0x61C0, "expand-store"},
  {0x6100, "expand-control"}, {0x61B0, "install-finish"},
}) do bp(site[1], site[2], 13) end

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:setKeys(0)
  if frame == 1 then emu:write8(0xC5FF, 0) end
  if frame >= FRAMES or emu:read8(0xD880) ~= 0x10 then
    line("finish")
    finished = true
    report:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write("done\n"); marker:close()
  end
end)
