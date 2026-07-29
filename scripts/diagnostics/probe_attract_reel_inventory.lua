-- Inventory every sprite-bearing episode in one cold-boot title/attract cycle.
--
-- This deliberately does not take screenshots: mgba-headless can execute the
-- long idle sequence quickly, while screenshots force the Qt renderer onto the
-- real-time path.  The companion Python verifier turns this trace into episode
-- summaries and can then request only the useful visual frames.

local OUT = os.getenv("ATTRACT_OUT") or "/tmp/penta-attract-inventory.tsv"
local FRAMES = tonumber(os.getenv("ATTRACT_FRAMES") or "14000")
local SAMPLE_EVERY = tonumber(os.getenv("ATTRACT_SAMPLE_EVERY") or "4")

local frame = 0
local previous_scene = -1
local previous_visible = -1
local report = assert(io.open(OUT, "w"))
report:write("kind\tframe\td880\tffc1\tffba\tffbf\tffbe\tfff2\tdd09\tvisible\thw_oam\tshadow_c000\tshadow_c100\n")

local function visible_oam(base)
  local sprites = {}
  for slot = 0, 39 do
    local address = base + slot * 4
    local y = emu:read8(address)
    local x = emu:read8(address + 1)
    local tile = emu:read8(address + 2)
    local attr = emu:read8(address + 3)
    -- GB OAM coordinates include the hardware offsets (Y-16, X-8).
    if y > 0 and y < 160 and x > 0 and x < 168 then
      table.insert(sprites, string.format(
        "%d:%d:%d:%02X:%02X", slot, y, x, tile, attr))
    end
  end
  return sprites
end

local function join(values)
  return table.concat(values, ",")
end

local function write_sample(kind, scene, ffc1, ffba, ffbf, ffbe, fff2, dd09, hw, c000, c100)
  report:write(string.format(
    "%s\t%d\t%02X\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%d\t%s\t%s\t%s\n",
    kind, frame, scene, ffc1, ffba, ffbf, ffbe, fff2, dd09, #hw,
    join(hw), join(c000), join(c100)))
end

callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)

  local scene = emu:read8(0xD880)
  local ffc1 = emu:read8(0xFFC1)
  local ffba = emu:read8(0xFFBA)
  local ffbf = emu:read8(0xFFBF)
  local ffbe = emu:read8(0xFFBE)
  local fff2 = emu:read8(0xFFF2)
  local dd09 = emu:read8(0xDD09)
  local hw = visible_oam(0xFE00)
  local c000 = visible_oam(0xC000)
  local c100 = visible_oam(0xC100)
  local visible = #hw

  local kind = nil
  if scene ~= previous_scene then
    kind = "scene"
  elseif visible ~= previous_visible then
    kind = "edge"
  elseif visible > 0 and frame % SAMPLE_EVERY == 0 then
    kind = "sample"
  end
  if kind ~= nil then
    write_sample(kind, scene, ffc1, ffba, ffbf, ffbe, fff2, dd09, hw, c000, c100)
  end

  previous_scene = scene
  previous_visible = visible
  if frame >= FRAMES then
    write_sample("done", scene, ffc1, ffba, ffbf, ffbe, fff2, dd09, hw, c000, c100)
    report:flush()
    report:close()
    local done = io.open(OUT .. ".done", "w")
    if done then
      done:write("OK\n")
      done:close()
    end
  end
end)
