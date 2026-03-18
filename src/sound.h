#ifndef __SOUND_H__
#define __SOUND_H__

#include <gb/gb.h>
#include <stdint.h>

// Initialize sound hardware (must be called once at startup)
void sound_init(void);

// Sound effects — each triggers immediately using hardware registers.
// Channel usage:
//   Channel 1 (square + sweep): shoot, player_hit
//   Channel 2 (square):         pickup arpeggio
//   Channel 4 (noise):          enemy_hit

// Short high-pitched sweep down (laser/shoot feel)
void sound_shoot(void);

// Short noise burst (impact/crunch)
void sound_enemy_hit(void);

// Descending tone (damage feedback)
void sound_player_hit(void);

// Ascending 3-note arpeggio on channel 2 (coin/item collect)
// Note: uses wait_vbl_done() internally for timing between notes
void sound_pickup(void);

// Low rumble warning sound when boss spawns
void sound_boss_warning(void);

// Call once per frame from the main loop to advance multi-frame
// sound effects (pickup arpeggio). Returns immediately if idle.
void sound_update(void);

#endif /* __SOUND_H__ */
