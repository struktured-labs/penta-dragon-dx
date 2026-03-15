#include "palettes.h"

void init_palettes(void) {
    // Load all 8 BG palettes
    set_bkg_palette(0, 8, bg_palettes[0]);

    // Load all 8 OBJ palettes
    set_sprite_palette(0, 8, obj_palettes[0]);
}

void load_boss_palette(uint8_t boss_id) {
    if (boss_id < 1 || boss_id > 8) return;
    uint8_t slot = boss_target_slot[boss_id - 1];
    set_sprite_palette(slot, 1, boss_palettes[boss_id - 1]);
}

void load_powerup_palette(uint8_t powerup_id) {
    if (powerup_id < 1 || powerup_id > 3) return;
    set_sprite_palette(0, 1, powerup_palettes[powerup_id - 1]);
}
