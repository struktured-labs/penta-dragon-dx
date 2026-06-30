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

pub fn register(r: &mut Registry) {
    r.add_item(CLAW_COMBO.clone());
    r.add_item(HOWL.clone());
}
