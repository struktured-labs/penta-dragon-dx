-- #54 function-contract probe. Native cold start, stage-index assistance at
-- the loader call only; stop immediately after it returns, before gameplay.
local target=assert(tonumber(os.getenv('HEADER_TARGET')))
local out=assert(os.getenv('HEADER_OUT'))
local started=false
local completed=false
local before={}
local function registers()
 local result={}
 for _,name in ipairs({'af','bc','de','hl','sp'}) do
  result[name]=emu:readRegister(name)
 end
 return result
end
emu:setBreakpoint(function()
 if emu:read8(0xFF99)~=1 then return end
 emu:writeRegister('a',target)
 before=registers()
 before.cycle=emu:currentCycle()
 before.dc09=emu:read8(0xDC09)
 started=true
end,0x0C2C)
emu:setBreakpoint(function()
 if not started or completed then return end
 local fh=assert(io.open(out,'w'))
 local after=registers()
 fh:write('header=')
 for address=0xFF9B,0xFFB7 do fh:write(string.format('%02x',emu:read8(address))) end
 fh:write('\n')
 for _,name in ipairs({'af','bc','de','hl','sp'}) do
  fh:write(string.format('%s_before=%d\n%s_after=%d\n',name,before[name],name,after[name]))
 end
 fh:write(string.format('bank=%d\ndc09_before=%d\ndc09_after=%d\ncycles=%d\n',
  emu:read8(0xFF99),before.dc09,emu:read8(0xDC09),emu:currentCycle()-before.cycle))
 fh:close()
 completed=true
 local marker=assert(io.open(out..'.done','w')); marker:write('complete\n'); marker:close()
end,0x0C2F)
-- The owning verifier stops this exact child after the completion marker.
-- os.exit inside Lua can crash Qt teardown, even from a frame callback.
dofile(assert(os.getenv('HEADER_BOOT_PROBE')))
