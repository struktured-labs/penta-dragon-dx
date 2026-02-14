#!/usr/bin/env python3
"""
Penta Dragon DX - Automated Regression Test Suite

Tests BG and OBJ colorization across multiple save states and reports results.

Usage:
    uv run python scripts/regression_test.py                  # Run all tests
    uv run python scripts/regression_test.py --verbose        # Show detailed output
    uv run python scripts/regression_test.py --test sara_w    # Run specific test
    uv run python scripts/regression_test.py --json           # Output JSON results

Exit codes:
    0 = All tests passed
    1 = One or more tests failed
    2 = Error running tests
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ROM_PATH = PROJECT_ROOT / "rom" / "working" / "penta_dragon_dx_FIXED.gb"
SAVESTATES_DIR = PROJECT_ROOT / "save_states_for_claude"
TMP_DIR = PROJECT_ROOT / "tmp" / "regression"


# ---------------------------------------------------------------------------
# Tile-to-palette mappings (expected)
# ---------------------------------------------------------------------------

# OBJ (sprite) expected palette by tile range
OBJ_TILE_PALETTE_MAP = {
    # (tile_low, tile_high): expected_palette
    (0x20, 0x27): 2,   # Sara W
    (0x28, 0x2F): 1,   # Sara D
    (0x30, 0x3F): 3,   # Crow
    (0x40, 0x4F): 4,   # Hornets
    (0x50, 0x5F): 5,   # Orcs
    (0x60, 0x6F): 6,   # Humanoid (soldier/moth/mage)
    (0x70, 0x7F): 7,   # Special (catfish)
}

# BG expected palette by tile range
BG_TILE_PALETTE_MAP = {
    (0x00, 0x3F): 0,   # Floor/edges/platforms
    (0x40, 0x5F): 6,   # Wall fill blocks
    (0x60, 0x87): 0,   # Arches/doorways
    (0x88, 0xDF): 1,   # Items (gold/yellow)
    (0xE0, 0xFD): 6,   # Decorative
    (0xFE, 0xFF): 0,   # Void
}


def expected_obj_palette(tile_id: int) -> Optional[int]:
    """Return expected OBJ palette for a tile ID, or None if not in known ranges."""
    for (low, high), pal in OBJ_TILE_PALETTE_MAP.items():
        if low <= tile_id <= high:
            return pal
    return None


def expected_bg_palette(tile_id: int) -> Optional[int]:
    """Return expected BG palette for a tile ID."""
    for (low, high), pal in BG_TILE_PALETTE_MAP.items():
        if low <= tile_id <= high:
            return pal
    return None


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class SpriteCheck:
    """Expected condition for a sprite check."""
    description: str
    # Tile range to look for
    tile_low: int
    tile_high: int
    # Expected palette(s) - sprite must match one of these
    expected_palettes: list[int]
    # If True, at least one sprite with these tiles must be found
    must_exist: bool = True
    # Minimum number of sprites that must match
    min_count: int = 1


@dataclass
class SlotCheck:
    """Check specific OAM slots by index (for Sara who always occupies slots 0-3)."""
    description: str
    # Slot range (inclusive)
    slot_low: int
    slot_high: int
    # Expected palette(s) for visible sprites in these slots
    expected_palettes: list[int]
    # If True, at least one slot must be visible
    must_be_visible: bool = True


@dataclass
class MemoryCheck:
    """Expected condition for a memory address."""
    address: int
    description: str
    # If not None, value must match exactly
    exact_value: Optional[int] = None
    # If not None, value must be nonzero
    nonzero: Optional[bool] = None
    # If not None, value must be zero
    zero: Optional[bool] = None
    # If not None, value must be in this set
    in_values: Optional[list[int]] = None


@dataclass
class BGCheck:
    """Expected condition for BG tile attributes."""
    description: str
    # Tile range to check
    tile_low: int
    tile_high: int
    # Expected palette
    expected_palette: int
    # Minimum number of matching tiles to consider valid
    min_tiles: int = 5
    # Minimum accuracy (fraction of tiles with correct palette)
    min_accuracy: float = 0.7


@dataclass
class TestCase:
    """A single regression test case."""
    name: str
    description: str
    savestate: str  # Filename in save_states_for_claude/
    sprite_checks: list[SpriteCheck] = field(default_factory=list)
    slot_checks: list[SlotCheck] = field(default_factory=list)
    memory_checks: list[MemoryCheck] = field(default_factory=list)
    bg_checks: list[BGCheck] = field(default_factory=list)
    # Number of frames to run before checking (let colorizer stabilize)
    warmup_frames: int = 90


@dataclass
class CheckResult:
    """Result of a single check within a test case."""
    name: str
    passed: bool
    message: str
    details: Optional[dict] = None


@dataclass
class TestResult:
    """Result of a complete test case."""
    test_name: str
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)
    error: Optional[str] = None
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Test case definitions
# ---------------------------------------------------------------------------

TEST_CASES = [
    TestCase(
        name="sara_w_alone",
        description="Sara Witch alone - slots 0-3 should have palette 2",
        savestate="level1_sara_w_alone.ss0",
        slot_checks=[
            SlotCheck(
                description="Sara W (slots 0-3) have palette 2",
                slot_low=0, slot_high=3,
                expected_palettes=[2],
            ),
        ],
        memory_checks=[
            MemoryCheck(0xFFBE, "Sara form = Witch (0)", exact_value=0),
            MemoryCheck(0xFFC1, "Gameplay active (nonzero)", nonzero=True),
            MemoryCheck(0xFFBF, "No boss (0)", exact_value=0),
        ],
    ),
    TestCase(
        name="sara_d_alone",
        description="Sara Dragon alone - slots 0-3 should have palette 1",
        savestate="level1_sara_d_alone.ss0",
        slot_checks=[
            SlotCheck(
                description="Sara D (slots 0-3) have palette 1",
                slot_low=0, slot_high=3,
                expected_palettes=[1],
            ),
        ],
        memory_checks=[
            MemoryCheck(0xFFBE, "Sara form = Dragon (nonzero)", nonzero=True),
            MemoryCheck(0xFFC1, "Gameplay active (nonzero)", nonzero=True),
        ],
    ),
    TestCase(
        name="hornets",
        description="Sara W with hornets - enemy sprites should have palette 4",
        savestate="level1_sara_w_4_hornets.ss0",
        slot_checks=[
            SlotCheck(
                description="Sara W (slots 0-3) have palette 2",
                slot_low=0, slot_high=3,
                expected_palettes=[2],
            ),
        ],
        sprite_checks=[
            SpriteCheck(
                description="Hornet sprites have palette 4",
                tile_low=0x40, tile_high=0x4F,
                expected_palettes=[4],
                must_exist=True,
                min_count=2,
            ),
        ],
        memory_checks=[
            MemoryCheck(0xFFBF, "No boss (0)", exact_value=0),
            MemoryCheck(0xFFC1, "Gameplay active", nonzero=True),
        ],
    ),
    TestCase(
        name="orc",
        description="Sara W with orc - orc sprites should have palette 5",
        savestate="level1_sara_w_orc.ss0",
        slot_checks=[
            SlotCheck(
                description="Sara W (slots 0-3) have palette 2",
                slot_low=0, slot_high=3,
                expected_palettes=[2],
            ),
        ],
        sprite_checks=[
            SpriteCheck(
                description="Orc sprites have palette 5",
                tile_low=0x50, tile_high=0x5F,
                expected_palettes=[5],
                must_exist=False,  # May be off-screen at frame 90
            ),
        ],
    ),
    TestCase(
        name="crow",
        description="Sara W with crow - crow sprites should have palette 3",
        savestate="level1_sara_w_crow.ss0",
        slot_checks=[
            SlotCheck(
                description="Sara W (slots 0-3) have palette 2",
                slot_low=0, slot_high=3,
                expected_palettes=[2],
            ),
        ],
        sprite_checks=[
            SpriteCheck(
                description="Crow sprites have palette 3",
                tile_low=0x30, tile_high=0x3F,
                expected_palettes=[3],
                must_exist=False,  # May fly off-screen
            ),
        ],
    ),
    TestCase(
        name="soldier",
        description="Sara W with soldier - soldier sprites should have palette 6",
        savestate="level1_sara_w_soldier.ss0",
        slot_checks=[
            SlotCheck(
                description="Sara W (slots 0-3) have palette 2",
                slot_low=0, slot_high=3,
                expected_palettes=[2],
            ),
        ],
        sprite_checks=[
            SpriteCheck(
                description="Soldier sprites have palette 6",
                tile_low=0x60, tile_high=0x6F,
                expected_palettes=[6],
                must_exist=False,  # May walk off-screen
            ),
        ],
    ),
    TestCase(
        name="moth",
        description="Sara W with moth - moth sprites should have palette 6",
        savestate="level1_sara_w_moth.ss0",
        slot_checks=[
            SlotCheck(
                description="Sara W (slots 0-3) have palette 2",
                slot_low=0, slot_high=3,
                expected_palettes=[2],
            ),
        ],
        sprite_checks=[
            SpriteCheck(
                description="Moth sprites have palette 6 (humanoid range)",
                tile_low=0x60, tile_high=0x6F,
                expected_palettes=[6],
                must_exist=False,  # May fly off-screen
            ),
        ],
    ),
    TestCase(
        name="gargoyle_boss",
        description="Gargoyle mini-boss - boss flag set, boss sprites get palette 6",
        savestate="level1_sara_w_gargoyle_mini_boss.ss0",
        slot_checks=[
            SlotCheck(
                description="Sara W (slots 0-3) have palette 2",
                slot_low=0, slot_high=3,
                expected_palettes=[2],
            ),
            SlotCheck(
                description="Boss entity (slots 4-19) have palette 6 or 7",
                slot_low=4, slot_high=19,
                expected_palettes=[6, 7],
                must_be_visible=True,
            ),
        ],
        memory_checks=[
            MemoryCheck(0xFFBF, "Boss flag = gargoyle (1)", exact_value=1),
            MemoryCheck(0xFFC1, "Gameplay active", nonzero=True),
        ],
    ),
    TestCase(
        name="spider_boss_sara_w",
        description="Spider mini-boss (Sara W) - boss flag should be set",
        savestate="level1_sara_w_spier_miniboss.ss0",
        slot_checks=[
            SlotCheck(
                description="Sara W (slots 0-3) have palette 2",
                slot_low=0, slot_high=3,
                expected_palettes=[2],
            ),
            SlotCheck(
                description="Boss entity (slots 4-39) have palette 6 or 7",
                slot_low=4, slot_high=39,
                expected_palettes=[6, 7],
                must_be_visible=False,  # Spider can be off-screen
            ),
        ],
        memory_checks=[
            MemoryCheck(0xFFBF, "Boss flag = spider (2)", exact_value=2),
        ],
    ),
    TestCase(
        name="spider_boss_sara_d",
        description="Spider mini-boss (Sara D) - Sara D palette + boss",
        savestate="level1_sara_d_spider_miniboss.ss0",
        slot_checks=[
            SlotCheck(
                description="Sara D (slots 0-3) have palette 1",
                slot_low=0, slot_high=3,
                expected_palettes=[1],
            ),
            SlotCheck(
                description="Boss entity (slots 4-39) have palette 6 or 7",
                slot_low=4, slot_high=39,
                expected_palettes=[6, 7],
                must_be_visible=False,  # Spider can be off-screen
            ),
        ],
        memory_checks=[
            MemoryCheck(0xFFBE, "Sara form = Dragon (nonzero)", nonzero=True),
            MemoryCheck(0xFFBF, "Boss flag = spider (2)", exact_value=2),
        ],
    ),
    TestCase(
        name="catfish_special",
        description="Catfish/special entities - check Sara and gameplay state",
        savestate="level1_cat_fish_moth_spike_hazard_orb_item.ss0",
        slot_checks=[
            SlotCheck(
                description="Sara (slots 0-3) have correct palette",
                slot_low=0, slot_high=3,
                expected_palettes=[1, 2],  # Either form
            ),
        ],
        memory_checks=[
            MemoryCheck(0xFFC1, "Gameplay active", nonzero=True),
        ],
    ),
    TestCase(
        name="bg_wall_tiles",
        description="BG wall tiles (0x40-0x5F) should have palette 6",
        savestate="level1_sara_w_alone.ss0",
        bg_checks=[
            BGCheck(
                description="Wall fill tiles (0x40-0x5F) have BG palette 6",
                tile_low=0x40, tile_high=0x5F,
                expected_palette=6,
                min_tiles=3,
                min_accuracy=0.6,
            ),
        ],
        # BG colorizer needs more frames to fill all 1024 positions
        warmup_frames=150,
    ),
    TestCase(
        name="bg_floor_tiles",
        description="BG floor tiles (0x00-0x3F) should have palette 0",
        savestate="level1_sara_w_alone.ss0",
        bg_checks=[
            BGCheck(
                description="Floor tiles (0x00-0x3F) have BG palette 0",
                tile_low=0x00, tile_high=0x3F,
                expected_palette=0,
                min_tiles=5,
                min_accuracy=0.6,
            ),
        ],
        warmup_frames=150,
    ),
    TestCase(
        name="bg_item_tiles",
        description="BG item tiles (0x88-0xDF) should have palette 1 (gold)",
        savestate="level1_sara_w_flash_item.ss0",
        bg_checks=[
            BGCheck(
                description="Item tiles (0x88-0xDF) have BG palette 1 (gold)",
                tile_low=0x88, tile_high=0xDF,
                expected_palette=1,
                min_tiles=1,
                min_accuracy=0.5,
            ),
        ],
        warmup_frames=150,
    ),
    TestCase(
        name="gameplay_flag",
        description="Gameplay flag (0xFFC1) should be nonzero during gameplay",
        savestate="v2.31_sara_w_mid_level1.ss0",
        memory_checks=[
            MemoryCheck(0xFFC1, "Gameplay active (nonzero)", nonzero=True),
            MemoryCheck(0xFFBE, "Sara form flag readable", in_values=[0, 1]),
            MemoryCheck(0xFFBF, "Boss flag readable", in_values=list(range(0, 9))),
        ],
    ),
    TestCase(
        name="title_screen",
        description="Title screen - gameplay flag should be zero (menu mode)",
        savestate="title_screen.ss0",
        memory_checks=[
            MemoryCheck(0xFFC1, "Not gameplay (zero on title)", zero=True),
        ],
        warmup_frames=30,
    ),
]


# ---------------------------------------------------------------------------
# Lua script generation
# ---------------------------------------------------------------------------

def generate_lua_script(test_case: TestCase, output_path: str) -> str:
    """Generate a Lua script that runs the test and writes results to JSON."""

    # Collect all memory addresses we need to read
    memory_addrs = set()
    for mc in test_case.memory_checks:
        memory_addrs.add(mc.address)
    # Always read key state flags
    for addr in [0xFFBE, 0xFFBF, 0xFFC0, 0xFFC1, 0xFFCB, 0xFFD0]:
        memory_addrs.add(addr)

    addr_list = ", ".join(f"0x{a:04X}" for a in sorted(memory_addrs))

    # Determine if we need BG checks
    need_bg = len(test_case.bg_checks) > 0

    # Build BG sampling code (read tiles from both tilemaps)
    bg_sample_lua = ""
    if need_bg:
        bg_sample_lua = r"""
    -- Sample BG tiles and attributes from both tilemaps
    -- We sample a grid of positions from the visible area
    local bg_tiles = {}
    local bg_attrs = {}
    local bg_sample_count = 0

    -- Read LCDC to determine which tilemap is active
    local lcdc = emu:read8(0xFF40)
    local tilemap_base = 0x9800
    if lcdc % 16 >= 8 then  -- bit 3
        tilemap_base = 0x9C00
    end

    -- Sample from the visible area (32x32 tilemap, but screen shows ~20x18)
    -- We sample all 1024 positions but focus checks on visible ones
    for ty = 0, 31 do
        for tx = 0, 31 do
            local offset = ty * 32 + tx
            local addr = tilemap_base + offset

            -- Read tile ID from tilemap (VRAM bank 0)
            -- Write 0 to VBK to select bank 0
            emu:write8(0xFF4F, 0)
            local tile_id = emu:read8(addr)

            -- Read attributes from VRAM bank 1
            emu:write8(0xFF4F, 1)
            local attr = emu:read8(addr)
            local bg_pal = attr % 8  -- bits 0-2

            -- Restore bank 0
            emu:write8(0xFF4F, 0)

            bg_sample_count = bg_sample_count + 1
            table.insert(bg_tiles, tile_id)
            table.insert(bg_attrs, bg_pal)
        end
    end
"""

    # Build the BG results JSON snippet
    bg_json_lua = ""
    if need_bg:
        bg_json_lua = r"""
    -- BG tile/palette data
    json = json .. '  "bg_sample_count": ' .. bg_sample_count .. ',\n'
    json = json .. '  "bg_tiles": ['
    for i, t in ipairs(bg_tiles) do
        if i > 1 then json = json .. ',' end
        json = json .. t
    end
    json = json .. '],\n'
    json = json .. '  "bg_palettes": ['
    for i, p in ipairs(bg_attrs) do
        if i > 1 then json = json .. ',' end
        json = json .. p
    end
    json = json .. '],\n'
"""

    output_json_path = output_path.replace("\\", "/")

    lua = f"""-- Regression test: {test_case.name}
-- Auto-generated Lua script

local WARMUP = {test_case.warmup_frames}
local frame = 0

callbacks:add("frame", function()
    frame = frame + 1
    if frame < WARMUP then return end
    if frame > WARMUP then return end  -- Only run on exactly the warmup frame

    -- Read OAM (hardware OAM at 0xFE00)
    local sprites = {{}}
    for slot = 0, 39 do
        local addr = 0xFE00 + slot * 4
        local y = emu:read8(addr)
        local x = emu:read8(addr + 1)
        local tile = emu:read8(addr + 2)
        local flags = emu:read8(addr + 3)
        local pal = flags % 8

        table.insert(sprites, {{
            slot = slot,
            y = y,
            x = x,
            tile = tile,
            flags = flags,
            palette = pal,
            visible = (y > 0 and y < 160 and x > 0 and x < 168)
        }})
    end

    -- Read memory flags
    local mem = {{}}
    local mem_addrs = {{{addr_list}}}
    for _, a in ipairs(mem_addrs) do
        mem[a] = emu:read8(a)
    end

    {bg_sample_lua}

    -- Build JSON output
    local json = '{{\\n'

    -- Sprite data
    json = json .. '  "sprites": [\\n'
    local first_sprite = true
    for _, s in ipairs(sprites) do
        if not first_sprite then json = json .. ',\\n' end
        first_sprite = false
        json = json .. string.format(
            '    {{"slot": %d, "y": %d, "x": %d, "tile": %d, "flags": %d, "palette": %d, "visible": %s}}',
            s.slot, s.y, s.x, s.tile, s.flags, s.palette,
            s.visible and "true" or "false"
        )
    end
    json = json .. '\\n  ],\\n'

    -- Memory data
    json = json .. '  "memory": {{\\n'
    local first_mem = true
    for _, a in ipairs(mem_addrs) do
        if not first_mem then json = json .. ',\\n' end
        first_mem = false
        json = json .. string.format('    "0x%04X": %d', a, mem[a])
    end
    json = json .. '\\n  }},\\n'

    {bg_json_lua}

    json = json .. '  "warmup_frames": ' .. WARMUP .. ',\\n'
    json = json .. '  "test_name": "{test_case.name}"\\n'
    json = json .. '}}\\n'

    -- Write output
    local f = io.open("{output_json_path}", "w")
    if f then
        f:write(json)
        f:close()
    end

    -- Signal done
    local done = io.open("DONE", "w")
    if done then
        done:write("OK")
        done:close()
    end
end)

console:log("Regression test '{test_case.name}' started (warmup={test_case.warmup_frames} frames)")
"""
    return lua


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def find_mgba() -> Optional[str]:
    """Find mgba-qt executable."""
    for candidate in ["/home/struktured/bin/mgba-qt", "/usr/local/bin/mgba-qt",
                      "/usr/bin/mgba-qt", "mgba-qt"]:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                return candidate
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return None


def run_test_case(
    test_case: TestCase,
    rom_path: Path,
    verbose: bool = False,
) -> TestResult:
    """Run a single test case headlessly and evaluate results."""
    start_time = time.time()

    # Validate savestate exists
    savestate_path = SAVESTATES_DIR / test_case.savestate
    if not savestate_path.exists():
        return TestResult(
            test_name=test_case.name,
            passed=False,
            error=f"Savestate not found: {savestate_path}",
        )

    # Create tmp dir
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    test_tmp = TMP_DIR / test_case.name
    test_tmp.mkdir(parents=True, exist_ok=True)

    # Generate Lua script
    output_json = test_tmp / "result.json"
    lua_script = generate_lua_script(test_case, str(output_json))
    lua_path = test_tmp / "test.lua"
    lua_path.write_text(lua_script)

    # Remove old output files
    for f in [output_json, test_tmp / "DONE"]:
        if f.exists():
            f.unlink()

    mgba = find_mgba()
    if not mgba:
        return TestResult(
            test_name=test_case.name,
            passed=False,
            error="mgba-qt not found",
        )

    # Build headless command
    cmd = [
        "xvfb-run", "-a",
        mgba,
        str(rom_path),
        "-t", str(savestate_path),
        "--script", str(lua_path),
        "-l", "0",
    ]

    env = os.environ.copy()
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SDL_AUDIODRIVER"] = "dummy"

    timeout_secs = max(30, test_case.warmup_frames // 60 * 3 + 15)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(test_tmp),
            env=env,
            start_new_session=True,
        )

        done_file = test_tmp / "DONE"
        wait_start = time.time()

        while time.time() - wait_start < timeout_secs:
            if done_file.exists():
                time.sleep(0.3)  # Let files flush
                break
            if proc.poll() is not None:
                break
            time.sleep(0.2)

        # Kill process
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            time.sleep(0.3)
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass

        # Read results
        if not output_json.exists():
            stderr_text = ""
            try:
                stderr_text = proc.stderr.read().decode()[:500]
            except Exception:
                pass
            return TestResult(
                test_name=test_case.name,
                passed=False,
                error=f"No output JSON produced. stderr: {stderr_text}",
                duration_seconds=time.time() - start_time,
            )

        try:
            data = json.loads(output_json.read_text())
        except json.JSONDecodeError as e:
            return TestResult(
                test_name=test_case.name,
                passed=False,
                error=f"Invalid JSON output: {e}",
                duration_seconds=time.time() - start_time,
            )

        # Evaluate checks
        checks = []
        checks.extend(evaluate_slot_checks(test_case, data, verbose))
        checks.extend(evaluate_sprite_checks(test_case, data, verbose))
        checks.extend(evaluate_memory_checks(test_case, data, verbose))
        checks.extend(evaluate_bg_checks(test_case, data, verbose))

        all_passed = all(c.passed for c in checks)

        return TestResult(
            test_name=test_case.name,
            passed=all_passed,
            checks=checks,
            duration_seconds=time.time() - start_time,
        )

    except Exception as e:
        return TestResult(
            test_name=test_case.name,
            passed=False,
            error=f"Exception: {e}",
            duration_seconds=time.time() - start_time,
        )


# ---------------------------------------------------------------------------
# Check evaluators
# ---------------------------------------------------------------------------

def evaluate_slot_checks(
    test_case: TestCase,
    data: dict,
    verbose: bool,
) -> list[CheckResult]:
    """Evaluate slot-based palette checks (for Sara who always occupies specific slots)."""
    results = []
    sprites = data.get("sprites", [])

    for check in test_case.slot_checks:
        # Get sprites in the specified slot range
        slot_sprites = [
            s for s in sprites
            if check.slot_low <= s.get("slot", -1) <= check.slot_high
            and s.get("visible", False)
        ]

        if check.must_be_visible and not slot_sprites:
            results.append(CheckResult(
                name=check.description,
                passed=False,
                message=f"No visible sprites in slots {check.slot_low}-{check.slot_high}",
            ))
            continue

        if not slot_sprites:
            results.append(CheckResult(
                name=check.description,
                passed=True,
                message="No visible sprites in slot range (not required)",
            ))
            continue

        correct = [
            s for s in slot_sprites
            if s.get("palette") in check.expected_palettes
        ]
        incorrect = [
            s for s in slot_sprites
            if s.get("palette") not in check.expected_palettes
        ]

        if incorrect:
            bad_details = [
                f"slot={s['slot']} tile=0x{s['tile']:02X} pal={s['palette']} "
                f"(expected {check.expected_palettes})"
                for s in incorrect
            ]
            results.append(CheckResult(
                name=check.description,
                passed=False,
                message=f"{len(incorrect)}/{len(slot_sprites)} sprites have wrong palette",
                details={
                    "correct_count": len(correct),
                    "incorrect_count": len(incorrect),
                    "incorrect_sprites": bad_details[:10],
                },
            ))
        else:
            results.append(CheckResult(
                name=check.description,
                passed=True,
                message=f"{len(correct)}/{len(slot_sprites)} sprites correct "
                        f"(palette {check.expected_palettes})",
            ))

    return results


def evaluate_sprite_checks(
    test_case: TestCase,
    data: dict,
    verbose: bool,
) -> list[CheckResult]:
    """Evaluate sprite palette checks against OAM data."""
    results = []
    sprites = data.get("sprites", [])

    for check in test_case.sprite_checks:
        # Find visible sprites in the tile range
        matching = [
            s for s in sprites
            if s.get("visible", False)
            and check.tile_low <= s.get("tile", -1) <= check.tile_high
        ]

        if check.must_exist and len(matching) < check.min_count:
            results.append(CheckResult(
                name=check.description,
                passed=False,
                message=f"Found {len(matching)} sprites in tile range "
                        f"0x{check.tile_low:02X}-0x{check.tile_high:02X}, "
                        f"expected at least {check.min_count}",
                details={"matching_count": len(matching), "tiles_found": [
                    f"0x{s['tile']:02X}" for s in matching
                ]},
            ))
            continue

        if not matching:
            # No sprites to check, and must_exist is False
            results.append(CheckResult(
                name=check.description,
                passed=True,
                message="No sprites in range (not required)",
            ))
            continue

        # Check palettes
        correct = [
            s for s in matching
            if s.get("palette") in check.expected_palettes
        ]
        incorrect = [
            s for s in matching
            if s.get("palette") not in check.expected_palettes
        ]

        if incorrect:
            bad_details = [
                f"slot={s['slot']} tile=0x{s['tile']:02X} pal={s['palette']} "
                f"(expected {check.expected_palettes})"
                for s in incorrect
            ]
            results.append(CheckResult(
                name=check.description,
                passed=False,
                message=f"{len(incorrect)}/{len(matching)} sprites have wrong palette",
                details={
                    "correct_count": len(correct),
                    "incorrect_count": len(incorrect),
                    "incorrect_sprites": bad_details[:10],
                },
            ))
        else:
            results.append(CheckResult(
                name=check.description,
                passed=True,
                message=f"{len(correct)}/{len(matching)} sprites correct "
                        f"(palette {check.expected_palettes})",
            ))

    return results


def evaluate_memory_checks(
    test_case: TestCase,
    data: dict,
    verbose: bool,
) -> list[CheckResult]:
    """Evaluate memory flag checks."""
    results = []
    memory = data.get("memory", {})

    for check in test_case.memory_checks:
        addr_key = f"0x{check.address:04X}"
        if addr_key not in memory:
            results.append(CheckResult(
                name=check.description,
                passed=False,
                message=f"Address {addr_key} not read",
            ))
            continue

        value = memory[addr_key]

        passed = True
        message = f"{addr_key} = 0x{value:02X} ({value})"

        if check.exact_value is not None and value != check.exact_value:
            passed = False
            message += f" -- expected 0x{check.exact_value:02X}"

        if check.nonzero is True and value == 0:
            passed = False
            message += " -- expected nonzero"

        if check.zero is True and value != 0:
            passed = False
            message += " -- expected zero"

        if check.in_values is not None and value not in check.in_values:
            passed = False
            message += f" -- expected one of {check.in_values}"

        results.append(CheckResult(
            name=check.description,
            passed=passed,
            message=message,
        ))

    return results


def evaluate_bg_checks(
    test_case: TestCase,
    data: dict,
    verbose: bool,
) -> list[CheckResult]:
    """Evaluate BG tile palette checks."""
    results = []
    bg_tiles = data.get("bg_tiles", [])
    bg_palettes = data.get("bg_palettes", [])

    if not bg_tiles and test_case.bg_checks:
        results.append(CheckResult(
            name="BG data availability",
            passed=False,
            message="No BG tile data in output",
        ))
        return results

    for check in test_case.bg_checks:
        # Find tiles in the range and check their palettes
        matching_indices = [
            i for i, t in enumerate(bg_tiles)
            if check.tile_low <= t <= check.tile_high
        ]

        if len(matching_indices) < check.min_tiles:
            results.append(CheckResult(
                name=check.description,
                passed=False,
                message=f"Found {len(matching_indices)} tiles in range "
                        f"0x{check.tile_low:02X}-0x{check.tile_high:02X}, "
                        f"need at least {check.min_tiles}",
                details={"found_count": len(matching_indices)},
            ))
            continue

        correct = sum(
            1 for i in matching_indices
            if bg_palettes[i] == check.expected_palette
        )
        total = len(matching_indices)
        accuracy = correct / total if total > 0 else 0.0

        if accuracy < check.min_accuracy:
            # Gather wrong palette distribution for diagnostics
            wrong_pal_dist: dict[int, int] = {}
            for i in matching_indices:
                p = bg_palettes[i]
                if p != check.expected_palette:
                    wrong_pal_dist[p] = wrong_pal_dist.get(p, 0) + 1

            results.append(CheckResult(
                name=check.description,
                passed=False,
                message=f"Accuracy {accuracy:.1%} ({correct}/{total}) "
                        f"< {check.min_accuracy:.0%} threshold",
                details={
                    "correct": correct,
                    "total": total,
                    "accuracy": round(accuracy, 3),
                    "wrong_palette_distribution": wrong_pal_dist,
                },
            ))
        else:
            results.append(CheckResult(
                name=check.description,
                passed=True,
                message=f"Accuracy {accuracy:.1%} ({correct}/{total} tiles correct, "
                        f"expected palette {check.expected_palette})",
            ))

    return results


# ---------------------------------------------------------------------------
# Summary printing
# ---------------------------------------------------------------------------

def print_summary(
    results: list[TestResult],
    verbose: bool = False,
) -> None:
    """Print a formatted summary table of all test results."""
    print()
    print("=" * 78)
    print("  PENTA DRAGON DX - REGRESSION TEST RESULTS")
    print("=" * 78)
    print()

    # Summary table header
    print(f"  {'Test Name':<30} {'Status':<8} {'Checks':<12} {'Time':>6}")
    print(f"  {'-'*30} {'-'*8} {'-'*12} {'-'*6}")

    passed_count = 0
    failed_count = 0
    error_count = 0

    for r in results:
        if r.error:
            status = "ERROR"
            error_count += 1
            checks_str = "---"
        elif r.passed:
            status = "PASS"
            passed_count += 1
            checks_str = f"{sum(1 for c in r.checks if c.passed)}/{len(r.checks)}"
        else:
            status = "FAIL"
            failed_count += 1
            checks_str = f"{sum(1 for c in r.checks if c.passed)}/{len(r.checks)}"

        time_str = f"{r.duration_seconds:.1f}s"
        print(f"  {r.test_name:<30} {status:<8} {checks_str:<12} {time_str:>6}")

    total = len(results)
    print(f"  {'-'*30} {'-'*8} {'-'*12} {'-'*6}")
    print(f"  {'TOTAL':<30} {'':<8} {passed_count}P/{failed_count}F/{error_count}E")
    print()

    # Details for failures
    has_failures = False
    for r in results:
        if r.error:
            if not has_failures:
                print("-" * 78)
                print("  FAILURE/ERROR DETAILS:")
                print("-" * 78)
                has_failures = True
            print(f"\n  [{r.test_name}] ERROR: {r.error}")
        elif not r.passed:
            if not has_failures:
                print("-" * 78)
                print("  FAILURE/ERROR DETAILS:")
                print("-" * 78)
                has_failures = True
            print(f"\n  [{r.test_name}]")
            for c in r.checks:
                if not c.passed:
                    print(f"    FAIL: {c.name}")
                    print(f"          {c.message}")
                    if verbose and c.details:
                        for k, v in c.details.items():
                            print(f"          {k}: {v}")

    # Verbose: show all check details
    if verbose:
        print()
        print("-" * 78)
        print("  ALL CHECK DETAILS:")
        print("-" * 78)
        for r in results:
            if r.error:
                continue
            print(f"\n  [{r.test_name}]")
            for c in r.checks:
                tag = "PASS" if c.passed else "FAIL"
                print(f"    [{tag}] {c.name}: {c.message}")

    print()
    print("=" * 78)
    if failed_count == 0 and error_count == 0:
        print(f"  ALL {total} TESTS PASSED")
    else:
        print(f"  {passed_count}/{total} PASSED, "
              f"{failed_count} FAILED, {error_count} ERRORS")
    print("=" * 78)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Penta Dragon DX Regression Test Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--rom", type=Path, default=ROM_PATH,
        help=f"ROM to test (default: {ROM_PATH.relative_to(PROJECT_ROOT)})",
    )
    parser.add_argument(
        "--test", type=str, default=None,
        help="Run a specific test by name (e.g., 'sara_w_alone')",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List available test cases and exit",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show detailed output for all checks",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    if args.list:
        print("Available test cases:")
        for tc in TEST_CASES:
            print(f"  {tc.name:<30} {tc.description}")
            print(f"  {'':>30} savestate: {tc.savestate}")
        return

    rom = args.rom
    if not rom.exists():
        print(f"ERROR: ROM not found: {rom}", file=sys.stderr)
        sys.exit(2)

    # Select test cases
    if args.test:
        selected = [tc for tc in TEST_CASES if args.test in tc.name]
        if not selected:
            print(f"ERROR: No test matching '{args.test}'", file=sys.stderr)
            print("Available tests:", file=sys.stderr)
            for tc in TEST_CASES:
                print(f"  {tc.name}", file=sys.stderr)
            sys.exit(2)
    else:
        selected = TEST_CASES

    # Use stderr for progress when in JSON mode
    progress = sys.stderr if args.json else sys.stdout

    print(f"ROM: {rom}", file=progress)
    print(f"Running {len(selected)} test(s)...\n", file=progress)

    # Run tests
    results: list[TestResult] = []
    for i, tc in enumerate(selected, 1):
        label = f"[{i}/{len(selected)}] {tc.name}"
        print(f"  {label:<40}", end="", flush=True, file=progress)

        result = run_test_case(tc, rom, verbose=args.verbose)
        results.append(result)

        if result.error:
            print(f"ERROR ({result.duration_seconds:.1f}s)", file=progress)
        elif result.passed:
            print(f"PASS  ({result.duration_seconds:.1f}s)", file=progress)
        else:
            failed_checks = [c for c in result.checks if not c.passed]
            print(f"FAIL  ({result.duration_seconds:.1f}s) "
                  f"[{len(failed_checks)} check(s) failed]", file=progress)

    # Output
    if args.json:
        json_output = {
            "rom": str(rom),
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed and not r.error),
            "errors": sum(1 for r in results if r.error),
            "results": [
                {
                    "name": r.test_name,
                    "passed": r.passed,
                    "error": r.error,
                    "duration": round(r.duration_seconds, 2),
                    "checks": [
                        {
                            "name": c.name,
                            "passed": c.passed,
                            "message": c.message,
                            "details": c.details,
                        }
                        for c in r.checks
                    ],
                }
                for r in results
            ],
        }
        print(json.dumps(json_output, indent=2))
    else:
        print_summary(results, verbose=args.verbose)

    # Exit code
    all_passed = all(r.passed for r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
