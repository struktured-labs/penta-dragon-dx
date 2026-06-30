// CLASS_SELECT — pick a class for this run.
// Phase 4: shows the 1 unlocked class (Wolfkin). Future content phases
// will fill out the roster.

#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/console.h>
#include <gbdk/font.h>
#include <stdio.h>

#include "core/types.h"
#include "game/class_select.h"
#include "game/player.h"
#include "render/palette.h"
#include "content.h"

u8 class_select_cursor;

static const u16 cs_palette[4] = {
    BGR555( 0,  2,  6),    // 0: deep blue
    BGR555( 6,  8, 18),    // 1: blue
    BGR555(20, 16, 28),    // 2: lavender
    BGR555(30, 30, 31),    // 3: white
};

static void render(void) {
    cls();
    gotoxy(5, 1);  printf("CHOOSE  CLASS");

    {
        u8 i;
        for (i = 0; i < N_CLASSES; ++i) {
            const class_def_t *c = &classes[i];
            gotoxy(2, (u8)(3 + i));
            if (i == class_select_cursor) printf("> ");
            else                          printf("  ");
            printf("%s", c->name);
        }
    }

    {
        const class_def_t *c = &classes[class_select_cursor];
        gotoxy(1, 11); printf("HP %u  MP %u",
            (u16)c->base_stats.hp_max, (u16)c->base_stats.mp_max);
        gotoxy(1, 12); printf("AT %u  DF %u  SP %u",
            (u16)c->base_stats.atk, (u16)c->base_stats.def, (u16)c->base_stats.spd);
    }

    gotoxy(2, 16); printf("A=START  B=BACK");
}

void class_select_enter(void) {
    DISPLAY_OFF;
    palette_bg_load(0, cs_palette);
    palette_bg_load(7, cs_palette);

    font_init();
    { font_t f = font_load(font_min); font_set(f); }

    class_select_cursor = 0;
    render();

    HIDE_SPRITES;
    SHOW_BKG;
    DISPLAY_ON;
}

void class_select_exit(void) {}

screen_id_t class_select_tick(u8 keys, u8 pressed) {
    keys;
    if (pressed & J_UP) {
        if (class_select_cursor == 0)
            class_select_cursor = (u8)(N_CLASSES - 1);
        else
            class_select_cursor--;
        render();
    } else if (pressed & J_DOWN) {
        class_select_cursor++;
        if (class_select_cursor >= N_CLASSES) class_select_cursor = 0;
        render();
    }

    if (pressed & J_A) {
        player_init_from_class(class_select_cursor);
        return SCREEN_RUN_INIT;
    }
    if (pressed & J_B) {
        return SCREEN_TITLE;
    }
    return SCREEN_SELF;
}

void class_select_draw(void) {
    // No per-frame redraw; render() runs on cursor change only.
}
