#ifndef __DATA_BANK2_H__
#define __DATA_BANK2_H__

#include <gb/gb.h>
#include <stdint.h>

// Bank reference for BG tile data in ROM bank 2
BANKREF_EXTERN(bg_tiles_bank)

// BG gameplay tile data (defined in data_bank2.c, ROM bank 2)
extern const unsigned char BG_GAMEPLAY_TILES[];
#define BG_GAMEPLAY_TILES_TILE_COUNT 256

// Level data constants
#define LEVEL1_NUM_COLUMNS 154

// Banked level data accessors
extern uint8_t banked_get_tile(uint16_t col, uint8_t row) __banked;
extern void banked_get_column(uint8_t *tiles, uint16_t col_idx) __banked;

#endif /* __DATA_BANK2_H__ */
