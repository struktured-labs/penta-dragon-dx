#include "itemmenu.h"
#include "enemy.h"
#include "boss.h"
#include "player.h"
#include "sound.h"
#include "music.h"
#include "hud.h"
#include <gb/gb.h>
#include <gb/cgb.h>

uint8_t item_counts[MAX_ITEM_TYPES];
uint8_t menu_open;
uint8_t menu_cursor;

// Menu uses the window layer overlay
// Window shows item list with cursor
// Layout (20 tiles wide):
//  Row 0: "== ITEMS =="
//  Row 1: "> FLASH  x3"
//  Row 2: "  POTION x1"
//  Row 3: "  SHIELD x0"
//  Row 4: "B:USE  A:CLOSE"

// Custom tile IDs for menu text (reuse HUD tile area 0xF0+)
// We'll write directly to window tilemap using tile IDs from
// the already-loaded BG tileset

void itemmenu_init(void) {
    uint8_t i;
    for (i = 0; i < MAX_ITEM_TYPES; i++) {
        item_counts[i] = 0;
    }
    // Start with 3 flash bombs
    item_counts[ITEM_FLASH_BOMB] = 3;
    item_counts[ITEM_POTION] = 1;

    menu_open = 0;
    menu_cursor = ITEM_FLASH_BOMB;
}

void itemmenu_open(void) {
    menu_open = 1;
    menu_cursor = ITEM_FLASH_BOMB;
    music_pause();
}

void itemmenu_close(void) {
    menu_open = 0;
    music_resume();
}

// Write a simple menu tile row to window layer
static void write_menu_row(uint8_t row, const uint8_t *tiles, uint8_t count) {
    set_win_tiles(0, row, count, 1, tiles);
}

void itemmenu_draw(void) {
    uint8_t row_buf[20];
    uint8_t i;
    uint8_t pal;

    if (!menu_open) return;

    // Fill menu background (using tile 0x00 = empty)
    for (i = 0; i < 20; i++) row_buf[i] = 0x00;

    // Move window to cover gameplay area
    move_win(7, 40);  // Show window from Y=40

    // Row 0: Header "ITEMS" (using floor tiles as visual separator)
    row_buf[0] = 0x14; // Solid block
    row_buf[1] = 0x14;
    row_buf[2] = 0x00;
    // "ITEMS" — we don't have alphabet tiles in gameplay VRAM
    // Use simple visual indicators instead
    row_buf[3] = 0x14;
    row_buf[4] = 0x14;
    row_buf[5] = 0x14;
    row_buf[6] = 0x14;
    row_buf[7] = 0x14;
    row_buf[8] = 0x00;
    row_buf[9] = 0x14;
    row_buf[10] = 0x14;
    write_menu_row(0, row_buf, 20);

    // Set window palette attributes
    VBK_REG = 1;
    for (i = 0; i < 20; i++) row_buf[i] = 0; // Palette 0
    write_menu_row(0, row_buf, 20);
    VBK_REG = 0;

    // Row 1-3: Item entries
    // Flash bomb
    for (i = 0; i < 20; i++) row_buf[i] = 0x00;
    row_buf[0] = (menu_cursor == ITEM_FLASH_BOMB) ? 0x05 : 0x00; // Cursor indicator
    row_buf[1] = 0x02; // Item icon (floor tile as placeholder)
    row_buf[2] = 0x03;
    row_buf[4] = 0x01; // "x"
    row_buf[5] = item_counts[ITEM_FLASH_BOMB]; // Count (as tile ID — shows as glyph)
    write_menu_row(1, row_buf, 20);

    // Potion
    for (i = 0; i < 20; i++) row_buf[i] = 0x00;
    row_buf[0] = (menu_cursor == ITEM_POTION) ? 0x05 : 0x00;
    row_buf[1] = 0x04;
    row_buf[2] = 0x03;
    row_buf[4] = 0x01;
    row_buf[5] = item_counts[ITEM_POTION];
    write_menu_row(2, row_buf, 20);

    // Shield
    for (i = 0; i < 20; i++) row_buf[i] = 0x00;
    row_buf[0] = (menu_cursor == ITEM_SHIELD) ? 0x05 : 0x00;
    row_buf[1] = 0x06;
    row_buf[2] = 0x03;
    row_buf[4] = 0x01;
    row_buf[5] = item_counts[ITEM_SHIELD];
    write_menu_row(3, row_buf, 20);

    // Row 4: separator
    for (i = 0; i < 20; i++) row_buf[i] = 0x14;
    write_menu_row(4, row_buf, 20);
}

uint8_t itemmenu_update(uint8_t keys, uint8_t prev_keys) {
    if (!menu_open) return 0;

    // Cursor movement (edge-triggered)
    if ((keys & J_DOWN) && !(prev_keys & J_DOWN)) {
        menu_cursor++;
        if (menu_cursor > ITEM_SHIELD) menu_cursor = ITEM_FLASH_BOMB;
        itemmenu_draw();
    }
    if ((keys & J_UP) && !(prev_keys & J_UP)) {
        if (menu_cursor <= ITEM_FLASH_BOMB)
            menu_cursor = ITEM_SHIELD;
        else
            menu_cursor--;
        itemmenu_draw();
    }

    // Use selected item (B button)
    if ((keys & J_B) && !(prev_keys & J_B)) {
        if (item_counts[menu_cursor] > 0) {
            item_counts[menu_cursor]--;

            switch (menu_cursor) {
                case ITEM_FLASH_BOMB:
                    // Clear all enemies on screen
                    enemy_init();
                    sound_enemy_hit();
                    break;
                case ITEM_POTION:
                    // Restore HP
                    player.hp = 255;
                    sound_pickup();
                    break;
                case ITEM_SHIELD:
                    // Temporary invulnerability
                    player.invuln = 180; // 3 seconds
                    sound_pickup();
                    break;
            }
            itemmenu_draw(); // Refresh counts
        }
    }

    // Close menu (A or START)
    if (((keys & J_A) && !(prev_keys & J_A)) ||
        ((keys & J_START) && !(prev_keys & J_START))) {
        itemmenu_close();
    }

    return 1; // Menu consumed input
}

void itemmenu_use_flash_bomb(void) {
    if (item_counts[ITEM_FLASH_BOMB] > 0) {
        item_counts[ITEM_FLASH_BOMB]--;
        enemy_init(); // Clear all enemies
        sound_enemy_hit();
        music_sfx_ch4(15);
    }
}

void itemmenu_add_item(uint8_t item_type) {
    if (item_type > 0 && item_type < MAX_ITEM_TYPES) {
        if (item_counts[item_type] < MAX_ITEM_COUNT) {
            item_counts[item_type]++;
            sound_pickup();
        }
    }
}
