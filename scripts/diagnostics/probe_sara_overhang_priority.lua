-- #14 Sara overhang priority probe (used by verify_sara_overhang_priority.py).
-- Cold boot, native title route (Start, A x4, Select), one position assist
-- (DC00..DC03 := 1240/1344 at frame 1201, the pre-secret corridor below the
-- black ceiling overhang), Down held for frames 1202..1212, no input after.
-- Assistance: DCBB := FF from frame 1201 (health only). Samples are exact
-- frames; each writes one JSON line and a native 160x144 screenshot.
local out = assert(os.getenv('PSO_OUT'))
local SAMPLES = {[1200] = 'floor', [1240] = 'overhang-1240', [1260] = 'overhang',
                 [1300] = 'overhang-1300'}
local LAST = 1300
local wram = emu.memory.wram
local n = 0
local events = assert(io.open(out .. '/events.jsonl', 'w'))
local function oam()
  local t = {}
  for i = 0, 3 do
    t[#t + 1] = string.format('[%d,%d,%d,%d]', emu:read8(0xFE00 + 4 * i), emu:read8(0xFE01 + 4 * i),
      emu:read8(0xFE02 + 4 * i), emu:read8(0xFE03 + 4 * i))
  end
  return '[' .. table.concat(t, ',') .. ']'
end
callbacks:add('frame', function()
  n = n + 1
  local keys = 0
  if n >= 180 and n < 186 then keys = 0x80 end
  if (n >= 193 and n < 199) or (n >= 241 and n < 247) or (n >= 291 and n < 297)
      or (n >= 391 and n < 397) then keys = 0x01 end
  if n >= 341 and n < 347 then keys = 0x08 end
  if n > 1201 and n <= 1212 then keys = 0x80 end
  emu:setKeys(keys)
  if n == 1201 then
    wram:write8(0x1C00, 1240 & 255); wram:write8(0x1C01, 1240 >> 8)
    wram:write8(0x1C02, 1344 & 255); wram:write8(0x1C03, 1344 >> 8)
  end
  if n >= 1201 then wram:write8(0x1CBB, 0xFF) end
  local tag = SAMPLES[n]
  if tag then
    local shot = string.format('%s/%s.png', out, tag)
    emu:screenshot(shot)
    events:write(string.format(
      '{"kind":"sample","tag":"%s","frame":%d,"scene":%d,"world":[%d,%d],"camera":"%02X%02X",' ..
      '"lcdc":%d,"oam":%s,"flags":[%d,%d,%d,%d],"screenshot":"%s"}\n',
      tag, n, wram:read8(0x1880),
      wram:read8(0x1C00) + 256 * wram:read8(0x1C01), wram:read8(0x1C02) + 256 * wram:read8(0x1C03),
      emu:read8(0xFF42), emu:read8(0xFF43), emu:read8(0xFF40), oam(),
      emu:read8(0xFFC2), emu:read8(0xFFC3), emu:read8(0xFFC4), emu:read8(0xFFC5), shot))
    events:flush()
  end
  if n >= LAST then
    events:write(string.format('{"kind":"done","frame":%d}\n', n))
    events:close()
    os.exit(0)
  end
end)
