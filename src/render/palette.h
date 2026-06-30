// CGB palette helpers — load 4-color palettes into the 8 BG and 8 OBJ slots.
#ifndef QUINTRA_RENDER_PALETTE_H
#define QUINTRA_RENDER_PALETTE_H

#include "core/types.h"

// Pack 5-bit r/g/b channels into BGR555 word (CGB native).
#define BGR555(r,g,b)  ((u16)((((b) & 0x1F) << 10) | (((g) & 0x1F) << 5) | ((r) & 0x1F)))

// Load 4-color palette into BG palette slot 0..7
void palette_bg_load(u8 slot, const u16 *colors);

// Load 4-color palette into OBJ palette slot 0..7
void palette_obj_load(u8 slot, const u16 *colors);

// Load N consecutive BG palettes starting at slot
void palette_bg_load_n(u8 first_slot, u8 n, const u16 *colors);

#endif
