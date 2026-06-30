-- Quintra Phase 7 smoke test.
-- Boots → TITLE → CLASS_SELECT → ROOM → walk → fire → walk through door
-- → screenshot at each transition → exit.

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
    console:log("SHOT " .. name)
end

local function tick(n) for _ = 1, n do emu:runFrame() end end

local function press(key, frames_held)
    emu:setKeys(key)
    tick(frames_held or 4)
    emu:setKeys(0)
    tick(4)
end

local function tap(key) press(key, 2) end

-- Boot + settle
tick(120); shot("01_title")

-- TITLE → CLASS_SELECT
tap(KEY_START); tick(40); shot("02_class_select")

-- CLASS_SELECT → RUN_INIT → ROOM 0
tap(KEY_A); tick(40); shot("03_room0_enter")

-- Walk south, into the bottom door
press(KEY_DOWN, 90); shot("04_room0_at_S_door")

-- Should have transitioned to room 1 now
tick(30); shot("05_room1_enter")

-- Walk further south into another door
press(KEY_DOWN, 90); shot("06_room2_enter")

-- East door
press(KEY_RIGHT, 90); shot("07_room3_enter")

-- North door
press(KEY_UP, 90); shot("08_room4_enter")

-- Fire test in this room
press(KEY_B + KEY_RIGHT, 6); tick(8); shot("09_fire_in_room4")

-- Spray + walk to engage enemies
emu:setKeys(KEY_B + KEY_LEFT); tick(60); emu:setKeys(0); tick(20)
shot("10_after_spray")

tick(60); shot("11_after_settle")

-- Return to TITLE via START
press(KEY_START, 4); tick(40); shot("12_back_to_title")

console:log("SMOKETEST DONE")
emu.frontend:quit()
