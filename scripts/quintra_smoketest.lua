-- Quintra Phase 9/10 smoke test.
-- Boots → TITLE → CLASS_SELECT → walks through 5 doors to the BOSS room
-- → fights → screenshot at each stage → exit.

local OUT_DIR = os.getenv("QUINTRA_OUT_DIR") or "/tmp/quintra-smoketest"

local KEY_A      = 0x01
local KEY_B      = 0x02
local KEY_SELECT = 0x04
local KEY_START  = 0x08
local KEY_RIGHT  = 0x10
local KEY_LEFT   = 0x20
local KEY_UP     = 0x40
local KEY_DOWN   = 0x80

local LOG_FILE = OUT_DIR .. "/debug.log"
local log_fh = io.open(LOG_FILE, "w")

local function shot(name)
    emu:screenshot(OUT_DIR .. "/h_" .. name .. ".png")
    local rc_proc = emu:read8(0xFFFE)
    local rc_room = emu:read8(0xFFFB)
    local vic     = emu:read8(0xFFFD)
    local in_boss = emu:read8(0xFFFC)
    local py      = emu:read8(0xFFFA)
    local px      = emu:read8(0xFFF9)
    local tile    = emu:read8(0xFFF8)
    local hp     = emu:read8(0xFFE4)
    local ifr    = emu:read8(0xFFE5)
    local line = string.format(
        "SHOT %-25s  room=%d vic=%d boss=0x%02X  pos=(%d,%d) tile=0x%02X  hp=%d ifr=%d\n",
        name, rc_room, vic, in_boss, px, py, tile, hp, ifr)
    if log_fh then log_fh:write(line); log_fh:flush() end
    console:log(line)
end

local function tick(n) for _ = 1, n do emu:runFrame() end end

local function hold(key, frames)
    -- Set keys on EVERY frame to defeat any per-frame reset
    for _ = 1, (frames or 4) do
        emu:setKeys(key)
        emu:runFrame()
    end
    emu:setKeys(0)
    tick(4)
end

local function press(key, frames_held) hold(key, frames_held or 4) end
local function tap(key) hold(key, 2) end

-- Walk through one door. Hold direction long enough to cross the room.
local function walk_through_door(dir_key)
    hold(dir_key, 220)
    tick(20)
end

-- Boot
tick(120); shot("01_title")
tap(KEY_START); tick(40); shot("02_class_select")

-- Cycle through all 5 classes to confirm cursor + stats update
tap(KEY_DOWN); tick(15); shot("02b_sauran")
tap(KEY_DOWN); tick(15); shot("02c_corvin")
tap(KEY_DOWN); tick(15); shot("02d_picsean")
tap(KEY_DOWN); tick(15); shot("02e_vespine")
tap(KEY_DOWN); tick(15)  -- wraps back to Wolfkin
tap(KEY_A); tick(40); shot("03_room0_enter")

-- Walk through 5 doors to reach boss room (run_state.room_counter == 5)
walk_through_door(KEY_DOWN);  shot("04_room1")
walk_through_door(KEY_DOWN);  shot("05_room2")
walk_through_door(KEY_DOWN);  shot("06_room3")
walk_through_door(KEY_DOWN);  shot("07_room4")
walk_through_door(KEY_DOWN);  shot("08_BOSS_room")

-- After 5 walks, player ends up at bottom of boss room (walked into south wall).
-- Boss is at center (y=72). Player at ~y=128. Fire UP at boss.
hold(KEY_A + KEY_UP, 200)
shot("09_boss_under_fire")

tick(30)
shot("10_boss_mid_fight")

-- Long sustained assault — boss has 50 HP, 2 dmg/shot, fire every 12 ticks
-- ~16 shots / 200 frames = ~32 damage. Two presses to finish (66 dmg total).
hold(KEY_A + KEY_UP, 400)
tick(60)
shot("11_after_long_assault")

-- START now PAUSES (dims palettes) instead of exiting
press(KEY_START, 4); tick(20); shot("12_paused")
press(KEY_START, 4); tick(20); shot("13_unpaused")

console:log("SMOKETEST DONE")
emu.frontend:quit()
