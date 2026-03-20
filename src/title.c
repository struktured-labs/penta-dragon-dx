#include "title.h"
#include "palettes.h"

// ============================================
// Title Screen — Faithful to original
// Two menu options: OPENING START / GAME START
// Cursor moves with D-pad, A/START confirms
// ============================================

#define TITLE_TILE_BASE  0xE0

// Letter indices
#define TL_A    0xE0
#define TL_C    0xE1
#define TL_D    0xE2
#define TL_E    0xE3
#define TL_G    0xE4
#define TL_I    0xE5
#define TL_N    0xE6
#define TL_O    0xE7
#define TL_P    0xE8
#define TL_R    0xE9
#define TL_S    0xEA
#define TL_T    0xEB
#define TL_X    0xEC
#define TL_M    0xED
#define TL_SPC  0xEE
#define TL_ARR  0xEF  // Arrow cursor ">"

// Custom 8x8 font tiles (2bpp, 16 bytes each)
static const unsigned char title_font[] = {
    // 0xE0: 'A'
    0x18, 0x18, 0x3C, 0x3C, 0x66, 0x66, 0x7E, 0x7E,
    0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x00, 0x00,
    // 0xE1: 'C'
    0x3C, 0x3C, 0x66, 0x66, 0x60, 0x60, 0x60, 0x60,
    0x60, 0x60, 0x66, 0x66, 0x3C, 0x3C, 0x00, 0x00,
    // 0xE2: 'D'
    0x7C, 0x7C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x66,
    0x66, 0x66, 0x66, 0x66, 0x7C, 0x7C, 0x00, 0x00,
    // 0xE3: 'E'
    0x7E, 0x7E, 0x60, 0x60, 0x60, 0x60, 0x7C, 0x7C,
    0x60, 0x60, 0x60, 0x60, 0x7E, 0x7E, 0x00, 0x00,
    // 0xE4: 'G'
    0x3C, 0x3C, 0x66, 0x66, 0x60, 0x60, 0x6E, 0x6E,
    0x66, 0x66, 0x66, 0x66, 0x3C, 0x3C, 0x00, 0x00,
    // 0xE5: 'I'
    0x7E, 0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18,
    0x18, 0x18, 0x18, 0x18, 0x7E, 0x7E, 0x00, 0x00,
    // 0xE6: 'N'
    0x66, 0x66, 0x76, 0x76, 0x7E, 0x7E, 0x6E, 0x6E,
    0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x00, 0x00,
    // 0xE7: 'O'
    0x3C, 0x3C, 0x66, 0x66, 0x66, 0x66, 0x66, 0x66,
    0x66, 0x66, 0x66, 0x66, 0x3C, 0x3C, 0x00, 0x00,
    // 0xE8: 'P'
    0x7C, 0x7C, 0x66, 0x66, 0x66, 0x66, 0x7C, 0x7C,
    0x60, 0x60, 0x60, 0x60, 0x60, 0x60, 0x00, 0x00,
    // 0xE9: 'R'
    0x7C, 0x7C, 0x66, 0x66, 0x66, 0x66, 0x7C, 0x7C,
    0x6C, 0x6C, 0x66, 0x66, 0x66, 0x66, 0x00, 0x00,
    // 0xEA: 'S'
    0x3C, 0x3C, 0x66, 0x66, 0x60, 0x60, 0x3C, 0x3C,
    0x06, 0x06, 0x66, 0x66, 0x3C, 0x3C, 0x00, 0x00,
    // 0xEB: 'T'
    0x7E, 0x7E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x18,
    0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00, 0x00,
    // 0xEC: 'X'
    0x66, 0x66, 0x66, 0x66, 0x3C, 0x3C, 0x18, 0x18,
    0x3C, 0x3C, 0x66, 0x66, 0x66, 0x66, 0x00, 0x00,
    // 0xED: 'M'
    0x63, 0x63, 0x77, 0x77, 0x7F, 0x7F, 0x6B, 0x6B,
    0x63, 0x63, 0x63, 0x63, 0x63, 0x63, 0x00, 0x00,
    // 0xEE: space (blank)
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    // 0xEF: arrow cursor ">"
    0x60, 0x60, 0x30, 0x30, 0x18, 0x18, 0x0C, 0x0C,
    0x18, 0x18, 0x30, 0x30, 0x60, 0x60, 0x00, 0x00,
};

#define TITLE_NUM_TILES  16

// Text strings
// "PENTA"
static const uint8_t title_penta[] = { TL_P, TL_E, TL_N, TL_T, TL_A };
// "DRAGON"
static const uint8_t title_dragon[] = { TL_D, TL_R, TL_A, TL_G, TL_O, TL_N };
// "DX"
static const uint8_t title_dx[] = { TL_D, TL_X };
// "OPENING START"
static const uint8_t menu_opening[] = {
    TL_O, TL_P, TL_E, TL_N, TL_I, TL_N, TL_G,
    TL_SPC,
    TL_S, TL_T, TL_A, TL_R, TL_T
};
#define MENU_OPENING_LEN 13
// "GAME   START"
static const uint8_t menu_game[] = {
    TL_G, TL_A, TL_M, TL_E, TL_SPC, TL_SPC, TL_SPC,
    TL_S, TL_T, TL_A, TL_R, TL_T
};
#define MENU_GAME_LEN 12
// "(C) PENTA DRAGON DX"
static const uint8_t copyright[] = {
    TL_SPC, TL_C, TL_SPC, TL_P, TL_E, TL_N, TL_T, TL_A,
    TL_SPC, TL_D, TL_R, TL_A, TL_G, TL_O, TL_N, TL_SPC,
    TL_D, TL_X
};
#define COPYRIGHT_LEN 18

static uint8_t blink_timer;
static uint8_t blink_visible;
static uint8_t menu_cursor;   // 0 = OPENING START, 1 = GAME START
static uint8_t prev_keys;

// Row positions
#define ROW_PENTA    3
#define ROW_DRAGON   5
#define ROW_DX       7
#define ROW_OPENING  11
#define ROW_GAME     13
#define ROW_COPY     16

static void draw_cursor(void) {
    uint8_t tile;
    // Clear both cursor positions
    tile = TL_SPC;
    set_bkg_tiles(2, ROW_OPENING, 1, 1, &tile);
    set_bkg_tiles(2, ROW_GAME, 1, 1, &tile);
    // Draw cursor at selected position
    tile = TL_ARR;
    if (menu_cursor == 0) {
        set_bkg_tiles(2, ROW_OPENING, 1, 1, &tile);
    } else {
        set_bkg_tiles(2, ROW_GAME, 1, 1, &tile);
    }
}

void title_init(void) {
    uint8_t row, col;
    uint8_t blank;
    uint8_t i;
    uint8_t start_col;
    uint8_t pal;

    DISPLAY_OFF;

    // Load title font tiles
    set_bkg_data(TITLE_TILE_BASE, TITLE_NUM_TILES, title_font);

    // Clear entire BG tilemap
    blank = TL_SPC;
    for (row = 0; row < 18; row++) {
        for (col = 0; col < 20; col++) {
            set_bkg_tiles(col, row, 1, 1, &blank);
        }
    }

    // Set palette attributes (palette 2 for text)
    VBK_REG = 1;
    pal = 2;
    for (row = 0; row < 18; row++) {
        for (col = 0; col < 20; col++) {
            set_bkg_tiles(col, row, 1, 1, &pal);
        }
    }
    VBK_REG = 0;

    // "PENTA" centered on row 3
    start_col = (20 - 5) / 2;
    for (i = 0; i < 5; i++) {
        set_bkg_tiles(start_col + i, ROW_PENTA, 1, 1, &title_penta[i]);
    }

    // "DRAGON" centered on row 5
    start_col = (20 - 6) / 2;
    for (i = 0; i < 6; i++) {
        set_bkg_tiles(start_col + i, ROW_DRAGON, 1, 1, &title_dragon[i]);
    }

    // "DX" centered on row 7
    start_col = (20 - 2) / 2;
    for (i = 0; i < 2; i++) {
        set_bkg_tiles(start_col + i, ROW_DX, 1, 1, &title_dx[i]);
    }

    // "OPENING START" at row 11, col 4
    for (i = 0; i < MENU_OPENING_LEN; i++) {
        set_bkg_tiles(4 + i, ROW_OPENING, 1, 1, &menu_opening[i]);
    }

    // "GAME   START" at row 13, col 4
    for (i = 0; i < MENU_GAME_LEN; i++) {
        set_bkg_tiles(4 + i, ROW_GAME, 1, 1, &menu_game[i]);
    }

    // Copyright at row 16
    start_col = (20 - COPYRIGHT_LEN) / 2;
    for (i = 0; i < COPYRIGHT_LEN; i++) {
        set_bkg_tiles(start_col + i, ROW_COPY, 1, 1, &copyright[i]);
    }

    // Initialize state
    menu_cursor = 0; // Default to OPENING START (matches original)
    blink_timer = 0;
    blink_visible = 1;
    prev_keys = 0xFF; // Prevent immediate selection on entry

    draw_cursor();

    // Match OG title screen scroll position
    SCX_REG = 8;
    SCY_REG = 8;

    // Hide window during title
    HIDE_WIN;

    SHOW_BKG;
    HIDE_SPRITES;
    DISPLAY_ON;
}

uint8_t title_update(void) {
    uint8_t keys = joypad();

    // Cursor blink
    blink_timer++;
    if (blink_timer >= 20) {
        blink_timer = 0;
        blink_visible ^= 1;
        if (blink_visible) {
            draw_cursor();
        } else {
            uint8_t blank = TL_SPC;
            set_bkg_tiles(2, ROW_OPENING, 1, 1, &blank);
            set_bkg_tiles(2, ROW_GAME, 1, 1, &blank);
        }
    }

    // Menu navigation (edge-triggered)
    if ((keys & J_UP) && !(prev_keys & J_UP)) {
        menu_cursor = 0;
        draw_cursor();
        blink_visible = 1;
        blink_timer = 0;
    }
    if ((keys & J_DOWN) && !(prev_keys & J_DOWN)) {
        menu_cursor = 1;
        draw_cursor();
        blink_visible = 1;
        blink_timer = 0;
    }

    // Confirm selection
    if (((keys & J_START) && !(prev_keys & J_START)) ||
        ((keys & J_A) && !(prev_keys & J_A))) {
        prev_keys = keys;
        if (menu_cursor == 0) {
            return 2; // OPENING START
        } else {
            return 1; // GAME START
        }
    }

    prev_keys = keys;
    return 0;
}

void title_cleanup(void) {
    // Nothing to do - game_init will reinitialize everything
}
