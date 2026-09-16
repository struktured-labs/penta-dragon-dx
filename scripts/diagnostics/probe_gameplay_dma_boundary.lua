-- Let the fixture's native HRAM DMA loop finish before moving its CPU.
local out=assert(os.getenv('GAMEPLAY_DMA_OUT'))
local loaded,done=false,false
callbacks:add('frame',function()
  if loaded then return end
  loaded=true
  assert(emu:loadStateFile(assert(os.getenv('GAMEPLAY_DMA_STATE')))~=false)
  -- Install after load: loading a state restores HRAM and can erase an
  -- earlier software breakpoint in that writable address range.
  assert(emu:setBreakpoint(function()
    if done then return end
    assert(emu:saveStateFile(out..'.ss0')~=false)
    done=true
    local marker=assert(io.open(out..'.done','w'))
    marker:write('complete');marker:close()
  end,0xFF90)>0)
end)
