-- Probe v2: full slot 2 capture per-frame to identify pal-4 source.
local OUT = os.getenv("OUT") or "tmp/sw2_writer"
local f = 0
local h = io.open(OUT..".log","w"); h:close()
local function log(m) local h = io.open(OUT..".log","a"); h:write(m.."\n"); h:close() end

local prev_hw_attr, prev_sh_a_attr, prev_sh_b_attr = -1, -1, -1
callbacks:add("frame", function()
  f = f + 1
  if f < 60 then return end
  if f > 250 then emu:stop(); return end
  -- Read slot 2: y=0xFE08, x=0xFE09, tile=0xFE0A, attr=0xFE0B
  local hw_attr = emu:read8(0xFE0B)
  local hw_tile = emu:read8(0xFE0A)
  local sh_a_attr = emu:read8(0xC00B)
  local sh_a_tile = emu:read8(0xC00A)
  local sh_b_attr = emu:read8(0xC10B)
  local sh_b_tile = emu:read8(0xC10A)
  if hw_attr ~= prev_hw_attr or sh_a_attr ~= prev_sh_a_attr or sh_b_attr ~= prev_sh_b_attr then
    log(string.format("f%d HW: t=%02X a=%02X(p%d) | shA: t=%02X a=%02X(p%d) | shB: t=%02X a=%02X(p%d)",
      f, hw_tile, hw_attr, hw_attr & 7,
      sh_a_tile, sh_a_attr, sh_a_attr & 7,
      sh_b_tile, sh_b_attr, sh_b_attr & 7))
    prev_hw_attr, prev_sh_a_attr, prev_sh_b_attr = hw_attr, sh_a_attr, sh_b_attr
  end
end)
