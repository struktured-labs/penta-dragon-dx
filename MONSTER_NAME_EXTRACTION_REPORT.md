# Extracted Monster Information from Screenshots

Based on analysis of 12,495 screenshots in rom/working.bak/, OCR extraction proved challenging due to the Game Boy's pixelated font. 

## OCR Challenges

The Game Boy's pixel font at 160x144 resolution makes accurate OCR extraction very difficult. Even with image scaling (8x) and contrast enhancement, standard OCR tools (Tesseract) struggle to accurately read the text.

## Findings

1. **Total Screenshots**: 12,495 PNG files
2. **Many screenshots show game frames without text** (title screen, gameplay, menus)
3. **Monster name screens appear to be less common** in the screenshot set
4. **Common non-monster text detected**:
   - "GAME START" (667 occurrences) - title screen menu
   - "OPENING START" / "POPENING START" (667 occurrences) - title screen menu

## Monster Metadata Available

The file `/home/struktured/projects/penta-dragon-dx/palettes/monster_palette_map.yaml` contains structural information about monsters organized by their tile IDs, including:

- Sara_D_or_DragonFly (tiles 0-3)
- Sara_W (tiles 4-7)
- Monster_tiles_8_9
- Monster_tiles_10_11
- Monster_tiles_12_13
- Monster_tiles_14_15
- Monster_tiles_18_19
- Monster_tiles_20_23
- And many more (30+ monster types identified by tile patterns)

However, the `names` field for each monster entry is currently empty: `names: []`

## Recommendations for Monster Name Extraction

Given the OCR challenges, here are more practical approaches:

### 1. **Manual Viewing with Sampling Tool**
Create a viewer that shows only screenshots likely to contain monster names (those with sprites in the center area) and allows manual annotation.

### 2. **Game ROM Analysis**
Extract text strings directly from the ROM file, which would be more reliable than OCR:
```bash
strings "Penta Dragon (J).gb" | grep -E '^[A-Z]{3,15}$'
```

### 3. **Use Japanese Game Resources**
Since this is a Japanese game ("Penta Dragon (J).gb"), the original monster names may be in Japanese. English names might not exist in the ROM.

### 4. **Disassembly Analysis**
The `reverse_engineering/disassembly/` directory might contain text/data sections with monster name strings.

## Next Steps

Would you like me to:
1. Create a manual annotation tool to browse screenshots and input names?
2. Extract text strings directly from the ROM file?
3. Analyze the disassembly files for monster name data?
4. Check if there's existing documentation or databases for this game?
