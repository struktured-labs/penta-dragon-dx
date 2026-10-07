-- #54: observe native rotate writes, without changing their values or timing.
local output=assert(os.getenv('ENTRY_OUT'))
local log=assert(io.open(output..'/rotations.tsv','w'))
log:write('cycle\tstage\tpc\taddress\tbefore\tafter\n'); log:flush()
local pending={}
for _,pc in ipairs({0x088A,0x088D}) do
 emu:setBreakpoint(function()
  if emu:read8(0xFFBA)~=7 then return end
  local address=emu:readRegister('hl')
  pending[pc]={address=address,value=emu:read8(address),cycle=emu:currentCycle()}
 end,pc)
 emu:setBreakpoint(function()
  local p=pending[pc]
  if not p then return end
  log:write(string.format('%d\t7\t%04X\t%04X\t%02X\t%02X\n',
   p.cycle,pc,p.address,p.value,emu:read8(p.address)))
  log:flush(); pending[pc]=nil
 end,pc+2)
end
dofile(assert(os.getenv('SECRET_REPLAY_PROBE')))
