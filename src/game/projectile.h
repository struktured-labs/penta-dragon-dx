#ifndef QUINTRA_GAME_PROJECTILE_H
#define QUINTRA_GAME_PROJECTILE_H

#include "core/types.h"
#include "game/entity.h"

// Element bitmask applied to the next player shot(s).
extern u8 g_shot_element;

// Spawn a player projectile at player.x/y in (dx,dy) direction (8-dir deltas)
// with explicit damage + ProjectileKind (PROJ_* from generated enums.h) —
// kind shapes speed/range/pierce so each class weapon feels distinct.
u8   projectile_spawn_player(i8 dx, i8 dy, u8 damage, u8 kind);

// Enemy-owned projectile from (px,py) toward direction (dx,dy), 2 px/tick.
u8   projectile_spawn_enemy(i16 px, i16 py, i8 dx, i8 dy, u8 damage);

// Per-frame update (called by entity_update_all dispatch)
void projectile_update(entity_t *e, u8 idx);

#endif
