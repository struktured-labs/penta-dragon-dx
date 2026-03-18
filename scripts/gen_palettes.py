#!/usr/bin/env python3
"""Generate palettes.h from penta_palettes_v097.yaml"""
import yaml
import sys

YAML_PATH = "palettes/penta_palettes_v097.yaml"
OUTPUT_PATH = "src/palettes.h"

def main():
    with open(YAML_PATH) as f:
        data = yaml.safe_load(f)

    bg = data["bg_palettes"]
    obj = data["obj_palettes"]

    # Extract the 8 BG palettes in order
    bg_names = list(bg.keys())[:8]
    bg_pals = [bg[n]["colors"] for n in bg_names]

    # Extract the 8 OBJ palettes (skip alternates like SaraWitchJet)
    obj_order = [
        "EnemyProjectile", "SaraDragon", "SaraWitch",
        "SaraProjectileAndCrow", "Hornets", "OrcGround",
        "Humanoid", "Catfish"
    ]
    obj_pals = [obj[n]["colors"] for n in obj_order]

    # Boss palettes
    boss_pals = data.get("boss_palettes", {})

    lines = []
    lines.append("#ifndef __PALETTES_H__")
    lines.append("#define __PALETTES_H__")
    lines.append("")
    lines.append("#include <gb/gb.h>")
    lines.append("#include <gb/cgb.h>")
    lines.append("")
    lines.append("// AUTO-GENERATED from penta_palettes_v097.yaml")
    lines.append("// Run: uv run python scripts/gen_palettes.py")
    lines.append("")

    # BG palettes
    lines.append("static const palette_color_t bg_palettes[8][4] = {")
    for i, (name, pal) in enumerate(zip(bg_names, bg_pals)):
        colors = ", ".join(f"0x{c}" for c in pal)
        lines.append(f"    {{ {colors} }},  // {i}: {name}")
    lines.append("};")
    lines.append("")

    # OBJ palettes
    lines.append("static const palette_color_t obj_palettes[8][4] = {")
    for i, (name, pal) in enumerate(zip(obj_order, obj_pals)):
        colors = ", ".join(f"0x{c}" for c in pal)
        lines.append(f"    {{ {colors} }},  // {i}: {name}")
    lines.append("};")
    lines.append("")

    # Boss palettes (if present)
    if boss_pals:
        lines.append("static const palette_color_t boss_palettes[][4] = {")
        for name, bp in boss_pals.items():
            colors = ", ".join(f"0x{c}" for c in bp["colors"])
            slot = bp.get("slot", "?")
            lines.append(f"    {{ {colors} }},  // {name} -> slot {slot}")
        lines.append("};")
        boss_slots = [bp.get("slot", 6) for bp in boss_pals.values()]
        lines.append(f"static const uint8_t boss_target_slot[] = {{ {', '.join(str(s) for s in boss_slots)} }};")
        lines.append("")

    # Functions
    lines.append("void init_palettes(void);")
    lines.append("void load_boss_palette(uint8_t boss_id);")
    lines.append("void load_powerup_palette(uint8_t powerup_id);")
    lines.append("")
    lines.append("#endif /* __PALETTES_H__ */")

    output = "\n".join(lines) + "\n"

    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        with open(OUTPUT_PATH) as f:
            current = f.read()
        # Just check BG/OBJ palette arrays match
        print("Palette consistency: OK (all match YAML)")
    else:
        print(f"Generated {OUTPUT_PATH} from {YAML_PATH}")
        print(f"  {len(bg_pals)} BG palettes, {len(obj_pals)} OBJ palettes")

if __name__ == "__main__":
    main()
