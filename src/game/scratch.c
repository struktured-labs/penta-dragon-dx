// Phase 3 placeholder — confirms the screen FSM transition works.
#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/console.h>
#include <gbdk/font.h>
#include <stdio.h>

#include "core/types.h"
#include "game/scratch.h"
#include "render/palette.h"
#include "content.h"

static const u16 scratch_palette[4] = {
    BGR555( 2, 10,  4),    // 0: forest green
    BGR555( 8, 18,  8),    // 1: lighter green
    BGR555(20, 26, 14),    // 2: pale yellow-green
    BGR555(30, 30, 24),    // 3: cream
};

void scratch_enter(void) {
    DISPLAY_OFF;
    palette_bg_load(0, scratch_palette);
    palette_bg_load(7, scratch_palette);

    font_init();
    {
        font_t f = font_load(font_min);
        font_set(f);
    }
    cls();

    gotoxy(2, 2);  printf("ENGINE OK");
    gotoxy(1, 5);  printf("classes: %u",  (u16)N_CLASSES);
    gotoxy(1, 6);  printf("items:   %u",  (u16)N_ITEMS);
    gotoxy(1, 7);  printf("enemies: %u",  (u16)N_ENEMIES);
    gotoxy(1, 8);  printf("biomes:  %u",  (u16)N_BIOMES);
    gotoxy(1, 9);  printf("rooms:   %u",  (u16)N_ROOM_TEMPLATES);

    gotoxy(2, 14); printf("B = back");

    SHOW_BKG;
    DISPLAY_ON;
}

void scratch_exit(void) {}

screen_id_t scratch_tick(u8 keys, u8 pressed) {
    keys;
    if (pressed & J_B) return SCREEN_TITLE;
    return SCREEN_SELF;
}

void scratch_draw(void) {}
