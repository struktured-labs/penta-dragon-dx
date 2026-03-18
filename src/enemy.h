#ifndef __ENEMY_H__
#define __ENEMY_H__

#include "types.h"

#define ENEMY_NONE      0
#define ENEMY_HORNET    1
#define ENEMY_CROW      2
#define ENEMY_ORC       3
#define ENEMY_HUMANOID  4
#define ENEMY_CATFISH   5
#define ENEMY_DRAGONFLY 6  // Fast hornet variant
#define ENEMY_SOLDIER   7  // Fast humanoid variant

typedef struct {
    uint8_t x;
    uint8_t y;
    int8_t  dx;
    int8_t  dy;
    uint8_t type;
    uint8_t hp;
    uint8_t frame;
    uint8_t anim_tick;
    uint8_t shoot_cd;
    uint8_t tile_base;
    uint8_t palette;
    uint8_t ai_state;
    int16_t ai_timer;
    uint8_t hit_flash;  // Frames of hit flash remaining
} Enemy;

extern Enemy enemies[MAX_ENEMIES];
extern uint8_t enemy_count;

void enemy_init(void);
void enemy_load_tiles(void);
void enemy_spawn(uint8_t type, uint8_t x, uint8_t y);
void enemy_update(void);
void enemy_draw(void);
uint8_t enemy_check_player_hit(uint8_t px, uint8_t py);

#endif /* __ENEMY_H__ */
