"""Verify the installed colorizer / perf-trim bytes haven't drifted.

Locks in critical iter-31 (OBJ slot-10+ unlock) + iter-39 (joypad trim) +
iter-40 (bg_sweep Phase 1+2 fusion) bytes that the live OAM regression suite
either doesn't cover or only covers transiently.

The teleport ROM and the v3.01 production ROM have different byte layouts at
some sites (teleport re-patches the wrapper and bg_sweep). We auto-detect
which ROM by sniffing a fingerprint byte, then run the appropriate check set.

Run from the pre-commit hook:
  uv run python scripts/diagnostics/verify_colorizer_bytes.py --rom <ROM>
"""

import argparse
import sys
from pathlib import Path

# Iter 31 — shared OBJ colorizer + post-DMA hwoam_recolor. Same bytes in
# both v3.01 and teleport ROMs.
ITER31_CHECKS = [
    (
        13 * 0x4000 + (0x7F40 - 0x4000),
        0xFA,
        "iter 31: hwoam_recolor entry at bank13:0x7F40 = 0xFA (LD A,[D880] — D880 scope gate)",
    ),
    (
        13 * 0x4000 + (0x7F41 - 0x4000),
        0x80,
        "iter 31: hwoam_recolor entry at bank13:0x7F41 = 0x80 (low byte of D880)",
    ),
    (
        13 * 0x4000 + (0x7F67 - 0x4000),
        0x28,
        "iter 31: hwoam_recolor LD B operand at bank13:0x7F67 (40 slots — raised from 10)",
    ),
    (
        13 * 0x4000 + (0x6A41 - 0x4000),
        0x1B,
        "iter 31: tile 0x10-0x1F → sara_palette JR offset at 0x6A41 (was 0x0B = pal_4)",
    ),
    (
        13 * 0x4000 + (0x6A11 - 0x4000),
        0x0A,
        "iter 31 sanity: shadow-pass LD B at 0x6A11 stays 10 (only post-DMA uses 40)",
    ),
    (
        13 * 0x4000 + (0x6A10 - 0x4000),
        0x06,
        "iter 31 sanity: colorizer LD B opcode at 0x6A10 stays 0x06 (LD B,n)",
    ),
]

# Iter 40 — bg_sweep fused-loop opcode signature. Same OPCODE in both ROMs;
# only the bg_table_hi operand at 0x6D1D differs (v3.01: 0x70, teleport: 0xDA).
ITER40_OPCODE_CHECKS = [
    (
        13 * 0x4000 + (0x6D1E - 0x4000),
        0x2A,
        "iter 40: bg_sweep fused-loop start LD A,[HL+] at 0x6D1E = 0x2A",
    ),
    (
        13 * 0x4000 + (0x6D1F - 0x4000),
        0x4F,
        "iter 40: bg_sweep LD C,A at 0x6D1F = 0x4F (tile into BC low)",
    ),
    (
        13 * 0x4000 + (0x6D20 - 0x4000),
        0x0A,
        "iter 40: bg_sweep LD A,[BC] opcode at 0x6D20 = 0x0A (fused lookup; pre-iter-40 had ADD HL math)",
    ),
    (
        13 * 0x4000 + (0x6D25 - 0x4000),
        0x30,
        "iter 40: bg_sweep CP 0x30 operand at 0x6D25 (DE-end-compare counter — fused-loop signature)",
    ),
]

# Iter 39 — wrapper joypad trim (9 reads → 3). v3.01 ONLY (teleport rewrites
# the wrapper). Skipped on teleport ROM.
#
# After `LD A, 0x10` (button-half mode select, opcode at 0x6F21+0x22) and
# `LDH [FF00], A` (0x6F23-24), the FIRST direction read's `LDH A, [FF00]`
# opcode (0xF0) lands at 0x6F25. With iter 39's 3-read trim, the THIRD
# read's opcode is at 0x6F29 and `CPL` (0x2F) closes the read group at
# 0x6F2B. If reverted to 9 reads, 0x6F2B would be 0xF0 (another read).
ITER39_V301_CHECKS = [
    (
        13 * 0x4000 + (0x6F25 - 0x4000),
        0xF0,
        "iter 39: wrapper joypad direction read 1 opcode at 0x6F25 = 0xF0 (LDH A,[FF00])",
    ),
    (
        13 * 0x4000 + (0x6F29 - 0x4000),
        0xF0,
        "iter 39: wrapper joypad direction read 3 opcode at 0x6F29 = 0xF0 (last of trimmed 3)",
    ),
    (
        13 * 0x4000 + (0x6F2B - 0x4000),
        0x2F,
        "iter 39: CPL at 0x6F2B closes direction-half (would be 0xF0 if 9 reads not trimmed)",
    ),
]

# Iter 40 — bg_table_hi operand differs by ROM. We pick the right expected
# value once we've identified the ROM.
ITER40_TABLE_HI_OFFSET = 13 * 0x4000 + (0x6D1D - 0x4000)

# Iter 211 — palette-source bytes for SaraWitch OBP-2 (the iconic pink-red).
# Both ROMs share obj_data at bank13:0x6840+. OBP-2 starts at 0x6850 with
# 00 00 (idx 0) BE 2E (idx 1 = 0x2EBE peach) 1F 51 (idx 2 = 0x511F pink-red)
# 42 08 (idx 3 = 0x0842 black). The iter 70 adversarial probe confirmed
# corrupting these bytes flows through palette_loader to the rendered
# screen and is detected by sara_w_pink_render. These byte locks add
# pre-test catch (the verifier fires before any mGBA test does).
ITER_211_SHARED_OBJ_PAL_CHECKS = [
    (13 * 0x4000 + (0x6852 - 0x4000), 0xBE,
     "iter 211: OBP-2 idx 1 (SaraWitch peach) low byte at bank13:0x6852 = 0xBE (0x2EBE)"),
    (13 * 0x4000 + (0x6853 - 0x4000), 0x2E,
     "iter 211: OBP-2 idx 1 (SaraWitch peach) high byte at bank13:0x6853 = 0x2E"),
    (13 * 0x4000 + (0x6854 - 0x4000), 0x1F,
     "iter 211: OBP-2 idx 2 (SaraWitch pink-red) low byte at bank13:0x6854 = 0x1F (0x511F)"),
    (13 * 0x4000 + (0x6855 - 0x4000), 0x51,
     "iter 211: OBP-2 idx 2 (SaraWitch pink-red) high byte at bank13:0x6855 = 0x51"),
    # Iter 212: SaraDragon (OBP-1) primary + secondary greens. Both ROMs
    # share obj_data, so these are valid checks across both.
    (13 * 0x4000 + (0x684A - 0x4000), 0xE0,
     "iter 212: OBP-1 idx 1 (SaraDragon bright green) low at bank13:0x684A = 0xE0 (0x03E0)"),
    (13 * 0x4000 + (0x684B - 0x4000), 0x03,
     "iter 212: OBP-1 idx 1 (SaraDragon bright green) high at bank13:0x684B = 0x03"),
    (13 * 0x4000 + (0x684C - 0x4000), 0xC0,
     "iter 212: OBP-1 idx 2 (SaraDragon mid green) low at bank13:0x684C = 0xC0 (0x01C0)"),
    (13 * 0x4000 + (0x684D - 0x4000), 0x01,
     "iter 212: OBP-1 idx 2 (SaraDragon mid green) high at bank13:0x684D = 0x01"),
    # Iter 214: BG palette source bytes — Dungeon (pal 0) + Items/font (pal 1).
    # bg_data shares bank13:0x6800+. Locks the iconic Dungeon-lavender +
    # cherry-red item color sources. Both ROMs share this block.
    (13 * 0x4000 + (0x6802 - 0x4000), 0x94,
     "iter 214: BG-pal-0 idx 1 (Dungeon lavender) low at bank13:0x6802 = 0x94 (0x7E94)"),
    (13 * 0x4000 + (0x6803 - 0x4000), 0x7E,
     "iter 214: BG-pal-0 idx 1 (Dungeon lavender) high at bank13:0x6803 = 0x7E"),
    (13 * 0x4000 + (0x680A - 0x4000), 0x1F,
     "iter 214: BG-pal-1 idx 1 (Items cherry red) low at bank13:0x680A = 0x1F (0x001F)"),
    (13 * 0x4000 + (0x680B - 0x4000), 0x00,
     "iter 214: BG-pal-1 idx 1 (Items cherry red) high at bank13:0x680B = 0x00"),
    # Iter 213: boss_pal source bytes — Gargoyle + Spider signature colors.
    # Both ROMs share obj_data including boss_pal at bank13:0x6880. Per iter
    # 145, Gargoyle boss_pal[0] idx 1 = 0x601F (renders dark magenta), and
    # Spider boss_pal[1] idx 2 = 0x00BF (the orange spider-body catcher).
    (13 * 0x4000 + (0x6882 - 0x4000), 0x1F,
     "iter 213: Gargoyle boss_pal[0] idx 1 low at bank13:0x6882 = 0x1F (0x601F)"),
    (13 * 0x4000 + (0x6883 - 0x4000), 0x60,
     "iter 213: Gargoyle boss_pal[0] idx 1 high at bank13:0x6883 = 0x60"),
    (13 * 0x4000 + (0x688C - 0x4000), 0xBF,
     "iter 213: Spider boss_pal[1] idx 2 low at bank13:0x688C = 0xBF (0x00BF orange catcher)"),
    (13 * 0x4000 + (0x688D - 0x4000), 0x00,
     "iter 213: Spider boss_pal[1] idx 2 high at bank13:0x688D = 0x00"),
]

# Iter 210 — cond_pal + shadow_main entry signatures (shared v3.01+teleport).
# cond_pal @ bank13:0x6C90 reads DF02 sentinel (cold-boot palette init guard).
# shadow_main @ bank13:0x69D0 starts the OBJ-shadow-colorizer (push regs +
# LDH A,[FFBE] for Sara form dispatch).
ITER_210_SHARED_PALETTE_CHECKS = [
    (13 * 0x4000 + (0x6C90 - 0x4000), 0xFA,
     "iter 210: cond_pal entry at bank13:0x6C90 = 0xFA (LD A,[DF02] sentinel check)"),
    (13 * 0x4000 + (0x6C91 - 0x4000), 0x02,
     "iter 210: cond_pal DF02 sentinel low byte at bank13:0x6C91 = 0x02"),
    (13 * 0x4000 + (0x69D0 - 0x4000), 0xF5,
     "iter 210: shadow_main entry at bank13:0x69D0 = 0xF5 (PUSH AF)"),
    (13 * 0x4000 + (0x69D4 - 0x4000), 0xF0,
     "iter 210: shadow_main FFBE read at bank13:0x69D4 = 0xF0 (LDH A,[FFBE])"),
]

# Iter 209 — safe-switching VBlank hook at bank0:0x0824. Same entry in
# both ROMs: `F0 99 F5 3E 0D E0 70` = LDH A,[FF99]; PUSH AF; LD A,0x0D;
# LDH [FF70],A — saves FF99 then maps WRAM bank 13 before calling the
# wrapper. Catches any change to the hook entry layout.
ITER_209_SHARED_VBLANK_HOOK_CHECKS = [
    (0x0824, 0xF0, "iter 209: VBlank hook entry at 0x0824 = 0xF0 (LDH A,[FF99])"),
    (0x0825, 0x99, "iter 209: VBlank hook entry at 0x0825 = 0x99 (FF99 low byte)"),
]

# Iter 208 — STAT IRQ vector. Teleport redirects to WRAM 0xDB50 (the
# iter 10 STAT-IRQ WRAM stub that re-stamps slot-1 attr from FFBE).
# v3.01 keeps the original 0x0853 target (unpatched).
ITER_208_STAT_IRQ_TELEPORT_CHECKS = [
    (0x0049, 0x50, "iter 208 (teleport): STAT IRQ JP low at 0x0049 = 0x50 (WRAM 0xDB50)"),
    (0x004A, 0xDB, "iter 208 (teleport): STAT IRQ JP high at 0x004A = 0xDB"),
]
ITER_208_STAT_IRQ_V301_CHECKS = [
    (0x0049, 0x53, "iter 208 (v3.01): STAT IRQ JP low at 0x0049 = 0x53 (original 0x0853)"),
    (0x004A, 0x08, "iter 208 (v3.01): STAT IRQ JP high at 0x004A = 0x08"),
]

# Iter 207 — colorize handler entry signature. Shared by v3.01 and teleport
# (both use the same handler at bank13:0x6E00). Bytes: F0 4F F5 AF E0 4F
# = LDH A,[FF4F]; PUSH AF; XOR A; LDH [FF4F],A (VBK save + zero — entry
# pattern of every CGB-safe routine that touches palette/attribute RAM).
ITER_207_SHARED_COLORIZE_CHECKS = [
    (
        13 * 0x4000 + (0x6E00 - 0x4000),
        0xF0,
        "iter 207: colorize handler entry at bank13:0x6E00 = 0xF0 (LDH A,[FF4F] VBK save)",
    ),
    (
        13 * 0x4000 + (0x6E01 - 0x4000),
        0x4F,
        "iter 207: colorize handler entry at bank13:0x6E01 = 0x4F (FF4F low byte)",
    ),
]

# Iter 206 — pin the lava_override + banner_override entry signatures.
# Both routines start with a D880 dispatch check and live in teleport-only
# regions. Catches any future change that moves the entry point or alters
# the gate value.
# Iter 217 — dungeon bg_table content (shared). bank13:0x7000 holds the
# 256-byte tile→palette dungeon table. Key entries:
# - 0x7080 = 0x01 (font/items tile 0x80 → pal 1 red — iter 16 verified)
# - 0x70E0 = 0x00 (banner letter tile 0xE0 → pal 0; only banner_override
#   re-routes to pal 4 in D880=0x1B scene)
ITER_217_SHARED_BG_TABLE_CHECKS = [
    (13 * 0x4000 + (0x7080 - 0x4000), 0x01,
     "iter 217: bg_table[0x80] (font/items tile) → pal 1 at bank13:0x7080 = 0x01"),
    (13 * 0x4000 + (0x70E0 - 0x4000), 0x00,
     "iter 217: bg_table[0xE0] (banner-letter tile baseline) → pal 0 at bank13:0x70E0 = 0x00"),
    # Iter 218: hazard (spikes) + wall-corner tile entries. All routed to
    # pal 6 (metallic) per iter 16's dungeon_table_spikes_metallic test.
    # The 2026-05-23 orange regression was tile-0x47 mapping to pal 1; this
    # check pins the post-fix pal 6 assignment.
    (13 * 0x4000 + (0x702A - 0x4000), 0x06,
     "iter 218: bg_table[0x2A] (spike tile) → pal 6 metallic at bank13:0x702A"),
    (13 * 0x4000 + (0x702E - 0x4000), 0x06,
     "iter 218: bg_table[0x2E] (spike tile) → pal 6 metallic at bank13:0x702E"),
    (13 * 0x4000 + (0x7047 - 0x4000), 0x06,
     "iter 218: bg_table[0x47] (wall corner) → pal 6 metallic at bank13:0x7047"),
    (13 * 0x4000 + (0x7057 - 0x4000), 0x06,
     "iter 218: bg_table[0x57] (wall corner) → pal 6 metallic at bank13:0x7057"),
]

# Iter 216 — inline hook entry signature (shared v3.01+teleport).
# bank1:0x42A5 is the live entry point used by both the title banner
# (bank1:0x3AD8 CALL 0x42A5) and ending-path buffer flush (bank1:0x43BA).
# Bytes: 0x26 0x98 0x2E 0x00 = LD H,0x98; LD L,0x00. The audit
# (cutscenes_intro_ending.md §1) corrected an earlier doc that said
# 0x42A6 RET; the actual entry is at 0x42A5 with LD H,0x98 opcode.
ITER_216_SHARED_INLINE_HOOK_CHECKS = [
    (0x42A5, 0x26,
     "iter 216: inline hook entry at bank1:0x42A5 = 0x26 (LD H, n8 opcode)"),
    (0x42A6, 0x98,
     "iter 216: inline hook entry at bank1:0x42A6 = 0x98 (LD H, 0x98 — VRAM tilemap high byte)"),
]

# Iter 215 — scene_detect entry signature (teleport-only).
# bank13:0x6FB0 = `FA 80 D8 21 0D DF BE C8`: LD A,[D880]; LD HL,DF0D;
# CP [HL]; RET Z (fast-path early-out when scene byte unchanged).
ITER_215_TELEPORT_SCENE_DETECT_CHECKS = [
    (13 * 0x4000 + (0x6FB0 - 0x4000), 0xFA,
     "iter 215: scene_detect entry at bank13:0x6FB0 = 0xFA (LD A,[D880])"),
    (13 * 0x4000 + (0x6FB3 - 0x4000), 0x21,
     "iter 215: scene_detect LD HL opcode at bank13:0x6FB3 = 0x21"),
    (13 * 0x4000 + (0x6FB4 - 0x4000), 0x0D,
     "iter 215: scene_detect DF0D cache addr low at bank13:0x6FB4 = 0x0D"),
    (13 * 0x4000 + (0x6FB5 - 0x4000), 0xDF,
     "iter 215: scene_detect DF0D cache addr high at bank13:0x6FB5 = 0xDF"),
]

# Iter 215b — CGB flag at 0x143 (shared, all CGB-capable ROMs must have this).
ITER_215_SHARED_CGB_FLAG_CHECKS = [
    (0x0143, 0x80,
     "iter 215: CGB flag at 0x0143 = 0x80 (CGB+DMG-compatible — game uses CGB palette/attr features)"),
]

ITER_206_TELEPORT_OVERRIDE_CHECKS = [
    (
        13 * 0x4000 + (0x7E00 - 0x4000),
        0xFA,
        "iter 206: lava_override entry at bank13:0x7E00 = 0xFA (LD A,[D880])",
    ),
    (
        13 * 0x4000 + (0x7E01 - 0x4000),
        0x80,
        "iter 206: lava_override entry at bank13:0x7E01 = 0x80 (low byte of D880)",
    ),
    (
        13 * 0x4000 + (0x7F70 - 0x4000),
        0xFA,
        "iter 206: banner_override entry at bank13:0x7F70 = 0xFA (LD A,[D880])",
    ),
    (
        13 * 0x4000 + (0x7F74 - 0x4000),
        0x1B,
        "iter 206: banner_override D880 gate value at bank13:0x7F74 = 0x1B (title banner scene)",
    ),
]

# Iter 2582e85 — level-select bleed fix. TELEPORT ONLY (v3.01 production
# left unpatched; verify the original 0x7393 target survives). The fix
# redirects bank1:0x3B47's JP NZ from 0x7393 to 0xDB28 (WRAM stub), and
# stages the stub bytes at bank13:0x53C2. Iter 157 verified end-to-end.
ITER_2582E85_TELEPORT_CHECKS = [
    (
        0x3B48,
        0x28,
        "iter 2582e85: bank1:0x3B48 JP NZ low byte = 0x28 (target 0xDB28 WRAM stub)",
    ),
    (
        0x3B49,
        0xDB,
        "iter 2582e85: bank1:0x3B49 JP NZ high byte = 0xDB",
    ),
    (
        13 * 0x4000 + (0x53C2 - 0x4000),
        0xE5,
        "iter 2582e85: stub source at bank13:0x53C2 starts with 0xE5 (PUSH HL)",
    ),
    (
        13 * 0x4000 + (0x53C3 - 0x4000),
        0xC5,
        "iter 2582e85: stub source at bank13:0x53C3 = 0xC5 (PUSH BC)",
    ),
]

# v3.01 sanity: the JP NZ should still point to 0x7393 (unpatched).
ITER_2582E85_V301_CHECKS = [
    (
        0x3B48,
        0x93,
        "v3.01 sanity: bank1:0x3B48 JP NZ low byte = 0x93 (unpatched, target 0x7393)",
    ),
    (
        0x3B49,
        0x73,
        "v3.01 sanity: bank1:0x3B49 JP NZ high byte = 0x73",
    ),
]


def identify_rom(rom: bytes) -> str:
    """Sniff which build this ROM is. Returns "v301", "teleport", or "unknown"."""
    # Teleport's wrapper at 0x6F10 starts with F8 (LD HL, SP+r8). v3.01's
    # wrapper at 0x6F10 starts with C5 (PUSH BC).
    wrapper_off = 13 * 0x4000 + (0x6F10 - 0x4000)
    head = rom[wrapper_off:wrapper_off + 3]
    if head[0] == 0xC5:
        return "v301"
    if head[0] == 0xF8:
        return "teleport"
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, help="ROM file to validate")
    args = parser.parse_args()
    rom = Path(args.rom).read_bytes()
    kind = identify_rom(rom)
    print(f"  [INFO] ROM type: {kind}")

    # iter 31's hwoam_recolor lives only in teleport (v3.01 production lacks
    # it — iter 43 verified backport regresses Sara timing). Skip those
    # checks on v3.01.
    # hwoam_recolor lives ONLY in teleport (3 checks: 0x7F40, 0x7F41, 0x7F67).
    # Skip them all on v3.01.
    hwoam_offsets = {
        13 * 0x4000 + (0x7F40 - 0x4000),
        13 * 0x4000 + (0x7F41 - 0x4000),
        13 * 0x4000 + (0x7F67 - 0x4000),
    }
    iter31_for_kind = ITER31_CHECKS if kind == "teleport" else [
        c for c in ITER31_CHECKS if c[0] not in hwoam_offsets
    ]
    checks = (list(iter31_for_kind) + list(ITER40_OPCODE_CHECKS)
              + list(ITER_207_SHARED_COLORIZE_CHECKS)
              + list(ITER_209_SHARED_VBLANK_HOOK_CHECKS)
              + list(ITER_210_SHARED_PALETTE_CHECKS)
              + list(ITER_211_SHARED_OBJ_PAL_CHECKS)
              + list(ITER_215_SHARED_CGB_FLAG_CHECKS)
              + list(ITER_216_SHARED_INLINE_HOOK_CHECKS)
              + list(ITER_217_SHARED_BG_TABLE_CHECKS))
    if kind == "v301":
        checks.extend(ITER39_V301_CHECKS)
        checks.extend(ITER_2582E85_V301_CHECKS)
        checks.extend(ITER_208_STAT_IRQ_V301_CHECKS)
        checks.append((
            ITER40_TABLE_HI_OFFSET,
            0x70,
            "iter 40 (v301): bg_sweep LD B operand at 0x6D1D = 0x70 (bg_table_hi from bank13:0x7000)",
        ))
    elif kind == "teleport":
        checks.extend(ITER_2582E85_TELEPORT_CHECKS)
        checks.extend(ITER_206_TELEPORT_OVERRIDE_CHECKS)
        checks.extend(ITER_208_STAT_IRQ_TELEPORT_CHECKS)
        checks.extend(ITER_215_TELEPORT_SCENE_DETECT_CHECKS)
        checks.append((
            ITER40_TABLE_HI_OFFSET,
            0xDA,
            "iter 40 (teleport): bg_sweep LD B operand at 0x6D1D = 0xDA (re-patched to WRAM 0xDA00)",
        ))
    else:
        print(f"  [WARN] unknown ROM kind; skipping wrapper/bg_table_hi checks")

    failed = 0
    for off, expected, desc in checks:
        actual = rom[off]
        if actual == expected:
            print(f"  [PASS] {desc}")
        else:
            print(f"  [FAIL] {desc}: got 0x{actual:02X}, expected 0x{expected:02X}")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
