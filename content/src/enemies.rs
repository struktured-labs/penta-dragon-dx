//! Enemy roster. Phase 2: 1 enemy (Blue Crawler — slow walker, fire-weak).

use quintra_content::{AiScriptId, Enemy, EnemyStats, ProjectileKind, Registry, ShotPattern};

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

pub const STONE_SENTINEL: Enemy = Enemy {
    id:         ENEMY_STONE_SENTINEL,
    name:       "S.Sentinel",
    sprite_set: SPRITE_SENTINEL,
    palette:    OBJ_PAL_SENTINEL,
    stats: EnemyStats {
        hp:       50,
        damage:   2,
        speed:    32,
        score:    200,
        weakness: 0x04,   // Lightning
        poise:    8,
    },
    ai_script:  AiScriptId::Walker,
    drop_table: DROP_SMALL_COIN,
    biomes:     &[BIOME_CRYSTAL_CAVERNS],
};

pub const HORNET: Enemy = Enemy {
    id:         ENEMY_HORNET,
    name:       "Hornet",
    sprite_set: SPRITE_CRAWLER,
    palette:    OBJ_PAL_CRAWLER,
    stats: EnemyStats { hp: 2, damage: 1, speed: 96, score: 15, weakness: 0x02, poise: 0 },
    ai_script:  AiScriptId::Chaser,
    drop_table: DROP_SMALL_COIN,
    biomes:     &[BIOME_CRYSTAL_CAVERNS],
};

pub const SKELETON: Enemy = Enemy {
    id:         ENEMY_SKELETON,
    name:       "Skeleton",
    sprite_set: SPRITE_CRAWLER,
    palette:    OBJ_PAL_CRAWLER,
    stats: EnemyStats { hp: 5, damage: 1, speed: 64, score: 20, weakness: 0x08, poise: 1 },
    ai_script:  AiScriptId::Chaser,
    drop_table: DROP_SMALL_COIN,
    biomes:     &[BIOME_CRYSTAL_CAVERNS],
};

pub const ORC: Enemy = Enemy {
    id:         ENEMY_ORC,
    name:       "Orc",
    sprite_set: SPRITE_CRAWLER,
    palette:    OBJ_PAL_CRAWLER,
    stats: EnemyStats { hp: 10, damage: 2, speed: 48, score: 40, weakness: 0x11, poise: 3 },  // fire + poison
    ai_script:  AiScriptId::Charger { telegraph_ticks: 30, charge_speed: 96 },
    drop_table: DROP_SMALL_COIN,
    biomes:     &[BIOME_CRYSTAL_CAVERNS],
};

pub const WISP: Enemy = Enemy {
    id:         ENEMY_WISP,
    name:       "Wisp",
    sprite_set: SPRITE_CRAWLER,
    palette:    OBJ_PAL_CRAWLER,
    stats: EnemyStats { hp: 2, damage: 1, speed: 32, score: 25, weakness: 0x04, poise: 0 },
    ai_script:  AiScriptId::Shooter {
        fire_rate: 90,
        projectile: ProjectileKind::Bullet,
        pattern: ShotPattern::Single,
    },
    drop_table: DROP_SMALL_COIN,
    biomes:     &[BIOME_CRYSTAL_CAVERNS],
};

pub fn register(r: &mut Registry) {
    r.add_enemy(BLUE_CRAWLER.clone());
    r.add_enemy(STONE_SENTINEL.clone());
    r.add_enemy(HORNET.clone());
    r.add_enemy(SKELETON.clone());
    r.add_enemy(ORC.clone());
    r.add_enemy(WISP.clone());
}
