-- iter 264: probe spiral_power_active pixel count #0000B5 at f=68/120/200/300
-- to see if the projectile rendering recovers at later frames.
local OUT = os.getenv("OUT") or "tmp/spiral_at_frames"
local f = 0

callbacks:add("frame", function()
  f = f + 1
  for _, target in ipairs({68, 120, 200, 300}) do
    if f == target then
      emu:screenshot(string.format("%s_f%d.png", OUT, target))
    end
  end
  if f > 310 then emu:stop() end
end)
