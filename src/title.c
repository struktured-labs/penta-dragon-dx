#include "title.h"
#include "palettes.h"

// ============================================
// Title Screen
// Uses custom font tiles loaded into BG tile data
// Displays "PENTA DRAGON DX" and "PRESS START"
// Shows Sara Witch sprite centered on screen
// ============================================

// Title screen font tiles (A-Z subset + space)
// Only the letters we need: A, D, E, G, N, O, P, R, S, T, X
// Plus space. We'll load them at BG tile 0xE0-0xEF.
#define TITLE_TILE_BASE  0xE0

// Letter indices within our custom set
#define TL_A    0xE0
#define TL_D    0xE1
#define TL_E    0xE2
#define TL_G    0xE3
#define TL_N    0xE4
#define TL_O    0xE5
#define TL_P    0xE6
#define TL_R    0xE7
#define TL_S    0xE8
#define TL_T    0xE9
#define TL_X    0xEA
#define TL_SPC  0xEB  // space
#define TL_DASH 0xEC  // dash/underline for decoration

// Custom 8x8 font tile data for title letters (2bpp, 16 bytes each)
static const unsigned char title_font[] = {
    // 0xE0: 'A'
    0x18, 0x18, 0x3C, 0x3C, 0x66, 0x66, 0x7E, 0x7E,
    0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x00, 0x00,
    // 0xE1: 'D'
    0x7C, 0x7C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x66,
    0x66, 0x66, 0x66, 0x66, 0x7C, 0x7C, 0x00, 0x00,
    // 0xE2: 'E'
    0x7E, 0x7E, 0x60, 0x60, 0x60, 0x60, 0x7C, 0x7C,
    0x60, 0x60, 0x60, 0x60, 0x7E, 0x7E, 0x00, 0x00,
    // 0xE3: 'G'
    0x3C, 0x3C, 0x66, 0x66, 0x60, 0x60, 0x6E, 0x6E,
    0x66, 0x66, 0x66, 0x66, 0x3C, 0x3C, 0x00, 0x00,
    // 0xE4: 'N'
    0x66, 0x66, 0x76, 0x76, 0x7E, 0x7E, 0x6E, 0x6E,
    0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x00, 0x00,
    // 0xE5: 'O'
    0x3C, 0x3C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x66,
    0x66, 0x66, 0x66, 0x66, 0x3C, 0x3C, 0x00, 0x00,
    // 0xE6: 'P'
    0x7C, 0x7C, 0x66, 0x66, 0x66, 0x66, 0x7C, 0x7C,
    0x60, 0x60, 0x60, 0x60, 0x60, 0x60, 0x00, 0x00,
    // 0xE7: 'R'
    0x7C, 0x7C, 0x66, 0x66, 0x66, 0x66, 0x7C, 0x7C,
    0x6C, 0x6C, 0x66, 0x66, 0x66, 0x66, 0x00, 0x00,
    // 0xE8: 'S'
    0x3C, 0x3C, 0x66, 0x66, 0x60, 0x60, 0x3C, 0x3C,
    0x06, 0x06, 0x66, 0x66, 0x3C, 0x3C, 0x00, 0x00,
    // 0xE9: 'T'
    0x7E, 0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18,
    0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00, 0x00,
    // 0xEA: 'X'
    0x66, 0x66, 0x66, 0x66, 0x3C, 0x3C, 0x18, 0x18,
    0x3C, 0x3C, 0x66, 0x66, 0x66, 0x66, 0x00, 0x00,
    // 0xEB: space (blank)
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    // 0xEC: dash/decoration line
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x7E, 0x7E,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};

#define TITLE_NUM_TILES  13

// "PENTA" = P E N T A
static const uint8_t title_line1[] = {
    TL_P, TL_E, TL_N, TL_T, TL_A
};
#define TITLE_LINE1_LEN 5

// "DRAGON" = D R A G O N
static const uint8_t title_line2[] = {
    TL_D, TL_R, TL_A, TL_G, TL_O, TL_N
};
#define TITLE_LINE2_LEN 6

// "DX" = D X
static const uint8_t title_line3[] = {
    TL_D, TL_X
};
#define TITLE_LINE3_LEN 2

// "PRESS START" = P R E S S _ S T A R T
static const uint8_t press_start[] = {
    TL_P, TL_R, TL_E, TL_S, TL_S,
    TL_SPC,
    TL_S, TL_T, TL_A, TL_R, TL_T
};
#define PRESS_START_LEN 11

static uint8_t blink_timer;
static uint8_t blink_visible;

void title_init(void) {
    uint8_t row, col;
    uint8_t blank;
    uint8_t i;
    uint8_t start_col;
    uint8_t pal;

    DISPLAY_OFF;

    // Load title font tiles
    set_bkg_data(TITLE_TILE_BASE, TITLE_NUM_TILES, title_font);

    // Clear entire BG tilemap with blank tiles
    blank = TL_SPC;
    for (row = 0; row < 18; row++) {
        for (col = 0; col < 20; col++) {
            set_bkg_tiles(col, row, 1, 1, &blank);
        }
    }

    // Set palette attributes for title (use palette 2 for text = purple/decorative)
    VBK_REG = 1;
    pal = 2;
    for (row = 0; row < 18; row++) {
        for (col = 0; col < 20; col++) {
            set_bkg_tiles(col, row, 1, 1, &pal);
        }
    }
    VBK_REG = 0;

    // Draw "PENTA" centered on row 4 (20 cols, 5 chars -> col 7)
    start_col = (20 - TITLE_LINE1_LEN) / 2;
    for (i = 0; i < TITLE_LINE1_LEN; i++) {
        set_bkg_tiles(start_col + i, 4, 1, 1, &title_line1[i]);
    }

    // Draw "DRAGON" centered on row 6
    start_col = (20 - TITLE_LINE2_LEN) / 2;
    for (i = 0; i < TITLE_LINE2_LEN; i++) {
        set_bkg_tiles(start_col + i, 6, 1, 1, &title_line2[i]);
    }

    // Draw "DX" centered on row 8 (with dash decoration on each side)
    start_col = (20 - TITLE_LINE3_LEN) / 2;
    // Decorative dashes
    blank = TL_DASH;
    set_bkg_tiles(start_col - 2, 8, 1, 1, &blank);
    for (i = 0; i < TITLE_LINE3_LEN; i++) {
        set_bkg_tiles(start_col + i, 8, 1, 1, &title_line3[i]);
    }
    set_bkg_tiles(start_col + TITLE_LINE3_LEN + 1, 8, 1, 1, &blank);

    // Draw "PRESS START" centered on row 13
    start_col = (20 - PRESS_START_LEN) / 2;
    for (i = 0; i < PRESS_START_LEN; i++) {
        set_bkg_tiles(start_col + i, 13, 1, 1, &press_start[i]);
    }

    blink_timer = 0;
    blink_visible = 1;

    // Reset scroll
    SCX_REG = 0;
    SCY_REG = 0;

    // Hide window during title
    HIDE_WIN;

    // Show BG, hide sprites on title screen
    SHOW_BKG;
    HIDE_SPRITES;
    DISPLAY_ON;
}

uint8_t title_update(void) {
    uint8_t keys;
    uint8_t i;
    uint8_t start_col;
    uint8_t blank;

    keys = joypad();

    // Blink "PRESS START" every 30 frames
    blink_timer++;
    if (blink_timer >= 30) {
        blink_timer = 0;
        blink_visible ^= 1;

        start_col = (20 - PRESS_START_LEN) / 2;
        if (blink_visible) {
            for (i = 0; i < PRESS_START_LEN; i++) {
                set_bkg_tiles(start_col + i, 13, 1, 1, &press_start[i]);
            }
        } else {
            blank = TL_SPC;
            for (i = 0; i < PRESS_START_LEN; i++) {
                set_bkg_tiles(start_col + i, 13, 1, 1, &blank);
            }
        }
    }

    // Check START button
    if (keys & J_START) {
        return 1;
    }

    return 0;
}

void title_cleanup(void) {
    // Nothing to do - game_init will reinitialize everything
}
