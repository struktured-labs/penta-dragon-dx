-- Lockstep pixel check (issue #49). LS_MODE=record: cold boot, run LS_FRAMES with
-- input LS_INPUT, every LS_EVERY frames save state LS_DIR/s<frame>.ss.
-- LS_MODE=replay: for every saved state, load it (into this ROM), run LS_M frames
-- with the same input schedule and hash each frame.  Output LS_OUT tsv:
-- state_frame  frame  scene  screen_hash  oam_hash
local MODE = os.getenv("LS_MODE") or "record"
local DIR = os.getenv("LS_DIR")
local OUT = os.getenv("LS_OUT")
local FRAMES = tonumber(os.getenv("LS_FRAMES") or "9000")
local EVERY = tonumber(os.getenv("LS_EVERY") or "60")
local M = tonumber(os.getenv("LS_M") or "8")
local INPUT = os.getenv("LS_INPUT") or "none"
local f = assert(io.open(OUT, "w"))
f:write("state\tframe\tscene\thash\toam\n")
local function keys_for(n)
  if INPUT == "game" then
    if n >= 180 and n < 186 then return 128 end
    if (n >= 193 and n < 199) or (n >= 300 and n < 306) then return 1 end
    if n < 600 then return 0 end
    local p = (n - 600) % 480
    local k = 0
    if p < 120 then k = 16 elseif p < 200 then k = 64 elseif p < 320 then k = 32 elseif p < 400 then k = 128 end
    if (n // 8) % 3 == 0 then k = k | 1 end
    return k
  end
  return 0
end
local function hash_screen()
  local img = emu:screenshotToImage()
  local h = 2166136261
  for y = 0, 143 do for x = 0, 159 do
    h = ((h ~ (img:getPixel(x, y) & 0xFFFFFF)) * 16777619) & 0xFFFFFFFF
  end end
  return h
end
local function hash_oam()
  local h = 2166136261
  for a = 0xFE00, 0xFE9F do h = ((h ~ emu:read8(a)) * 16777619) & 0xFFFFFFFF end
  return h
end
local function scene()
  local svbk = emu:read8(0xFF70); emu:write8(0xFF70, 1)
  local s = emu:read8(0xD880); emu:write8(0xFF70, svbk); return s
end
local function done()
  f:close(); local d = io.open(OUT .. ".done", "w"); d:write("OK\n"); d:close()
end
local frame, state, finished = 0, 0, false
local list, li = {}, 0
if MODE == "replay" then
  for n = EVERY, FRAMES - M, EVERY do list[#list + 1] = n end
end
local function load_next()
  li = li + 1
  if li > #list then done(); finished = true; return end
  state = list[li]
  local path = DIR .. "/s" .. state .. ".ss"
  local ok = emu:loadStateFile(path)
  if not ok then
    local fh = io.open(path, "rb")
    if fh then local buf = fh:read("a"); fh:close(); ok = emu:loadStateBuffer(buf) end
  end
  if not ok then
    local e = io.open(OUT .. ".err", "a"); e:write("load failed " .. path .. "\n"); e:close()
    finished = true; f:close(); return
  end
  frame = state
  emu:setKeys(keys_for(frame))
end
local started = false
callbacks:add("frame", function()
  if finished then return end
  if MODE == "record" then
    frame = frame + 1
    if state > 0 and frame <= state + M then
      f:write(string.format("%d\t%d\t%02x\t%08x\t%08x\n", state, frame, scene(), hash_screen(), hash_oam()))
    end
    if frame % EVERY == 0 and frame <= FRAMES - M then
      emu:saveStateFile(DIR .. "/s" .. frame .. ".ss")
      state = frame
    end
    emu:setKeys(keys_for(frame))
    if frame >= FRAMES then done(); finished = true end
    return
  end
  if not started then started = true; load_next(); return end
  frame = frame + 1
  f:write(string.format("%d\t%d\t%02x\t%08x\t%08x\n", state, frame, scene(), hash_screen(), hash_oam()))
  if frame >= state + M then load_next() else emu:setKeys(keys_for(frame)) end
end)
