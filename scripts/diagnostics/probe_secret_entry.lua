-- Diagnostic probe: read-only by default; explicit ENTRY_* assistance is recorded by the runner.
local out=assert(os.getenv('ENTRY_OUT'))
local n=0
local frames=tonumber(os.getenv('ENTRY_FRAMES') or '1200')
local continuous=os.getenv('ENTRY_CONTINUOUS_SECRET')=='1'
local warpFrame=tonumber(os.getenv('ENTRY_WARP_FRAME') or '1201')
local pendingWarp=nil
local previousScene,previousStage=-1,-1
local wram=assert(emu.memory.wram)
-- #45: distinguish data consumption from execution at byte-shaped reference
-- sites. FF99 is the software bank shadow, recorded explicitly, not a claim
-- that these observations prove global unreachability or allocation safety.
if os.getenv('ENTRY_FADE_REFERENCE_READERS')=='1' then
 local log=assert(io.open(out..'/fade-reference-readers.tsv','w'))
 log:write('kind\tframe\tcycle\tfile_offset\tpc\tbank_shadow\thl\tde\tbc\n')
 log:flush()
 for _,offset in ipairs({0x1918A,0x2C2DF,0x2C60F,0x2CCD9,0x2D4D7,
                         0x2D55B,0x2D763,0x34364,0x36264,0x40364,
                         0x42264,0x80364,0x82264}) do
  local physical=offset
  local bank=math.floor(physical/0x4000)
  local address=0x4000+(physical%0x4000)
  local function record(kind)
   local shadow=emu:read8(0xFF99)
   if shadow~=bank then return end
   log:write(string.format('%s\t%d\t%d\t%06X\t%04X\t%02X\t%04X\t%04X\t%04X\n',
    kind,n,emu:currentCycle(),physical,emu:readRegister('PC')&65535,shadow,
    emu:readRegister('HL')&65535,emu:readRegister('DE')&65535,
    emu:readRegister('BC')&65535))
   log:flush()
  end
  assert(emu:setWatchpoint(function() record('read') end,address,C.WATCHPOINT_TYPE.READ)>0)
  assert(emu:setBreakpoint(function() record('execute') end,address)>0)
 end
end
-- #45 placement investigation on the unmodified fixed-bank parent. Data
-- reads and instruction entry are separate observations; neither proves
-- global unreachability. Do not read watched bytes from inside callbacks.
if os.getenv('ENTRY_FIXED_FADE_ALLOCATION')=='1' then
 local log=assert(io.open(out..'/fixed-fade-allocation.tsv','w'))
 log:write('kind\tframe\tcycle\taddress\tpc\tbank\n')
 log:flush()
 local function record(kind,address)
  log:write(string.format('%s\t%d\t%d\t%04X\t%04X\t%02X\n',
   kind,n,emu:currentCycle(),address,emu:readRegister('PC')&65535,
   emu:read8(0xFF99)))
  log:flush()
 end
 for site=0xCF,0xE0 do
  local address=site
  assert(emu:setWatchpoint(function() record('read',address) end,
   address,C.WATCHPOINT_TYPE.READ)>0)
  assert(emu:setBreakpoint(function() record('execute',address) end,address)>0)
 end
end
-- #45 exact 988b late-route layout only; opt-in, read-only and bounded by run.
if os.getenv('ENTRY_RETURN_FADE_WINDOW')=='1' then
 local log=assert(io.open(out..'/return-fade-window.tsv','w'))
 log:write('kind\tframe\tcycle\tpc\tly\tstat\tbgp\tobp\tkey1\n')
 local pending=false
 local function record(kind,pc)
  log:write(string.format('%s\t%d\t%d\t%04X\t%d\t%02X\t%02X\t%02X\t%02X\n',
   kind,n,emu:currentCycle(),pc,emu:read8(0xFF44),emu:read8(0xFF41),
   emu:read8(0xFF47),emu:read8(0xFF48),emu:read8(0xFF4D)))
  log:flush()
 end
 for _,site in ipairs({{'acquire',0x5BF8},{'ready',0x5C0F},{'final_upload_end',0x5BF7}}) do
  local kind,pc=site[1],site[2]
  assert(emu:setBreakpoint(function()
   if emu:read8(0xFF99)~=20 then return end
   if kind=='acquire' then
    if pending then return end
    pending=true
   elseif kind=='ready' then pending=false end
   record(kind,pc)
  end,pc)>0)
 end
end
if os.getenv('ENTRY_RETURN_POLL_PHASE')=='1' then
 local phase=assert(io.open(out..'/return-poll-phase.tsv','w'))
 phase:write('cycle\tpc\tbank\tsp\tstack\taf\tbc\tly\tstat\n')
 local sites={{0x0040,0},{0x081D,0},{0x0048,0},{0x086B,0}}
 -- Exact native-control and trial04 mode-test instructions; bounded third wait.
 for _,base in ipairs({{0x407E,1},{0x63ED,20}}) do
  for _,offset in ipairs({0,2,4,6,8,10,12,13,15}) do
   table.insert(sites,{base[1]+offset,base[2]})
  end
 end
 for _,site in ipairs(sites) do
  local pc,bank=site[1],site[2]
  assert(emu:setBreakpoint(function()
   local cycle=emu:currentCycle()
   if cycle<1137842700 or cycle>1137860300 then return end
   if bank~=0 and emu:read8(0xFF99)~=bank then return end
   local sp=emu:readRegister('SP')&65535
   phase:write(string.format('%d\t%04X\t%02X\t%04X\t%04X\t%04X\t%04X\t%d\t%02X\n',
    cycle,pc,emu:read8(0xFF99),sp,emu:read8(sp)|(emu:read8((sp+1)&65535)<<8),
    emu:readRegister('AF')&65535,emu:readRegister('BC')&65535,
    emu:read8(0xFF44),emu:read8(0xFF41)))
   phase:flush()
  end,pc)>0)
 end
end
if os.getenv('ENTRY_RETURN_LOADER_TIMING')=='1' then
 local timing=assert(io.open(out..'/return-loader-timing.tsv','w'))
 timing:write('frame\tcycle\tpc\tbank\tsp\tly\ttick\tscene\tstage\tb\tstat\n')
 local sites={{0x0F33,0},{0x0F47,0},{0x0F64,0},{0x4068,1},{0x406E,1},
                      {0x5C22,20},{0x5C83,20},
                      {0x09A2,0},{0x4F7E,1},{0x0C29,0},{0x0C96,0},
                      {0x1EC0,0},{0x0038,0}}
 -- Exact trial04 labels only; never treat these as universal bank20 entries.
 if os.getenv('ENTRY_RETURN_LOCAL_WAIT_TIMING')=='1' then
  for _,site in ipairs({{0x63C1,20},{0x63E6,20}}) do table.insert(sites,site) end
 end
 for _,site in ipairs(sites) do
  local pc,bank=site[1],site[2]
  assert(emu:setBreakpoint(function()
   if bank~=0 and emu:read8(0xFF99)~=bank then return end
   timing:write(string.format('%d\t%d\t%04X\t%02X\t%04X\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\n',
    n,emu:currentCycle(),pc,emu:read8(0xFF99),emu:readRegister('SP')&65535,
    emu:read8(0xFF44),emu:read8(0xFFD4),wram:read8(0x1880),emu:read8(0xFFBA),
    (emu:readRegister('BC')>>8)&255,emu:read8(0xFF41)))
   timing:flush()
  end,pc)>0)
 end
end
if os.getenv('ENTRY_SECRET_FADE_TIMING')=='1' then
 local fade=assert(io.open(out..'/secret-fade-timing.tsv','w'))
 fade:write('frame\tcycle\tpc\tbank\tsp\tly\ttick\tscene\tstage\n')
 for _,site in ipairs({0x1460,0x1482,0x1498,0x149B,0x1473,0x1476,0x1479,
                      0x15DA,0x0F7A,0x15DD,0x15E2,0x75F0,0x0F33}) do
  local pc=site
  assert(emu:setBreakpoint(function()
   if n<tonumber(os.getenv('ENTRY_FADE_FIRST') or '2400') or
      n>tonumber(os.getenv('ENTRY_FADE_LAST') or '2700') then return end
   if pc==0x75F0 and emu:read8(0xFF99)~=1 then return end
   fade:write(string.format('%d\t%d\t%04X\t%02X\t%04X\t%d\t%02X\t%02X\t%02X\n',
    n,emu:currentCycle(),pc,emu:read8(0xFF99),emu:readRegister('SP')&65535,
    emu:read8(0xFF44),emu:read8(0xFFD4),wram:read8(0x1880),emu:read8(0xFFBA)))
   fade:flush()
  end,pc)>0)
 end
end
if os.getenv('ENTRY_MAP_GATE_TIMING')=='1' then
 local gate=assert(io.open(out..'/map-gate-timing.tsv','w'))
 gate:write('frame\tcycle\tpc\tactive\tce\tscene\n')
 for _,site in ipairs({0x13CD,0x13D2}) do
  local pc=site
  assert(emu:setBreakpoint(function()
   if n<1000 then return end
   gate:write(string.format('%d\t%d\t%04X\t%02X\t%02X\t%02X\n',
    n,emu:currentCycle(),pc,emu:read8(0xFFC1),emu:read8(0xFFCE),wram:read8(0x1880)))
   gate:flush()
  end,pc)>0)
 end
end
if os.getenv('ENTRY_TITLE_INPUT_TIMING')=='1' then
 local input=assert(io.open(out..'/title-input-timing.tsv','w'))
 input:write('frame\tcycle\tpc\ta\tf\tsp\tly\tjoy\tedge\ttick\tscene\n')
 -- #35: native title selection return and transition, bounded to exit window.
 for _,site in ipairs({0x3B26,0x3B37,0x3B3F}) do
  local pc=site
  assert(emu:setBreakpoint(function()
   if n<190 or n>195 then return end
   input:write(string.format('%d\t%d\t%04X\t%02X\t%02X\t%04X\t%d\t%02X\t%02X\t%02X\t%02X\n',
    n,emu:currentCycle(),pc,emu:readRegister('A')&255,emu:readRegister('F')&255,
    emu:readRegister('SP')&65535,emu:read8(0xFF44),emu:read8(0xFF93),
    emu:read8(0xFF94),emu:read8(0xFFD4),wram:read8(0x1880)))
   input:flush()
  end,pc)>0)
 end
end
if os.getenv('ENTRY_RETURN_BUILD')=='1' then
 local trace=assert(io.open(out..'/return-build.tsv','w'))
 trace:write('frame\tcycle\tpc\tbank\ta\tce\tcache\tpage\trequest\tsource\n')
 for _,site in ipairs({0x16DD,0x5077,0x1303,0x4284,0x4295,0x42ED,0x0F7A,0x15E2}) do
  local pc=site
  assert(emu:setBreakpoint(function()
   local bank=emu:read8(0xFF99)
   if pc>=0x4000 and bank~=1 then return end
   local source={}
   for i=0,31 do source[#source+1]=string.format('%02X',wram:read8(0x1A0+i)) end
   trace:write(string.format('%d\t%d\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%s\n',
    n,emu:currentCycle(),pc,bank,emu:readRegister('A')&255,emu:read8(0xFFCE),
    wram:read8(0x1CFD),wram:read8(0x1C0B),emu:read8(0xFFC4),table.concat(source)))
   trace:flush()
  end,pc)>0)
 end
end
if os.getenv('ENTRY_RETURN_PUBLICATION')=='1' then
 local trace=assert(io.open(out..'/return-publication.tsv','w'))
 trace:write('frame\tcycle\taddress\told\tnew\tpc\tbank\tly\tscene\tstage\tactive\tpending\n')
 for _,site in ipairs({0xFF40,0xFF47,0xDF5C}) do
  local address=site
  assert(emu:setWatchpoint(function(info)
   if address==0xDF5C and (emu:read8(0xFF70)&7)>1 then return end
   trace:write(string.format('%d\t%d\t%04X\t%02X\t%02X\t%04X\t%02X\t%d\t%02X\t%02X\t%02X\t%02X\n',
    n,emu:currentCycle(),address,info.oldValue&255,info.newValue&255,
    emu:readRegister('PC')&65535,emu:read8(0xFF99),emu:read8(0xFF44),
    wram:read8(0x1880),emu:read8(0xFFBA),emu:read8(0xFFC1),wram:read8(0x1F5C)))
   trace:flush()
  end,address,C.WATCHPOINT_TYPE.WRITE)>0)
 end
end
local itemTrace=nil
if os.getenv('ENTRY_PAUSE_ITEM_USE')=='1' then
 itemTrace=assert(io.open(out..'/item-action.tsv','w'))
 itemTrace:write('frame\tmenu\tgroup\tcursor\tpause_timer\tslot0\tslot1\n')
end
if os.getenv('ENTRY_SECRET_PUBLICATION')=='1' then
 local publication=assert(io.open(out..'/secret-publication.tsv','w'))
 publication:write('frame\tcycle\told_lcdc\tlcdc\tscene\tstage\tmenu\tpc\tbank\ttiles\tattrs\n')
 assert(emu:setWatchpoint(function(info)
  if wram:read8(0x1880)~=9 or emu:read8(0xFFBA)~=7 then return end
  local value=info.newValue&255
  local base=(value&8)~=0 and 0x1C00 or 0x1800
  -- Pinned core memory-domain segment stride is GB_SIZE_VRAM=4000,
  -- despite each physical bank containing only2000 bytes. No serialization.
  local tiles,attrs={},{}
  for i=0,767 do
   tiles[#tiles+1]=string.format('%02X',emu.memory.vram:read8(base+i))
   attrs[#attrs+1]=string.format('%02X',emu.memory.vram:read8(0x4000+base+i))
  end
  publication:write(string.format('%d\t%d\t%02X\t%02X\t09\t07\t%02X\t%04X\t%02X\t%s\t%s\n',
   n,emu:currentCycle(),info.oldValue&255,value,emu:read8(0xFFE4),
   emu:readRegister('PC')&65535,emu:read8(0xFF99),table.concat(tiles),table.concat(attrs)))
  publication:flush()
 end,0xFF40,C.WATCHPOINT_TYPE.WRITE)>0)
end
if os.getenv('ENTRY_TITLE_HELPER_TIMING')=='1' then
 local title=assert(io.open(out..'/title-helper.tsv','w'))
 title:write('event\tframe\tcycle\tpc\tsp\tbc\tde\thl\tdc09\tly\tmode\n')
 for _,site in ipairs({{'enter',0x6A57},{'return0',0x6A83},{'return7',0x6A8C}}) do
  local name,pc=site[1],site[2]
  emu:setBreakpoint(function()
   if emu:read8(0xFF99)~=13 then return end
   title:write(string.format('%s\t%d\t%d\t%04X\t%04X\t%04X\t%04X\t%04X\t%02X\t%d\t%d\n',
    name,n,emu:currentCycle(),pc,emu:readRegister('SP')&65535,
    emu:readRegister('BC')&65535,emu:readRegister('DE')&65535,
    emu:readRegister('HL')&65535,wram:read8(0x1C09),emu:read8(0xFF44),emu:read8(0xFF41)&3))
   title:flush()
  end,pc)
 end
end
if os.getenv('ENTRY_CRAM_TIMING')=='1' then
 local cram=assert(io.open(out..'/cram-timing.tsv','w'))
 cram:write('frame\tcycle\tport\tindex\tvalue\tpc\tbank\tlcdc\tmode\tly\tie\tscene\tstage\n')
 for _,port in ipairs({0xFF69,0xFF6B}) do
  local address=port
  assert(emu:setWatchpoint(function(info)
   cram:write(string.format('%d\t%d\t%04X\t%02X\t%02X\t%04X\t%02X\t%02X\t%d\t%d\t%02X\t%02X\t%02X\n',
    n,emu:currentCycle(),address,emu:read8(address-1),info.newValue&255,
    emu:readRegister('PC')&65535,emu:read8(0xFF99),emu:read8(0xFF40),emu:read8(0xFF41)&3,
    emu:read8(0xFF44),emu:read8(0xFFFF),wram:read8(0x1880),emu:read8(0xFFBA)))
   cram:flush()
  end,address,C.WATCHPOINT_TYPE.WRITE)>0)
 end
end
if os.getenv('ENTRY_NATIVE_WARP_TRACE')=='1' then
 local warpTrace=assert(io.open(out..'/native-warp.tsv','w'))
 warpTrace:write('event\tframe\tcycle\tde\thl\tevent_id\tca\tx\ty\n')
 for _,site in ipairs({{'dispatch',0x13E5},{'transfer',0x151D},{'match',0x164E},{'position',0x15F7}}) do
  local name,pc=site[1],site[2]
  emu:setBreakpoint(function()
   warpTrace:write(string.format('%s\t%d\t%d\t%04X\t%04X\t%02X\t%02X\t%d\t%d\n',name,n,emu:currentCycle(),emu:readRegister('DE')&65535,emu:readRegister('HL')&65535,emu:read8(0xFFD3),emu:read8(0xFFCA),wram:read8(0x1C00)+256*wram:read8(0x1C01),wram:read8(0x1C02)+256*wram:read8(0x1C03)))
   warpTrace:flush()
  end,pc)
 end
end
if os.getenv('ENTRY_WARP_AT_LOOP')=='1' then
 emu:setBreakpoint(function()
  if pendingWarp then
   local x,y=pendingWarp[1],pendingWarp[2]
   wram:write8(0x1C00,x&255);wram:write8(0x1C01,x>>8)
   wram:write8(0x1C02,y&255);wram:write8(0x1C03,y>>8)
   pendingWarp=nil
  end
 end,0x016C)
end
local hist={}
if os.getenv('ENTRY_ACTOR_BOUNDARY')=='1' then
 local trace=assert(io.open(out..'/actor-boundary.tsv','w'))
 trace:write('event\tframe\tcycle\tactors\n')
 for _,site in ipairs({{'loop',0x016C},{'boss',0x2B91}}) do
  local name,pc=site[1],site[2]
  emu:setBreakpoint(function()
   local bytes={}
   for address=0x1C00,0x1CBF do bytes[#bytes+1]=string.format('%02X',wram:read8(address)) end
   trace:write(string.format('%s\t%d\t%d\t%s\n',name,n,emu:currentCycle(),table.concat(bytes)))
   trace:flush()
  end,pc)
 end
end
if os.getenv('ENTRY_BOSS_IRQ_RETURN')=='1' then
 local trace=assert(io.open(out..'/boss-irq-return.tsv','w'))
 trace:write('event\tframe\tcycle\tsp\tstack_pc\n')
 for _,site in ipairs({{'vblank',0x40},{'stat',0x48},{'timer',0x50},{'ret_site',tonumber(os.getenv('ENTRY_IRQ_SITE') or '2BD7',16)}}) do
  local name,pc=site[1],site[2]
  emu:setBreakpoint(function()
   if n<tonumber(os.getenv('ENTRY_IRQ_FROM') or '1488') or n>tonumber(os.getenv('ENTRY_IRQ_TO') or '1500') then return end
   local sp=emu:readRegister('SP')&65535
   trace:write(string.format('%s\t%d\t%d\t%04X\t%04X\n',name,n,emu:currentCycle(),sp,emu:read8(sp)|(emu:read8((sp+1)&65535)<<8)))
   trace:flush()
  end,pc)
 end
end
if os.getenv('ENTRY_BOSS_CADENCE')=='1' then
 local timing=assert(io.open(out..'/boss-cadence.tsv','w'))
 timing:write('event\tframe\tcycle\tsp\tie\ta\tf\tbc\tde\thl\n')
 local function record(event)
  timing:write(string.format('%s\t%d\t%d\t%04X\t%02X\t%02X\t%02X\t%04X\t%04X\t%04X\n',event,n,emu:currentCycle(),emu:readRegister('SP')&65535,emu:read8(0xFFFF),emu:readRegister('A')&255,emu:readRegister('F')&255,emu:readRegister('BC')&65535,emu:readRegister('DE')&65535,emu:readRegister('HL')&65535))
  timing:flush()
 end
 emu:setBreakpoint(function() record('loop') end,0x016C)
 emu:setBreakpoint(function() record('boss_enter') end,0x2B91)
 emu:setBreakpoint(function() record('boss_caller_resume') end,0x2842)
 emu:setBreakpoint(function() record('boss_return') end,tonumber(os.getenv('ENTRY_BOSS_RETURN') or '2BD9',16))
end
if os.getenv('ENTRY_BOSS_DMA')=='1' then
 local actual=assert(io.open(out..'/boss-dma-source.tsv','w'))
 actual:write('frame\tcycle\tpage\tsource\n')
 emu:setBreakpoint(function()
  if n<830 or n>860 then return end
  local page=emu:readRegister('A')&255
  local bytes={}
  for address=page*256+16,page*256+79 do bytes[#bytes+1]=string.format('%02X',emu:read8(address)) end
  actual:write(string.format('%d\t%d\t%02X\t%s\n',n,emu:currentCycle(),page,table.concat(bytes)))
  actual:flush()
 end,0xFF89)
 local dma=assert(io.open(out..'/boss-dma.tsv','w'))
 dma:write('frame\tcycle\treturn_pc\tbank\tde\tc\tshadow\tcopy_caller\n')
 emu:setBreakpoint(function()
  if n<830 or n>860 then return end
  local sp=emu:readRegister('SP')&65535
  local bytes={}
  for address=0xC110,0xC14F do bytes[#bytes+1]=string.format('%02X',emu:read8(address)) end
  dma:write(string.format('%d\t%d\t%04X\t%02X\t%04X\t%02X\t%s\t%04X\n',n,emu:currentCycle(),emu:read8(sp)|(emu:read8(sp+1)<<8),emu:read8(0xFF99),emu:readRegister('DE')&65535,emu:readRegister('C')&255,table.concat(bytes),emu:read8(sp+4)|(emu:read8(sp+5)<<8)))
  dma:flush()
 end,0x0040)
end
if os.getenv('ENTRY_MENU_STACK')=='1' then
 local stack=assert(io.open(out..'/menu-stack.tsv','w'))
 stack:write('event\tframe\tsp\tbc\tde\thl\tsvbk\n')
 local active=false
 local function record(event)
  stack:write(string.format('%s\t%d\t%04X\t%04X\t%04X\t%04X\t%02X\n',event,n,emu:readRegister('SP')&65535,emu:readRegister('BC')&65535,emu:readRegister('DE')&65535,emu:readRegister('HL')&65535,emu:read8(0xFF70)&7))
  stack:flush()
 end
 emu:setBreakpoint(function() record('enter');active=true end,0x7C00,20)
 emu:setBreakpoint(function() record('lowest') end,0x7C8C,20)
 emu:setBreakpoint(function() record('exit');active=false end,0x406F,20)
 emu:setBreakpoint(function() if active then record('timer_inside') end end,0x0050)
end
if os.getenv('ENTRY_MENU_INPUT')=='1' then
 local input=assert(io.open(out..'/menu-input.tsv','w'))
 input:write('frame\tcycle\tpc\tselector\n')
 emu:setWatchpoint(function(info)
  input:write(string.format('%d\t%d\t%04X\t%02X\n',n,emu:currentCycle(),emu:readRegister('PC')&65535,(info.newValue or info.value or 0)&255))
  input:flush()
 end,0xDCDB,C.WATCHPOINT_TYPE.WRITE)
end
if os.getenv('ENTRY_NATIVE_MENU_CADENCE')=='1' then
 local cadence=assert(io.open(out..'/native-menu-cadence.tsv','w'))
 cadence:write('frame\tcycle\tscene\tlcdc\n')
 emu:setBreakpoint(function()
  cadence:write(string.format('%d\t%d\t%02X\t%02X\n',n,emu:currentCycle(),wram:read8(0x1880),emu:read8(0xFF40)))
  cadence:flush()
 end,0x200E)
end
if os.getenv('ENTRY_MENU_CRITICAL')=='1' then
 local critical=assert(io.open(out..'/menu-critical.tsv','w'))
 critical:write('event\tframe\tcycle\tly\tstat\tvbk\tie\tiflag\n')
 local sites={{'di',0x4031},{'reveal_ei',0x7F09}}
 for _,config in ipairs({{'pair_before','ENTRY_MENU_WRITE_BEFORE','4067'},{'pair_after','ENTRY_MENU_WRITE_AFTER','406B'}}) do
  for address in string.gmatch(os.getenv(config[2]) or config[3],'[^,]+') do
   table.insert(sites,{config[1],assert(tonumber(address,16))})
  end
 end
 for _,site in ipairs(sites) do
  local name,pc=site[1],site[2]
  emu:setBreakpoint(function()
   critical:write(string.format('%s\t%d\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\n',name,n,emu:currentCycle(),emu:read8(0xFF44),emu:read8(0xFF41),emu:read8(0xFF4F),emu:read8(0xFFFF),emu:read8(0xFF0F)))
   critical:flush()
  end,pc,20)
 end
end
local soundTiming=nil
if os.getenv('ENTRY_VBLANK_HELPERS')=='1' or os.getenv('ENTRY_OAM_TIMING')=='1' then
 local helpers=assert(io.open(out..'/vblank-helpers.tsv','w'))
 helpers:write('pc\tframe\tcycle\tly\tstat\tsp\n')
 local dma=assert(io.open(out..'/oam-dma.tsv','w'))
 dma:write('frame\tcycle\tly\tstat\tpc\tvalue\tlcdc\n')
 local dmaBoundary=assert(io.open(out..'/oam-boundary.tsv','w'))
 dmaBoundary:write('frame\tcycle\tly\tstat\tpc\n')
 for _,address in ipairs({0xFF80,0xFF8B}) do
  local pc=address
  emu:setBreakpoint(function()
   dmaBoundary:write(string.format('%d\t%d\t%d\t%d\t%04X\n',n,emu:currentCycle(),emu:read8(0xFF44),emu:read8(0xFF41),pc))
   dmaBoundary:flush()
  end,pc)
 end
 emu:setWatchpoint(function(info)
  dma:write(string.format('%d\t%d\t%d\t%d\t%04X\t%02X\t%02X\n',n,emu:currentCycle(),emu:read8(0xFF44),emu:read8(0xFF41),emu:readRegister('PC')&65535,(info.newValue or info.value or 0)&255,emu:read8(0xFF40)))
  dma:flush()
 end,0xFF46,C.WATCHPOINT_TYPE.WRITE)
 local helperSites=os.getenv('ENTRY_VBLANK_HELPERS')=='1' and {0x73FC,0x6F1D,0x6F20,0x6F23,0x6F26,0x6F3D,0x6F68,0x6F6E,0x6F82,0x6F8C,0x6F8F} or {}
 if os.getenv('ENTRY_PRELUDE_COST')=='1' then
  for _,pc in ipairs({0x6E80,0x6E83,0x6F90,0x6F98,0x6F9D,0x6F9F,0x6FA2,0x572C,0x7E00}) do table.insert(helperSites,pc) end
 end
 if os.getenv('ENTRY_PALETTE_SETUP_COST')=='1' then
  for _,pc in ipairs({0x5484,0x548C,0x53F2,0x6D43,0x69B8,0x69CD,0x6E96,0x71DB}) do table.insert(helperSites,pc) end
 end
 for _,address in ipairs(helperSites) do
  local pc=address
  emu:setBreakpoint(function()
   helpers:write(string.format('%04X\t%d\t%d\t%d\t%d\t%04X\n',pc,n,emu:currentCycle(),emu:read8(0xFF44),emu:read8(0xFF41),emu:readRegister('SP')&65535))
   helpers:flush()
  end,pc,13)
 end
end
if os.getenv('ENTRY_IRQ_COST_TRACE')=='1' then
 local irq=assert(io.open(out..'/irq-cost.tsv','w'))
 irq:write('event\tkind\tframe\tcycle\tsp\tpc\n')
 for _,site in ipairs({{'begin','vblank',0x0040},{'end','vblank',0x081D},{'begin','timer',0x0050},{'end','timer',0x06D0},{'begin','stat',0x0048},{'end','stat',0x086B},{'begin','vblank_hook',0x06DC},{'end','vblank_hook',0x06DF},{'other','serial',0x0058},{'other','joypad',0x0060}}) do
  local event,kind,pc=site[1],site[2],site[3]
  emu:setBreakpoint(function()
   irq:write(string.format('%s\t%s\t%d\t%d\t%04X\t%04X\n',event,kind,n,emu:currentCycle(),emu:readRegister('SP')&65535,pc))
   irq:flush()
  end,pc)
 end
end
if os.getenv('ENTRY_SOUND_TIMING')=='1' then
 soundTiming=assert(io.open(out..'/sound-timing.tsv','w'))
 soundTiming:write('kind\tframe\tcycle\tscene\tpc\tbank\tsvbk\tvalue\ttma\ttac\tstack_word\tcanonical\tstage\n')
 local function record(kind,value)
  local sp=emu:readRegister('SP')&65535
  local stackWord=emu:read8(sp)|(emu:read8((sp+1)&65535)<<8)
  soundTiming:write(string.format('%s\t%d\t%d\t%02X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%04X\t%02X\t%02X\n',kind,n,emu:currentCycle(),wram:read8(0x1880),emu:readRegister('PC')&65535,emu:read8(0xFF99),emu:read8(0xFF70)&7,value,emu:read8(0xFF06),emu:read8(0xFF07),stackWord,emu:read8(0xFFB7),emu:read8(0xFFBA)))
 end
 emu:setBreakpoint(function() record('timer',emu:read8(0xFF05)) end,0x50)
 local soundPorts={0xFF14,0xFF19,0xFF1E,0xFF23,0xFF26}
 -- #45 residual PCM can change without a channel trigger. Retain every
 -- register/wave-RAM write when explicitly requested, including unused ports.
 if os.getenv('ENTRY_SOUND_ALL_REGISTERS')=='1' then
  soundPorts={}
  for port=0xFF10,0xFF3F do table.insert(soundPorts,port) end
 end
 for _,address in ipairs(soundPorts) do
  local name=string.format('%04X',address)
  emu:setWatchpoint(function(info) record(name,(info.newValue or info.value or 0)&255) end,address,C.WATCHPOINT_TYPE.WRITE)
 end
end
local soundCommands=nil
if os.getenv('ENTRY_SOUND_COMMANDS')=='1' then
 soundCommands=assert(io.open(out..'/sound-commands.tsv','w'))
 soundCommands:write('event\tframe\tcycle\tscene\tcommand\tactive\tpc\tbank\tsvbk\tcaller\n')
 local function record(event,reg)
  local sp=emu:readRegister('SP')&65535
  local caller=emu:read8(sp)|(emu:read8((sp+1)&65535)<<8)
  soundCommands:write(string.format('%s\t%d\t%d\t%02X\t%02X\t%02X\t%04X\t%02X\t%02X\t%04X\n',event,n,emu:currentCycle(),wram:read8(0x1880),emu:readRegister(reg)&255,wram:read8(0x1888),emu:readRegister('PC')&65535,emu:read8(0xFF99),emu:read8(0xFF70)&7,caller))
 end
 emu:setBreakpoint(function() record('request','A') end,0x0038)
 emu:setBreakpoint(function() record('read','A') end,0x45B6,3)
 emu:setBreakpoint(function() record('reject','C') end,0x45C2,3)
 emu:setBreakpoint(function() record('accept','C') end,0x45C7,3)
end
local dmaSafety=nil
if os.getenv('ENTRY_DMA_SAFETY')=='1' then
 dmaSafety=assert(io.open(out..'/dma-safety.tsv','w'))
 dmaSafety:write('kind\tframe\tcycle\tpc\tbank\ta\tsvbk\tvbk\tlcdc\tstat\tly\thdma5\tsp\n')
 local function sample(kind)
  dmaSafety:write(string.format('%s\t%d\t%d\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%04X\n',kind,n,emu:currentCycle(),emu:readRegister('PC')&65535,emu:read8(0xFF99),emu:readRegister('A')&255,emu:read8(0xFF70)&7,emu:read8(0xFF4F)&1,emu:read8(0xFF40),emu:read8(0xFF41),emu:read8(0xFF44),emu:read8(0xFF55),emu:readRegister('SP')&65535))
 end
 -- Only addresses supplied by the bound candidate's decoded helper are used.
 for addr in string.gmatch(os.getenv('ENTRY_DMA_SITES') or '', '[^,]+') do
  local pc=assert(tonumber(addr,16))
  emu:setBreakpoint(function() sample('before') end,pc,36)
  emu:setBreakpoint(function() sample('after') end,pc+2,36)
 end
 emu:setWatchpoint(function() sample('svbk') end,0xFF70,C.WATCHPOINT_TYPE.WRITE)
 for _,addr in ipairs({0x40,0x48,0x50,0x58,0x60}) do
  emu:setBreakpoint(function() sample('irq') end,addr)
 end
end
local copyTrace=nil
local copyStart=nil
-- #26 full public copier boundary, shared by stock and DX. Older DX timing
-- began inside its banked helper and excluded preparation/post-copy work.
if os.getenv('ENTRY_FULL_COPY_TRACE')=='1' then
 local full=assert(io.open(out..'/full-copy-timing.tsv','w'))
 full:write('event\tframe\tcycle\tscene\tstage\tsp\treturn_pc\thl\n')
 local active=nil
 local function log(event,ret)
  full:write(string.format('%s\t%d\t%d\t%02X\t%02X\t%04X\t%04X\t%04X\n',event,n,emu:currentCycle(),wram:read8(0x1880),emu:read8(0xFFBA),emu:readRegister('SP')&65535,ret,emu:readRegister('HL')&65535))
  full:flush()
 end
 emu:setBreakpoint(function()
  assert(not active,'nested full copier entry')
  local sp=emu:readRegister('SP')&65535
  local ret=emu:read8(sp)|(emu:read8(sp+1)<<8)
  log('entry_observed',ret)
  assert(ret==0x12E0 or ret==0x0FF2 or ret==0x43BD or ret==0x43D8,'unknown copier caller')
  active={sp=sp,ret=ret}
  log('begin',ret)
 end,0x42A7,1)
 for _,ret in ipairs({0x12E0,0x0FF2,0x43BD,0x43D8}) do
  emu:setBreakpoint(function()
   if active and active.ret==ret and (emu:readRegister('SP')&65535)==((active.sp+2)&65535) then
    log('end',ret)
    active=nil
   end
  end,ret,ret<0x4000 and 0 or 1)
 end
end
if os.getenv('ENTRY_STOCK_COPY_TRACE')=='1' then
 local stockCopy=assert(io.open(out..'/stock-copy-timing.tsv','w'))
 stockCopy:write('start_frame\tend_frame\tscene\tstage\tstart_cycle\tend_cycle\tdelta\n')
 local started=nil
 emu:setBreakpoint(function()
  assert(started==nil,'nested stock copier entry')
  started={n,wram:read8(0x1880),emu:read8(0xFFBA),emu:currentCycle()}
 end,0x42A7,1)
 emu:setBreakpoint(function()
  if started then
   local finish=emu:currentCycle()
   stockCopy:write(string.format('%d\t%d\t%02X\t%02X\t%d\t%d\t%d\n',
     started[1],n,started[2],started[3],started[4],finish,finish-started[4]))
   stockCopy:flush()
   started=nil
  end
 end,0x436D,1)
end
if os.getenv('ENTRY_COPY_TRACE')=='1' then
 copyTrace=assert(io.open(out..'/copy-timing.tsv','w'))
 copyTrace:write('start_frame\tend_frame\tscene\tstage\tstart_cycle\tend_cycle\tdelta\ttag\n')
 emu:setBreakpoint(function()
  assert(copyStart==nil,'nested copier entry')
  copyStart={n,wram:read8(0x1880),emu:read8(0xFFBA),emu:currentCycle(),emu:read8(0xFF01)}
 end,0x6C80,28)
 emu:setBreakpoint(function()
  if copyStart then
   local finish=emu:currentCycle()
   copyTrace:write(string.format('%d\t%d\t%02X\t%02X\t%d\t%d\t%d\t%02X\n',copyStart[1],n,copyStart[2],copyStart[3],copyStart[4],finish,finish-copyStart[4],copyStart[5]))
   copyTrace:flush()
   copyStart=nil
  end
 end,0x42ED,1)
end
local boundaryTrace=nil
if os.getenv('ENTRY_BOUNDARY_TRACE')=='1' then
 boundaryTrace=assert(io.open(out..'/boundary.tsv','w'))
 boundaryTrace:write('frame\tpc\tbank\tsp\tlcdc\tstat\tly\thdma5\tsvbk\tie\n')
end
local attrWrites=nil
if os.getenv('ENTRY_ATTR_TRACE')=='1' then
 attrWrites=assert(io.open(out..'/attribute-writes.tsv','w'))
 attrWrites:write('frame\taddress\tpc\tbank\tvbk\tscene\told\tnew\n')
 for _,site in ipairs({0x9804,0x980E,0x9C44,0x9C4E,0xFF55}) do
  local address=site
  emu:setWatchpoint(function(info)
   attrWrites:write(string.format('%d\t%04X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\n',n,address,emu:readRegister('PC')&65535,emu:read8(0xFF99),emu:read8(0xFF4F)&1,wram:read8(0x1880),(info.oldValue or 0)&255,(info.newValue or info.value or 0)&255))
  end,address,C.WATCHPOINT_TYPE.WRITE)
 end
end
local recheck={}
local registers={}
local sites={}
local inputs={}
local poll={}
local continueTest=os.getenv('ENTRY_CONTINUE_TEST')=='1'
local continueTrace=continueTest and assert(io.open(out..'/continue.tsv','w')) or nil
local continuePoll=continueTest and assert(io.open(out..'/continue-poll.tsv','w')) or nil
if continueTest then
 emu:setBreakpoint(function()
  continuePoll:write(string.format('%d\t%02X\t%02X\t%02X\t%02X\n',n,emu:read8(0xFF94),emu:read8(0xFF95),emu:read8(0xFF93),emu:read8(0xFF00)))
 end,0x4A9C,1)
end
local projectileTrace=os.getenv('ENTRY_PROJECTILE_TRACE')=='1' and assert(io.open(out..'/projectile-sources.tsv','w')) or nil
local projectileCopies=os.getenv('ENTRY_PROJECTILE_COPIES')=='1' and assert(io.open(out..'/projectile-copies.tsv','w')) or nil
local pendingProjectile=nil
if projectileTrace then
 emu:setBreakpoint(function()
  if n>=tonumber(os.getenv('ENTRY_PROJECTILE_TRACE_FROM') or '1201') then
   local hl=emu:readRegister('HL')&65535
   local bytes={}
   for i=0,47 do bytes[#bytes+1]=string.format('%02X',emu:read8(hl+i)) end
   projectileTrace:write(string.format('%d\t%02X\t%04X\t%s\n',n,emu:read8(0xFF99),hl,table.concat(bytes)))
   if projectileCopies then
    assert(not pendingProjectile, 'unfinished projectile copy')
    pendingProjectile=string.format('%d\t%02X\t%04X\t%04X\t%04X\t%s',n,emu:read8(0xFF99),hl,emu:readRegister('BC')&65535,emu:readRegister('DE')&65535,table.concat(bytes))
   end
  end
 end,0x2B17)
 if projectileCopies then
  emu:setBreakpoint(function()
   if pendingProjectile then
    local bytes={}
    for i=0,47 do bytes[#bytes+1]=string.format('%02X',emu:read8(0xDC55+i)) end
    projectileCopies:write(pendingProjectile..'\t'..table.concat(bytes)..'\n')
    pendingProjectile=nil
   end
  end,0x2B34)
 end
end
local deathTrace=os.getenv('ENTRY_DEATH_TRACE')=='1' and assert(io.open(out..'/death-writes.tsv','w')) or nil
if deathTrace then
 for _,address in ipairs({0xD880,0xDCDC,0xDCDD,0xDCBB,0xDC24}) do
  local watchedAddress=address
  emu:setWatchpoint(function(info)
   if n>=tonumber(os.getenv('ENTRY_DEATH_TRACE_FROM') or '1201') and (emu:read8(0xFF70)&7)<=1 then
    local sp=emu:readRegister('SP')&65535
    local stack={}
    for i=0,15 do stack[#stack+1]=string.format('%02X',emu:read8(sp+i)) end
    deathTrace:write(string.format('%d\t%04X\t%04X\t%02X\t%02X\t%02X\t%s\n',n,watchedAddress,emu:readRegister('PC')&65535,emu:read8(0xFF99),(info.oldValue or 0)&255,(info.newValue or info.value or 0)&255,table.concat(stack)))
    if watchedAddress==0xDC24 and n>=5500 then
     local hl=emu:readRegister('HL')&65535
     local entry={}
     for i=-5,5 do entry[#entry+1]=string.format('%02X',emu:read8((hl+i)&65535)) end
     deathTrace:write(string.format('source\t%d\t%04X\t%04X\t%s\n',n,emu:readRegister('PC')&65535,hl,table.concat(entry)))
    end
   end
  end,watchedAddress,C.WATCHPOINT_TYPE.WRITE)
 end
 for _,site in ipairs({0x1004,0x1028,0x4A44}) do
  local address=site
  emu:setBreakpoint(function()
   if n>1200 then
    deathTrace:write(string.format('damage\t%d\t%04X\tA%02X\tF%02X\tBC%04X\tenergy%02X\tattack%02X\tmode%02X\n',n,address,emu:readRegister('A')&255,emu:readRegister('F')&255,emu:readRegister('BC')&65535,wram:read8(0x1CBB),wram:read8(0x1C24),wram:read8(0x1CF2)))
   end
  end,address,address<0x4000 and -1 or 1)
 end
end
local priorityTrace=os.getenv('ENTRY_PRIORITY_TRACE')=='1' and assert(io.open(out..'/priority.tsv','w')) or nil
if priorityTrace then priorityTrace:write('frame\ta0\ta1\ta2\ta3\tq2\thelper\n') end
local loopTrace = os.getenv('ENTRY_LOOP_TRACE')=='1' and assert(io.open(out..'/loops.tsv','w')) or nil
if os.getenv('ENTRY_LOOP_WORK_TRACE')=='1' then
 local work=assert(io.open(out..'/loop-work.tsv','w'))
 work:write('event\tframe\tcycle\tscene\tstage\tx\ty\tslot0\tslot1\tslot2\tslot3\tslot4\n')
 for _,site in ipairs({{'loop',0x016C},{'animation_end',0x0178},{'de9_end',0x017B},{'e7c_end',0x017E},{'map_prepare',0x12D4},{'map_expand',0x12DA},{'map_copy',0x12DD},{'map_commit',0x12E0},{'service55bb',0x0181},{'objects',0x0184},{'service4f5d',0x0187},{'tail',0x018A},{'map_return',0x01F0}}) do
  local name,pc=site[1],site[2]
  emu:setBreakpoint(function()
   work:write(string.format('%s\t%d\t%d\t%02X\t%02X\t%d\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\n',name,n,emu:currentCycle(),wram:read8(0x1880),emu:read8(0xFFBA),wram:read8(0x1C00)+256*wram:read8(0x1C01),wram:read8(0x1C02)+256*wram:read8(0x1C03),wram:read8(0x1C85),wram:read8(0x1C8D),wram:read8(0x1C95),wram:read8(0x1C9D),wram:read8(0x1CA5)))
   work:flush()
  end,pc)
 end
end
if loopTrace then
 loopTrace:write('frame\tscene\tstage\tx\ty\n')
 emu:setBreakpoint(function()
  if os.getenv('ENTRY_ARENA_LOOP')=='1' and emu:read8(0xFF99)~=2 then return end
  loopTrace:write(string.format('%d\t%02X\t%02X\t%d\t%d\n',n,wram:read8(0x1880),emu:read8(0xFFBA),wram:read8(0x1C00)+256*wram:read8(0x1C01),wram:read8(0x1C02)+256*wram:read8(0x1C03)))
 end,os.getenv('ENTRY_ARENA_LOOP')=='1' and 0x406F or 0x016C)
end
if os.getenv('ENTRY_PORTAL_TRACE')=='1' then
 for _,site in ipairs({0x13E5,0x13FE,0x140B,0x1482,0x14D4,0x14F9,0x151D,0x154D,0x1626,0x1636,0x165A,0x166A,0x169C,0x169E,0x16C5}) do
  local addr=site
  emu:setBreakpoint(function()
   local key=string.format('%04X DE%04X HL%04X CA%02X D3%02X TABLE%02X%02X',addr,emu:readRegister('DE')&65535,emu:readRegister('HL')&65535,emu:read8(0xFFCA),emu:read8(0xFFD3),emu:read8(0xFFAD),emu:read8(0xFFAC))
   sites[key]=(sites[key] or 0)+1
  end,addr)
 end
end
if os.getenv('ENTRY_WAIT_TRACE')=='1' then
 for _,addr0 in ipairs({0x00B0,0x00B4,0x00B6,0x00B7,0x00BA,0x00BC,0x00BD}) do
  local addr=addr0
  emu:setBreakpoint(function()
   if n>=2990 and n<=3002 then
    poll[#poll+1]=string.format('%d/%04X/A%02X/B%02X/C%02X/P%02X/O%02X/M%02X',n,addr,emu:readRegister('A')&255,emu:readRegister('B')&255,emu:readRegister('C')&255,emu:read8(0xFF93),emu:read8(0xFF95),emu:read8(0xFF96))
   end
  end,addr)
 end
 emu:setBreakpoint(function()
  inputs[#inputs+1]=string.format('game/%d/%02X/%02X/%04X/%04X',n,emu:read8(0xFF94),emu:read8(0xFF95),emu:readRegister('A')&0xFFFF,emu:readRegister('F')&0xFFFF)
 end,0x0A70)
 emu:setBreakpoint(function()
  local key=string.format('%d/%02X/%02X/%02X',n,emu:read8(0xFF94),emu:read8(0xFF95),emu:read8(0xFF00))
  inputs[#inputs+1]=key
 end,0x1D8E)
 for _,address in ipairs({0x7F00,0x7F27,0x7F32,0x4082,0x4083,0x016C}) do
  local addr=address
  emu:setBreakpoint(function()
   local sp=emu:readRegister('SP')&0xFFFF
   local key=string.format('%04X/%04X/%02X%02X',addr,sp,emu:read8(sp+1),emu:read8(sp))
   sites[key]=(sites[key] or 0)+1
  end,addr,addr<0x4000 and -1 or 20)
 end
 emu:setBreakpoint(function()
  local ly=emu:read8(0xFF44)
  hist[ly]=(hist[ly] or 0)+1
 end,0x7F16,20)
 emu:setBreakpoint(function()
  local ly=emu:read8(0xFF44)
  recheck[ly]=(recheck[ly] or 0)+1
  local a=emu:readRegister('A')
  local f=emu:readRegister('F')
  local key=string.format('%s/%s/%d',tostring(a),tostring(f),ly)
  registers[key]=(registers[key] or 0)+1
 end,0x7F21,20)
end
local trace=assert(io.open(out..'/trace.tsv','w'))
trace:write('frame\tscene\tstage\tbonus\tmode\troom\tx\ty\thp\tworld_x\tworld_y\tc2\tc3\tc4\tc5\n')
callbacks:add('frame',function()
 if n==0 and os.getenv('ENTRY_ONCE_HP') then
  local hp=tonumber(os.getenv('ENTRY_ONCE_HP'))
  assert(hp and hp>=0 and hp<=255 and hp%1==0)
  emu.memory.wram:write8(0x1CBB,hp)
 end
 n=n+1
 if os.getenv('ENTRY_DENSE_INVENTORY')=='1' and n==1180 then
  -- #26 diagnostic: populated native menus, not a claimed recorded inventory.
  -- Native menu rendering still owns its buffers and attributes.
  local groups={{1,1,1,1,1,1,1,1,1,5},{6,7,8,9,10,11,6,7,8,9},{12,13,14,15,16,12,13,14,15,16}}
  for g=0,2 do
   for slot=0,9 do wram:write8(0x1CBD+g*10+slot,groups[g+1][slot+1]) end
  end
  wram:write8(0x1CDB,0)
 end
 if boundaryTrace then
  boundaryTrace:write(string.format('%d\t%04X\t%02X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n',n,emu:readRegister('PC')&65535,emu:read8(0xFF99),emu:readRegister('SP')&65535,emu:read8(0xFF40),emu:read8(0xFF41),emu:read8(0xFF44),emu:read8(0xFF55),emu:read8(0xFF70),emu:read8(0xFFFF)))
  boundaryTrace:flush()
 end
 local keys=tonumber(os.getenv('ENTRY_KEYS') or '0')
 if continueTest then
  local start=os.getenv('ENTRY_COLD')=='1' and 1200 or 0
  if n==start+1 then
   emu:write8(0xFFE6,1) -- Explicit diagnostic credit; not a native progression claim.
   wram:write8(0x1CBB,0) -- One death stimulus, no scene or rendering writes.
  end
  keys=(n>=start+180 and n<start+600 and n%12<6) and keys or 0
  continueTrace:write(string.format('%d\t%02X\t%02X\t%02X\t%02X\t%02X\n',n,wram:read8(0x1880),emu:read8(0xFFE6),emu:read8(0xFFE7),emu:read8(0xFF94),keys))
 end
 if os.getenv('ENTRY_PULSE_A')=='1' and n%12>=6 then keys=keys&0xFE end
 if n>tonumber(os.getenv('ENTRY_KEY_FRAMES') or '999999') then keys=0 end
 if os.getenv('ENTRY_COLD')=='1' then
  if n<=1200 then keys=0 end
  if n>=180 and n<186 then keys=0x80 end
  if (n>=193 and n<199) or (n>=241 and n<247) or (n>=291 and n<297) or (n>=391 and n<397) then keys=1 end
  if n>=341 and n<347 then keys=8 end
 end
 if os.getenv('ENTRY_FLOOR_PATROL')=='1' and n>1200 then
  keys=math.floor((n-1201)/100)%2==0 and 32 or 16
 end
 emu:setKeys(keys)
 -- Restored menu-open fixture: neutral hold, one Select pulse, then the
 -- requested ordinary movement/fire keys. No gameplay-memory assistance.
 if os.getenv('ENTRY_RESUME_MENU_AT') then
  local closeAt=assert(tonumber(os.getenv('ENTRY_RESUME_MENU_AT')))
  assert(closeAt>=1 and closeAt%1==0)
  if n<closeAt then keys=0
  elseif n<closeAt+6 then keys=4 end
  emu:setKeys(keys)
 end
 if continuous then
  if n>1200 and n<warpFrame then keys=65 end
  if n>=warpFrame and n<warpFrame+120 then keys=129 end
  if n>=warpFrame+120 and n<=tonumber(os.getenv('ENTRY_FIRE_START') or '3600') then keys=0 end
  local walkAfter=tonumber(os.getenv('ENTRY_RETURN_WALK_AFTER') or '7200')
  if os.getenv('ENTRY_RETURN_WALK')=='1' and n>walkAfter then
   local directions={128,32,64,16}
   keys=directions[math.floor((n-walkAfter-1)/480)%4+1] | (n%12<6 and 1 or 0)
  end
  local menuAt=tonumber(os.getenv('ENTRY_MENU_AT') or '-1000')
  if n>=menuAt and n<menuAt+126 then
   keys=((n<menuAt+6 or n>=menuAt+120) and 4 or 0)
   if os.getenv('ENTRY_MENU_INPUT')=='1' then
    if n>=menuAt+20 and n<menuAt+26 then keys=128 end
    if n>=menuAt+60 and n<menuAt+66 then keys=64 end
   end
  end
  emu:setKeys(keys)
 end
 if os.getenv('ENTRY_PAUSE_ITEM_USE')=='1' then
  local start=tonumber(os.getenv('ENTRY_MENU_AT') or '3300')
  if n>=start and n<start+126 then
   keys=0
   if n<start+6 then keys=4
   elseif n>=start+20 and n<start+26 then keys=128
   elseif n>=start+40 and n<start+46 then keys=16
   elseif n>=start+60 and n<start+66 then keys=1 end
   emu:setKeys(keys)
  end
 end
 if (n==1 and os.getenv('ENTRY_WARP_BEFORE')=='1') or (continuous and n==warpFrame) or (os.getenv('ENTRY_COLD_WARP')=='1' and n==warpFrame) then
  local x=tonumber(os.getenv('ENTRY_WARP_X') or '1240')
  local y=tonumber(os.getenv('ENTRY_WARP_Y') or '1344')
  if os.getenv('ENTRY_WARP_AT_LOOP')=='1' then pendingWarp={x,y}
  else
   wram:write8(0x1C00,x&255);wram:write8(0x1C01,x>>8)
   wram:write8(0x1C02,y&255);wram:write8(0x1C03,y>>8)
  end
 end
 if os.getenv('ENTRY_MINIBOSS_ASSIST')=='1' then
  -- Existing native-spawn diagnostic recipe; no ROM descriptor edits.
  if n>=492 and emu:read8(0xFFBF)==0 then
   emu:setKeys(16 | (n%8<2 and 1 or 0))
  end
  if n==560 then
   local section=tonumber(os.getenv('ENTRY_MINIBOSS_SECTION') or '0')
   assert(section and section>=0 and section<=5 and section%1==0,'invalid section')
   wram:write8(0x1CB8,section)
  end
  if n>=560 and emu:read8(0xFFBF)==0 then
   wram:write8(0x1CBA,1);emu:write8(0xFFD6,0x1E)
   for _,address in ipairs({0x1C85,0x1C8D,0x1C95,0x1C9D,0x1CA5}) do wram:write8(address,0) end
  end
  local menuAt=tonumber(os.getenv('ENTRY_MENU_AT') or '-1000')
  local menuHold=tonumber(os.getenv('ENTRY_MINIBOSS_MENU_HOLD') or '120')
  assert(menuHold and menuHold>=12 and menuHold%1==0,'invalid miniboss menu hold')
  if n>=menuAt and n<menuAt+menuHold+6 then
   emu:setKeys((n<menuAt+6 or n>=menuAt+menuHold) and 4 or 0)
  end
 end
 if os.getenv('ENTRY_ASSIST_RESOURCE')=='1' and (not continuous or n>1200) then
  -- #37: DCBB is health. DCDD is the native ten-slot menu cursor, NOT health.
  wram:write8(0x1CBB,255)
 end
 if os.getenv('ENTRY_ASSIST_HEALTH')=='1' and wram:read8(0x1880)==2 then
  wram:write8(0x1CBB,255)
 end
 if itemTrace then
  itemTrace:write(string.format('%d\t%d\t%d\t%d\t%d\t%d\t%d\n',n,emu:read8(0xFFE4),wram:read8(0x1CDB),wram:read8(0x1CDD),wram:read8(0x1CF1),wram:read8(0x1CC7),wram:read8(0x1CC8)))
 end
 -- #42: hp is physical DCBB; DCDC is not the health counter.
 trace:write(string.format('%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n',n,wram:read8(0x1880),emu:read8(0xFFBA),emu:read8(0xFFD0),emu:read8(0xFFC1),emu:read8(0xFFBD),wram:read8(0x1C00),wram:read8(0x1C02),wram:read8(0x1CBB),wram:read8(0x1C00)+256*wram:read8(0x1C01),wram:read8(0x1C02)+256*wram:read8(0x1C03),emu:read8(0xFFC2),emu:read8(0xFFC3),emu:read8(0xFFC4),emu:read8(0xFFC5)))
 if priorityTrace then
  local bytes={}
  for i=0x1B40,0x1B7E do bytes[#bytes+1]=string.format('%02X',wram:read8(i)) end
  priorityTrace:write(string.format('%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%s\n',n,emu:read8(0xFE03),emu:read8(0xFE07),emu:read8(0xFE0B),emu:read8(0xFE0F),wram:read8(0x1B3E),table.concat(bytes)))
 end
 local scene,stage=wram:read8(0x1880),emu:read8(0xFFBA)
 local menuCaptureAt=tonumber(os.getenv('ENTRY_MENU_AT') or '-1000')
 local menuCapture=os.getenv('ENTRY_MENU_CAPTURE')=='1' and n>=menuCaptureAt-1 and n<=menuCaptureAt+130
 if menuCapture or n==frames or n==tonumber(os.getenv('ENTRY_MENU_AT') or '-1000')+60 or (os.getenv('ENTRY_RETURN_WALK')=='1' and n>=7200 and n%480==0) or (continuous and (scene~=previousScene or stage~=previousStage or n==3600)) or (os.getenv('ENTRY_FINAL_ONLY')~='1' and (n==1 or n%tonumber(os.getenv('ENTRY_CAPTURE_EVERY') or '120')==0)) then
  emu:screenshot(string.format('%s/frame-%04d.png',out,n))
  emu:saveStateFile(string.format('%s/frame-%04d.ss0',out,n))
 end
 previousScene,previousStage=scene,stage
 if n==frames then
  if soundTiming then soundTiming:close() end
  if soundCommands then soundCommands:close() end
  if dmaSafety then dmaSafety:close() end
  if boundaryTrace then boundaryTrace:close() end
  if attrWrites then attrWrites:close() end
  if continueTrace then continueTrace:close() end
  if continuePoll then continuePoll:close() end
  if projectileTrace then projectileTrace:close() end
  if projectileCopies then
   assert(not pendingProjectile, 'run ended during projectile copy')
   projectileCopies:close()
  end
  if deathTrace then deathTrace:close() end
  if priorityTrace then priorityTrace:close() end
  if loopTrace then loopTrace:close() end
  trace:close()
  local h=assert(io.open(out..'/wait-ly.tsv','w'))
  for ly=0,153 do if hist[ly] then h:write(string.format('%d\t%d\n',ly,hist[ly])) end end
  h:close()
  local q=assert(io.open(out..'/recheck-ly.tsv','w'))
  for ly=0,153 do if recheck[ly] then q:write(string.format('%d\t%d\n',ly,recheck[ly])) end end
  q:close()
  local z=assert(io.open(out..'/recheck-registers.tsv','w'))
  for key,count in pairs(registers) do z:write(key..'\t'..count..'\n') end
  z:close()
  local s=assert(io.open(out..'/sites.tsv','w'))
  for key,count in pairs(sites) do s:write(key..'\t'..count..'\n') end
  s:close()
  local i=assert(io.open(out..'/inputs.tsv','w'))
  for _,row in ipairs(inputs) do i:write(row..'\n') end
  i:close()
  local p=assert(io.open(out..'/poll.tsv','w'));for _,row in ipairs(poll) do p:write(row..'\n') end;p:close();os.exit(0)
 end
end)
-- #43 signal only after every callback and initial input is installed.
local startupGate = os.getenv('ENTRY_NATIVE_START_GATE')
if startupGate and os.getenv('ENTRY_NATIVE_DEFER_START')~='1' then
 local ready = assert(io.open(startupGate, 'w'))
 ready:write('probe initialization complete\n')
 ready:close()
end
