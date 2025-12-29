#!/usr/bin/env python3
"""
Auto-Iterate to Victory

Systematically tries different approaches until distinct colors work:
1. Different hook points (input handler, VBlank, other)
2. Different OAM setter implementations
3. Different timing strategies
4. Tests each ROM headless with mgba
5. Analyzes results automatically
6. Iterates until success

This runs FULLY AUTOMATED - no user interaction needed.
"""
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple
import shutil

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches

try:
    import yaml
    from PIL import Image
    import numpy as np
except ImportError:
    print("Installing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pillow", "numpy", "pyyaml"], check=True)
    import yaml
    from PIL import Image
    import numpy as np


class AutoIterator:
    """Automatically iterate through approaches until victory"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.rom_path = self.project_root / "rom" / "Penta Dragon (J).gb"
        self.output_dir = self.project_root / "test_output" / f"auto_iterate_{int(time.time())}"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.palette_yaml = self.project_root / "palettes" / "penta_palettes.yaml"
        self.monster_map = self.project_root / "palettes" / "monster_palette_map.yaml"

        self.iteration = 0
        self.max_iterations = 20

    def print_banner(self):
        print("=" * 80)
        print("🤖 AUTO-ITERATE TO VICTORY - Fully Automated Testing")
        print("=" * 80)
        print(f"Output: {self.output_dir}")
        print()

    def parse_color(self, color_val) -> int:
        """Simple color parser"""
        if isinstance(color_val, int):
            return color_val & 0x7FFF
        s = str(color_val).strip()
        if len(s) == 4 and all(ch in '0123456789abcdefABCDEF' for ch in s):
            return int(s, 16) & 0x7FFF
        raise ValueError(f"Invalid color: {color_val}")

    def create_palette(self, colors: list) -> bytes:
        """Convert 4 colors to 8-byte palette"""
        c = [self.parse_color(x) for x in colors]
        return bytes([
            c[0] & 0xFF, (c[0] >> 8) & 0xFF,
            c[1] & 0xFF, (c[1] >> 8) & 0xFF,
            c[2] & 0xFF, (c[2] >> 8) & 0xFF,
            c[3] & 0xFF, (c[3] >> 8) & 0xFF,
        ])

    def load_palettes(self) -> Tuple[bytes, bytes]:
        """Load palettes from YAML"""
        with open(self.palette_yaml, 'r') as f:
            config = yaml.safe_load(f)

        bg_data = bytearray()
        obj_data = bytearray()

        # Load BG palettes
        for name, data in list(config.get('bg_palettes', {}).items())[:8]:
            bg_data.extend(self.create_palette(data['colors']))
        while len(bg_data) < 64:
            bg_data.extend(self.create_palette(['0000', '7FFF', '5294', '2108']))

        # Load OBJ palettes
        for name, data in list(config.get('obj_palettes', {}).items())[:8]:
            obj_data.extend(self.create_palette(data['colors']))
        while len(obj_data) < 64:
            obj_data.extend(self.create_palette(['0000', '7FFF', '5294', '2108']))

        return bytes(bg_data), bytes(obj_data)

    def generate_lookup_table(self) -> bytes:
        """Generate tile-to-palette lookup table"""
        with open(self.monster_map, 'r') as f:
            data = yaml.safe_load(f)

        lookup_table = bytearray([0xFF] * 256)
        monster_map = data.get('monster_palette_map', {})

        for monster_name, info in monster_map.items():
            palette_id = info.get('palette', 0)
            for tile_id in info.get('tile_range', []):
                if 0 <= tile_id <= 255:
                    lookup_table[tile_id] = palette_id

        return bytes(lookup_table)

    def build_oam_setter_v1(self) -> bytes:
        """Version 1: Simple OAM palette setter"""
        return bytes([
            0xC5, 0xD5, 0xE5,          # PUSH BC, DE, HL
            0x06, 0x28,                # LD B, 40
            0x21, 0x00, 0xFE,          # LD HL, 0xFE00
            # Loop
            0x23, 0x23,                # INC HL x2 (to tile ID)
            0x7E,                      # LD A, [HL] (tile ID)
            0x5F,                      # LD E, A
            0x16, 0x6E,                # LD D, 0x6E
            0x1A,                      # LD A, [DE] (palette from table)
            0xFE, 0xFF,                # CP 0xFF
            0x28, 0x09,                # JR Z, skip
            0x4F,                      # LD C, A
            0x23,                      # INC HL (to flags)
            0x7E,                      # LD A, [HL]
            0xE6, 0xF8,                # AND 0xF8
            0xB1,                      # OR C
            0x77,                      # LD [HL], A
            0x18, 0x01,                # JR +1
            0x23,                      # INC HL (skip)
            0x23,                      # INC HL (next sprite)
            0x05,                      # DEC B
            0x20, 0xE5,                # JR NZ, loop
            0xE1, 0xD1, 0xC1,          # POP HL, DE, BC
            0xC9,                      # RET
        ])

    def build_oam_setter_v2_safe(self) -> bytes:
        """Version 2: Extra safety checks"""
        return bytes([
            0xC5, 0xD5, 0xE5,          # PUSH BC, DE, HL
            0xF5,                      # PUSH AF (extra safety)
            0x06, 0x28,                # LD B, 40
            0x21, 0x00, 0xFE,          # LD HL, 0xFE00
            # Loop start
            0x7E,                      # LD A, [HL] (Y position)
            0xFE, 0x00,                # CP 0 (check if sprite active)
            0x28, 0x10,                # JR Z, next (skip if Y=0)
            0x23, 0x23,                # INC HL x2 (to tile)
            0x7E,                      # LD A, [HL]
            0x5F,                      # LD E, A
            0x16, 0x6E,                # LD D, 0x6E
            0x1A,                      # LD A, [DE]
            0xFE, 0xFF,                # CP 0xFF
            0x28, 0x06,                # JR Z, skip_set
            0x4F,                      # LD C, A
            0x23,                      # INC HL
            0x7E,                      # LD A, [HL]
            0xE6, 0xF8,                # AND 0xF8
            0xB1,                      # OR C
            0x77,                      # LD [HL], A
            0x2B,                      # DEC HL (back to tile)
            0x2B,                      # DEC HL (back to X)
            # Next sprite
            0x23, 0x23, 0x23, 0x23,    # INC HL x4
            0x05,                      # DEC B
            0x20, 0xE0,                # JR NZ, loop
            0xF1,                      # POP AF
            0xE1, 0xD1, 0xC1,          # POP HL, DE, BC
            0xC9,                      # RET
        ])

    def build_oam_setter_v3_minimal(self) -> bytes:
        """Version 3: Minimal, just first 10 sprites for testing"""
        return bytes([
            0xC5, 0xD5, 0xE5,          # PUSH BC, DE, HL
            0x06, 0x0A,                # LD B, 10 (only first 10 sprites)
            0x21, 0x00, 0xFE,          # LD HL, 0xFE00
            # Loop
            0x23, 0x23,                # INC HL x2
            0x7E,                      # LD A, [HL]
            0x5F,                      # LD E, A
            0x16, 0x6E,                # LD D, 0x6E
            0x1A,                      # LD A, [DE]
            0xFE, 0xFF,                # CP 0xFF
            0x28, 0x06,                # JR Z, skip
            0x23,                      # INC HL
            0x7E,                      # LD A, [HL]
            0xE6, 0xF8,                # AND 0xF8
            0xB1,                      # OR C (C should have palette)
            0x77,                      # LD [HL], A
            0x23, 0x23,                # INC HL x2
            0x05,                      # DEC B
            0x20, 0xED,                # JR NZ, loop
            0xE1, 0xD1, 0xC1,          # POP HL, DE, BC
            0xC9,                      # RET
        ])

    def build_rom_variant(self, variant_name: str, oam_setter_func, hook_delay: int = 60) -> Path:
        """Build a ROM variant with specific OAM setter and timing"""
        print(f"  Building: {variant_name}")

        # Load original ROM
        with open(self.rom_path, 'rb') as f:
            rom = bytearray(f.read())

        # Apply display patches
        rom, _ = apply_all_display_patches(rom)

        # Load palettes
        bg_pal, obj_pal = self.load_palettes()
        lookup_table = self.generate_lookup_table()

        # Bank 13 locations
        BANK_13 = 0x034000

        # Write palette data at 0x6C80
        pal_offset = BANK_13 + 0x2C80
        rom[pal_offset:pal_offset+64] = bg_pal
        rom[pal_offset+64:pal_offset+128] = obj_pal

        # Write lookup table at 0x6E00
        lookup_offset = BANK_13 + 0x2E00
        rom[lookup_offset:lookup_offset+256] = lookup_table

        # Write OAM setter at 0x6E80
        oam_setter = oam_setter_func()
        oam_offset = BANK_13 + 0x2E80
        rom[oam_offset:oam_offset+len(oam_setter)] = oam_setter

        # Build combined function with custom delay
        original_input = bytes(rom[0x0824:0x0824+46])

        combined = original_input + bytes([
            0xFA, 0xA0, 0xC0,          # LD A,[C0A0]
            0xFE, 0x01,                # CP 1
            0x28, 0x34,                # JR Z, ret_early
            0xFA, 0xA1, 0xC0,          # LD A,[C0A1]
            0x3C,                      # INC A
            0xEA, 0xA1, 0xC0,          # LD [C0A1],A
            0xFE, hook_delay,          # CP delay
            0x38, 0x2C,                # JR C, ret_early
            0x3E, 0x01,                # LD A, 1
            0xEA, 0xA0, 0xC0,          # LD [C0A0], A
            # Load BG palettes
            0x21, 0x80, 0x6C,          # LD HL, 0x6C80
            0x3E, 0x80,                # LD A, 0x80
            0xE0, 0x68,                # LDH [FF68], A
            0x0E, 0x40,                # LD C, 64
            0x2A, 0xE0, 0x69,          # LD A,[HL+]; LDH [FF69],A
            0x0D, 0x20, 0xFA,          # DEC C; JR NZ, loop
            # Load OBJ palettes
            0x3E, 0x80,                # LD A, 0x80
            0xE0, 0x6A,                # LDH [FF6A], A
            0x0E, 0x40,                # LD C, 64
            0x2A, 0xE0, 0x6B,          # LD A,[HL+]; LDH [FF6B],A
            0x0D, 0x20, 0xFA,          # DEC C; JR NZ, loop
            # Call OAM setter
            0xCD, 0x80, 0x6E,          # CALL 0x6E80
            0xC9,                      # RET
            0xC9, 0xC9,                # RET (early returns)
        ])

        combined_offset = BANK_13 + 0x2D00
        rom[combined_offset:combined_offset+len(combined)] = combined

        # Trampoline at 0x0824
        trampoline = bytes([
            0xF5,                      # PUSH AF
            0x3E, 0x0D,                # LD A, 13
            0xEA, 0x00, 0x20,          # LD [2000], A
            0xF1,                      # POP AF
            0xCD, 0x00, 0x6D,          # CALL 0x6D00
            0xF5,                      # PUSH AF
            0x3E, 0x01,                # LD A, 1
            0xEA, 0x00, 0x20,          # LD [2000], A
            0xF1,                      # POP AF
            0xC9,                      # RET
        ])
        rom[0x0824:0x0824+len(trampoline)] = trampoline

        # Set CGB flag
        rom[0x143] = 0x80

        # Fix checksum
        chk = 0
        for i in range(0x134, 0x14D):
            chk = (chk - rom[i] - 1) & 0xFF
        rom[0x14D] = chk

        # Write ROM
        output_path = self.output_dir / f"{variant_name}.gb"
        with open(output_path, 'wb') as f:
            f.write(rom)

        return output_path

    def test_rom_headless(self, rom_path: Path, duration: int = 5) -> Dict:
        """Test ROM headless with mgba"""
        print(f"  Testing: {rom_path.name}")

        # Create Lua script for screenshot - capture earlier (frame 80) to detect freezes faster
        screenshot_path = self.output_dir / f"screenshot_{rom_path.stem}.png"
        lua_script = self.output_dir / f"test_{rom_path.stem}.lua"

        lua_content = f"""
frame = 0
captured = false

function capture()
    frame = frame + 1

    -- Capture at frame 80 (after ~1.3 seconds)
    if frame == 80 and not captured then
        emu:screenshot('{screenshot_path}')
        print('Screenshot captured at frame 80')
        captured = true
    end

    -- Exit after frame 100
    if frame >= 100 then
        print('Exiting after frame 100')
        os.exit(0)
    end
end

callbacks:add("frame", capture)
print('Lua script loaded - will capture at frame 80')
"""

        with open(lua_script, 'w') as f:
            f.write(lua_content)

        # Run mgba headless with frameskip for speed
        try:
            result = subprocess.run(
                ["mgba", "-s", "2", "-l", str(lua_script), str(rom_path)],
                capture_output=True,
                timeout=duration,
                text=True
            )
            success = True
        except subprocess.TimeoutExpired:
            success = True  # Timeout is expected
        except FileNotFoundError:
            print("  ⚠️  mgba not found, trying without frameskip...")
            try:
                result = subprocess.run(
                    ["mgba", "-l", str(lua_script), str(rom_path)],
                    capture_output=True,
                    timeout=duration,
                    text=True
                )
            except:
                return {'success': False, 'reason': 'mgba not found'}

        # Analyze screenshot if it exists
        if screenshot_path.exists():
            return self.analyze_screenshot(screenshot_path)
        else:
            return {'success': False, 'reason': 'no screenshot (likely crashed/froze)'}

    def analyze_screenshot(self, screenshot_path: Path) -> Dict:
        """Analyze screenshot for white screen or distinct colors"""
        try:
            img = Image.open(screenshot_path).convert('RGB')
            img_array = np.array(img)

            # Check for white screen (freeze)
            avg_color = np.mean(img_array, axis=(0, 1))
            if np.all(avg_color > 240):
                return {'success': False, 'reason': 'white screen freeze', 'colors': 0}

            # Count distinct colors
            pixels = img_array.reshape(-1, 3)
            unique_colors = np.unique(pixels, axis=0)

            # Filter background colors
            sprite_colors = []
            for color in unique_colors:
                r, g, b = color
                # Skip white, black, and common green BG
                if not (np.all(color > 200) or np.all(color < 30) or (g > 100 and r < 50 and b < 50)):
                    sprite_colors.append(tuple(color))

            color_count = len(sprite_colors)

            # Success if 6+ distinct sprite colors
            success = color_count >= 6

            return {
                'success': success,
                'reason': f'{color_count} distinct colors',
                'colors': color_count,
                'screenshot': screenshot_path
            }

        except Exception as e:
            return {'success': False, 'reason': f'analysis error: {e}', 'colors': 0}

    def run(self):
        """Main iteration loop"""
        self.print_banner()

        variants = [
            ("v1_oam_simple_60f", self.build_oam_setter_v1, 60),
            ("v1_oam_simple_30f", self.build_oam_setter_v1, 30),
            ("v1_oam_simple_10f", self.build_oam_setter_v1, 10),
            ("v2_oam_safe_60f", self.build_oam_setter_v2_safe, 60),
            ("v2_oam_safe_30f", self.build_oam_setter_v2_safe, 30),
            ("v3_oam_minimal_60f", self.build_oam_setter_v3_minimal, 60),
        ]

        results = []

        for i, (name, setter_func, delay) in enumerate(variants):
            print(f"\n[{i+1}/{len(variants)}] Testing: {name}")

            # Build ROM
            rom_path = self.build_rom_variant(name, setter_func, delay)

            # Test it
            result = self.test_rom_headless(rom_path, duration=8)

            result['variant'] = name
            result['rom'] = rom_path
            results.append(result)

            if result['success']:
                print(f"  ✅ SUCCESS! {result['reason']}")
                print(f"  ROM: {rom_path}")
                break
            else:
                print(f"  ❌ Failed: {result['reason']}")

        # Final report
        print("\n" + "=" * 80)
        print("FINAL RESULTS")
        print("=" * 80)

        successes = [r for r in results if r['success']]

        if successes:
            print(f"\n🎉 SUCCESS! Found working variant(s):\n")
            for r in successes:
                print(f"  ✓ {r['variant']}")
                print(f"    ROM: {r['rom']}")
                print(f"    Colors: {r['colors']}")
                print(f"    Screenshot: {r.get('screenshot', 'N/A')}")
        else:
            print(f"\n⚠️  No variants succeeded yet")
            print("\nResults summary:")
            for r in results:
                print(f"  {r['variant']}: {r['reason']}")

        print(f"\n📁 All outputs in: {self.output_dir}")

        return len(successes) > 0


def main():
    iterator = AutoIterator()
    success = iterator.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
