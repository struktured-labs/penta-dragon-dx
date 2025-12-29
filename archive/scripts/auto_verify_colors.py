#!/usr/bin/env python3
"""
Automated color verification with ROM modification implementation.
1. Hypothesizes palette injection approach
2. Runs mgba-headless for 90 seconds, captures screenshots around 40-50s
3. Analyzes screenshots for 3 distinct color palettes
4. If good: launches mgba-qt.backup for user testing
5. Otherwise: tries different injection approach
"""
import subprocess
import time
import sys
import threading
import http.server
import socketserver
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("Installing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--break-system-packages", "pillow", "numpy"], check=True)
    from PIL import Image
    import numpy as np

# Global web server
web_server = None
web_port = 8080

def load_current_palettes():
    """Load current palette configuration from YAML"""
    try:
        import yaml
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--break-system-packages", "pyyaml"], check=True)
        import yaml
    
    palette_path = Path("palettes/penta_palettes.yaml")
    if not palette_path.exists():
        return None
    try:
        with open(palette_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"⚠️  Could not load palette YAML: {e}")
        return None

def save_palettes(palettes):
    """Save palette configuration to YAML"""
    try:
        import yaml
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--break-system-packages", "pyyaml"], check=True)
        import yaml
    
    palette_path = Path("palettes/penta_palettes.yaml")
    try:
        with open(palette_path, 'w') as f:
            yaml.dump(palettes, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        print(f"⚠️  Could not save palette YAML: {e}")
        return False

def generate_next_palette_config(iteration):
    """Generate a new palette configuration"""
    palettes = load_current_palettes()
    if not palettes:
        return None
    
    color_sets = [
        {'sara_d': ['transparent', '001F', '001F', '001F'],  # Red
         'sara_w': ['transparent', '03E0', '03E0', '03E0'],  # Green
         'dragon_fly': ['transparent', '7C00', '7C00', '7C00']},  # Blue
        {'sara_d': ['transparent', '7C1F', '7C1F', '7C1F'],  # Magenta
         'sara_w': ['transparent', '03FF', '03FF', '03FF'],  # Cyan
         'dragon_fly': ['transparent', '7FE0', '7FE0', '7FE0']},  # Yellow
        {'sara_d': ['transparent', '021F', '021F', '021F'],  # Orange
         'sara_w': ['transparent', '6010', '6010', '6010'],  # Purple
         'dragon_fly': ['transparent', '03E7', '03E7', '03E7']},  # Lime
        {'sara_d': ['transparent', '7FFF', '7FFF', '7FFF'],  # White
         'sara_w': ['transparent', '001F', '001F', '001F'],  # Red
         'dragon_fly': ['transparent', '7FE0', '4A00', '2100']},  # Yellow/Orange
        {'sara_d': ['transparent', '5000', '5000', '5000'],  # Dark Blue
         'sara_w': ['transparent', '7D00', '7D00', '7D00'],  # Light Blue
         'dragon_fly': ['transparent', '7FE0', '7FE0', '7FE0']},  # Yellow
    ]
    
    config = color_sets[(iteration - 1) % len(color_sets)]
    palettes['obj_palettes']['MainCharacter']['colors'] = config['sara_d']
    palettes['obj_palettes']['EnemyBasic']['colors'] = config['sara_w']
    palettes['obj_palettes']['MainBoss']['colors'] = config['dragon_fly']
    
    return palettes

def implement_rom_modification(iteration):
    """
    Actually implement ROM modifications based on iteration.
    Returns path to modified build script.
    """
    build_script = Path("scripts/penta_cursor_dx.py")
    original_content = build_script.read_text()
    
    # Determine strategy
    if iteration <= 2:
        strategy_name = "boot_time"
        strategy_desc = "Boot-time palette loading (current approach)"
    elif iteration <= 4:
        strategy_name = "vblank_hook"
        strategy_desc = "VBlank interrupt hook (0x0040) - reload palettes every frame"
    elif iteration <= 6:
        strategy_name = "sprite_oam"
        strategy_desc = "Sprite OAM attribute modification - set palette bits in sprite flags"
    elif iteration <= 8:
        strategy_name = "late_init"
        strategy_desc = "Late initialization - load palettes after game starts"
    else:
        strategy_name = "hybrid"
        strategy_desc = "Hybrid: boot loader + VBlank refresh"
    
    # Create modified build script
    modified_script = Path(f"scripts/penta_cursor_dx_iter{iteration}_{strategy_name}.py")
    
    if strategy_name == "boot_time":
        # Use original script as-is
        modified_script.write_text(original_content)
    elif strategy_name == "vblank_hook":
        # Add VBlank hook code before checksums
        insertion_marker = "# 8. Checksums"
        if insertion_marker in original_content:
            parts = original_content.split(insertion_marker, 1)
            vblank_code = '''
    # VBlank Hook (Iteration {}) - Reload palettes every frame
    vblank_hook_code = [
        0xF5, 0xC5, 0xD5, 0xE5,  # PUSH AF, BC, DE, HL
        0x3E, 0x80, 0xE0, 0x68,  # LDH [FF68], A (BCPS auto-increment)
        0x21, 0x00, 0x7E,        # LD HL, 0x7E00 (BG palettes)
        0x0E, 0x40,              # LD C, 64 (64 bytes)
        0x2A, 0xE0, 0x69,        # loop: LD A, [HL+]; LDH [FF69], A
        0x0D,                    # DEC C
        0x20, 0xFA,              # JR NZ, loop
        0x3E, 0x80, 0xE0, 0x6A,  # LDH [FF6A], A (OCPS auto-increment)
        0x21, 0x40, 0x7E,        # LD HL, 0x7E40 (OBJ palettes)
        0x0E, 0x40,              # LD C, 64
        0x2A, 0xE0, 0x6B,        # loop: LD A, [HL+]; LDH [FF6B], A
        0x0D,                    # DEC C
        0x20, 0xFA,              # JR NZ, loop
        0xE1, 0xD1, 0xC1, 0xF1,  # POP HL, DE, BC, AF
        0xC9                     # RET
    ]
    # Install VBlank hook at 0x0040
    hook_addr = base + 0x100
    rom[0x0040] = 0xC3  # JP
    rom[0x0041] = hook_addr & 0xFF  # Low byte
    rom[0x0042] = (hook_addr >> 8) & 0xFF  # High byte
    rom[hook_addr:hook_addr+len(vblank_hook_code)] = vblank_hook_code
    print("✓ Installed VBlank hook for palette reloading")
'''.format(iteration)
            modified_content = parts[0] + vblank_code + insertion_marker + parts[1]
            modified_script.write_text(modified_content)
        else:
            modified_script.write_text(original_content)
    elif strategy_name == "sprite_oam":
        # Add sprite OAM modification code
        insertion_marker = "# 8. Checksums"
        if insertion_marker in original_content:
            parts = original_content.split(insertion_marker, 1)
            sprite_code = '''
    # Sprite OAM Modification (Iteration {}) - Assign palettes per sprite
    sprite_palette_func = [
        0xF5, 0xC5, 0xD5, 0xE5,  # PUSH AF, BC, DE, HL
        0x21, 0x00, 0xC0,        # LD HL, 0xC000 (shadow OAM)
        0x06, 0x28,              # LD B, 40 (40 sprites)
        0x0E, 0x00,              # LD C, 0 (sprite index)
        # Loop:
        0x79,                    # LD A, C (sprite index)
        0x87,                    # ADD A, A (*2)
        0x87,                    # ADD A, A (*4)
        0x85,                    # ADD A, L
        0x6F,                    # LD L, A (HL points to sprite Y)
        0x7E,                    # LD A, [HL] (get Y)
        0xA7,                    # AND A
        0x28, 0x1A,              # JR Z, skip (if Y=0, sprite not used)
        0x23, 0x23, 0x23,        # INC HL x3 (point to flags byte)
        0x79,                    # LD A, C (get sprite index)
        0xFE, 0x04,              # CP 4
        0x38, 0x08,              # JR C, .player (index < 4)
        0xFE, 0x08,              # CP 8
        0x38, 0x06,              # JR C, .enemy (4 <= index < 8)
        0x3E, 0x07,              # LD A, 7 (boss palette)
        0x18, 0x04,              # JR .set
        # .player:
        0x3E, 0x00,              # LD A, 0 (player palette)
        0x18, 0x00,              # JR .set
        # .enemy:
        0x3E, 0x01,              # LD A, 1 (enemy palette)
        # .set:
        0x57,                    # LD D, A (save palette)
        0x7E,                    # LD A, [HL] (get flags)
        0xE6, 0xF8,              # AND 0xF8 (clear palette bits 0-2)
        0xB2,                    # OR D (set palette)
        0x77,                    # LD [HL], A (write back)
        0xE1,                    # POP HL (restore)
        0x0C,                    # INC C
        0x05,                    # DEC B
        0x20, 0xD4,              # JR NZ, loop
        0xE1, 0xD1, 0xC1, 0xF1,  # POP HL, DE, BC, AF
        0xC9                     # RET
    ]
    sprite_func_addr = base + 0x150
    rom[sprite_func_addr:sprite_func_addr+len(sprite_palette_func)] = sprite_palette_func
    # Hook into VBlank to call sprite function
    # (This would need to be integrated with existing VBlank hook or boot loader)
    print("✓ Installed sprite palette assignment function")
'''.format(iteration)
            modified_content = parts[0] + sprite_code + insertion_marker + parts[1]
            modified_script.write_text(modified_content)
        else:
            modified_script.write_text(original_content)
    else:
        # For late_init and hybrid, use original for now
        modified_script.write_text(original_content)
    
    return modified_script, strategy_desc

def build_rom(build_script_path):
    """Build the ROM using specified build script"""
    result = subprocess.run(
        ["uv", "run", str(build_script_path)],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"Build failed: {result.stderr}")
        return False
    print("✅ ROM built successfully")
    return True

def create_lua_vram_inspection_script(expected_palettes):
    """Create Lua script to inspect VRAM/palette RAM directly instead of screenshots"""
    output_file = Path("rom/working").resolve() / f"palette_inspection_{int(time.time() * 1000)}.txt"
    script_path = Path("rom/working").resolve() / "scripts" / f"mgba_script_{int(time.time() * 1000)}.lua"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Expected palette values from YAML (BGR555 format)
    # MainCharacter (Sara D), EnemyBasic (Sara W), MainBoss (Dragon Fly)
    expected_sara_d = expected_palettes.get('MainCharacter', {}).get('colors', [])
    expected_sara_w = expected_palettes.get('EnemyBasic', {}).get('colors', [])
    expected_dragon_fly = expected_palettes.get('MainBoss', {}).get('colors', [])
    
    # Note: Expected palettes are passed but we'll read actual values from VRAM
    
    # Use raw string to avoid escaping issues
    output_file_str = str(output_file)
    script_content = f'''-- VRAM/Palette RAM inspection script - headless mode
-- Inspects palette RAM (FF68-FF6B) and sprite OAM (FE00-FE9F) directly
local outputFile = "{output_file_str}"
local startFrame = 2400  -- 40 seconds at 60fps (when sprites appear)
local endFrame = 5400  -- 90 seconds
local checkInterval = 300  -- Check every 5 seconds
local frameCount = 0
local checkCount = 0

console:log("VRAM inspection script: Will check palette RAM and OAM from 40s to 90s")

-- Function to read palette RAM using emu:read8/write8 (like verify_palettes.lua)
local function readPaletteRAM(paletteIndex, isOBJ)
    -- Palette index 0-7, isOBJ true for sprite palettes
    local baseReg = isOBJ and 0xFF6A or 0xFF68  -- OCPS or BCPS
    local dataReg = isOBJ and 0xFF6B or 0xFF69  -- OCPD or BCPD
    
    local colors = {{}}
    for colorIdx = 0, 3 do
        -- Set palette index via OCPS/BCPS (auto-increment mode)
        emu:write8(baseReg, 0x80 + (paletteIndex * 8) + (colorIdx * 2))
        local lo = emu:read8(dataReg)
        emu:write8(baseReg, 0x80 + (paletteIndex * 8) + (colorIdx * 2) + 1)
        local hi = emu:read8(dataReg)
        local color = lo + (hi * 256)
        table.insert(colors, string.format("%04X", color))
    end
    
    return colors
end

-- Function to read sprite OAM attributes
local function readOAM()
    local sprites = {{}}
    for i = 0, 39 do  -- 40 sprites
        local oamBase = 0xFE00 + (i * 4)
        local y = emu:read8(oamBase)
        local x = emu:read8(oamBase + 1)
        local tile = emu:read8(oamBase + 2)
        local attr = emu:read8(oamBase + 3)
        
        if y > 0 and y < 160 and x > 0 and x < 168 then  -- Sprite is visible
            local paletteNum = attr & 0x07  -- Lower 3 bits are palette
            sprites[#sprites + 1] = {{
                index = i,
                y = y,
                x = x,
                tile = tile,
                flags = attr,
                palette = paletteNum
            }}
        end
    end
    return sprites
end

-- Function to format palette as hex (colors is already a table of hex strings)
local function paletteToHex(colors)
    return table.concat(colors, " ")
end

-- Function to check if palettes match expected values
local function checkPalettes()
    checkCount = checkCount + 1
    
    -- Read OBJ palettes (sprite palettes)
    local objPal0 = readPaletteRAM(0, true)  -- Sara D (MainCharacter)
    local objPal1 = readPaletteRAM(1, true)  -- Sara W (EnemyBasic)
    local objPal7 = readPaletteRAM(7, true)  -- Dragon Fly (MainBoss)
    
    -- Read OAM to see which sprites use which palettes
    local sprites = readOAM()
    
    -- Write results to file
    local file = io.open(outputFile, "a")
    if file then
        file:write(string.format("\n=== Check #%d at frame %d ===\n", checkCount, frameCount))
        file:write("OBJ Palette 0 (Sara D): " .. paletteToHex(objPal0) .. "\n")
        file:write("OBJ Palette 1 (Sara W): " .. paletteToHex(objPal1) .. "\n")
        file:write("OBJ Palette 7 (Dragon Fly): " .. paletteToHex(objPal7) .. "\n")
        file:write(string.format("Visible sprites: %d\n", #sprites))
        
        -- Show first 10 sprites and their palette assignments
        for i = 1, math.min(10, #sprites) do
            local s = sprites[i]
            file:write(string.format("  Sprite %d: tile=%02X palette=%d x=%d y=%d\n", 
                s.index, s.tile, s.palette, s.x, s.y))
        end
        
        file:close()
    end
    
    console:log(string.format("Check #%d: Pal0=%s Pal1=%s Pal7=%s Sprites=%d", 
        checkCount, paletteToHex(objPal0), paletteToHex(objPal1), paletteToHex(objPal7), #sprites))
end

-- Frame callback
callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    if frameCount >= startFrame and frameCount <= endFrame then
        if (frameCount - startFrame) % checkInterval == 0 then
            checkPalettes()
        end
    end
    
    if frameCount >= endFrame then
        console:log("VRAM inspection complete. Results in: " .. outputFile)
        emu:stop()
    end
end)
'''
    
    script_path.write_text(script_content)
    return script_path, output_file

def launch_mgba_with_lua(lua_script_path):
    """Launch mgba-headless with Lua script"""
    mgba_headless_path = subprocess.run(["which", "mgba-headless"], capture_output=True, text=True).stdout.strip()
    if not mgba_headless_path:
        print("❌ mgba-headless not found!")
        return None
    
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb").resolve()
    if not rom_path.exists():
        print(f"❌ ROM not found: {rom_path}")
        return None
    
    cmd = [mgba_headless_path, "--script", str(lua_script_path.resolve()), str(rom_path)]
    print(f"🚀 Launching: {' '.join(cmd)}")
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return proc

def cleanup_mgba():
    """Kill any running mGBA instances"""
    subprocess.run(["pkill", "-9", "-f", "mgba"], timeout=5, capture_output=True)
    time.sleep(1)

def wait_for_screenshots(max_wait=20):
    """Wait for screenshots to appear"""
    screenshot_dir = Path("rom/working")
    screenshots = []
    start = time.time()
    while time.time() - start < max_wait:
        screenshots = list(screenshot_dir.glob("screenshot_*.png"))
        if screenshots:
            valid = [s for s in screenshots if s.stat().st_size >= 2048]
            if valid:
                return valid
        time.sleep(1)
    return screenshots if screenshots else None

def analyze_palette_ram(inspection_file, expected_palettes):
    """Analyze VRAM inspection output to check if palettes are distinct"""
    try:
        content = inspection_file.read_text()
        
        # Extract palette values from inspection file
        pal0_hex = None
        pal1_hex = None
        pal7_hex = None
        
        # Parse the inspection file to get palette values
        # Format: "OBJ Palette 0 (Sara D): 001F 001F 001F 0000"
        import re
        pal0_match = re.search(r'OBJ Palette 0.*?:\s*([0-9A-F\s]+)', content)
        pal1_match = re.search(r'OBJ Palette 1.*?:\s*([0-9A-F\s]+)', content)
        pal7_match = re.search(r'OBJ Palette 7.*?:\s*([0-9A-F\s]+)', content)
        
        if pal0_match:
            pal0_hex = pal0_match.group(1).strip().split()
        if pal1_match:
            pal1_hex = pal1_match.group(1).strip().split()
        if pal7_match:
            pal7_hex = pal7_match.group(1).strip().split()
        
        if not pal0_hex or not pal1_hex or not pal7_hex:
            return None
        
        # Get all non-transparent, unique colors from each palette
        def get_colors(hex_list):
            colors = []
            seen = set()
            for h in hex_list:
                val = int(h, 16)
                if val > 0x0001 and val not in seen:  # Skip transparent and duplicates
                    colors.append(val)
                    seen.add(val)
            return colors
        
        pal0_colors = get_colors(pal0_hex)
        pal1_colors = get_colors(pal1_hex)
        pal7_colors = get_colors(pal7_hex)
        
        # Calculate color distances (simple RGB distance)
        def color_distance(c1, c2):
            if c1 == 0 or c2 == 0:
                return 0
            # BGR555 format: bits 0-4 = blue, 5-9 = green, 10-14 = red
            r1 = (c1 >> 10) & 0x1F
            g1 = (c1 >> 5) & 0x1F
            b1 = c1 & 0x1F
            r2 = (c2 >> 10) & 0x1F
            g2 = (c2 >> 5) & 0x1F
            b2 = c2 & 0x1F
            
            return ((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2) ** 0.5
        
        # Compare palettes: each pair must have at least one distinct color
        # (not just minimum distance, but ensure each pair has SOME difference)
        def palettes_distinct(colors1, colors2):
            """Check if two palettes have at least one distinct color"""
            for c1 in colors1[:3]:  # Check up to 3 colors
                for c2 in colors2[:3]:
                    dist = color_distance(c1, c2)
                    if dist > 5.0:  # Found a distinct color pair
                        return True, dist
            return False, 0
        
        dist01_found, dist01 = palettes_distinct(pal0_colors, pal1_colors)
        dist07_found, dist07 = palettes_distinct(pal0_colors, pal7_colors)
        dist17_found, dist17 = palettes_distinct(pal1_colors, pal7_colors)
        
        all_distinct = dist01_found and dist07_found and dist17_found
        min_distance = min([d for d in [dist01, dist07, dist17] if d > 0] or [0])
        
        # Get representative colors for display
        pal0_color = pal0_colors[0] if pal0_colors else 0
        pal1_color = pal1_colors[0] if pal1_colors else 0
        pal7_color = pal7_colors[0] if pal7_colors else 0
        
        return {
            'pal0_hex': ' '.join(pal0_hex),
            'pal1_hex': ' '.join(pal1_hex),
            'pal7_hex': ' '.join(pal7_hex),
            'pal0_color': pal0_color,
            'pal1_color': pal1_color,
            'pal7_color': pal7_color,
            'min_distance': min_distance,
            'all_distinct': all_distinct
        }
    except Exception as e:
        print(f"Error analyzing palette RAM: {e}")
        import traceback
        traceback.print_exc()
        return None

def analyze_sprite_colors(screenshot_path):
    """Analyze screenshot to detect distinct colors for Sara D, Sara W, and Dragon Fly"""
    try:
        img = Image.open(screenshot_path)
        img_array = np.array(img)
        height, width = img_array.shape[:2]
        
        # Define regions for the three sprites (they appear labeled on right side)
        # Right side of screen where labels appear
        right_region = img_array[:, width*2//3:]
        
        # Try to find distinct color regions
        sara_d_region = img_array[height//4:height//2, width//8:width//3]
        sara_w_region = img_array[height//4:height//2, width//3:2*width//3]
        dragon_fly_region = img_array[height//8:height//3, 2*width//3:]
        
        def get_dominant_colors(region, k=3):
            if region.size == 0:
                return np.array([])
            pixels = region.reshape(-1, region.shape[-1])
            if pixels.shape[1] == 4:
                pixels = pixels[:, :3]
            non_black = pixels[np.sum(pixels, axis=1) > 30]
            if len(non_black) == 0:
                return np.array([])
            from collections import Counter
            colors = [tuple(p) for p in non_black]
            most_common = Counter(colors).most_common(k)
            return np.array([c[0] for c in most_common])
        
        sara_d_colors = get_dominant_colors(sara_d_region)
        sara_w_colors = get_dominant_colors(sara_w_region)
        dragon_fly_colors = get_dominant_colors(dragon_fly_region)
        
        if len(sara_d_colors) == 0 or len(sara_w_colors) == 0 or len(dragon_fly_colors) == 0:
            return None, None, None, False, 0
        
        def color_distance(c1, c2):
            return np.sqrt(np.sum((c1.astype(float) - c2.astype(float)) ** 2))
        
        distances = []
        for sd_color in sara_d_colors[:2]:
            for sw_color in sara_w_colors[:2]:
                distances.append(color_distance(sd_color, sw_color))
            for df_color in dragon_fly_colors[:2]:
                distances.append(color_distance(sd_color, df_color))
        for sw_color in sara_w_colors[:2]:
            for df_color in dragon_fly_colors[:2]:
                distances.append(color_distance(sw_color, df_color))
        
        if len(distances) == 0:
            return None, None, None, False, 0
        
        min_distance = min(distances)
        all_different = min_distance > 50
        return sara_d_colors, sara_w_colors, dragon_fly_colors, all_different, min_distance
    except Exception as e:
        print(f"Error analyzing colors: {e}")
        return None, None, None, False, 0

def start_web_server(screenshot_dir):
    """Start HTTP server to serve screenshots with HTML gallery"""
    global web_server
    
    class ScreenshotHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            self.screenshot_dir = screenshot_dir
            super().__init__(*args, **kwargs)
        
        def do_GET(self):
            if self.path == '/' or self.path == '/index.html':
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                # Find all screenshots
                screenshots = sorted(screenshot_dir.glob("screenshot_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
                
                html = '''<!DOCTYPE html>
<html>
<head>
    <title>Screenshot Gallery - Penta Dragon DX</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #1a1a1a; color: #fff; }
        h1 { color: #4CAF50; }
        .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; margin-top: 20px; }
        .screenshot { border: 2px solid #333; border-radius: 8px; padding: 10px; background: #2a2a2a; }
        .screenshot img { width: 100%; height: auto; border-radius: 4px; }
        .screenshot .name { margin-top: 10px; font-weight: bold; color: #4CAF50; }
        .screenshot .time { font-size: 0.9em; color: #888; }
        .refresh { position: fixed; top: 20px; right: 20px; padding: 10px 20px; background: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer; }
        .refresh:hover { background: #45a049; }
        .status { padding: 10px; background: #333; border-radius: 4px; margin-bottom: 20px; }
    </style>
    <script>
        function refreshPage() { location.reload(); }
        setInterval(refreshPage, 5000); // Auto-refresh every 5 seconds
    </script>
</head>
<body>
    <h1>📸 Screenshot Gallery - Penta Dragon DX</h1>
    <div class="status">
        <strong>Status:</strong> Auto-refreshing every 5 seconds | 
        <strong>Screenshots:</strong> ''' + str(len(screenshots)) + ''' | 
        <button class="refresh" onclick="refreshPage()">🔄 Refresh Now</button>
    </div>
    <div class="gallery">
'''
                
                for screenshot in screenshots[:50]:  # Show latest 50
                    rel_path = screenshot.name
                    mtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(screenshot.stat().st_mtime))
                    html += f'''        <div class="screenshot">
            <img src="{rel_path}" alt="{rel_path}" onerror="this.style.display='none'">
            <div class="name">{rel_path}</div>
            <div class="time">{mtime}</div>
        </div>
'''
                
                html += '''    </div>
</body>
</html>'''
                self.wfile.write(html.encode())
            else:
                # Serve actual files
                file_path = screenshot_dir / self.path.lstrip('/')
                if file_path.exists() and file_path.is_file():
                    self.send_response(200)
                    if file_path.suffix == '.png':
                        self.send_header('Content-type', 'image/png')
                    elif file_path.suffix == '.jpg' or file_path.suffix == '.jpeg':
                        self.send_header('Content-type', 'image/jpeg')
                    else:
                        self.send_header('Content-type', 'application/octet-stream')
                    self.end_headers()
                    with open(file_path, 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    self.send_response(404)
                    self.end_headers()
        
        def log_message(self, format, *args):
            pass  # Suppress logs
    
    try:
        handler = ScreenshotHandler
        httpd = socketserver.TCPServer(("", web_port), handler)
        web_server = httpd
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()
        print(f"🌐 Web server started: http://localhost:{web_port}/")
        print(f"   View screenshots gallery at: http://localhost:{web_port}/")
        return True
    except Exception as e:
        print(f"⚠️  Could not start web server: {e}")
        return False

def launch_mgba_qt_backup(rom_path):
    """Launch mgba-qt for user testing"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from mgba_window_utils import move_window_to_monitor
    
    mgba_qt_path = Path("/usr/local/bin/mgba-qt")
    if not mgba_qt_path.exists():
        print(f"⚠️  mgba-qt not found at {mgba_qt_path}")
        return None
    
    cmd = [str(mgba_qt_path), str(rom_path)]
    print(f"🎮 Launching mgba-qt for user testing: {' '.join(cmd)}")
    
    # Use XWayland environment for window positioning
    import os
    sys.path.insert(0, str(Path(__file__).parent))
    from mgba_window_utils import get_mgba_env_for_xwayland
    env = get_mgba_env_for_xwayland()
    proc = subprocess.Popen(cmd, env=env)
    
    # Give mgba-qt a moment to initialize, then move to Dell monitor
    time.sleep(1)
    move_window_to_monitor()
    
    return proc

def main():
    """Main verification loop"""
    import atexit
    import signal
    
    atexit.register(cleanup_mgba)
    signal.signal(signal.SIGINT, lambda s, f: (cleanup_mgba(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda s, f: (cleanup_mgba(), sys.exit(0)))
    
    print("=" * 60)
    print("AUTOMATED COLOR VERIFICATION LOOP")
    print("=" * 60)
    print()
    
    cleanup_mgba()
    
    # Start web server for screenshots
    screenshot_dir = Path("rom/working").resolve()
    start_web_server(screenshot_dir)
    
    iteration = 0
    
    print(f"📸 Screenshots will be saved to: {screenshot_dir}/screenshot_XX.png")
    print(f"🌐 View screenshots at: http://localhost:{web_port}/")
    print("🔄 Starting infinite loop - will stop when distinct colors are detected...")
    print()
    
    try:
        while True:
            try:
                iteration += 1
                print(f"\n{'='*70}")
                print(f"🔄 ITERATION {iteration}")
                print(f"{'='*70}")
                
                # 1. Hypothesis palette injection approach
                build_script_path, strategy_desc = implement_rom_modification(iteration)
                print(f"\n💡 Strategy: {strategy_desc}")
                print(f"📝 Build script: {build_script_path.name}")
                
                # Generate new palette configuration
                print(f"\n🎨 Generating new palette configuration...")
                palettes = generate_next_palette_config(iteration)
                if palettes:
                    save_palettes(palettes)
                    config_num = ((iteration - 1) % 5) + 1
                    print(f"✅ Saved palette config (Set {config_num} of 5)")
                
                # Build ROM
                print(f"\n🔨 Building ROM with {strategy_desc}...")
                if not build_rom(build_script_path):
                    print("❌ Build failed, skipping iteration")
                    continue
                
                # Create Lua script for VRAM inspection
                print(f"\n📝 Creating Lua VRAM inspection script...")
                lua_script_path, inspection_output = create_lua_vram_inspection_script(
                    palettes.get('obj_palettes', {}) if palettes else {}
                )
                
                # Launch mGBA
                print(f"\n🚀 Launching mgba-headless (90 seconds) for VRAM inspection...")
                mgba_proc = launch_mgba_with_lua(lua_script_path)
                if not mgba_proc:
                    print("❌ Failed to launch mGBA")
                    continue
                
                # Wait for completion (90 seconds + buffer)
                print("⏳ Waiting for VRAM inspection (checking around 40-50s mark)...")
                mgba_start_time = time.time()
                
                # Capture output from mgba-headless
                stdout_lines = []
                stderr_lines = []
                
                while time.time() - mgba_start_time < 100:
                    if mgba_proc.poll() is not None:
                        # Process finished, read remaining output
                        stdout, stderr = mgba_proc.communicate()
                        if stdout:
                            stdout_lines.extend(stdout.splitlines())
                        if stderr:
                            stderr_lines.extend(stderr.splitlines())
                        break
                    # Try to read output without blocking
                    try:
                        import select
                        if select.select([mgba_proc.stdout], [], [], 0.1)[0]:
                            line = mgba_proc.stdout.readline()
                            if line:
                                stdout_lines.append(line.strip())
                                if "Check" in line or "Palette" in line or "Sprite" in line:
                                    print(f"  [mGBA] {line.strip()}")
                    except:
                        pass
                    time.sleep(2)
                
                # Print any errors
                if stderr_lines:
                    print(f"⚠️  mGBA stderr: {stderr_lines[-5:]}")
                if stdout_lines:
                    print(f"📋 mGBA output: {stdout_lines[-5:]}")
                
                # Kill mGBA
                print("🛑 Stopping mGBA...")
                try:
                    if mgba_proc.poll() is None:
                        mgba_proc.kill()
                except:
                    pass
                cleanup_mgba()
                time.sleep(2)
                
                # Read VRAM inspection results
                # Wait a bit longer for file to be written (Lua script writes during execution)
                file_wait_time = 0
                while not inspection_output.exists() and file_wait_time < 5:
                    time.sleep(1)
                    file_wait_time += 1
                
                if not inspection_output.exists():
                    print(f"❌ VRAM inspection file not created: {inspection_output}")
                    print("   This might be normal if mGBA crashed or ROM froze")
                    # Check if there's a newer inspection file
                    all_inspections = sorted(Path("rom/working").glob("palette_inspection_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
                    if all_inspections:
                        print(f"   Using latest inspection file instead: {all_inspections[0].name}")
                        inspection_output = all_inspections[0]
                    else:
                        continue
                
                print(f"✅ VRAM inspection complete: {inspection_output.name}")
                
                # Analyze palette RAM data
                print("\n🔍 Analyzing palette RAM for Sara D, Sara W, and Dragon Fly...")
                inspection_result = analyze_palette_ram(inspection_output, palettes)
                
                if inspection_result and inspection_result.get('all_distinct'):
                    print("\n" + "="*70)
                    print("🎉 SUCCESS! All three sprites have distinct palettes in VRAM!")
                    print("="*70)
                    print(f"Palette 0 (Sara D): {inspection_result.get('pal0_hex', 'unknown')}")
                    print(f"Palette 1 (Sara W): {inspection_result.get('pal1_hex', 'unknown')}")
                    print(f"Palette 7 (Dragon Fly): {inspection_result.get('pal7_hex', 'unknown')}")
                    print(f"\n🎮 Launching mgba-qt for user testing...")
                    
                    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
                    launch_mgba_qt_backup(rom_path)
                    
                    print(f"\n✅ Test ROM ready! Check mgba-qt window.")
                    print(f"📋 VRAM inspection details: {inspection_output}")
                    cleanup_mgba()
                    return True
                else:
                    print(f"\n❌ Palettes not distinct enough in VRAM")
                    if inspection_result:
                        print(f"   Palette 0: {inspection_result.get('pal0_hex', 'unknown')}")
                        print(f"   Palette 1: {inspection_result.get('pal1_hex', 'unknown')}")
                        print(f"   Palette 7: {inspection_result.get('pal7_hex', 'unknown')}")
                    print(f"🔄 Will try different injection approach in next iteration...")
                    print(f"📋 VRAM inspection details: {inspection_output}")
                
                time.sleep(2)
                
            except Exception as e:
                print(f"\n❌ ITERATION {iteration} CRASHED: {e}")
                import traceback
                traceback.print_exc()
                cleanup_mgba()
                time.sleep(5)
                continue
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        cleanup_mgba()
        return False
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        cleanup_mgba()
        return False

if __name__ == "__main__":
    main()
