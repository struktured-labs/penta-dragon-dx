#ifndef QUINTRA_GAME_ENEMY_AI_H
#define QUINTRA_GAME_ENEMY_AI_H

#include "core/types.h"
#include "game/entity.h"

// Spawn an enemy by content enemy_id_t at given tile coords.
u8   enemy_spawn(u8 enemy_content_id, u8 tile_x, u8 tile_y);

// Per-frame update (called by entity_update_all dispatch)
void enemy_update(entity_t *e, u8 idx);

// Move an enemy 1px by (dx,dy) if the target tile is walkable + in bounds.
// Returns 1 if it moved. Exposed for knockback in combat.
u8 enemy_try_step(entity_t *e, i8 dx, i8 dy);

#endif
