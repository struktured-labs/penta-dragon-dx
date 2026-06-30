//! Enemy roster. Phase 2: 1 enemy (Blue Crawler — slow walker, fire-weak).

use quintra_content::{AiScriptId, Enemy, EnemyStats, Registry};

use crate::ids::*;

pub const BLUE_CRAWLER: Enemy = Enemy {
    id:         ENEMY_BLUE_CRAWLER,
    name:       "B. Crawler",
    sprite_set: SPRITE_CRAWLER,
    palette:    OBJ_PAL_CRAWLER,
    stats: EnemyStats {
        hp:       3,
        damage:   1,
        speed:    64,     // 0.25 px/tick (fixed point)
        score:    10,
        weakness: 0x01,   // Fire bit
        poise:    0,
    },
    ai_script:  AiScriptId::Walker,
    drop_table: DROP_SMALL_COIN,
    biomes:     &[BIOME_CRYSTAL_CAVERNS],
};

pub fn register(r: &mut Registry) {
    r.add_enemy(BLUE_CRAWLER.clone());
}
