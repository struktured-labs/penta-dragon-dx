"""Mini-boss OBJ palette verification.

Reach the first mini-boss (DCB8=2 in level 1 = Gargoyle), dump OBJ palette
RAM + the OBJ attribute bytes of sprites currently displayed. Compare to
the expected per-boss palette from the YAML (boss_palette_table at
bank13 0x6880 / boss_slot_table at 0x68C0).

By default, DCB8 is force-written to 2 at gameplay+300 frames to
deterministically reach the mini-boss within the probe budget. Pass
--natural to let the game's section-counter advance naturally; this is
slower but catches regressions in the spawn state machine that the
forced-spawn path would mask.

PASS criteria:
  - Mini-boss sprite OAM entries have non-default OBJ palette indices
    (= the boss colorizer ran)
  - At least one OBJ palette in RAM contains non-FF7F (non-white)

FAIL means boss sprite was colored as default DMG grayscale or palette
load failed for OBJ region.
"""
from __future__ import annotations
import os, sys, subprocess, tempfile, argparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MGBA_QT = os.path.join(ROOT, "scripts", "mgba-qt-singleflight")
DEFAULT_STATE = os.path.join(
    ROOT, "save_states_for_claude", "level1_sara_w_gargoyle_mini_boss.ss0"
)

PROBE = r"""
local OUT = os.getenv("STATE_PATH")
local FORCE_SPAWN = (os.getenv("FORCE_SPAWN") or "1") == "1"
local STATE_LOADED = (os.getenv("STATE_LOADED") or "0") == "1"
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
local miniboss_at = -1
local fired = false
local boss_attr_checked = 0
local boss_attr_mismatches = 0

callbacks:add("frame", function()
    if fired then return end
    f = f + 1

    if STATE_LOADED and gameplay_at < 0 then
        gameplay_at = f
    end

    if gameplay_at < 0 then
        local keys = 0
        for _, s in ipairs(SCHEDULE) do
            if f >= s[1] and f <= s[2] then keys = s[3]; break end
        end
        emu:setKeys(keys)
        local scene = emu:read8(0xD880)
        if emu:read8(0xFFC1) == 1 and scene >= 0x02 and scene < 0x0C then
            gameplay_at = f
        end
        return
    end

    -- During gameplay: walk right + fire + godmode to live long enough
    -- to reach the gargoyle mini-boss section
    emu:setKeys(KEY_RIGHT + (f % 4 == 0 and KEY_A or 0))
    emu:write8(0xDCDD, 0x17); emu:write8(0xDCDC, 0xFF); emu:write8(0xDCBB, 0xFF)

    -- Force DCB8 to advance into mini-boss section by writing it directly.
    -- DCB8=2 spawns the gargoyle, DCB8=5 spawns the spider.
    -- If FORCE_SPAWN is disabled, let the game's section counter advance
    -- naturally — this exercises the spawn state machine end-to-end.
    local elapsed = f - gameplay_at
    -- A one-frame write races the section updater and became flaky as VBlank
    -- timing changed. Hold the requested section until the boss flag publishes.
    if FORCE_SPAWN and elapsed >= 300 and elapsed < 420
        and emu:read8(0xFFBF) == 0 then
        emu:write8(0xDCB8, 2)
    end

    -- Detect mini-boss active: FFBF != 0
    if miniboss_at < 0 and emu:read8(0xFFBF) ~= 0 then
        miniboss_at = f
    end

    -- Gargoyle/Spider alternate composed-sprite pages every few animation
    -- beats. Check the full $30-$4F footprint over several seconds so a
    -- periodic OBJ5/OBJ6/OBJ7 color flip cannot hide behind one snapshot.
    if miniboss_at > 0 and f >= miniboss_at + 30 then
        local boss_id = emu:read8(0xFFBF)
        local expected_slot = (boss_id % 2 == 1) and 6 or 7
        for sprite = 0, 39 do
            local base = 0xFE00 + sprite * 4
            local y = emu:read8(base); local x = emu:read8(base + 1)
            local tile = emu:read8(base + 2)
            if y > 0 and y < 160 and x > 0 and x < 168
                and tile >= 0x30 and tile < 0x50 then
                boss_attr_checked = boss_attr_checked + 1
                if (emu:read8(base + 3) & 0x07) ~= expected_slot then
                    boss_attr_mismatches = boss_attr_mismatches + 1
                end
            end
        end
    end

    if miniboss_at > 0 and f >= miniboss_at + 300 then
        fired = true
        local fh = io.open(OUT, "w")
        fh:write(string.format(
            "FFBF=%d\nD880=0x%02X\nDCB8=%d\nDD09=%d\n"
                .. "boss_attr_checked=%d\nboss_attr_mismatches=%d\n",
            emu:read8(0xFFBF), emu:read8(0xD880), emu:read8(0xDCB8),
            emu:read8(0xDD09), boss_attr_checked, boss_attr_mismatches))
        -- Dump OBJ palette RAM (FF6A index, FF6B data)
        fh:write("# OBJ palette RAM:\n")
        for p = 0, 7 do
            local line = string.format("objpal%d:", p)
            for c = 0, 3 do
                local idx = (p * 8) + (c * 2)
                emu:write8(0xFF6A, idx); local lo = emu:read8(0xFF6B)
                emu:write8(0xFF6A, idx + 1); local hi = emu:read8(0xFF6B)
                line = line .. string.format(" %02X%02X", lo, hi)
            end
            fh:write(line .. "\n")
        end
        -- Dump non-zero OAM entries (visible sprites)
        local non_zero = 0
        local obj_palettes = {}
        for sprite = 0, 39 do
            local base = 0xFE00 + sprite * 4
            local y = emu:read8(base); local x = emu:read8(base + 1)
            if y > 0 and y < 160 and x > 0 and x < 168 then
                non_zero = non_zero + 1
                local tile = emu:read8(base + 2); local attr = emu:read8(base + 3)
                local pal = attr & 0x07
                obj_palettes[pal] = (obj_palettes[pal] or 0) + 1
            end
        end
        fh:write(string.format("visible_sprites=%d\n", non_zero))
        fh:write("# OBJ-pal-index usage among visible sprites:\n")
        for p = 0, 7 do
            fh:write(string.format("obj_pal_usage_%d=%d\n", p, obj_palettes[p] or 0))
        end
        fh:close()
        os.exit(0)
    end

    -- Give natural-spawn mode much more budget (state machine takes
    -- several minutes of in-game time to reach DCB8=2).
    local budget = FORCE_SPAWN and 1800 or 12000
    if elapsed > budget and miniboss_at < 0 then
        fired = true
        local fh = io.open(OUT, "w")
        fh:write("FFBF=-1\n# never reached mini-boss\n")
        fh:close()
        os.exit(0)
    end
end)
"""


def run_probe(
    rom_path: str,
    force_spawn: bool = True,
    state_path: str | None = None,
) -> dict:
    out = tempfile.NamedTemporaryFile(suffix=".txt", delete=False).name
    lua = tempfile.NamedTemporaryFile(suffix=".lua", delete=False, mode="w")
    lua.write(PROBE); lua.close()
    env = os.environ.copy()
    env["STATE_PATH"] = out
    env["FORCE_SPAWN"] = "1" if force_spawn else "0"
    env["STATE_LOADED"] = "1" if state_path else "0"
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SDL_AUDIODRIVER"] = "dummy"
    cmd = [MGBA_QT]
    if state_path:
        cmd.extend(["-t", state_path])
    cmd.extend([rom_path, "--script", lua.name, "-l", "0"])
    # Natural-spawn mode runs the in-game state machine for thousands of
    # frames; bump the wall-clock budget proportionally.
    timeout = 600 if not force_spawn else 180
    subprocess.run(cmd, env=env, capture_output=True, timeout=timeout)
    if not os.path.exists(out) or os.path.getsize(out) < 10:
        raise RuntimeError(f"miniboss harness produced no output")
    with open(out) as fh: text = fh.read()
    obj_palettes = []
    state = {}
    obj_pal_usage = {}
    for line in text.splitlines():
        if line.startswith("objpal") and ":" in line:
            obj_palettes.append(line.split(":", 1)[1].strip().split())
        elif line.startswith("obj_pal_usage_"):
            idx = int(line.split("_")[3].split("=")[0])
            obj_pal_usage[idx] = int(line.split("=")[1])
        elif "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            state[k.strip()] = v.strip()
    try: os.unlink(out); os.unlink(lua.name)
    except OSError: pass
    return {"state": state, "obj_palettes": obj_palettes, "obj_pal_usage": obj_pal_usage}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--natural", action="store_true",
                    help="Let DCB8 advance via the game's spawn state machine "
                         "instead of force-writing DCB8=2. Slower but catches "
                         "spawn-mechanism regressions.")
    ap.add_argument(
        "--boot",
        action="store_true",
        help="boot and force the miniboss instead of loading the checked-in "
             "real Gargoyle state",
    )
    ap.add_argument(
        "--state",
        default=DEFAULT_STATE,
        help="real miniboss savestate used by the deterministic default path",
    )
    args = ap.parse_args()

    state_path = None if args.boot or args.natural else args.state
    if state_path and not os.path.isfile(state_path):
        raise SystemExit(f"FAIL: miniboss savestate not found: {state_path}")
    r = run_probe(
        args.rom,
        force_spawn=not args.natural,
        state_path=state_path,
    )
    print(f"ROM: {args.rom}")
    print(f"State: {r['state']}")
    print(f"OBJ palette usage: {r['obj_pal_usage']}")
    if r['obj_palettes']:
        print(f"OBJ palette RAM (8 palettes):")
        for i, p in enumerate(r['obj_palettes']):
            print(f"  objpal{i}: {' '.join(p)}")

    failures = []
    if r['state'].get('FFBF', '-1') == '-1':
        failures.append("never reached mini-boss")
    else:
        if state_path and r['state'].get('DD09') != '0':
            failures.append(
                f"real miniboss has DD09={r['state'].get('DD09')} "
                "instead of gameplay value 0"
            )
        distinct_obj_pal_words = len(set(w for pal in r['obj_palettes'] for w in pal))
        if distinct_obj_pal_words < 3:
            failures.append(f"OBJ palette has only {distinct_obj_pal_words} distinct words "
                            "→ OBJ palette load broken")
        non_zero_obj_pal_usage = sum(1 for c in r['obj_pal_usage'].values() if c > 0)
        if non_zero_obj_pal_usage < 1:
            failures.append("no visible sprites → can't verify boss colorization")
        if int(r['state'].get('boss_attr_checked', '0')) <= 0:
            failures.append("no $30-$4F miniboss animation attributes sampled")
        if int(r['state'].get('boss_attr_mismatches', '-1')) != 0:
            failures.append(
                f"{r['state'].get('boss_attr_mismatches')} miniboss "
                "animation samples used the wrong boss slot"
            )

    if failures:
        print("\nFAIL:")
        for f in failures: print(f"  - {f}")
        sys.exit(1)
    else:
        print("\nPASS: mini-boss reached and OBJ palette colorized.")
        sys.exit(0)


if __name__ == "__main__":
    main()
