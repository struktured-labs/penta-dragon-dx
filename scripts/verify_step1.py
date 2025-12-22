#!/usr/bin/env python3
"""
Verify STEP 1: Boot-Time Palette Loading
Checks if Palette 1 is loaded into CGB palette RAM
"""
import subprocess
import time
import os
from pathlib import Path

ROM_PATH = Path(__file__).parent.parent / 'rom' / 'working' / 'Penta Dragon (J).gb'
OUTPUT_DIR = Path(__file__).parent.parent / 'step1_output'

def build_rom():
    """Build ROM with Step 1 only"""
    print("🔨 Building ROM with Step 1 (boot palette loader)...")
    result = subprocess.run(
        ['python3', 'scripts/step1_boot_palette_only.py'],
        cwd=Path(__file__).parent.parent,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"❌ Build failed: {result.stderr}")
        return False
    print(result.stdout)
    return ROM_PATH.exists()

def create_verification_lua():
    """Create Lua script to verify palette is loaded"""
    log_path = OUTPUT_DIR / 'step1_verification.log'
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    lua = f"""
-- Step 1 Verification: Check if Palette 1 is loaded at boot
local frameCount = 0
local logFile = nil

-- Expected Palette 1 values (SARA_W: transparent, green, orange, dark green)
local expected = {{
    0x0000,  -- transparent
    0x03E0,  -- green
    0x021F,  -- orange
    0x0280   -- dark green
}}

function log(msg)
    if logFile then
        logFile:write(msg .. "\\n")
    end
    console:log(msg)
end

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Initialize log file
    if frameCount == 1 then
        logFile = io.open("{log_path}", "w")
        log("=== Step 1 Verification: Boot-Time Palette Loading ===")
        log("")
        
        -- Check 1: Boot hook is installed
        local boot_hook = emu:read8(0x0150)
        if boot_hook == 0xCD then
            log("✅ CHECK 1: Boot hook installed at 0x0150 (CALL instruction)")
        else
            log("❌ CHECK 1: Boot hook NOT installed (found 0x" .. string.format("%02X", boot_hook) .. ")")
        end
        log("")
    end
    
    -- Check 2: Verify palette is loaded (check after boot, around frame 10)
    if frameCount == 10 then
        log("--- CHECK 2: Palette Loading Verification ---")
        log("Checking OBJ Palette 1 in CGB palette RAM (0xFF6A-0xFF6B):")
        log("")
        
        local all_match = true
        
        -- Read OBJ Palette 1 (index 8-15)
        for colorIdx = 0, 3 do
            -- Set palette index register (OCPS)
            -- 0x88 = auto-increment (bit 7), OBJ palette (bit 6), index 8 (bits 0-5)
            emu:write8(0xFF6A, 0x80 + (1 * 8) + (colorIdx * 2))
            local lo = emu:read8(0xFF6B)  -- Read low byte (OCPD)
            emu:write8(0xFF6A, 0x80 + (1 * 8) + (colorIdx * 2) + 1)
            local hi = emu:read8(0xFF6B)  -- Read high byte (OCPD)
            local color = lo + (hi * 256)
            local expected_color = expected[colorIdx + 1]
            
            if color == expected_color then
                log(string.format("  Color %d: 0x%04X ✅ (matches expected)", colorIdx, color))
            else
                log(string.format("  Color %d: 0x%04X ❌ (expected 0x%04X)", colorIdx, color, expected_color))
                all_match = false
            end
        end
        
        log("")
        if all_match then
            log("✅ CHECK 2: Palette 1 loaded correctly!")
            log("   All 4 colors match expected values")
        else
            log("❌ CHECK 2: Palette 1 NOT loaded correctly")
            log("   Some colors don't match expected values")
        end
        log("")
    end
    
    -- Check 3: Verify palette persists (check again later)
    if frameCount == 100 then
        log("--- CHECK 3: Palette Persistence ---")
        log("Checking if Palette 1 is still loaded after 100 frames:")
        log("")
        
        local still_loaded = true
        for colorIdx = 0, 3 do
            emu:write8(0xFF6A, 0x80 + (1 * 8) + (colorIdx * 2))
            local lo = emu:read8(0xFF6B)
            emu:write8(0xFF6A, 0x80 + (1 * 8) + (colorIdx * 2) + 1)
            local hi = emu:read8(0xFF6B)
            local color = lo + (hi * 256)
            local expected_color = expected[colorIdx + 1]
            
            if color ~= expected_color then
                still_loaded = false
                log(string.format("  Color %d: 0x%04X ❌ (was overwritten)", colorIdx, color))
            end
        end
        
        if still_loaded then
            log("✅ CHECK 3: Palette persists (not overwritten)")
        else
            log("❌ CHECK 3: Palette was overwritten by game")
        end
        log("")
    end
    
    -- Stop after checks complete
    if frameCount >= 150 then
        log("=== Verification Complete ===")
        if logFile then
            logFile:close()
        end
        emu:quit()
    end
end)

console:log("Step 1 verification script loaded")
"""
    script_path = OUTPUT_DIR / 'verify_step1.lua'
    script_path.write_text(lua)
    return script_path

def run_verification():
    """Run mGBA with verification script"""
    script_path = create_verification_lua()
    mgba_qt = '/usr/local/bin/mgba-qt'
    
    rom_path_abs = ROM_PATH.resolve()
    lua_script_abs = script_path.resolve()
    
    # Use Xvfb for headless operation
    xvfb_available = subprocess.run(['which', 'Xvfb'], capture_output=True).returncode == 0
    
    if xvfb_available:
        display_num = 99
        xvfb_cmd = ['Xvfb', f':{display_num}', '-screen', '0', '1024x768x24', '-ac']
        xvfb_proc = subprocess.Popen(xvfb_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        display_env = f':{display_num}'
        print(f"✓ Using Xvfb virtual display :{display_num}")
    else:
        display_env = os.environ.get('DISPLAY', ':0')
        print(f"⚠️  Xvfb not available, using DISPLAY={display_env}")
        xvfb_proc = None
    
    env = os.environ.copy()
    env['DISPLAY'] = display_env
    env['QT_QPA_PLATFORM'] = 'xcb'
    
    cmd = [mgba_qt, str(rom_path_abs), '--script', str(lua_script_abs), '--fastforward']
    
    print(f"🚀 Running verification...")
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        proc.wait(timeout=60)  # Give more time for verification
    except subprocess.TimeoutExpired:
        proc.kill()
        print("⚠️  Verification timed out, but log may have been created")
        # Still try to analyze results even if timed out
        time.sleep(1)
        return True  # Return True to allow analysis
    
    if xvfb_available and xvfb_proc:
        try:
            xvfb_proc.terminate()
            xvfb_proc.wait(timeout=1)
        except:
            xvfb_proc.kill()
    
    return True

def analyze_results():
    """Analyze verification log"""
    log_path = OUTPUT_DIR / 'step1_verification.log'
    
    if not log_path.exists():
        print("❌ Verification log not found")
        return False
    
    with open(log_path, 'r') as f:
        content = f.read()
    
    print("\n" + "=" * 60)
    print("Verification Results:")
    print("=" * 60)
    print(content)
    print("=" * 60)
    
    # Check for success indicators
    # Step 1 goal: Verify palette loads at boot (CHECK 2 is the critical one)
    palette_loaded = "✅ CHECK 2" in content and "Palette 1 loaded correctly" in content
    
    print(f"\n📊 Summary:")
    if "✅ CHECK 1" in content:
        print("   ✅ Boot hook installed")
    if palette_loaded:
        print("   ✅ Palette loaded correctly at boot")
    if "✅ CHECK 3" in content:
        print("   ✅ Palette persists (not overwritten)")
    elif "❌ CHECK 3" in content:
        print("   ⚠️  Palette gets overwritten (expected - will fix in Step 2)")
    
    # Step 1 passes if palette loads correctly (CHECK 2)
    # CHECK 3 failure is expected - game overwrites palettes, we'll fix that later
    if palette_loaded:
        print("\n✅ STEP 1 PASSED: Boot-time palette loading works!")
        print("   Palette 1 is correctly loaded into CGB palette RAM at boot")
        print("   (Note: Palette gets overwritten later - that's Step 2's problem)")
        return True
    else:
        print("\n❌ STEP 1 FAILED: Palette not loaded correctly")
        print("   Review log file for details:", log_path)
        return False

def main():
    print("=" * 60)
    print("STEP 1 Verification: Boot-Time Palette Loading")
    print("=" * 60)
    print()
    
    # Build ROM
    if not build_rom():
        print("❌ Failed to build ROM")
        return False
    
    # Run verification
    if not run_verification():
        print("❌ Verification failed or timed out")
        return False
    
    # Analyze results
    return analyze_results()

if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)

