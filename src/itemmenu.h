#ifndef __ITEMMENU_H__
#define __ITEMMENU_H__

#include "types.h"

// Item inventory
#define ITEM_NONE       0
#define ITEM_FLASH_BOMB 1  // B button — clears screen of enemies
#define ITEM_POTION     2  // Restores HP
#define ITEM_SHIELD     3  // Temporary invulnerability
#define MAX_ITEM_TYPES  4
#define MAX_ITEM_COUNT  9  // Max of each item

// Inventory: count of each item type
extern uint8_t item_counts[MAX_ITEM_TYPES];

// Menu state
extern uint8_t menu_open;
extern uint8_t menu_cursor;

// Initialize inventory
void itemmenu_init(void);

// Open the item menu (called when START pressed during gameplay)
void itemmenu_open(void);

// Close the item menu
void itemmenu_close(void);

// Update menu (handle cursor movement and selection)
// Returns 1 if menu consumed the input (don't process gameplay)
uint8_t itemmenu_update(uint8_t keys, uint8_t prev_keys);

// Draw the menu overlay
void itemmenu_draw(void);

// Use flash bomb (B button during gameplay, no menu needed)
void itemmenu_use_flash_bomb(void);

// Add an item to inventory (called when picking up items in the level)
void itemmenu_add_item(uint8_t item_type);

#endif /* __ITEMMENU_H__ */
