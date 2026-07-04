#include <gb/gb.h>
#include <gb/cgb.h>

#include "core/types.h"
#include "game/player.h"
#include "game/run_state.h"
#include "render/hud.h"
#include "render/palette.h"
#include "render/tiles.h"

// HUD palette — bright accent (red hearts, gold coin) on dark BG
static const u16 hud_palette[4] = {
    BGR555( 0,  0,  0),    // 0: transparent / dark BG
    BGR555(10, 14, 20),    // 1: outline gray-blue
    BGR555(31, 20,  6),    // 2: coin gold
    BGR555(31,  6,  8),    // 3: heart red
};

// 1-row HUD layout (20 tiles wide):
//
//   col:  0 1 2 3 4   ...   15 16 17 18 19
//        [hearts × 5] [pad] [$] [d] [d] [d] [pad]
//
// Hearts: 5 slots. Each shows full/half/empty based on player.hp.
// Coin count: 3 digits, leading zeros suppressed via blank tile.

void hud_init(void) {
    tiles_load_hud();
    // Place HUD on BG palette slot 7 (won't collide with room pal 0)
    palette_bg_load(7, hud_palette);

    // Fill all 20 WIN tiles with blank, then set palette attribute = 7
    {
        u8 row[20];
        u8 attr[20];
        u8 i;
        for (i = 0; i < 20; ++i) { row[i] = HUD_BLANK; attr[i] = 0x07; }
        VBK_REG = 0; set_win_tiles(0, 0, 20, 1, row);
        VBK_REG = 1; set_win_tiles(0, 0, 20, 1, attr);
        VBK_REG = 0;
    }

    // Bottom-strip HUD: the GB window extends to the bottom-right of the
    // frame from wherever it starts, so a top-row HUD would occlude the
    // whole playfield (the Phase-6..13 "blank room" bug). WY=136 shows
    // only the last 8 scanlines. WX=7 = window x=0.
    WY_REG = 136;
    WX_REG = 7;
    LCDC_REG |= 0x40;   // WIN map = 0x9C00 (match set_win_tiles target)

    hud_redraw_all();
}

void hud_show(void) { SHOW_WIN; }
void hud_hide(void) { HIDE_WIN; }

void hud_redraw_hp(void) {
    u8 row[5];
    u8 hearts_total = player.hp_max;     // half-hearts
    u8 hearts_filled = player.hp;
    u8 i;

    for (i = 0; i < HUD_MAX_HEARTS; ++i) {
        u8 cap_full  = (u8)(2 + (i * 2));    // half-hearts up to and including full
        u8 cap_half  = (u8)(1 + (i * 2));
        if ((u8)((i * 2)) >= hearts_total) {
            row[i] = HUD_BLANK;             // no heart slot for this class
        } else if (hearts_filled >= cap_full) {
            row[i] = HUD_HEART_FULL;
        } else if (hearts_filled >= cap_half) {
            row[i] = HUD_HEART_HALF;
        } else {
            row[i] = HUD_HEART_EMPTY;
        }
    }
    VBK_REG = 0;
    set_win_tiles(0, 0, HUD_MAX_HEARTS, 1, row);
}

void hud_redraw_coins(void) {
    u8 row[4];
    u16 c = player.coins;
    if (c > 999) c = 999;
    row[0] = HUD_COIN;
    row[1] = (u8)(HUD_DIGIT_0 + (c / 100));
    row[2] = (u8)(HUD_DIGIT_0 + ((c / 10) % 10));
    row[3] = (u8)(HUD_DIGIT_0 + (c % 10));
    VBK_REG = 0;
    set_win_tiles(15, 0, 4, 1, row);
}

void hud_redraw_depth(void) {
    // Room depth as 2 digits, centered-ish (cols 8-9). Boss lives at depth 5.
    u8 row[2];
    u8 d = run_state.room_counter;
    if (d > 99) d = 99;
    row[0] = (u8)(HUD_DIGIT_0 + (d / 10));
    row[1] = (u8)(HUD_DIGIT_0 + (d % 10));
    VBK_REG = 0;
    set_win_tiles(8, 0, 2, 1, row);
}

void hud_redraw_all(void) {
    hud_redraw_hp();
    hud_redraw_coins();
    hud_redraw_depth();
}
