-- Trace HW OAM slot 1 attr (FE07) every frame to diagnose the
-- "even slots correct / odd slots palette 4" pattern. Also dump key state.
local OUT = os.getenv("OUT") or "/tmp/slot1_trace"
local STATE = os.getenv("STATE") or "save_states_for_claude/level1_sara_w_alone.ss0"
local f, done = 0, false
local LOG = io.open(OUT..".log", "w")
local function log(m) if LOG then LOG:write(m.."\n"); LOG:flush() end end
log("slot1_trace start, state="..STATE)

callbacks:add("frame", function()
  if done then return end
  f = f + 1
  if f == 10 then
    pcall(function() emu:loadStateFile(STATE) end)
    log("loaded state at f=10")
  end
  emu:setKeys(0)

  if f >= 20 and f <= 70 then
    -- Sample every frame
    local ffbe = emu:read8(0xFFBE)
    local ffbf = emu:read8(0xFFBF)
    local d880 = emu:read8(0xD880)
    local s0y = emu:read8(0xFE00); local s0t = emu:read8(0xFE02); local s0a = emu:read8(0xFE03)
    local s1y = emu:read8(0xFE04); local s1t = emu:read8(0xFE06); local s1a = emu:read8(0xFE07)
    local s2y = emu:read8(0xFE08); local s2t = emu:read8(0xFE0A); local s2a = emu:read8(0xFE0B)
    local s3y = emu:read8(0xFE0C); local s3t = emu:read8(0xFE0E); local s3a = emu:read8(0xFE0F)
    log(string.format("f%d D880=%02X FFBE=%02X FFBF=%02X | s0:y=%d t=%02X a=%02X(p%d) | s1:y=%d t=%02X a=%02X(p%d) | s2:y=%d t=%02X a=%02X(p%d) | s3:y=%d t=%02X a=%02X(p%d)",
      f, d880, ffbe, ffbf,
      s0y, s0t, s0a, s0a&7,
      s1y, s1t, s1a, s1a&7,
      s2y, s2t, s2a, s2a&7,
      s3y, s3t, s3a, s3a&7))
  end

  if f == 70 then
    done = true
    log("done")
    emu:stop()
  end
end)
