//! Item definitions. Phase 2: 2 items (Wolfkin's starter melee + active).

use quintra_content::{
    Effect, Item, ItemKind, ProjectileKind, Rarity, Registry, Stat, Status, Trigger,
};

use crate::ids::*;

pub const CLAW_COMBO: Item = Item {
    id:          ITEM_CLAW_COMBO,
    name:        "Claw Combo",
    description: "3-hit melee combo. Hold B to chain.",
    kind: ItemKind::Weapon {
        fire_rate:  12,    // ticks between shots
        damage:     2,
        projectile: ProjectileKind::Spike,
        mp_cost:    0,
    },
    icon_sprite: SPRITE_ITEM_CLAW,
    palette:     OBJ_PAL_ITEM_GOLD,
    rarity:      Rarity::Common,
    effects:     &[],
};

pub const HOWL: Item = Item {
    id:          ITEM_HOWL,
    name:        "Howl",
    description: "Stun all enemies in radius for 1 second.",
    kind: ItemKind::Active { cooldown_rooms: 2 },
    icon_sprite: SPRITE_ITEM_HOWL,
    palette:     OBJ_PAL_ITEM_GOLD,
    rarity:      Rarity::Rare,
    effects: &[
        Effect::OnRoomClear(Trigger::ApplyStatus {
            status: Status::Stunned,
            duration_ticks: 60,
        }),
        Effect::StatBoost { stat: Stat::Spd, delta: 0 },  // placeholder
    ],
};

// --- Other starter weapons (one per class)

pub const TAIL_SPIKE: Item = Item {
    id:          ITEM_TAIL_SPIKE,
    name:        "Tail Spike",
    description: "Short heavy strike. Bonus damage on hit.",
    kind: ItemKind::Weapon { fire_rate: 15, damage: 3, projectile: ProjectileKind::Spike, mp_cost: 0 },
    icon_sprite: SPRITE_ITEM_CLAW, palette: OBJ_PAL_ITEM_GOLD, rarity: Rarity::Common,
    effects: &[],
};

pub const FEATHER_SHURIKEN: Item = Item {
    id:          ITEM_FEATHER_SHURI,
    name:        "Featherbarb",
    description: "Ranged shuriken. Returns after hit.",
    kind: ItemKind::Weapon { fire_rate: 10, damage: 1, projectile: ProjectileKind::Shuriken, mp_cost: 0 },
    icon_sprite: SPRITE_ITEM_CLAW, palette: OBJ_PAL_ITEM_GOLD, rarity: Rarity::Common,
    effects: &[],
};

pub const BUBBLE_BOLT: Item = Item {
    id:          ITEM_BUBBLE_BOLT,
    name:        "BubbleBolt",
    description: "Slow piercing bubble.",
    kind: ItemKind::Weapon { fire_rate: 15, damage: 2, projectile: ProjectileKind::Bubble, mp_cost: 0 },
    icon_sprite: SPRITE_ITEM_CLAW, palette: OBJ_PAL_ITEM_GOLD, rarity: Rarity::Common,
    effects: &[],
};

pub const STINGER: Item = Item {
    id:          ITEM_STINGER,
    name:        "Stinger",
    description: "Fast strike. High critical chance.",
    kind: ItemKind::Weapon { fire_rate: 8, damage: 2, projectile: ProjectileKind::Spike, mp_cost: 0 },
    icon_sprite: SPRITE_ITEM_CLAW, palette: OBJ_PAL_ITEM_GOLD, rarity: Rarity::Common,
    effects: &[Effect::StatBoost { stat: Stat::Lck, delta: 3 }],
};

// --- Actives

pub const STONESKIN: Item = Item {
    id: ITEM_STONESKIN, name: "Stoneskin",
    description: "3 seconds of invulnerability.",
    kind: ItemKind::Active { cooldown_rooms: 2 },
    icon_sprite: SPRITE_ITEM_HOWL, palette: OBJ_PAL_ITEM_GOLD, rarity: Rarity::Rare,
    effects: &[],
};

pub const MURDER: Item = Item {
    id: ITEM_MURDER, name: "Murder",
    description: "Conjure 3 homing crow shards.",
    kind: ItemKind::Active { cooldown_rooms: 3 },
    icon_sprite: SPRITE_ITEM_HOWL, palette: OBJ_PAL_ITEM_GOLD, rarity: Rarity::Rare,
    effects: &[Effect::OnRoomClear(Trigger::SpawnProjectile { kind: ProjectileKind::Homing, count: 3 })],
};

pub const TIDAL_WAVE: Item = Item {
    id: ITEM_TIDAL_WAVE, name: "TidalWave",
    description: "Sweeping line attack.",
    kind: ItemKind::Active { cooldown_rooms: 2 },
    icon_sprite: SPRITE_ITEM_HOWL, palette: OBJ_PAL_ITEM_GOLD, rarity: Rarity::Rare,
    effects: &[],
};

pub const SWARM: Item = Item {
    id: ITEM_SWARM, name: "Swarm",
    description: "3 seconds of auto-aim drones.",
    kind: ItemKind::Active { cooldown_rooms: 3 },
    icon_sprite: SPRITE_ITEM_HOWL, palette: OBJ_PAL_ITEM_GOLD, rarity: Rarity::Rare,
    effects: &[],
};

// --- Passive stat boosts (dropped from enemies + shops)

pub const IRON_HEART: Item = Item {
    id: ITEM_IRON_HEART, name: "Iron Heart",
    description: "Permanent +2 max HP for this run.",
    kind: ItemKind::Passive,
    icon_sprite: SPRITE_ITEM_CLAW, palette: OBJ_PAL_ITEM_GOLD, rarity: Rarity::Uncommon,
    effects: &[Effect::StatBoost { stat: Stat::Hp, delta: 2 }],
};

pub const SPEED_RING: Item = Item {
    id: ITEM_SPEED_RING, name: "Speed Ring",
    description: "+1 SPD.",
    kind: ItemKind::Passive,
    icon_sprite: SPRITE_ITEM_CLAW, palette: OBJ_PAL_ITEM_GOLD, rarity: Rarity::Uncommon,
    effects: &[Effect::StatBoost { stat: Stat::Spd, delta: 1 }],
};

pub const POWER_STONE: Item = Item {
    id: ITEM_POWER_STONE, name: "PowerStone",
    description: "+1 ATK damage.",
    kind: ItemKind::Passive,
    icon_sprite: SPRITE_ITEM_CLAW, palette: OBJ_PAL_ITEM_GOLD, rarity: Rarity::Uncommon,
    effects: &[Effect::StatBoost { stat: Stat::Atk, delta: 1 }],
};

pub const TOUGH_SKIN: Item = Item {
    id: ITEM_TOUGH_SKIN, name: "Tough Skin",
    description: "+1 DEF — soaks incoming damage.",
    kind: ItemKind::Passive,
    icon_sprite: SPRITE_ITEM_CLAW, palette: OBJ_PAL_ITEM_GOLD, rarity: Rarity::Uncommon,
    effects: &[Effect::StatBoost { stat: Stat::Def, delta: 1 }],
};

pub const LUCKY_COIN: Item = Item {
    id: ITEM_LUCKY_COIN, name: "Lucky Coin",
    description: "+2 LCK. Better drops + crit chance.",
    kind: ItemKind::Passive,
    icon_sprite: SPRITE_ITEM_CLAW, palette: OBJ_PAL_ITEM_GOLD, rarity: Rarity::Rare,
    effects: &[Effect::StatBoost { stat: Stat::Lck, delta: 2 }],
};

pub fn register(r: &mut Registry) {
    r.add_item(CLAW_COMBO.clone());
    r.add_item(TAIL_SPIKE.clone());
    r.add_item(FEATHER_SHURIKEN.clone());
    r.add_item(BUBBLE_BOLT.clone());
    r.add_item(STINGER.clone());
    r.add_item(HOWL.clone());
    r.add_item(STONESKIN.clone());
    r.add_item(MURDER.clone());
    r.add_item(TIDAL_WAVE.clone());
    r.add_item(SWARM.clone());
    r.add_item(IRON_HEART.clone());
    r.add_item(SPEED_RING.clone());
    r.add_item(POWER_STONE.clone());
    r.add_item(TOUGH_SKIN.clone());
    r.add_item(LUCKY_COIN.clone());
}
