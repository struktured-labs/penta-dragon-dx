// CLASS_SELECT — pick a class for this run.
// Phase 4: shows the 1 unlocked class (Wolfkin). Future content phases
// will fill out the roster.

#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/console.h>
#include <gbdk/font.h>
#include <stdio.h>

#include "audio/sfx.h"
#include "core/types.h"
#include "game/class_select.h"
#include "game/player.h"
#include "render/class_palettes.h"
#include "render/palette.h"
#include "render/tiles.h"
#include "content.h"

u8 class_select_cursor;

static const u16 cs_palette[4] = {
    BGR555( 0,  2,  6),    // 0: deep blue
    BGR555( 6,  8, 18),    // 1: blue
    BGR555(20, 16, 28),    // 2: lavender
    BGR555(30, 30, 31),    // 3: white
};

// Gold star cursor (reuses the bullet sprite tile)
static const u16 cursor_palette[4] = {
    BGR555( 0,  0,  0),
    BGR555(31, 24,  0),
    BGR555(28, 16,  0),
    BGR555(31, 31,  4),
};

// Live 16x16 preview of the highlighted class, in its own colors.
static void update_preview(void) {
    u8 base = (u8)(SPR_CLASS_BASE + (u8)(class_select_cursor * SPR_CLASS_STRIDE));
    u8 sx = 128, sy = 72;
    palette_obj_load(1, class_obj_palettes[class_select_cursor]);
    set_sprite_tile(0, base);
    set_sprite_tile(1, (u8)(base + 1));
    set_sprite_tile(2, (u8)(base + 2));
    set_sprite_tile(3, (u8)(base + 3));
    set_sprite_prop(0, 0x01); set_sprite_prop(1, 0x01);
    set_sprite_prop(2, 0x01); set_sprite_prop(3, 0x01);
    move_sprite(0, sx,         sy);
    move_sprite(1, (u8)(sx+8), sy);
    move_sprite(2, sx,         (u8)(sy+8));
    move_sprite(3, (u8)(sx+8), (u8)(sy+8));
    // Cursor star beside the highlighted class row
    set_sprite_tile(4, SPR_BULLET);
    set_sprite_prop(4, 0x02);
    move_sprite(4, 16, (u8)((3 + class_select_cursor) * 8 + 16));
}

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
    palette_obj_load(2, cursor_palette);

    font_init();
    { font_t f = font_load(font_min); font_set(f); }

    // Class metasprites + cursor star for the live preview
    tiles_load_all_class_sprites();
    tiles_load_fx_sprites();

    class_select_cursor = 0;
    render();
    update_preview();

    SHOW_SPRITES;
    SHOW_BKG;
    DISPLAY_ON;
}

void class_select_exit(void) {
    // Park preview + cursor sprites
    move_sprite(0, 0, 0); move_sprite(1, 0, 0);
    move_sprite(2, 0, 0); move_sprite(3, 0, 0);
    move_sprite(4, 0, 0);
}

screen_id_t class_select_tick(u8 keys, u8 pressed) {
    keys;
    if (pressed & J_UP) {
        if (class_select_cursor == 0)
            class_select_cursor = (u8)(N_CLASSES - 1);
        else
            class_select_cursor--;
        render();
        update_preview();
        sfx_play(SFX_HIT);          // soft move blip
    } else if (pressed & J_DOWN) {
        class_select_cursor++;
        if (class_select_cursor >= N_CLASSES) class_select_cursor = 0;
        render();
        update_preview();
        sfx_play(SFX_HIT);
    }

    if (pressed & J_A) {
        sfx_play(SFX_COIN);         // confirm
        player_init_from_class(class_select_cursor);
        return SCREEN_RUN_INIT;
    }
    if (pressed & J_B) {
        sfx_play(SFX_HURT);         // cancel
        return SCREEN_TITLE;
    }
    return SCREEN_SELF;
}

void class_select_draw(void) {
    // No per-frame redraw; render() runs on cursor change only.
}
