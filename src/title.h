#ifndef __TITLE_H__
#define __TITLE_H__

#include "types.h"

// Initialize the title screen display
void title_init(void);

// Update title screen logic (check for START press)
// Returns 1 when player presses START (ready to play)
uint8_t title_update(void);

// Clean up title screen before transitioning to gameplay
void title_cleanup(void);

#endif /* __TITLE_H__ */
