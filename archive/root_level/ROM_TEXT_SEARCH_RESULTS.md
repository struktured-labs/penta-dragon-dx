# ROM Text Search Results - Monster Names

## Search Date
2025-01-19

## ROM File Searched
`rom/working/penta_dragon_cursor_dx.gb`

## Search Methods Used
1. `strings` command with various filters
2. Case-insensitive grep for monster-related terms
3. Python binary search for patterns
4. Hex dump search for ASCII sequences

## Results

### Found Text Strings

**Game Title:**
- `PENTADRAGON` - Found at offset 0x0139 (313 decimal)
  - Context: Appears to be in header/metadata area
  - Format: Null-terminated string `PENTADRAGON\x00`

**No Monster Names Found:**
- ❌ "dragonfly" - Not found
- ❌ "dragon fly" - Not found  
- ❌ "dragon" (as monster name) - Not found
- ❌ "sara" - Not found
- ❌ "vampire" - Not found
- ❌ Other common monster names (bat, ghost, slime, etc.) - Not found

### Other Text Patterns Found

Most text found appears to be:
- Game code/data patterns (e.g., `ABCDEFGHIJKLMNO`, `PQRSTUVWXYZ`)
- Tile/graphics data (repeated patterns like `BVBVBVBVBV`)
- Menu/UI strings (likely in different encoding)
- Binary data that happens to contain ASCII characters

### Analysis

**Why Monster Names Aren't Found:**

1. **Japanese Game**: Penta Dragon is a Japanese Game Boy game. Monster names are likely stored in Japanese characters (katakana/hiragana), which wouldn't appear as ASCII text.

2. **Custom Encoding**: Game Boy games often use custom character encoding for text, not standard ASCII. The text might be stored as:
   - Tile indices pointing to character graphics
   - Custom encoding tables
   - Compressed/encoded text

3. **No Text Storage**: Monster names might not be stored as text strings at all. They could be:
   - Hardcoded in graphics/tiles
   - Referenced by ID numbers only
   - Stored in external data (not in ROM)

4. **Modified ROM**: The ROM being searched (`penta_dragon_cursor_dx.gb`) is a modified/patched version. Original text might have been altered or removed during patching.

### Recommendations

1. **Search Original ROM**: Try searching the original unmodified ROM file if available
2. **Japanese Character Search**: Use tools that can detect Japanese character encoding (Shift-JIS, etc.)
3. **Graphics Analysis**: Monster names might be stored as graphics tiles rather than text
4. **Disassembly**: Analyze the ROM's assembly code to find text data tables
5. **Game Documentation**: Check if there's official documentation or fan translations with monster names

### Next Steps

To find monster names, consider:
- Using a Game Boy ROM disassembler/debugger
- Searching for Japanese character patterns
- Analyzing the original Japanese ROM
- Checking game documentation/wikis
- Manual extraction from screenshots (as attempted with OCR)

