#ifndef __HUD_H__
#define __HUD_H__

#include "types.h"

// Initialize the HUD (Window layer at bottom of screen)
void hud_init(void);

// Update the HUD display each frame
void hud_update(void);

// Show GAME OVER text on HUD
void hud_game_over(void);

// Show VICTORY text on HUD
void hud_victory(void);

#endif /* __HUD_H__ */
