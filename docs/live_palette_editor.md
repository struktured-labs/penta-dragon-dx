# Live Palette Editor (mGBA)

Tune CGB palette colors in real time while the game runs in mGBA.

## How it works

```
    [browser]                [Python server]              [mGBA + Lua]
  http://localhost:8077  →  /tmp/live_palettes.txt  →   CGB CRAM writes
       (sliders)              (text file)                (~0.5s latency)
```

1. The Python server (`scripts/live_palette_editor.py`) hosts a browser UI
   with color pickers for all 16 palettes (8 BG + 8 OBJ).
2. When you pick a color, the server writes the new state to a flat text
   file at `/tmp/live_palettes.txt`.
3. The Lua script (`scripts/lua/live_palettes.lua`) running inside mGBA
   polls the file every 30 frames (~0.5s).
4. On change detected, Lua decodes the BGR555 values and writes them to
   CGB BCPS/BCPD (BG palette) or OCPS/OCPD (OBJ palette).

The game continues running. You see the color change in the running
emulator within half a second of picking it in the browser.

## Setup

One-time:
```bash
pip install pyyaml  # if not already installed
```

## Usage

Terminal 1 (Python server):
```bash
cd /home/struktured/projects/penta-dragon-dx-claude
python3 scripts/live_palette_editor.py
```

Terminal 2 (mGBA with Lua script loaded):
```bash
mgba-qt rom/working/penta_dragon_dx_v301.gb \
  --script scripts/lua/live_palettes.lua
```

Browser:
```
http://localhost:8077
```

Get into the dungeon (or any scene), then tune colors in the browser.
Sara's pink, dungeon floor blue, wall gray, item yellow — all editable
live without restarting the ROM.

## Saving your tuned colors

In the browser, click "Save to YAML". This appends your current state
to `palettes/penta_palettes_v097.yaml`. After saving, rebuild the
production ROM to bake them in:

```bash
python3 scripts/build_v301_gdma.py
```

The ROM now has your tuned colors permanently.

## Format reference

CGB palettes are stored as BGR555 (5 bits each for blue, green, red).
The text file uses 4-char hex strings:

```
BG0:0=7FFF,1=7E94,2=3D4A,3=0000
OBJ2:0=0000,1=2EBE,2=511F,3=0842
```

`BG<n>` = BG palette `n` (0-7). `OBJ<n>` = OBJ palette `n` (0-7).
`<idx>=<hex>` = color index `idx` (0-3) set to 4-char BGR555 hex.

Lines starting with `#` are ignored. The Lua script reads only lines
matching the patterns above.

## What's tunable

| Palette | Default name | Used by |
|---|---|---|
| BG 0 | Dungeon | Floor + most BG tiles |
| BG 1 | BG1 | Items (chests, potions) |
| BG 2 | BG2 | (decorative) |
| BG 3 | BG3 | (decorative) |
| BG 4 | BG4 | (decorative) |
| BG 5 | BG5 | (decorative) |
| BG 6 | BG6 | Walls (slate gray) |
| BG 7 | BG7 | (mystery/special) |
| OBJ 0 | EnemyProjectile | Enemy projectiles + effects |
| OBJ 1 | SaraDragon | Sara in Dragon form |
| OBJ 2 | SaraWitch | Sara in Witch form |
| OBJ 3 | SaraProjectileAndCrow | Sara projectiles + Crow enemies |
| OBJ 4 | Hornets | Hornet enemies |
| OBJ 5 | OrcGround | Orc/ground enemies |
| OBJ 6 | Humanoid | Soldier/moth/spike (Gargoyle override when miniboss=1) |
| OBJ 7 | Catfish | Catfish (Spider override when miniboss=2) |

## Troubleshooting

- **Colors don't update**: Verify mGBA is running with the Lua script.
  The script prints `Applied N palette writes` to mGBA's script console
  when an update is detected.
- **Wrong RGB conversion**: The conversion is BGR555 ↔ RGB888 quantized
  to 5 bits per channel. So your 24-bit color picker can only represent
  32 values per channel — minor rounding when re-serialized to BGR555.
- **mGBA crashed**: Check if the polled file has malformed lines.
  Lines that don't match the format are silently skipped.
