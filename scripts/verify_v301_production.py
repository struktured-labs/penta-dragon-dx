#!/usr/bin/env python3
"""Smoke-test for v3.01 production ROM.

Runs autoplay stress test + screenshot capture and verifies:
  - FFC1 reaches 1 by frame 600
  - D880 remains in the Stage 1 dungeon scene while room IDs advance
  - FFBD cycles at least 2 of rooms {1, 3, 5, 7}
  - Screenshot at frame 1500 has visible content (>2KB PNG)
  - No 0x00 (stuck) state in D880

Returns exit 0 on PASS, 1 on FAIL.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


STRESS_LUA = """
local OUT = os.getenv("STRESS_OUT")
local f = 0
local TITLE_END = 500
local KEY_A=0x01; local KEY_START=0x08
local KEY_RIGHT=0x10; local KEY_LEFT=0x20; local KEY_UP=0x40; local KEY_DOWN=0x80
local TITLE = {{180,185,KEY_DOWN},{193,198,KEY_A},{241,246,KEY_A},
               {291,296,KEY_A},{341,346,KEY_START},{391,396,KEY_A}}

local seen_d880, seen_ffbd = {}, {}
local ffc1_first = -1
local sample_count = 0
local STRESS_END = 2000
local done = false

callbacks:add("frame", function()
    if done then return end
    f = f + 1
    if f <= TITLE_END then
        local k = 0
        for _, e in ipairs(TITLE) do
            if f >= e[1] and f <= e[2] then k = e[3]; break end
        end
        emu:setKeys(k); return
    end
    local keys = KEY_A
    if (f % 30) < 5 then keys = keys + KEY_UP
    elseif (f % 30) < 10 then keys = keys + KEY_DOWN
    elseif (f % 30) < 15 then keys = keys + KEY_LEFT
    elseif (f % 30) < 20 then keys = keys + KEY_RIGHT
    end
    emu:setKeys(keys)
    if f % 10 == 0 then
        sample_count = sample_count + 1
        local d880 = emu:read8(0xD880)
        local ffbd = emu:read8(0xFFBD)
        local ffc1 = emu:read8(0xFFC1)
        if ffc1 == 1 and ffc1_first < 0 then ffc1_first = f end
        seen_d880[d880] = (seen_d880[d880] or 0) + 1
        seen_ffbd[ffbd] = (seen_ffbd[ffbd] or 0) + 1
    end
    if f == 1500 then emu:screenshot(os.getenv("SCREEN_OUT")) end
    if f >= STRESS_END then
        local fh = io.open(OUT, "w")
        fh:write(string.format("frames=%d samples=%d ffc1_first=%d\\n", f, sample_count, ffc1_first))
        fh:write("D880:")
        for k, v in pairs(seen_d880) do fh:write(string.format(" 0x%02X=%d", k, v)) end
        fh:write("\\nFFBD:")
        for k, v in pairs(seen_ffbd) do fh:write(string.format(" %d=%d", k, v)) end
        fh:write("\\n")
        fh:close()
        done = true
    end
end)
"""


def main():
    rom = Path(sys.argv[1] if len(sys.argv) > 1 else "rom/working/penta_dragon_dx_v301.gb")
    if not rom.exists():
        print(f"FAIL: ROM not found: {rom}")
        return 1

    with tempfile.TemporaryDirectory() as tmpdir:
        lua_path = Path(tmpdir) / "smoke.lua"
        lua_path.write_text(STRESS_LUA)
        stress_out = Path(tmpdir) / "stress.txt"
        screen_out = Path(tmpdir) / "screen.png"

        env = os.environ.copy()
        env["STRESS_OUT"] = str(stress_out)
        env["SCREEN_OUT"] = str(screen_out)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["SDL_AUDIODRIVER"] = "dummy"

        proc = subprocess.Popen(
            ["xvfb-run", "-a", "mgba-qt", str(rom), "--script", str(lua_path)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(60):
                time.sleep(1)
                if stress_out.exists() and stress_out.stat().st_size > 0:
                    time.sleep(1)
                    break
        finally:
            proc.terminate()
            try: proc.wait(timeout=3)
            except subprocess.TimeoutExpired: proc.kill()

        if not stress_out.exists():
            print("FAIL: stress test did not produce output")
            return 1

        result = stress_out.read_text()
        print(f"Stress test output:\n{result}")

        # Parse
        ffc1_match = re.search(r"ffc1_first=(\d+)", result)
        ffc1_first = int(ffc1_match.group(1)) if ffc1_match else -1
        d880_states = set(re.findall(r"0x([0-9A-F]+)=", result.split("D880:")[1].split("\n")[0]))
        ffbd_states = set(re.findall(r"(\d+)=", result.split("FFBD:")[1].split("\n")[0]))
        ffbd_rooms = ffbd_states & {"1", "3", "5", "7"}

        screen_ok = screen_out.exists() and screen_out.stat().st_size > 2000
        screen_size = screen_out.stat().st_size if screen_out.exists() else 0

        # Checks
        checks = [
            ("FFC1 reaches 1 by f≤600", 0 < ffc1_first <= 600),
            ("D880 includes 0x02 (dungeon)", "02" in d880_states),
            ("D880 stays in Stage 1 dungeon", d880_states == {"02"}),
            ("No D880=0x00 (stuck)", "00" not in d880_states),
            ("FFBD cycles ≥2 rooms in {1,3,5,7}", len(ffbd_rooms) >= 2),
            (f"Screenshot ≥ 2KB (got {screen_size})", screen_ok),
        ]
        passed = True
        for name, ok in checks:
            status = "PASS" if ok else "FAIL"
            print(f"  {status}: {name}")
            if not ok: passed = False
        return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
