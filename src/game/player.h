// Player state — lives in WRAM at $C400 per the design.
#ifndef QUINTRA_GAME_PLAYER_H
#define QUINTRA_GAME_PLAYER_H

#include "core/types.h"

#define INVENTORY_SLOTS 16   // Phase 4-5; bumped to 64 in Phase 6+

// Facing direction (4-dir, mapped to D-pad bits in tick fns)
enum {
    FACE_S = 0,    // default-facing-down at game start
    FACE_E,
    FACE_N,
    FACE_W,
};

typedef struct {
    u8     class_id;
    u8     hp_max;       // half-hearts
    u8     hp;
    u8     mp_max;
    u8     mp;
    u8     atk, def, spd, lck;
    ppos_t x, y;         // pixel position within current room (i16, no fix-point)
    u8     facing;
    u8     anim_frame;
    u8     iframes;
    u16    coins;
    u8     active_item;  // item_id_t LSB (Phase 4 — extend to u16 later)
    u8     active_charge;
    u8     starter_weapon;
    u8     fire_cooldown;                // ticks until next shot allowed
    u8     move_acc;                     // sub-pixel movement accumulator (5 = 1px)
    u8     inventory[INVENTORY_SLOTS];   // item id LSBs; 0xFF = empty
    u8     score_lo, score_hi;           // 16-bit score
} player_state_t;

extern player_state_t player;

void player_init_from_class(u8 class_id);
void player_clear(void);

#endif
