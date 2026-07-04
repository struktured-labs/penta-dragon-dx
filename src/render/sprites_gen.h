// Auto-generated declarations matching sprites_gen.c.
// Regenerate both files via: python3 scripts/sprite_authoring.py c > src/render/sprites_gen.c
#ifndef QUINTRA_RENDER_SPRITES_GEN_H
#define QUINTRA_RENDER_SPRITES_GEN_H

#include "core/types.h"

// 16x16 player class metasprites (4 tiles each, row-major TL/TR/BL/BR)
extern const u8 sprite_class_wolfkin[64];
extern const u8 sprite_class_sauran[64];
extern const u8 sprite_class_corvin[64];
extern const u8 sprite_class_picsean[64];
extern const u8 sprite_class_vespine[64];

// 8x8 enemy sprites
extern const u8 sprite_enemy_crawler[16];
extern const u8 sprite_enemy_hornet[16];
extern const u8 sprite_enemy_skeleton[16];
extern const u8 sprite_enemy_orc[16];

// 8x8 FX sprites
extern const u8 sprite_fx_bullet_a[16];
extern const u8 sprite_fx_bullet_b[16];
extern const u8 sprite_fx_muzzle[16];
extern const u8 sprite_fx_impact[16];

// 16x16 boss metasprite
extern const u8 sprite_boss_sentinel[64];

// 8x8 dungeon BG tiles
extern const u8 bgt_floor_plain[16];
extern const u8 bgt_floor_crack[16];
extern const u8 bgt_floor_pebble[16];
extern const u8 bgt_wall_brick[16];
extern const u8 bgt_door_frame[16];
extern const u8 bgt_pillar[16];
extern const u8 bgt_crystal[16];
extern const u8 bgt_rubble[16];

#endif
