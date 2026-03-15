#ifndef __PALETTES_H__
#define __PALETTES_H__

#include <gb/gb.h>
#include <gb/cgb.h>

// BGR555 palette data from penta_palettes_v097.yaml
// Each palette = 4 colors x 2 bytes = 8 bytes

// ============================================
// BACKGROUND PALETTES (8 palettes)
// ============================================

// Palette 0 - Dungeon floor/platform (blue-white)
// Palette 1 - Items/pickups (gold/yellow)
// Palette 2 - Decorative (purple/magenta)
// Palette 3 - Nature/organic (green)
// Palette 4 - Water/ice (cyan/teal)
// Palette 5 - Fire/lava (red/orange)
// Palette 6 - Stone/castle walls (blue-gray)
// Palette 7 - Mystery/special (deep blue)

static const palette_color_t bg_palettes[8][4] = {
    { 0x7FFF, 0x7E94, 0x3D4A, 0x0000 },  // 0: Dungeon
    { 0x03FF, 0x02DF, 0x019F, 0x0000 },  // 1: Items (gold)
    { 0x7E1F, 0x5C0F, 0x3807, 0x0000 },  // 2: Decorative (purple)
    { 0x03E0, 0x02A0, 0x0160, 0x0000 },  // 3: Nature (green)
    { 0x7FE0, 0x5EC0, 0x3D80, 0x0000 },  // 4: Water (cyan)
    { 0x03FF, 0x00DF, 0x001F, 0x0000 },  // 5: Fire (red/orange)
    { 0x6F7B, 0x4E73, 0x2D4A, 0x0000 },  // 6: Stone walls
    { 0x7E10, 0x5C08, 0x3800, 0x0000 },  // 7: Mystery (navy)
};

// ============================================
// SPRITE PALETTES (8 palettes)
// ============================================

// Palette 0 - Enemy projectiles / effects (blue)
// Palette 1 - Sara Dragon (green)
// Palette 2 - Sara Witch (skin/pink)
// Palette 3 - Sara W projectile + Crows (red)
// Palette 4 - Hornets (yellow/orange)
// Palette 5 - Orc/ground (green/brown)
// Palette 6 - Humanoid/soldier (purple)
// Palette 7 - Catfish/special (cyan)

static const palette_color_t obj_palettes[8][4] = {
    { 0x0000, 0x7C00, 0x5800, 0x3000 },  // 0: Enemy projectile (blue)
    { 0x0000, 0x03E0, 0x01C0, 0x0000 },  // 1: Sara Dragon (green)
    { 0x0000, 0x2EBE, 0x511F, 0x0842 },  // 2: Sara Witch (skin/pink)
    { 0x0000, 0x001F, 0x0017, 0x000F },  // 3: Sara W proj + Crow (red)
    { 0x0000, 0x03FF, 0x00DF, 0x0000 },  // 4: Hornets (yellow)
    { 0x0000, 0x02A0, 0x0160, 0x0000 },  // 5: Orc (green/brown)
    { 0x0000, 0x7C1F, 0x4C0F, 0x0000 },  // 6: Humanoid (purple)
    { 0x0000, 0x7FE0, 0x3CC0, 0x0000 },  // 7: Catfish (cyan)
};

// ============================================
// BOSS PALETTES (8 bosses, loaded dynamically)
// ============================================

// boss_id 1-8 maps to index 0-7
// Each boss targets either slot 6 or slot 7

static const uint8_t boss_target_slot[8] = {
    6, 7, 6, 7, 6, 7, 6, 7
};

static const palette_color_t boss_palettes[8][4] = {
    { 0x0000, 0x601F, 0x400F, 0x0000 },  // 1: Gargoyle (dark magenta)
    { 0x0000, 0x001F, 0x00BF, 0x0000 },  // 2: Spider (red/orange)
    { 0x0000, 0x0CBF, 0x0859, 0x040F },  // 3: Crimson (crimson)
    { 0x0000, 0x7F94, 0x668A, 0x4940 },  // 4: Ice (ice blue)
    { 0x0000, 0x70B4, 0x584F, 0x3C08 },  // 5: Void (violet)
    { 0x0000, 0x0BC8, 0x06C4, 0x01C0 },  // 6: Poison (toxic green)
    { 0x0000, 0x0F1F, 0x0A58, 0x0150 },  // 7: Knight (gold)
    { 0x0000, 0x7FFF, 0x5AD6, 0x318C },  // 8: Angela (white/silver)
};

// ============================================
// POWERUP PALETTES (loaded into OBJ palette 0)
// ============================================

static const palette_color_t powerup_palettes[3][4] = {
    { 0x0000, 0x7FE0, 0x5EC0, 0x3E80 },  // 1: Spiral (cyan)
    { 0x0000, 0x03FF, 0x02BF, 0x019F },  // 2: Shield (gold)
    { 0x0000, 0x00FF, 0x00BF, 0x005F },  // 3: Turbo (orange)
};

// ============================================
// JET FORM PALETTES (bonus stage)
// ============================================

static const palette_color_t jet_witch_palette[4] =
    { 0x0000, 0x7C1F, 0x5817, 0x3010 };  // Magenta/purple

static const palette_color_t jet_dragon_palette[4] =
    { 0x0000, 0x7FE0, 0x4EC0, 0x2D80 };  // Cyan/blue

// Load all palettes at boot
void init_palettes(void);

// Load boss palette into target slot
void load_boss_palette(uint8_t boss_id);

// Load powerup palette into OBJ slot 0
void load_powerup_palette(uint8_t powerup_id);

#endif /* __PALETTES_H__ */
