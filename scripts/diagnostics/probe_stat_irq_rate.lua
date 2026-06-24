-- Probe: count STAT IRQ rate via DB50 stub execution counter (write to scratch)
-- Patch the stub at runtime to INC a counter byte in WRAM (0xCFFE — known free).
local OUT = os.getenv("OUT") or "tmp/stat_rate"
local f = 0
local patched = false
local h = io.open(OUT..".log","w"); h:close()
local function log(m) local h = io.open(OUT..".log","a"); h:write(m.."\n"); h:close() end

callbacks:add("frame", function()
  f = f + 1
  if not patched and f == 30 then
    -- Patch STAT stub PROLOGUE: instead of PUSH AF (1B), make it INC [0xCFFE]
    -- A simple counter at HRAM ($FFFE is stack but $CFFE is WRAM far end)
    -- The stub starts at 0xDB50. First byte is 0xF5 (PUSH AF).
    -- Replace first 4 bytes with: LD HL, 0xCFFE; INC [HL]; PUSH AF (4 bytes squeezed isn't possible)
    -- Alternative: just sample FF41 to see STAT state
    log("# STAT register state samples (FF41 mode bits + LYC + interrupt enable):")
    patched = true
  end
  if f == 60 or f == 100 or f == 200 then
    local stat = emu:read8(0xFF41)
    local lyc = emu:read8(0xFF45)
    local ie = emu:read8(0xFFFF)
    local ime_sample = -- not directly readable
    log(string.format("f%d: STAT=%02X (mode=%d, LYC_match=%d, sources=mode0:%d mode1:%d mode2:%d lyc:%d) LYC=%d IE=%02X",
        f, stat, stat & 3, (stat >> 2) & 1,
        (stat >> 3) & 1, (stat >> 4) & 1, (stat >> 5) & 1, (stat >> 6) & 1,
        lyc, ie))
  end
  if f > 220 then emu:stop() end
end)
