-- Replay an unchanged operator state; never normalize game/video memory.
local OUT = assert(os.getenv("PENTA_CAPTURED_MENU_OUT"))
local STATE = assert(os.getenv("PENTA_CAPTURED_MENU_STATE"))
local LUT = assert(io.open(assert(os.getenv("PENTA_CAPTURED_MENU_LUT")), "rb"))
local lut = LUT:read("*a"); LUT:close(); assert(#lut == 256)
local trace = assert(io.open(OUT .. "/frames.tsv", "w"))
trace:write("frame\tkeys\tsvbk\tscene\troom\tmenu\tlcdc\tscx\tscy\tbase\tmismatches\texamples\n")
local loaded, frame = false, 0
local CLOSE_KEYS = {b=2, select=4, start=8}
local close_key = assert(CLOSE_KEYS[os.getenv("PENTA_CAPTURED_MENU_CLOSE") or "b"])
local raw_vram = assert(emu.memory.vram)
local raw_wram = assert(emu.memory.wram)
local function game(address) return raw_wram:read8(address - 0xC000) end
local snapshots = {[1]=true,[59]=true,[90]=true,[239]=true,[300]=true,[360]=true}
callbacks:add("frame", function()
  if not loaded then
    local ok, result = pcall(function() return emu:loadStateFile(STATE) end)
    assert(ok and result ~= false, "operator state failed to load")
    loaded = true
    emu:setKeys(0)
    return
  end
  frame = frame + 1
  local keys = 0
  if frame >= 60 and frame < 66 then keys = close_key end
  -- Recovery is a separate interval, never part of stationary qualification.
  if frame >= 240 and frame < 264 then keys = 0x40 end
  emu:setKeys(keys)
  local lcdc, scx, scy = emu:read8(0xFF40), emu:read8(0xFF43), emu:read8(0xFF42)
  local wy = emu:read8(0xFF4A)
  local window = (lcdc & 0x20) ~= 0 and wy < 144
  local height = window and wy or 144
  local base = (lcdc & 8) ~= 0 and 0x9C00 or 0x9800
  local cols = math.floor(((scx & 7) + 159) / 8) + 1
  local rows = math.floor(((scy & 7) + height - 1) / 8) + 1
  local cells = {}
  for y=0,rows-1 do
    for x=0,cols-1 do
      local address = base + ((math.floor(scy / 8) + y) & 31) * 32
        + ((math.floor(scx / 8) + x) & 31)
      cells[#cells+1] = {address, raw_vram:read8(address - 0x8000)}
    end
  end
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  local bad, examples = 0, {}
  for _,cell in ipairs(cells) do
    local actual = emu:read8(cell[1])
    local expected = string.byte(lut, cell[2]+1)
    if actual ~= expected then
      bad = bad + 1
      if #examples < 12 then
        examples[#examples+1] = string.format("%04X:t%02X:a%02X:e%02X",cell[1],cell[2],actual,expected)
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  trace:write(string.format("%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%04X\t%d\t%s\n",
    frame,keys,emu:read8(0xFF70),game(0xD880),emu:read8(0xFFBD),emu:read8(0xFFE4),
    lcdc,scx,scy,base,bad,table.concat(examples,";")))
  emu:screenshot(string.format("%s/frame-%04d.png",OUT,frame))
  if snapshots[frame] then
    assert(emu:saveStateFile(string.format("%s/frame-%04d.ss0",OUT,frame)) ~= false)
  end
  if frame == 360 then
    trace:close()
    local done = assert(io.open(OUT .. "/done.txt", "w"))
    done:write("complete\n"); done:close()
    os.exit(0)
  end
end)
