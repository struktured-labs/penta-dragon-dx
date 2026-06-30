#include <gb/gb.h>
#include <gb/cgb.h>

#include "render/palette.h"

static void load_to_pal(u8 ps_reg_select_lo, u8 slot, const u16 *colors) {
    // Auto-increment + start at (slot * 8) — each palette is 4 colors × 2 bytes
    if (ps_reg_select_lo == 0) {
        rBCPS = 0x80 | (u8)(slot << 3);
        rBCPD = (u8)(colors[0] & 0xFF); rBCPD = (u8)(colors[0] >> 8);
        rBCPD = (u8)(colors[1] & 0xFF); rBCPD = (u8)(colors[1] >> 8);
        rBCPD = (u8)(colors[2] & 0xFF); rBCPD = (u8)(colors[2] >> 8);
        rBCPD = (u8)(colors[3] & 0xFF); rBCPD = (u8)(colors[3] >> 8);
    } else {
        rOCPS = 0x80 | (u8)(slot << 3);
        rOCPD = (u8)(colors[0] & 0xFF); rOCPD = (u8)(colors[0] >> 8);
        rOCPD = (u8)(colors[1] & 0xFF); rOCPD = (u8)(colors[1] >> 8);
        rOCPD = (u8)(colors[2] & 0xFF); rOCPD = (u8)(colors[2] >> 8);
        rOCPD = (u8)(colors[3] & 0xFF); rOCPD = (u8)(colors[3] >> 8);
    }
}

void palette_bg_load(u8 slot, const u16 *colors) {
    load_to_pal(0, slot, colors);
}

void palette_obj_load(u8 slot, const u16 *colors) {
    load_to_pal(1, slot, colors);
}

void palette_bg_load_n(u8 first_slot, u8 n, const u16 *colors) {
    u8 i;
    for (i = 0; i < n; ++i) {
        palette_bg_load((u8)(first_slot + i), colors + (u16)(i * 4));
    }
}
