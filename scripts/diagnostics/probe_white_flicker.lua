-- iter 241: white-flicker + half-color-sprite diagnostic v3
-- Tracks PER-SLOT OAM attribute palette changes across frames. If the same
-- slot's CGB pal index flips between two values frame-to-frame, that's the
-- "half one color half another" mechanism the user reported.
-- Also tracks: LCDC bit 3/4 toggles (tile-map / tile-data area swap).
--
-- Run via:
--   QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy \
--     timeout 30 xvfb-run -a mgba-qt rom/working/penta_dragon_dx_teleport.gb \
--       -t save_states_for_claude/<state>.ss0 \
--       --script scripts/diagnostics/probe_white_flicker.lua -l 0

local OUT = os.getenv("OUT") or "tmp/white_flicker"
local f = 0
local MAX_FRAMES = tonumber(os.getenv("FRAMES") or "600")

local function log(msg)
  local h = io.open(OUT .. ".log", "a")
  if h then h:write(msg .. "\n"); h:close() end
end

do
  local h = io.open(OUT .. ".log", "w")
  if h then h:write("# white-flicker probe v3 (iter 241) — OAM attr tracking\n"); h:close() end
end

local function read_cram(is_obj, pal, color)
  local idx_reg = is_obj and 0xFF6A or 0xFF68
  local data_reg = is_obj and 0xFF6B or 0xFF69
  local idx = pal * 8 + color * 2
  emu:write8(idx_reg, idx)
  local lo = emu:read8(data_reg)
  emu:write8(idx_reg, idx + 1)
  local hi = emu:read8(data_reg)
  return (hi << 8) | lo
end

-- Per-slot history. attr_seen[slot][attr_pal] = first_seen_frame
local prev_attr = {}
local attr_changes_per_slot = {}
for s = 0, 39 do
  prev_attr[s] = -1
  attr_changes_per_slot[s] = 0
end

-- LCDC bit tracking
local prev_lcdc = -1
local lcdc_changes = {}

callbacks:add("frame", function()
  f = f + 1
  if f > MAX_FRAMES then
    log(string.format("DONE. final D880=%02X FFC1=%d", emu:read8(0xD880), emu:read8(0xFFC1)))
    log("--- attr changes per slot (slots with >0 changes) ---")
    for s = 0, 39 do
      if attr_changes_per_slot[s] > 0 then
        log(string.format("  slot%d: %d attr changes", s, attr_changes_per_slot[s]))
      end
    end
    log("--- LCDC bit changes ---")
    for bit = 0, 7 do
      if lcdc_changes[bit] and lcdc_changes[bit] > 0 then
        log(string.format("  bit %d: %d toggles", bit, lcdc_changes[bit]))
      end
    end
    emu:stop()
    return
  end

  if f < 60 then return end

  -- LCDC bit-level tracking
  local lcdc = emu:read8(0xFF40)
  if prev_lcdc >= 0 and lcdc ~= prev_lcdc then
    for bit = 0, 7 do
      local mask = 1 << bit
      if (lcdc & mask) ~= (prev_lcdc & mask) then
        lcdc_changes[bit] = (lcdc_changes[bit] or 0) + 1
      end
    end
  end
  prev_lcdc = lcdc

  -- OAM attr palette tracking per slot
  for s = 0, 39 do
    local y = emu:read8(0xFE00 + s * 4)
    if y > 0 and y < 160 then
      local attr = emu:read8(0xFE00 + s * 4 + 3)
      local pal = attr & 7  -- CGB OBJ palette index
      if prev_attr[s] >= 0 and pal ~= prev_attr[s] then
        attr_changes_per_slot[s] = attr_changes_per_slot[s] + 1
        if attr_changes_per_slot[s] <= 3 then  -- limit per-slot noise
          local x = emu:read8(0xFE00 + s*4 + 1)
          local tile = emu:read8(0xFE00 + s*4 + 2)
          log(string.format("f%d slot%d ATTR pal %d -> %d (Y=%d X=%d tile=%02X attr=%02X)",
              f, s, prev_attr[s], pal, y, x, tile, attr))
        end
      end
      prev_attr[s] = pal
    else
      prev_attr[s] = -1  -- slot offscreen, reset
    end
  end

  if f % 200 == 0 then
    -- Snapshot all CRAM pal entries to log (color 1 only, compact)
    local bg = ""
    for p = 0, 7 do bg = bg .. string.format(" %04X", read_cram(false, p, 1)) end
    local ob = ""
    for p = 0, 7 do ob = ob .. string.format(" %04X", read_cram(true, p, 1)) end
    log(string.format("# f%d LCDC=%02X BGc1:%s | OBJc1:%s", f, lcdc, bg, ob))
  end
end)
