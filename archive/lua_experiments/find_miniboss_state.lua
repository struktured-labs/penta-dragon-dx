-- Mini-boss state finder
-- Run this, then enter a room with a mini-boss
-- Press SELECT to snapshot RAM before/after mini-boss appears
-- Press START to snapshot after mini-boss is defeated

print("=== MINI-BOSS STATE FINDER ===")
print("1. Navigate to just BEFORE a mini-boss room")
print("2. Press SELECT to take 'before' snapshot")
print("3. Enter room with mini-boss visible")
print("4. Press SELECT again to take 'during' snapshot")
print("5. Defeat the mini-boss")
print("6. Press START to take 'after' snapshot")
print("")

local snapshots = {}
local snapshot_names = {"before", "during", "after"}
local snapshot_count = 0

local function take_snapshot(name)
    local snap = {}
    -- Capture WRAM (0xC000-0xDFFF)
    for addr = 0xC000, 0xDFFF do
        snap[addr] = emu:read8(addr)
    end
    -- Capture HRAM (0xFF80-0xFFFE)
    for addr = 0xFF80, 0xFFFE do
        snap[addr] = emu:read8(addr)
    end
    return snap
end

local function compare_snapshots(snap1, snap2, name1, name2)
    local changes = {}
    for addr, val1 in pairs(snap1) do
        local val2 = snap2[addr]
        if val1 ~= val2 then
            table.insert(changes, {addr=addr, old=val1, new=val2})
        end
    end
    return changes
end

local function save_report()
    local log = io.open("tmp/miniboss_state.log", "w")
    log:write("=== MINI-BOSS STATE ANALYSIS ===\n\n")

    if snapshots["before"] and snapshots["during"] then
        local changes = compare_snapshots(snapshots["before"], snapshots["during"], "before", "during")
        log:write(string.format("=== CHANGES: before -> during (%d differences) ===\n", #changes))
        table.sort(changes, function(a,b) return a.addr < b.addr end)
        for i, c in ipairs(changes) do
            if i <= 100 then  -- Limit output
                log:write(string.format("  0x%04X: %02X -> %02X\n", c.addr, c.old, c.new))
            end
        end
        if #changes > 100 then
            log:write(string.format("  ... and %d more\n", #changes - 100))
        end
        log:write("\n")
    end

    if snapshots["during"] and snapshots["after"] then
        local changes = compare_snapshots(snapshots["during"], snapshots["after"], "during", "after")
        log:write(string.format("=== CHANGES: during -> after (%d differences) ===\n", #changes))
        table.sort(changes, function(a,b) return a.addr < b.addr end)
        for i, c in ipairs(changes) do
            if i <= 100 then
                log:write(string.format("  0x%04X: %02X -> %02X\n", c.addr, c.old, c.new))
            end
        end
        if #changes > 100 then
            log:write(string.format("  ... and %d more\n", #changes - 100))
        end
        log:write("\n")
    end

    -- Find addresses that changed in BOTH transitions (likely mini-boss related)
    if snapshots["before"] and snapshots["during"] and snapshots["after"] then
        log:write("=== ADDRESSES CHANGED IN BOTH TRANSITIONS (likely mini-boss state) ===\n")
        local changes1 = compare_snapshots(snapshots["before"], snapshots["during"], "before", "during")
        local changes2 = compare_snapshots(snapshots["during"], snapshots["after"], "during", "after")

        local changed1 = {}
        for _, c in ipairs(changes1) do
            changed1[c.addr] = {old=c.old, new=c.new}
        end

        for _, c in ipairs(changes2) do
            if changed1[c.addr] then
                local before_val = changed1[c.addr].old
                local during_val = changed1[c.addr].new
                local after_val = c.new
                log:write(string.format("  0x%04X: %02X -> %02X -> %02X\n",
                    c.addr, before_val, during_val, after_val))
            end
        end
    end

    log:write("\nAnalysis complete!\n")
    log:close()
    print("Report saved to tmp/miniboss_state.log")
end

-- Also capture OAM to see mini-boss sprite info
local function capture_oam()
    local log = io.open("tmp/miniboss_oam.log", "w")
    log:write("=== OAM SNAPSHOT (Mini-boss sprites) ===\n\n")

    for slot = 0, 39 do
        local base = 0xFE00 + slot * 4
        local y = emu:read8(base)
        local x = emu:read8(base + 1)
        local tile = emu:read8(base + 2)
        local flags = emu:read8(base + 3)

        if y > 0 and y < 160 then  -- Visible sprite
            log:write(string.format("Slot %2d: Y=%3d X=%3d Tile=0x%02X Flags=0x%02X\n",
                slot, y, x, tile, flags))
        end
    end

    log:close()
    print("OAM saved to tmp/miniboss_oam.log")
end

local last_select = false
local last_start = false

callbacks:add("frame", function()
    -- Read button state
    emu:write8(0xFF00, 0x20)
    local buttons = emu:read8(0xFF00)
    local select_pressed = (buttons & 0x04) == 0
    local start_pressed = (buttons & 0x08) == 0

    -- SELECT: take before/during snapshot
    if select_pressed and not last_select then
        snapshot_count = snapshot_count + 1
        if snapshot_count <= 2 then
            local name = snapshot_names[snapshot_count]
            snapshots[name] = take_snapshot(name)
            print(string.format("Snapshot '%s' taken! (%d/3)", name, snapshot_count))

            if snapshot_count == 2 then
                capture_oam()  -- Capture OAM when mini-boss is visible
            end
        end
    end

    -- START: take after snapshot and generate report
    if start_pressed and not last_start then
        if snapshot_count >= 2 then
            snapshots["after"] = take_snapshot("after")
            snapshot_count = 3
            print("Snapshot 'after' taken!")
            save_report()
            print("Done! Check tmp/miniboss_state.log")
        else
            print("Need to take 'before' and 'during' snapshots first (press SELECT)")
        end
    end

    last_select = select_pressed
    last_start = start_pressed
end)
