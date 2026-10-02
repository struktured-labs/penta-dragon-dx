-- Per-frame screen hash (issue #49 prototype pixel-identity / attract-demo check).
-- PIX_OUT: tsv path; PIX_FRAMES: frames to run; PIX_INPUT: "none" or "play"
local OUT = os.getenv("PIX_OUT") or "tmp/pix.tsv"
local FRAMES = tonumber(os.getenv("PIX_FRAMES") or "6000")
local MODE = os.getenv("PIX_INPUT") or "none"
local f = assert(io.open(OUT, "w"))
f:write("frame\tscene\thash\n")
local frame = 0
-- play script: START presses to get through title into stage 1, then a
-- fixed directional/fire pattern (A=1 B=2 SEL=4 START=8 R=16 L=32 U=64 D=128)
local function keys_for(n)
  if MODE == "game" then
    -- verify_game_start_routes "delayed" A route: Down@180, A@193, stage A@300
    if n >= 180 and n < 186 then return 128 end
    if (n >= 193 and n < 199) or (n >= 300 and n < 306) then return 1 end
    if n < 600 then return 0 end
    local p = (n - 600) % 480
    local k = 0
    if p < 120 then k = 16 elseif p < 200 then k = 64 elseif p < 320 then k = 32 elseif p < 400 then k = 128 end
    if (n // 8) % 3 == 0 then k = k | 1 end
    return k
  end
  if MODE ~= "play" then return 0 end
  for _, s in ipairs({400, 520, 640, 760, 880}) do
    if n >= s and n < s + 6 then return 8 end
  end
  if n < 1000 then return 0 end
  local p = (n - 1000) % 480
  local k = 0
  if p < 120 then k = 16 elseif p < 200 then k = 64 elseif p < 320 then k = 32 elseif p < 400 then k = 128 end
  if (n // 8) % 3 == 0 then k = k | 1 end
  return k
end
local function hash_screen()
  local img = emu:screenshotToImage()
  local h = 2166136261
  for y = 0, 143 do
    for x = 0, 159 do
      h = ((h ~ (img:getPixel(x, y) & 0xFFFFFF)) * 16777619) & 0xFFFFFFFF
    end
  end
  return h
end
callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(keys_for(frame))
  local svbk = emu:read8(0xFF70)
  emu:write8(0xFF70, 1)
  local scene = emu:read8(0xD880)
  emu:write8(0xFF70, svbk)
  f:write(string.format("%d\t%02x\t%08x\n", frame, scene, hash_screen()))
  if frame >= FRAMES then
    f:close()
    local d = io.open(OUT .. ".done", "w"); d:write("OK\n"); d:close()
    frame = -1e9
  end
end)
