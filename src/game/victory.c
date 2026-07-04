// VICTORY — boss-defeated screen, returns to TITLE.

#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/console.h>
#include <gbdk/font.h>
#include <stdio.h>

#include "audio/music.h"
#include "core/types.h"
#include "game/run_state.h"
#include "game/victory.h"
#include "render/palette.h"

static u8 pulse;

static const u16 victory_palette[4] = {
    BGR555( 0,  4,  2),    // 0: deep emerald
    BGR555( 4, 16,  6),    // 1: forest green
    BGR555(24, 28,  6),    // 2: bright yellow-green
    BGR555(31, 31, 24),    // 3: cream-gold
};

void victory_enter(void) {
    DISPLAY_OFF;
    HIDE_SPRITES;
    HIDE_WIN;
    palette_bg_load(0, victory_palette);
    palette_bg_load(7, victory_palette);

    font_init();
    { font_t f = font_load(font_min); font_set(f); }
    cls();

    gotoxy(6, 3);  printf("VICTORY!");
    gotoxy(2, 6);  printf("3 sentinels");
    gotoxy(2, 7);  printf("felled. depths");
    gotoxy(2, 8);  printf("cleansed!");

    gotoxy(2, 11); printf("rooms   %u", (u16)run_state.room_counter);
    gotoxy(2, 12); printf("kills   %u", (u16)run_state.enemies_killed);
    gotoxy(2, 13); printf("score   %u", (u16)run_state.score);

    gotoxy(2, 16); printf("PRESS  START");

    pulse = 0;
    music_play_victory();
    SHOW_BKG;
    DISPLAY_ON;
}

void victory_exit(void) {}

screen_id_t victory_tick(u8 keys, u8 pressed) {
    keys;
    if (pressed & J_START) return SCREEN_TITLE;
    if (pressed & J_A)     return SCREEN_TITLE;
    return SCREEN_SELF;
}

void victory_draw(void) {
    // Pulse color index 2 between green-yellow and pale-gold
    pulse = (u8)(pulse + 1);
    if (pulse >= 90) pulse = 0;
    {
        u8 phase = pulse < 45 ? pulse : (u8)(89 - pulse);
        u8 r     = (u8)(24 - (phase >> 1));
        u8 g     = (u8)(28 + (phase >> 3));
        u8 b     = (u8)(6  + (phase >> 1));
        u16 c2   = BGR555(r, g, b);
        u16 pal[4] = {
            victory_palette[0],
            victory_palette[1],
            c2,
            victory_palette[3],
        };
        palette_bg_load(0, pal);
        palette_bg_load(7, pal);
    }
}
