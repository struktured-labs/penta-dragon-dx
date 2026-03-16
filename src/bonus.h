#ifndef __BONUS_H__
#define __BONUS_H__

#include "types.h"

// Bonus stage: vertical corridor shooter (jet form)
// Triggered between stages as a reward/break
// FFD0=1 in original, enemies descend from top

// Bonus stage state
extern uint8_t bonus_active;
extern uint16_t bonus_timer;

// Initialize bonus stage
void bonus_init(void);

// Update bonus stage logic (enemies descend from top, player shoots up)
// Returns 1 when bonus is complete
uint8_t bonus_update(uint8_t keys);

// Draw bonus stage elements
void bonus_draw(void);

// Clean up after bonus (restore normal gameplay)
void bonus_cleanup(void);

#endif /* __BONUS_H__ */
