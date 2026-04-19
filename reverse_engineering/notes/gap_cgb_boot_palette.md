# Gap #8: CGB Boot ROM Palette Selection

## Header Verification (both ROMs)

| Field | Original `Penta Dragon (J).gb` | DX `penta_dragon_dx_v290.gb` |
|-------|------|-------|
| Title bytes 0x134-0x143 (hex) | `50454e5441445241474f4e0000000000` | `50454e5441445241474f4e0000000080` |
| Title ASCII | `PENTADRAGON` + 5 nulls | `PENTADRAGON` + 4 nulls + 0x80 |
| 4th letter (0x137) | `0x54` ('T') | `0x54` ('T') |
| Title checksum (sum 0x134-0x143 mod 256) | `0x33` | `0xB3` |
| **CGB flag (0x143)** | `0x00` (DMG) | `0x80` (CGB-enhanced) |

**Critical**: 0x143 doubles as the last byte of the 16-byte title field. Setting it to 0x80 (CGB flag) for the DX ROM also changed the title checksum from 0x33 → 0xB3. Both then fail to match any known commercial entry — but for different reasons.

## Original ROM (DMG flag)

When the original ROM runs on a CGB, the boot ROM applies DMG-compatibility palette logic:

1. Compute checksum: `0x33`
2. Compare against hardcoded (checksum, 4th-letter) table
3. `(0x33, 0x5E)` matches → BUBBLE BOBBLE entry; `(0x33, 0x54)` does NOT match
4. Fallback → palette index 0x1C ("default white"): BG/OBJ palettes filled with `0x7FFF` (all white)
5. Title screen unreadable: white-on-white

## DX ROM (CGB flag 0x80)

When CGB flag is set, the CGB boot ROM bypasses DMG-compat palette logic entirely. Palette RAM behavior at handoff:

- **CGB native mode**: Boot ROM does NOT initialize CGB palette RAM. Game must write BCPS/BCPD itself before showing graphics.
- Empirically the title screen still appears white because the v290 hook does not load the title-screen palette until `cond_pal` runs in VBlank — and the vanilla title-draw code runs first. If palette RAM happens to be filled with `0x7FFF` from some prior state (or from the CGB boot ROM clearing it as part of logo display), the title shows white.

## Why MiSTer Behaves Differently

MiSTer's CGB boot ROM implementation may zero-fill palette RAM differently than real hardware:

- Real CGB hardware: palette RAM has indeterminate state
- mgba: emulates real hardware — title screen appears white (matches our finding)
- MiSTer with "Audio mode = No Pops": the GBC core's boot sequence happens to leave palette RAM in a state that lets `cond_pal` overwrite cleanly within the first few frames

## Suggested Fix

Two viable options:

1. **Pre-VBlank palette load**: Hook the very first instruction the cartridge executes (0x0150 boot entry) to write a baseline palette to BCPS/BCPD before the title-draw code runs. ~30 cycle insertion at boot.

2. **Header rewrite to land on a good DMG-compat palette**: Only useful if we ever revert to DMG flag. Pick a known-good (checksum, 4th-letter) pair from the boot ROM table — e.g., changing one title byte to make checksum hit `(0x86, 0x4E)` = ALLEYWAY (gold/red palette). Not relevant for DX since we use CGB flag.

**Recommended**: Option 1. Add a 4-color BG0 init (white, light, dark, black) at 0x0150 entry to guarantee title visibility regardless of boot palette state.

## Verification Procedure

```
mgba-qt --log-level 7 --log-file /tmp/cgb_boot.log rom/working/penta_dragon_dx_v290.gb
# Filter log for BCPS/BCPD writes during frames 0-60
grep -E "FF68|FF69" /tmp/cgb_boot.log
```

Expected: zero writes from boot ROM (CGB native mode), first write from `cond_pal` at ~frame 1 VBlank.

## References

- Pan Docs: https://gbdev.io/pandocs/Power_Up_Sequence.html
- gekkio mooneye-test-suite — CGB boot ROM disassembly
- SameBoy boot ROM source (open-source CGB boot ROM clone)
