-- Natural default OPENING selection. No game-memory or ROM writes.
local OUT = assert(os.getenv('OPENING_INVENTORY_OUT'))
local LIMIT = tonumber(os.getenv('OPENING_INVENTORY_FRAMES') or '12000')
local report = assert(io.open(OUT .. '/capture.tsv', 'w'))
local f, last_scene, last_panel, count = 0, -1, -1000, 0
local reached, finished = false, false
local addresses = {0xDCE2,0xDCE5,0xDCE6,0xDCE7,0xDCE8,0xDCE9,0xDCEA,
  0xDCEB,0xDCEE,0xDCEF,0xDCF0,0xDD07,0xDF07,0xDF49,0xDF4A}
local function game(a) return emu.memory.wram:read8(a-0xC000) end
local function finish()
  if finished then return end
  finished = true
  emu:setKeys(0)
  report:write('done\t' .. (reached and '1' or '0') .. '\n')
  report:close()
  local marker = assert(io.open(OUT .. '/capture.done', 'w'))
  marker:write('complete\n')
  marker:close()
end
callbacks:add('frame', function()
  if finished then return end
  f = f + 1
  local scene = game(0xD880)
  if scene ~= last_scene then
    report:write(string.format('scene\t%d\t%d\t%d\t%d\t%d\n', f,scene,
      emu:read8(0xFFC1),emu:read8(0xFFBA),emu:read8(0xFFE4)))
    last_scene = scene
  end
  if scene == 0x15 then reached = true end
  local press = (not reached and f>=180 and f<=1800 and f%120<4)
    or (reached and scene==0x15 and f%300<2)
  emu:setKeys(press and 1 or 0)
  if scene == 0x15 and f-last_panel>=360 then
    count=count+1
    local lcdc,sy,sx=emu:read8(0xFF40),emu:read8(0xFF42),emu:read8(0xFF43)
    local base=(lcdc&8)~=0 and 0x1C00 or 0x1800
    local tiles,attrs,state={},{},{}
    -- This mGBA raw VRAM domain exposes bank zero only. Read bank-one
    -- attributes through the bus, restoring VBK before CPU execution resumes.
    local old_vbk=emu:read8(0xFF4F)
    emu:write8(0xFF4F,1)
    for row=0,17 do
      for col=0,19 do
        local a=base+(((sy+row*8)>>3)&31)*32+(((sx+col*8)>>3)&31)
        tiles[#tiles+1]=string.format('%02X',emu.memory.vram:read8(a))
        attrs[#attrs+1]=string.format('%02X',emu:read8(0x8000+a))
      end
    end
    emu:write8(0xFF4F,old_vbk)
    for _,a in ipairs(addresses) do state[#state+1]=string.format('%02X',game(a)) end
    local name=string.format('panel%02d_f%d.png',count,f)
    emu:screenshot(OUT .. '/' .. name)
    report:write(string.format('panel\t%d\t%s\t%s\t%s\t%s\n',f,
      table.concat(tiles),table.concat(attrs),table.concat(state),name))
    last_panel=f
  end
  report:flush()
  if reached and (scene==0 or scene==1 or scene==0x1C) and f-last_panel>120 then finish() end
  if f>=LIMIT then finish() end
end)
