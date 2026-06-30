-- Quintra Phase 4 smoke test.
-- Boots → screenshots TITLE → press START → screenshots CLASS_SELECT →
-- press A → screenshots ROOM → press LEFT for several frames → screenshots →
-- quits.

local OUT_DIR = os.getenv("QUINTRA_OUT_DIR") or "/tmp/quintra-smoketest"

-- GBDK joypad bitmask
local KEY_A      = 0x01
local KEY_B      = 0x02
local KEY_SELECT = 0x04
local KEY_START  = 0x08
local KEY_RIGHT  = 0x10
local KEY_LEFT   = 0x20
local KEY_UP     = 0x40
local KEY_DOWN   = 0x80

local function shot(name)
    local path = OUT_DIR .. "/h_" .. name .. ".png"
    emu:screenshot(path)
    console:log("SHOT " .. name .. " -> " .. path)
end

local function tick(n)
    for _ = 1, n do emu:runFrame() end
end

local function press(key, frames_held)
    emu:setKeys(key)
    tick(frames_held or 4)
    emu:setKeys(0)
    tick(4)
end

-- Boot + settle
tick(120)
shot("01_title")

-- Engage
press(KEY_START, 4)
tick(60)
shot("02_class_select")

-- Confirm class
press(KEY_A, 4)
tick(40)
shot("03_room_enter")

-- Move around
press(KEY_LEFT, 24)
shot("04_room_left")

press(KEY_DOWN, 24)
shot("05_room_down")

press(KEY_RIGHT, 24)
shot("06_room_right")

-- Try walking into wall (should be blocked, sprite stays inside the room)
press(KEY_UP, 80)
shot("07_room_after_wall_push")

-- Back to title via START (Phase 4 wires this)
press(KEY_START, 4)
tick(40)
shot("08_back_to_title")

console:log("SMOKETEST DONE")
-- Exit
emu.frontend:quit()
