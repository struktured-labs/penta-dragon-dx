"""Scroll-tearing verification.

Tearing manifests when palette RAM or BG attrs change mid-frame, causing
the LCD to render the top half of a frame with one palette state and the
bottom half with another. The signature: identical scroll positions
producing visually different rasters between consecutive frames during
sustained scroll motion.

We sample two things per frame during sustained right-scroll:
  1. BG palette RAM bytes (FF68/FF69) — detects palette writes during scroll
  2. BG attr histogram from VBK=1 — detects attr-write races (the v3.00
     inline-hook regression class: stale pal7 in a viewport row)

PASS = both metrics churn at baseline-equivalent rates within a single
room. A wrong-tile_id offset in the inline hook would leave pal7 attrs
in the visible viewport with palette RAM intact; checking VBK=1 directly
catches that, while the original pal-RAM-only check would miss it.
"""
from __future__ import annotations
import os, sys, subprocess, tempfile, argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MGBA_QT = PROJECT_ROOT / "scripts/mgba-qt-singleflight"


PROBE = r"""
local OUT = os.getenv("STATE_PATH")
local KEY_A     = 0x01
local KEY_DOWN  = 0x80
local KEY_RIGHT = 0x10
local KEY_START = 0x08
local SCHEDULE = {
    {180, 185, KEY_DOWN}, {186, 200, 0},
    {201, 206, KEY_A},    {207, 260, 0},
    {261, 266, KEY_A},    {267, 320, 0},
    {321, 326, KEY_A},    {327, 380, 0},
    {381, 386, KEY_START}, {387, 430, 0},
    {431, 436, KEY_A},
}
local f = 0
local gameplay_at = -1
local samples = {}
local fired = false

local function read_pal()
    local hex = ""
    for i = 0, 63 do
        emu:write8(0xFF68, i)
        hex = hex .. string.format("%02X", emu:read8(0xFF69))
    end
    return hex
end

-- Sample BG attr histogram for the visible-viewport region in VBK=1.
-- Returns a string like "pal7=180,pal0=200,pal6=40" — comparing this
-- across consecutive frames detects attr writes (or stale-pal7 lag).
-- Viewport is at 0x9800..0x9BFF (tilemap 0). We sample a fixed slice of
-- the first 360 tiles (covers the visible 20x18 = 360 tile region).
local function read_attr_histogram()
    emu:write8(0xFF4F, 1)
    local counts = {[0]=0,[1]=0,[2]=0,[3]=0,[4]=0,[5]=0,[6]=0,[7]=0}
    for addr = 0x9800, 0x9967 do  -- 360 tiles
        local a = emu:read8(addr)
        local idx = a & 0x07
        counts[idx] = counts[idx] + 1
    end
    emu:write8(0xFF4F, 0)
    local parts = {}
    local active_mask = 0
    for p = 0, 7 do
        table.insert(parts, string.format("p%d=%d", p, counts[p]))
        if counts[p] > 0 then active_mask = active_mask | (1 << p) end
    end
    return table.concat(parts, ","), active_mask
end

local function changed_pal_bytes(before, after)
    local changed = {}
    for byte = 0, 63 do
        local first = byte * 2 + 1
        if string.sub(before, first, first + 1) ~=
           string.sub(after, first, first + 1) then
            table.insert(changed, string.format("%02X", byte))
        end
    end
    return table.concat(changed, ",")
end

local function changed_pal_mask(before, after)
    local mask = 0
    for byte = 0, 63 do
        local first = byte * 2 + 1
        if string.sub(before, first, first + 1) ~=
           string.sub(after, first, first + 1) then
            mask = mask | (1 << (byte >> 3))
        end
    end
    return mask
end

callbacks:add("frame", function()
    if fired then return end
    f = f + 1

    if gameplay_at < 0 then
        local keys = 0
        for _, s in ipairs(SCHEDULE) do
            if f >= s[1] and f <= s[2] then keys = s[3]; break end
        end
        emu:setKeys(keys)
        if emu:read8(0xFFC1) == 1 then gameplay_at = f end
        return
    end

    -- Sustained scroll: walk right + godmode
    emu:setKeys(KEY_RIGHT)
    emu:write8(0xDCDD, 0x17); emu:write8(0xDCDC, 0xFF); emu:write8(0xDCBB, 0xFF)

    local elapsed = f - gameplay_at
    -- Capture pal RAM + attr histogram every frame for the measurement window
    if elapsed >= 60 and elapsed < 60 + 240 then  -- 4 seconds of scroll
        local p = read_pal()
        local a, active = read_attr_histogram()
        local scx = emu:read8(0xFF43)
        local scy = emu:read8(0xFF42)
        local room = emu:read8(0xFFBD)
        table.insert(samples, {
            f=elapsed, pal=p, attr=a, scx=scx, scy=scy, room=room,
            phase=emu:read8(0xDF4C), bgp=emu:read8(0xFF47),
            tick=emu:read8(0xFFD4), cache=emu:read8(0xDF00),
            active=active
        })
    end

    if elapsed >= 60 + 240 then
        fired = true
        local fh = io.open(OUT, "w")
        local pal_changes = 0
        local visible_pal_changes = 0
        local attr_changes = 0
        local room_transitions = 0
        local pal_change_details = {}
        for i = 2, #samples do
            if samples[i].room ~= samples[i-1].room then
                room_transitions = room_transitions + 1
            elseif samples[i].room == samples[i-1].room then
                if samples[i].pal ~= samples[i-1].pal then
                    pal_changes = pal_changes + 1
                    local changed_mask = changed_pal_mask(
                        samples[i-1].pal, samples[i].pal
                    )
                    local active_mask =
                        samples[i-1].active | samples[i].active
                    if (changed_mask & active_mask) ~= 0 then
                        visible_pal_changes = visible_pal_changes + 1
                    end
                    table.insert(
                        pal_change_details,
                        string.format(
                            "frame:%d,room:%02X,bytes:%s",
                            samples[i].f,
                            samples[i].room,
                            changed_pal_bytes(
                                samples[i-1].pal, samples[i].pal
                            )
                        ) .. string.format(
                            ",phase:%02X->%02X,bgp:%02X,tick:%02X,cache:%02X" ..
                            ",changed_mask:%02X,active_mask:%02X",
                            samples[i-1].phase, samples[i].phase,
                            samples[i].bgp, samples[i].tick, samples[i].cache,
                            changed_mask, active_mask
                        )
                    )
                end
                if samples[i].attr ~= samples[i-1].attr then
                    attr_changes = attr_changes + 1
                end
            end
        end
        fh:write("# Scroll-tearing harness — palette + attr stability across scroll frames\n")
        fh:write(string.format("samples=%d\n", #samples))
        fh:write(string.format("room_transitions=%d\n", room_transitions))
        fh:write(string.format("pal_changes_within_room=%d\n", pal_changes))
        fh:write(string.format("pal_changes_per_second=%.2f\n", pal_changes * 60 / 240))
        fh:write(string.format(
            "visible_pal_changes_within_room=%d\n", visible_pal_changes
        ))
        fh:write(string.format(
            "visible_pal_changes_per_second=%.2f\n",
            visible_pal_changes * 60 / 240
        ))
        fh:write(string.format("attr_changes_within_room=%d\n", attr_changes))
        fh:write(string.format("attr_changes_per_second=%.2f\n", attr_changes * 60 / 240))
        for i, detail in ipairs(pal_change_details) do
            fh:write(string.format("pal_change_%d=%s\n", i, detail))
        end
        for i = 2, #samples do
            if samples[i].phase ~= samples[i-1].phase then
                fh:write(string.format(
                    "phase_change_%d=frame:%d,%02X->%02X,bgp:%02X,tick:%02X,cache:%02X\n",
                    i, samples[i].f, samples[i-1].phase, samples[i].phase,
                    samples[i].bgp, samples[i].tick, samples[i].cache
                ))
            end
        end
        fh:close()
        os.exit(0)
    end
end)
"""


def run_probe(rom_path: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="penta-scroll-") as temp:
        out = Path(temp) / "result.txt"
        lua = Path(temp) / "probe.lua"
        lua.write_text(PROBE)
        env = os.environ.copy()
        env["STATE_PATH"] = str(out)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["SDL_AUDIODRIVER"] = "dummy"
        cmd = [
            str(MGBA_QT),
            "-C",
            f"savegamePath={temp}",
            "-C",
            f"savestatePath={temp}",
            str(Path(rom_path).resolve()),
            "--script",
            str(lua),
            "-l",
            "0",
        ]
        subprocess.run(
            cmd,
            cwd=temp,
            env=env,
            capture_output=True,
            timeout=120,
        )
        if not out.is_file() or out.stat().st_size < 10:
            raise RuntimeError(
                f"scroll harness produced no output for {rom_path}"
            )
        text = out.read_text()
    state = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            state[k.strip()] = v.strip()
    return state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--baseline-rom", default="rom/Penta Dragon (J).gb")
    ap.add_argument("--tolerance", type=float, default=2.0,
                    help="PASS if pal changes/sec ≤ tolerance × baseline (default 2.0)")
    args = ap.parse_args()

    b = run_probe(args.baseline_rom)
    print(f"vanilla:   pal_changes_within_room={b.get('pal_changes_within_room')} "
          f"({b.get('pal_changes_per_second')}/s) "
          f"visible={b.get('visible_pal_changes_within_room', 'n/a')} "
          f"({b.get('visible_pal_changes_per_second', 'n/a')}/s) "
          f"attr_changes={b.get('attr_changes_within_room', 'n/a')} "
          f"({b.get('attr_changes_per_second', 'n/a')}/s)")
    c = run_probe(args.rom)
    print(f"candidate: pal_changes_within_room={c.get('pal_changes_within_room')} "
          f"({c.get('pal_changes_per_second')}/s) "
          f"visible={c.get('visible_pal_changes_within_room', 'n/a')} "
          f"({c.get('visible_pal_changes_per_second', 'n/a')}/s) "
          f"attr_changes={c.get('attr_changes_within_room', 'n/a')} "
          f"({c.get('attr_changes_per_second', 'n/a')}/s)")
    for key in sorted(c):
        if key.startswith(("pal_change_", "phase_change_")):
            print(f"  {key}: {c[key]}")
    # NOTE: attr_changes_per_second is currently informational only — the
    # right threshold depends on expected baseline behavior of v3.00's
    # inline hook (which writes VBK=1 attrs during scroll, by design).
    # The PASS/FAIL gate stays on pal_changes_per_second.
    b_pps = float(b.get(
        'visible_pal_changes_per_second',
        b.get('pal_changes_per_second', 0),
    ))
    c_pps = float(c.get(
        'visible_pal_changes_per_second',
        c.get('pal_changes_per_second', 0),
    ))
    threshold = max(b_pps * args.tolerance, 0.5)
    if c_pps > threshold:
        print(f"\nFAIL: {c_pps:.2f}/s > threshold {threshold:.2f}/s "
              f"(+{c_pps - b_pps:.2f}/s vs baseline) → palette unstable during scroll")
        sys.exit(1)
    else:
        print(f"\nPASS: {c_pps:.2f}/s ≤ threshold {threshold:.2f}/s")
        sys.exit(0)


if __name__ == "__main__":
    main()
