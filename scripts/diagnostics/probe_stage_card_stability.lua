-- Consecutive-frame receipt for every pre-Stage-1 screen that says STAGE 01.
--
-- The save-present route first shows the level-select/high-score screen while
-- D880=$00/FFC1=$00, then the native STAGE splash at D880=$18.  A single late
-- screenshot cannot catch the reported one-frame return to uncolorized text,
-- so retain the rendered frame plus tile/attribute/CRAM state on every frame
-- from title confirmation through settled gameplay.

local OUT = assert(os.getenv("STAGE_CARD_OUT"))
local LIMIT = tonumber(os.getenv("STAGE_CARD_MAX_FRAMES") or "760")
local FORCE_SAVE = os.getenv("STAGE_CARD_FORCE_SAVE") ~= "0"
local CAPTURE_START = tonumber(os.getenv("STAGE_CARD_CAPTURE_START") or "170")

local KEY_A = 0x01
local KEY_START = 0x08
local KEY_DOWN = 0x80

local frame = 0
local first_gameplay = -1
local saw_selector = false
local saw_splash = false
local done = false
local transition_writes = {}
local publication_events = {}
local trace = assert(io.open(OUT .. "/frames.tsv", "w"))
trace:write(
  "frame\td880\td881\tffc1\tdcfd\tffba\tffb7\tffbf\tffc0\tffd0\t" ..
  "ffbd\tlcdc\tbgp\tdf00\tdf02\tdf04\tdf08\tdf4c\tdf51\tdf5b\t" ..
  "dc0b\tdc0e\tdc0f\tbase\t" ..
  "populated\tnonzero_attrs\tpal0\tpal1\tpal2\tpal3\tpal4\tpal5\t" ..
  "pal6\tpal7\ttile_hash\tattr_hash\tbg0\tbg_cram\ttiles\tattrs\t" ..
  "screenshot\n")

local function pulse(lo, hi, key)
  return (frame >= lo and frame < hi) and key or 0
end

local function register(name)
  local readers = {
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:getRegister(string.upper(name)) end,
    function() return emu:readRegister(string.lower(name)) end,
    function() return emu:readRegister(string.upper(name)) end,
  }
  for _, reader in ipairs(readers) do
    local ok, value = pcall(reader)
    if ok and value then return value & 0xFFFF end
  end
  return 0xFFFF
end

local function read_bg0_cram()
  local old_bcps = emu:read8(0xFF68)
  local parts = {}
  for index = 0, 7 do
    emu:write8(0xFF68, index)
    parts[#parts + 1] = string.format("%02X", emu:read8(0xFF69))
  end
  emu:write8(0xFF68, old_bcps)
  return table.concat(parts)
end

-- Optional bounded trace for the reported outgoing-title color loss. This
-- observes writers without changing CPU, game memory, or presentation state.
if os.getenv("PENTA_TITLE_TRACE") == "1" then
  local title_trace = assert(io.open(OUT .. "/title-writes.tsv", "w"))
  title_trace:write("frame\taddress\told\tnew\tpc\tbank\tsvbk\tvbk\tly\n")
  local count = 0
  for _, watched in ipairs({0xDF08, 0xFF40, 0x9821, 0x9C21}) do
    local address = watched
    emu:setRangeWatchpoint(function(info)
      if frame >= 185 and frame <= 215 and count < 200 then
        count = count + 1
        title_trace:write(string.format("%d\t%04X\t%02X\t%02X\t%04X\t%02X\t%02X\t%02X\t%02X\n",
          frame,address,info.oldValue & 0xFF,info.newValue & 0xFF,register("PC"),
          emu:read8(0xFF99),emu:read8(0xFF70),emu:read8(0xFF4F),emu:read8(0xFF44)))
        title_trace:flush()
      end
    end, address, address + 1, C.WATCHPOINT_TYPE.WRITE)
  end
end

-- Optional bounded observation of the stage-card graphics being replaced.
-- No CPU/register/WRAM normalization is performed by these watchpoints.
if os.getenv("PENTA_STAGE_LOAD_TRACE") == "1" then
  local load_trace = assert(io.open(OUT .. "/stage-load-writes.tsv", "w"))
  load_trace:write("frame\taddress\told\tnew\tpc\tbank\tsp\treturn_pc\tlcdc\tbgp\tvbk\tly\tstack\n")
  local count = 0
  for _, watched in ipairs({0x8000, 0x9000, 0x96E0, 0x9882, 0xFF40, 0xFF47}) do
    local address = watched
    emu:setRangeWatchpoint(function(info)
      if frame >= 475 and frame <= 515 and count < 200 then
        count = count + 1
        local sp = register("SP")
        local return_pc = emu:read8(sp) | (emu:read8((sp + 1) & 0xFFFF) << 8)
        local stack = {}
        for offset = 0, 15 do
          stack[#stack + 1] = string.format("%02X", emu:read8((sp + offset) & 0xFFFF))
        end
        load_trace:write(string.format("%d\t%04X\t%02X\t%02X\t%04X\t%02X\t%04X\t%04X\t%02X\t%02X\t%02X\t%02X\t%s\n",
          frame,address,info.oldValue & 0xFF,info.newValue & 0xFF,register("PC"),
          emu:read8(0xFF99),sp,return_pc,emu:read8(0xFF40),emu:read8(0xFF47),
          emu:read8(0xFF4F),emu:read8(0xFF44),table.concat(stack)))
        load_trace:flush()
      end
    end, address, address + 1, C.WATCHPOINT_TYPE.WRITE)
  end
end

pcall(function()
  emu:setRangeWatchpoint(function(info)
    if #transition_writes < 32 then
      transition_writes[#transition_writes + 1] = string.format(
        "f%d:%02X>%02X:pc%04X:b%02X:l%02X", frame,
        info.oldValue & 0xFF, info.newValue & 0xFF,
        register("PC"), emu:read8(0xFF99), emu:read8(0xFF40))
    end
  end, 0xD880, 0xD881, C.WATCHPOINT_TYPE.WRITE)
end)

-- The fixed-bank title/gameplay dispatcher calls the native hidden-map
-- publisher at $12DD, then selects that completed map through the LCDC write
-- at $12EC.  Receipt-lock both sides of that boundary: a palette fix belongs
-- after publication and before visibility, never on the earlier D880 scene
-- transition where it would recolor the outgoing STAGE card.
for _, record in ipairs({
  {0x12DD, "publisher-call"},
  {0x12E0, "publisher-return"},
  {0x12EC, "map-flip"},
}) do
  local address, label = record[1], record[2]
  pcall(function()
    emu:setBreakpoint(function()
      if #publication_events < 64 then
        publication_events[#publication_events + 1] = string.format(
          "f%d:%s:pc%04X:a%02X:b%02X:svbk%02X:l%02X:bg0%s",
          frame, label, register("PC"), register("A") & 0xFF,
          emu:read8(0xFF99), emu:read8(0xFF70), emu:read8(0xFF40),
          read_bg0_cram())
      end
    end, address)
  end)
end

-- The mGBA watchpoint API does not report writes while the game temporarily
-- exposes another switchable WRAM bank. Trace every native absolute D880
-- writer as an independent fallback and retain only the splash handoff.
for _, address in ipairs({
  0x0020, 0x0084, 0x15BF, 0x39D0, 0x3A9E, 0x3B4D, 0x3BA5, 0x3DD1,
  0x4F6A, 0x4F71, 0x4F79, 0x54C3, 0x5516, 0x5532, 0x75B8, 0x75E4,
  0x7CDD, 0x4246, 0x4870, 0x48FA, 0x499B, 0x4A0F, 0x4A78, 0x4AEF,
  0x4B63, 0x4BD7, 0x4C48, 0x41F5,
}) do
  local writer = address
  pcall(function()
    emu:setBreakpoint(function()
      if emu:read8(0xD880) == 0x18 and #transition_writes < 32
          and emu:read8(writer) == 0xEA
          and emu:read8(writer + 1) == 0x80
          and emu:read8(writer + 2) == 0xD8 then
        transition_writes[#transition_writes + 1] = string.format(
          "f%d:writer:pc%04X:b%02X:a%02X:l%02X", frame, writer,
          emu:read8(0xFF99), register("A") & 0xFF,
          emu:read8(0xFF40))
      end
    end, writer)
  end)
end

local function hash_byte(value, byte)
  -- Small deterministic 32-bit hash.  The multiplication stays exact for
  -- Lua's numeric range after the explicit 32-bit mask on every byte.
  return ((value ~ byte) * 16777619) & 0xFFFFFFFF
end

local function sample_visible()
  local lcdc = emu:read8(0xFF40)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local old_vbk = emu:read8(0xFF4F)
  local tile_hash = 2166136261
  local attr_hash = 2166136261
  local tile_parts = {}
  local attr_parts = {}
  local populated = 0
  local nonzero = 0
  local palettes = {0, 0, 0, 0, 0, 0, 0, 0}

  emu:write8(0xFF4F, 0)
  for row = 0, 17 do
    for column = 0, 19 do
      local tile = emu:read8(base + row * 32 + column)
      tile_hash = hash_byte(tile_hash, tile)
      tile_parts[#tile_parts + 1] = string.format("%02X", tile)
      if tile ~= 0 then populated = populated + 1 end
    end
  end

  emu:write8(0xFF4F, 1)
  for row = 0, 17 do
    for column = 0, 19 do
      local attr = emu:read8(base + row * 32 + column)
      attr_hash = hash_byte(attr_hash, attr)
      attr_parts[#attr_parts + 1] = string.format("%02X", attr)
      local palette = attr & 0x07
      palettes[palette + 1] = palettes[palette + 1] + 1
      if palette ~= 0 then nonzero = nonzero + 1 end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return base, populated, nonzero, palettes, tile_hash, attr_hash,
    table.concat(tile_parts), table.concat(attr_parts)
end

local function read_bg_cram()
  local old_bcps = emu:read8(0xFF68)
  local bytes = {}
  for index = 0, 63 do
    emu:write8(0xFF68, index)
    bytes[#bytes + 1] = emu:read8(0xFF69)
  end
  emu:write8(0xFF68, old_bcps)
  local parts = {}
  for _, value in ipairs(bytes) do
    parts[#parts + 1] = string.format("%02X", value)
  end
  return table.concat(parts), table.concat(parts, "", 1, 8)
end

local function write_result(status, message)
  if done then return end
  done = true
  trace:flush()
  trace:close()
  local result = assert(io.open(OUT .. "/result.txt", "w"))
  result:write(string.format("status=%s\n", status))
  result:write(string.format("message=%s\n", message))
  result:write(string.format("frames=%d\n", frame))
  result:write(string.format("first_gameplay=%d\n", first_gameplay))
  result:write(string.format("force_save=%d\n", FORCE_SAVE and 1 or 0))
  result:write(string.format("capture_start=%d\n", CAPTURE_START))
  result:write(string.format("saw_selector=%d\n", saw_selector and 1 or 0))
  result:write(string.format("saw_splash=%d\n", saw_splash and 1 or 0))
  result:write("transition_writes=" .. table.concat(
    transition_writes, ";") .. "\n")
  result:write("publication_events=" .. table.concat(
    publication_events, ";") .. "\n")
  result:close()
  os.exit(status == "ok" and 0 or 2)
end

callbacks:add("frame", function()
  if done then return end
  frame = frame + 1

  -- Reproduce the continue path without relying on a mutable user save.  Stop
  -- forcing the flag immediately after GAME START consumes it.
  if FORCE_SAVE and frame <= 220 then emu:write8(0xDCFD, 0x01) end

  local keys = pulse(180, 186, KEY_DOWN) | pulse(193, 199, KEY_A)
  if FORCE_SAVE then
    keys = keys
      | pulse(241, 247, KEY_A)
      -- Stock reaches the fully interactive selector three frames before DX.
      -- Pressing on the old frame-291 boundary was accepted only by stock; DX
      -- saw the initial edge while its fade was still settling and waited for
      -- the frame-391 fallback. Frame 300 is safely interactive in both.
      | pulse(300, 306, KEY_A)
      | pulse(341, 347, KEY_START)
      | pulse(391, 397, KEY_A)
  else
    -- Match the release blank-SRAM route exactly: DOWN, title A, then one
    -- Stage-card A at title-confirm +107. No WRAM/SRAM fixture write and no
    -- rescue inputs are permitted on the cyan-flash gate.
    keys = keys | pulse(300, 306, KEY_A)
  end
  emu:setKeys(keys)

  local d880 = emu:read8(0xD880)
  local ffc1 = emu:read8(0xFFC1)
  if frame > 220 and d880 == 0 and ffc1 == 0 then saw_selector = true end
  if d880 == 0x18 then saw_splash = true end
  if first_gameplay < 0 and d880 == 0x02 and ffc1 == 1 then
    first_gameplay = frame
  end

  if frame >= CAPTURE_START then
    local base, populated, nonzero, palettes, tile_hash, attr_hash,
      tiles, attrs =
      sample_visible()
    local bg_cram, bg0 = read_bg_cram()
    local screenshot = string.format("frame-%04d.png", frame)
    emu:screenshot(OUT .. "/" .. screenshot)
    trace:write(string.format(
      "%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t" ..
      "%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t" ..
      "%02X\t%02X\t%02X\t%04X\t" ..
      "%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%08X\t%08X\t" ..
      "%s\t%s\t%s\t%s\t%s\n",
      frame, d880, emu:read8(0xD881), ffc1, emu:read8(0xDCFD),
      emu:read8(0xFFBA), emu:read8(0xFFB7), emu:read8(0xFFBF),
      emu:read8(0xFFC0), emu:read8(0xFFD0), emu:read8(0xFFBD),
      emu:read8(0xFF40), emu:read8(0xFF47), emu:read8(0xDF00),
      emu:read8(0xDF02), emu:read8(0xDF04), emu:read8(0xDF08),
      emu:read8(0xDF4C), emu:read8(0xDF51), emu:read8(0xDF5B),
      emu:read8(0xDC0B), emu:read8(0xDC0E), emu:read8(0xDC0F),
      base, populated, nonzero,
      palettes[1], palettes[2], palettes[3], palettes[4],
      palettes[5], palettes[6], palettes[7], palettes[8],
      tile_hash, attr_hash, bg0, bg_cram, tiles, attrs, screenshot))
    if frame % 10 == 0 then trace:flush() end
  end

  if first_gameplay >= 0 and frame >= first_gameplay + 15 then
    write_result("ok", "selector-splash-gameplay-complete")
    return
  end
  if frame >= LIMIT then write_result("failed", "route-timeout") end
end)
