#pragma bank 2

#include <gb/gb.h>
#include <stdint.h>

// ============================================
// ROM Bank 2: BG gameplay tile data (4096 bytes)
// ============================================

BANKREF(bg_tiles_bank)

// 256 tiles x 16 bytes = 4096 bytes
#include "../assets/extracted/bg/include/bg_gameplay.h"

// Banked loader function — called via __banked trampoline from bank 0
// The __banked attribute means GBDK auto-switches to bank 2 on call
// and auto-restores the previous bank on return
void load_bg_tiles_banked(void) __banked {
    set_bkg_data(0, 255, BG_GAMEPLAY_TILES);
}

// Level data stays in bank 1 (banked function calls with parameters
// cause stack issues — keep frequently-accessed data in main bank)
