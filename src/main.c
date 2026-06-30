// Quintra — Phase 2 bootstrap
// Boots in CGB mode, references generated content to prove the Rust→C
// codegen seam works end-to-end. Real screen state machine arrives in Phase 3.

#include <gb/gb.h>
#include <gb/cgb.h>

#include "core/types.h"
#include "content.h"   // generated umbrella

// Sanity refs — keeps SDCC from dead-stripping the generated tables and
// lets a save-state inspector verify the content reached the ROM.
const u8 quintra_n_classes = N_CLASSES;
const u8 quintra_n_items   = N_ITEMS;
const u8 quintra_n_enemies = N_ENEMIES;
const u8 quintra_n_biomes  = N_BIOMES;
const u8 quintra_n_rooms   = N_ROOM_TEMPLATES;

// Pack RGB555 -> BGR555 word (CGB native)
#define MK_BGR(r,g,b)  ((u16)((((b) & 0x1F) << 10) | (((g) & 0x1F) << 5) | ((r) & 0x1F)))

// Phase 2 placeholder palette — deep purple-blue, "title vibe"
static const u16 boot_bg_pal[4] = {
    MK_BGR( 0,  0,  3),    // 0 — near-black blue
    MK_BGR( 4,  2, 12),    // 1 — deep indigo
    MK_BGR(14,  6, 20),    // 2 — magenta-blue
    MK_BGR(28, 20, 31),    // 3 — pale lilac (highlight)
};

static void load_bg_palette_0(void) {
    rBCPS = 0x80;  // auto-increment, palette 0 / color 0
    rBCPD = boot_bg_pal[0] & 0xFF; rBCPD = boot_bg_pal[0] >> 8;
    rBCPD = boot_bg_pal[1] & 0xFF; rBCPD = boot_bg_pal[1] >> 8;
    rBCPD = boot_bg_pal[2] & 0xFF; rBCPD = boot_bg_pal[2] >> 8;
    rBCPD = boot_bg_pal[3] & 0xFF; rBCPD = boot_bg_pal[3] >> 8;
}

// 16-byte gradient tile (8x8, 2bpp)
static const u8 gradient_tile[16] = {
    0x00, 0x00,
    0xFF, 0x00,
    0xFF, 0x00,
    0xFF, 0xFF,
    0xFF, 0xFF,
    0xFF, 0x00,
    0xFF, 0x00,
    0x00, 0x00,
};

void main(void) {
    DISPLAY_OFF;

    load_bg_palette_0();

    // Load gradient tile to VRAM index 0
    set_bkg_data(0, 1, gradient_tile);

    // Fill BG tilemap with tile 0
    {
        u8 fill[20];
        u8 y;
        for (y = 0; y < 20; ++y) fill[y] = 0;
        for (y = 0; y < 18; ++y) {
            set_bkg_tiles(0, y, 20, 1, fill);
        }
    }

    SHOW_BKG;
    DISPLAY_ON;

    for (;;) {
        wait_vbl_done();
    }
}
