// GAMEOVER — death stats screen, returns to TITLE.

#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/console.h>
#include <gbdk/font.h>
#include <stdio.h>

#include "audio/music.h"
#include "core/types.h"
#include "game/gameover.h"
#include "game/run_state.h"
#include "render/palette.h"

static const u16 gameover_palette[4] = {
    BGR555( 4,  0,  2),    // 0: deep red-black
    BGR555(12,  2,  4),    // 1: dark crimson
    BGR555(28,  8,  8),    // 2: bright red
    BGR555(31, 28, 28),    // 3: pale pink-white
};

void gameover_enter(void) {
    DISPLAY_OFF;
    HIDE_SPRITES;
    HIDE_WIN;
    palette_bg_load(0, gameover_palette);
    palette_bg_load(7, gameover_palette);

    font_init();
    { font_t f = font_load(font_min); font_set(f); }
    cls();

    gotoxy(6, 3);  printf("GAME  OVER");
    gotoxy(2, 7);  printf("rooms   %u", (u16)run_state.room_counter);
    gotoxy(2, 8);  printf("kills   %u", (u16)run_state.enemies_killed);
    gotoxy(2, 9);  printf("score   %u", (u16)run_state.score);
    gotoxy(2, 14); printf("PRESS  START");

    music_play_gameover();
    SHOW_BKG;
    DISPLAY_ON;
}

void gameover_exit(void) {}

screen_id_t gameover_tick(u8 keys, u8 pressed) {
    keys;
    if (pressed & J_START) return SCREEN_TITLE;
    if (pressed & J_A)     return SCREEN_TITLE;
    return SCREEN_SELF;
}

void gameover_draw(void) {}
