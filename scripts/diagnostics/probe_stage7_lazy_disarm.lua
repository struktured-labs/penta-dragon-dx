-- Forced execution matrix for the r279 Stage-7 lazy redirect disarm.
local OUT = assert(os.getenv("STAGE7_DISARM_OUT"), "STAGE7_DISARM_OUT required")
local DONE = assert(os.getenv("STAGE7_DISARM_DONE"), "STAGE7_DISARM_DONE required")

local cases = {
  {name="later-stage-d880", d880=0x06, ffba=0x04,
   classifier=1, disarm=1, dab7=0xEB, native=1},
  {name="later-stage-ffba", d880=0x08, ffba=0x04,
   classifier=0, disarm=1, dab7=0xEB, native=1},
  {name="death-retry", d880=0x17, ffba=0x06,
   classifier=1, disarm=0, dab7=0x31, native=0},
  {name="miniboss-return", d880=0x0A, ffba=0x06,
   classifier=1, disarm=0, dab7=0x31, native=0},
}

local frame = 0
local current = 0
local active = false
local phase = "boot"
local rows = {}
local counts = {helper=0, classifier=0, disarm=0, native=0}
local finished = false

local function reg(name)
  local ok, value = pcall(function() return emu:readRegister(name) end)
  if ok and type(value) == "number" then return value & 0xFFFF end
  ok, value = pcall(function() return emu:getRegister(name) end)
  if ok and type(value) == "number" then return value & 0xFFFF end
  return -1
end

local function setreg(name, value)
  local ok, message = pcall(function() emu:writeRegister(name, value) end)
  assert(ok, "writeRegister " .. name .. " failed: " .. tostring(message))
end

local function write16(address, value)
  emu:write8(address, value & 0xFF)
  emu:write8((address + 1) & 0xFFFF, (value >> 8) & 0xFF)
end

local function runtime_ready()
  local expected = {
    0xE1,0xD1,0xC1,0xF5,0xFA,0x80,0xD8,0xFE,0x08,0x28,0x02,
    0x18,0x00,0xF3,0xF1,0xF1,0xF1,0x3E,0x16,0xC3,0x47,0x08,
  }
  for index, value in ipairs(expected) do
    if emu:read8(0xDAE8 + index) ~= value then return false end
  end
  return emu:read8(0xDAB6) == 0x18
end

local function finish(status, message)
  if finished then return end
  finished = true
  local handle = assert(io.open(OUT, "w"))
  handle:write("status\tmessage\n")
  handle:write(status .. "\t" .. message .. "\n")
  handle:write("name\td880\tffba\thelper\tclassifier\tdisarm\tnative" ..
    "\tdab7\tsp\tbank\tsvbk\tbc\tde\thl" ..
    "\tnative_sp\tnative_bc\tnative_de\tnative_hl\tnative_pc\tpassed\n")
  for _, row in ipairs(rows) do
    handle:write(table.concat(row, "\t") .. "\n")
  end
  handle:close()
  local marker = assert(io.open(DONE, "w"))
  marker:write(status .. "\t" .. message .. "\n")
  marker:close()
  emu:stop()
end

local inject_case

local function next_case()
  current = current + 1
  if current > #cases then
    finish("PASS", "forced-lazy-disarm-matrix")
    return
  end
  inject_case()
end

inject_case = function()
  local case = cases[current]
  counts = {helper=0, classifier=0, disarm=0, native=0}
  phase = "route"
  active = true
  emu:setKeys(0)
  emu:write8(0xFFFF, 0x00)
  emu:write8(0xFF70, 0x01)
  emu:write8(0xD880, case.d880)
  emu:write8(0xFFBA, case.ffba)
  emu:write8(0xFFC1, 0x01)
  emu:write8(0xFF40, 0x8B)
  emu:write8(0xFF55, 0xFF)
  emu:write8(0xDAB7, 0x31)
  emu:write8(0x2100, 0x0D)
  emu:write8(0xFF99, 0x0D)
  local sp = 0xCFF0
  write16(sp + 0, 0x1111)
  write16(sp + 2, 0x2222)
  write16(sp + 4, 0x3333)
  write16(sp + 6, 0x3493)
  write16(sp + 8, 0x42B1)
  write16(sp + 10, 0x1234)
  setreg("sp", sp)
  setreg("pc", 0xDAE9)
end

emu:setBreakpoint(function()
  if active and phase == "route" and emu:read8(0xFF99) == 0x16 then
    counts.helper = counts.helper + 1
  end
end, 0x6C80)

emu:setBreakpoint(function()
  if active and phase == "route" and emu:read8(0xFF99) == 0x16 then
    counts.classifier = counts.classifier + 1
  end
end, 0x723B)

emu:setBreakpoint(function()
  if active and phase == "route" and emu:read8(0xFF99) == 0x16 then
    counts.disarm = counts.disarm + 1
  end
end, 0x7233)

emu:setBreakpoint(function()
  if not active or phase ~= "route" or emu:read8(0xFF99) ~= 0x16 then return end
  local case = cases[current]
  local dab7 = emu:read8(0xDAB7)
  local sp, bank, svbk = reg("sp"), emu:read8(0xFF99), emu:read8(0xFF70) & 7
  local bc, de, hl = reg("bc"), reg("de"), reg("hl")
  local passed = counts.helper == 1
    and counts.classifier == case.classifier
    and counts.disarm == case.disarm
    and dab7 == case.dab7
    and sp == 0xCFF8 and bank == 0x16 and svbk == 1
    and bc == 0x3333 and de == 0x2222 and hl == 0x1111
  rows[#rows + 1] = {
    case.name, string.format("%02X", case.d880), string.format("%02X", case.ffba),
    tostring(counts.helper), tostring(counts.classifier), tostring(counts.disarm),
    "PENDING", string.format("%02X", dab7), string.format("%04X", sp),
    string.format("%02X", bank), string.format("%02X", svbk),
    string.format("%04X", bc), string.format("%04X", de),
    string.format("%04X", hl), "PENDING", "PENDING", "PENDING", "PENDING",
    "PENDING", passed and "1" or "0",
  }
  if not passed then
    finish("FAIL", "route-case-" .. case.name)
    return
  end
  if case.native == 1 then
    phase = "native"
    write16(0xCFF0, 0x1111)
    write16(0xCFF2, 0x2222)
    write16(0xCFF4, 0x3333)
    write16(0xCFF6, 0x1234)
    setreg("hl", 0xA1A1)
    setreg("de", 0xB2B2)
    setreg("bc", 0xC3C3)
    setreg("sp", 0xCFF0)
    setreg("pc", 0xDAB6)
  else
    rows[#rows][7] = "0"
    for index = 15, 19 do rows[#rows][index] = "NA" end
    next_case()
  end
end, 0x71B3)

emu:setBreakpoint(function()
  if not active or phase ~= "native" then return end
  counts.native = counts.native + 1
  local row = rows[#rows]
  local sp, bc, de, hl, pc = reg("sp"), reg("bc"), reg("de"), reg("hl"), reg("pc")
  local passed = emu:read8(0xDAB7) == 0xEB and sp == 0xCFF8
    and bc == 0x3333 and de == 0x2222 and hl == 0x1111 and pc == 0x1234
    and counts.native == 1 and counts.helper == 1
  row[7] = tostring(counts.native)
  row[15] = string.format("%04X", sp)
  row[16] = string.format("%04X", bc)
  row[17] = string.format("%04X", de)
  row[18] = string.format("%04X", hl)
  row[19] = string.format("%04X", pc)
  if not passed then row[20] = "0" end
  if row[20] ~= "1" then
    finish("FAIL", "native-epilogue-return-" .. cases[current].name)
    return
  end
  next_case()
end, 0x1234)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  if not active and runtime_ready() then
    current = 1
    inject_case()
    return
  end
  if not active and frame > 600 then
    finish("FAIL", "runtime-not-installed")
  elseif active and frame > 900 then
    finish("FAIL", "execution-timeout")
  end
end)

callbacks:add("shutdown", function()
  if not finished then finish("FAIL", "unexpected-shutdown") end
end)
