// TITLE screen — "QUINTRA" + "PRESS START". Pulses palette so the screen
// feels alive while waiting on player input.

#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/console.h>
#include <gbdk/font.h>
#include <stdio.h>

#include "core/types.h"
#include "game/loop.h"
#include "game/title.h"
#include "render/palette.h"

static u8  pulse_phase;
static u16 last_palette_color2;

// "Title vibe" palette: deep purple background, lilac highlight, white text.
// Color 0: background (deep indigo)
// Color 1: shadow / mid (purple)
// Color 2: pulsing accent (cycles between magenta/cyan)
// Color 3: text (near-white)
static const u16 title_palette_steady[4] = {
    BGR555( 1,  0,  5),    // 0: deep indigo
    BGR555( 6,  2, 14),    // 1: purple
    BGR555(20,  8, 26),    // 2: magenta-pink (starting)
    BGR555(30, 30, 31),    // 3: near-white
};

void title_enter(void) {
    DISPLAY_OFF;

    palette_bg_load(0, title_palette_steady);
    // Mirror to palette 7 so font_init's choice of palette doesn't surprise us
    palette_bg_load(7, title_palette_steady);

    font_init();
    {
        font_t f = font_load(font_min);   // tiny font into VRAM
        font_set(f);
    }

    // Clear screen (font_set may leave junk)
    cls();

    // Layout: 20 cols × 18 rows. Center "QUINTRA" (7 chars) at col 6.
    gotoxy(6, 4);
    printf("QUINTRA");
    gotoxy(5, 6);
    printf("THE  ROGUELIKE");
    gotoxy(4, 12);
    printf("PRESS  START");
    gotoxy(3, 16);
    printf("v0.3  phase 3");

    pulse_phase         = 0;
    last_palette_color2 = title_palette_steady[2];

    SHOW_BKG;
    DISPLAY_ON;
}

void title_exit(void) {
    // No-op for now.
}

screen_id_t title_tick(u8 keys, u8 pressed) {
    keys;
    if (pressed & J_START) {
        return SCREEN_SCRATCH;   // Phase 3 destination; Phase 4 will route to CLASS_SELECT
    }
    return SCREEN_SELF;
}

void title_draw(void) {
    // Pulse color index 2 — cycles through a magenta/cyan ramp every ~90 frames.
    // Triangle wave: 0..45 magenta-ish, 45..89 cyan-ish.
    pulse_phase = (u8)(pulse_phase + 1);
    if (pulse_phase >= 90) pulse_phase = 0;

    {
        u8  phase    = pulse_phase < 45 ? pulse_phase : (u8)(89 - pulse_phase);
        u8  r        = (u8)(20 - (phase >> 1));     // 20 → ~0
        u8  g        = (u8)(4  + (phase >> 1));     // 4 → ~26
        u8  b        = (u8)(26 - (phase >> 2));     // 26 → 15
        u16 c2       = BGR555(r, g, b);
        u16 pal[4] = {
            title_palette_steady[0],
            title_palette_steady[1],
            c2,
            title_palette_steady[3],
        };
        palette_bg_load(0, pal);
        palette_bg_load(7, pal);
        last_palette_color2 = c2;
    }
}
