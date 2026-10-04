-- Stage-1 Continue palette probe (miniboss and no-boss control).
-- Cold boot through the native title route. Assistance (memory only, declared
-- in the verifier): DCBB=FF keepalive before the death stimulus; for the
-- miniboss case DCB8=section-1 plus DCBA=1/FFD6=1E pulses until the native
-- Gargoyle spawns (FFBF!=0); then FFE6=1 (one credit) and DCBB=0. The control
-- walks a fixed pattern so a native hit applies the lethal HP. Continue is
-- accepted with native A presses. Every CRAM data write (FF69/FF6B) from the
-- death onward is logged with LY and STAT.
local out = assert(os.getenv('PMC_OUT'))
local case = assert(os.getenv('PMC_CASE'))   -- 'miniboss' or 'control'
local wram = assert(emu.memory.wram)
local ev = assert(io.open(out .. '/events.jsonl', 'w'))
local n = 0
local gameAt, mbAt, deathAt, firstPoll, resumeAt = nil, nil, nil, nil, nil
local hold = 120
local function E(kind, fields)
  local parts = {string.format('"frame":%d,"kind":"%s"', n, kind)}
  for k, v in pairs(fields or {}) do
    if type(v) == 'number' then parts[#parts + 1] = string.format('"%s":%d', k, v)
    else parts[#parts + 1] = string.format('"%s":"%s"', k, tostring(v)) end
  end
  ev:write('{' .. table.concat(parts, ',') .. '}\n'); ev:flush()
end
local function cram(tag, png)
  local s68, s6a = emu:read8(0xFF68), emu:read8(0xFF6A)
  local bg, obj = {}, {}
  for i = 0, 63 do emu:write8(0xFF68, i); bg[#bg + 1] = string.format('%02X', emu:read8(0xFF69)) end
  for i = 0, 63 do emu:write8(0xFF6A, i); obj[#obj + 1] = string.format('%02X', emu:read8(0xFF6B)) end
  emu:write8(0xFF68, s68); emu:write8(0xFF6A, s6a)
  if png then emu:screenshot(string.format('%s/%s.png', out, tag)) end
  E('cram', {tag = tag, bg = table.concat(bg), obj = table.concat(obj),
             scene = wram:read8(0x1880), ffbf = emu:read8(0xFFBF)})
end
local writes = 0
local function watch(port)
  emu:setWatchpoint(function()
    if not deathAt or (resumeAt and n > resumeAt + 300) then return end
    writes = writes + 1
    local stat = emu:read8(0xFF41)
    if stat & 3 == 3 then
      E('mode3_write', {port = port, index = emu:read8(port - 1), ly = emu:read8(0xFF44),
                        pc = emu:readRegister('pc')})
    end
  end, port, C.WATCHPOINT_TYPE.WRITE)
end
watch(0xFF69); watch(0xFF6B)
emu:setBreakpoint(function()
  if deathAt and not firstPoll then firstPoll = n; E('continue_poll') end
end, 0x4A9C)
callbacks:add('frame', function()
  n = n + 1
  local keys = 0
  local scene = wram:read8(0x1880)
  local ffbf = emu:read8(0xFFBF)
  local ffc1 = emu:read8(0xFFC1)
  if not gameAt then
    if n >= 180 and n < 186 then keys = 0x80 end
    for _, first in ipairs({193, 241, 291, 391}) do if n >= first and n < first + 6 then keys = 1 end end
    if n >= 341 and n < 347 then keys = 8 end
    if n > 460 and n % 40 < 6 then keys = (n % 80 < 40) and 1 or 8 end
    if ffc1 == 1 and scene == 2 and n > 300 then gameAt = n; E('gameplay') end
  elseif not mbAt then
    wram:write8(0x1CBB, 0xFF)
    keys = (n % 8 == 0) and 1 or 0
    if case == 'control' and n == gameAt + 200 then mbAt = n; E('control_start') end
    if case == 'miniboss' then
      if n == gameAt + 150 then wram:write8(0x1CB8, 1) end
      if n >= gameAt + 150 and (n - gameAt) % 60 == 30 and wram:read8(0x1CB8) == 1 then
        wram:write8(0x1CBA, 1); emu:write8(0xFFD6, 0x1E)
      end
      if ffbf ~= 0 and n > gameAt + 150 then mbAt = n; E('miniboss', {ffbf = ffbf, scene = scene}) end
    end
  elseif not deathAt then
    if n < mbAt + hold then wram:write8(0x1CBB, 0xFF) end
    if n == mbAt + hold - 2 then cram('pre-death', true) end
    if n == mbAt + hold then emu:write8(0xFFE6, 1); wram:write8(0x1CBB, 0); E('stimulus') end
    if case == 'control' and n > mbAt + hold then
      keys = ({0x40, 0x10, 0x80, 0x20})[((n - mbAt - hold) // 45) % 4 + 1]
    end
    if scene == 0x17 then deathAt = n; E('death') end
    if n == mbAt + hold + 1500 then E('no_death'); ev:close(); os.exit(3) end
  else
    if not resumeAt then
      local anchor = firstPoll or (deathAt + 200)
      if n >= anchor + 12 and (n - anchor - 12) % 12 < 6 and n < anchor + 440 then keys = 1 end
      if scene ~= 0x17 and ffc1 == 1 and n > deathAt + 30 then
        resumeAt = n; E('resume', {scene = scene, ffbf = ffbf})
      end
      if n == deathAt + 900 then E('no_resume'); ev:close(); os.exit(3) end
    else
      local d = n - resumeAt
      if d == 30 or d == 60 or d == 300 then cram(string.format('resume+%d', d), d ~= 60) end
      if d == 301 then E('done', {cram_writes = writes}); ev:close(); os.exit(0) end
    end
  end
  emu:setKeys(keys)
  if n == 9000 then E('limit'); ev:close(); os.exit(4) end
end)
