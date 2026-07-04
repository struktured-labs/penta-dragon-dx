// INVENTORY / STATS pause screen. Opened with START from a room; shows the
// hero's class, live stats, held weapon + signature, coins, and run depth.
// Returns to the room via a resume flag so the room is NOT regenerated.

#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/console.h>
#include <gbdk/font.h>
#include <stdio.h>

#include "audio/sfx.h"
#include "core/types.h"
#include "game/inventory.h"
#include "game/player.h"
#include "game/room.h"
#include "game/run_state.h"
#include "render/palette.h"
#include "content.h"

static const u16 inv_palette[4] = {
    BGR555( 1,  2,  6),    // 0: deep blue
    BGR555( 8, 10, 20),    // 1: slate
    BGR555(20, 20, 28),    // 2: light
    BGR555(31, 31, 31),    // 3: white
};

static const char *class_name(u8 id) {
    if (id < N_CLASSES) return classes[id].name;
    return "?";
}

// items[] is keyed by array position but item.id != index beyond the 5
// starters — resolve the real entry by id (small table, linear scan is fine).
static const char *item_name_by_id(u16 id) {
    u8 i;
    for (i = 0; i < N_ITEMS; ++i) {
        if (items[i].id == id) return items[i].name;
    }
    return "-";
}

void inventory_enter(void) {
    DISPLAY_OFF;
    HIDE_SPRITES;
    HIDE_WIN;
    palette_bg_load(0, inv_palette);
    palette_bg_load(7, inv_palette);

    font_init();
    { font_t f = font_load(font_min); font_set(f); }
    cls();

    gotoxy(5, 0);  printf("- PACK -");
    gotoxy(1, 2);  printf("%s", class_name(player.class_id));
    gotoxy(11, 2); printf("stage %u", (u16)(run_state.bosses_beaten + 1));

    gotoxy(1, 4);  printf("HP %u/%u", (u16)player.hp, (u16)player.hp_max);
    gotoxy(11, 4); printf("MP %u/%u", (u16)player.mp, (u16)player.mp_max);
    gotoxy(1, 6);  printf("ATK %u", (u16)player.atk);
    gotoxy(8, 6);  printf("DEF %u", (u16)player.def);
    gotoxy(1, 8);  printf("SPD %u", (u16)player.spd);
    gotoxy(8, 8);  printf("LCK %u", (u16)player.lck);

    gotoxy(1, 11); printf("WPN A:");
    printf("%s", item_name_by_id(player.starter_weapon));
    gotoxy(1, 12); printf("SIG B:");
    printf("%s", item_name_by_id(player.active_item));

    gotoxy(1, 14); printf("coins %u", (u16)player.coins);
    gotoxy(1, 15); printf("bosses %u/%u", (u16)run_state.bosses_beaten, (u16)BOSSES_TO_WIN);
    gotoxy(1, 16); printf("kills %u", (u16)run_state.enemies_killed);

    gotoxy(2, 17); printf("START/B = resume");

    SHOW_BKG;
    DISPLAY_ON;
}

void inventory_exit(void) {}

screen_id_t inventory_tick(u8 keys, u8 pressed) {
    keys;
    if (pressed & (J_START | J_B)) {
        sfx_play(SFX_COIN);
        room_request_resume();
        return SCREEN_ROOM;
    }
    return SCREEN_SELF;
}

void inventory_draw(void) {}
