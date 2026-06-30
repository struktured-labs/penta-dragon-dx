//! Class definitions. Phase 2: 1 class (Wolfkin). Phases later add the
//! remaining four (Sauran, Corvin, Picsean, Vespine).

use quintra_content::{BaseStats, Class, FormTheme, Registry};

use crate::ids::*;

pub const WOLFKIN: Class = Class {
    id:            CLASS_WOLFKIN,
    name:          "Wolfkin",
    form_theme:    FormTheme::Wolfkin,
    palette:       OBJ_PAL_WOLFKIN,
    sprite_set:    SPRITE_WOLFKIN,
    starter_weapon: ITEM_CLAW_COMBO,
    signature_active: ITEM_HOWL,
    passive_perk:  PERK_MOVE_SPEED_PLUS_20,
    base_stats: BaseStats {
        hp_max: 8,   // 4 hearts
        mp_max: 4,
        atk:    2,
        def:    1,
        spd:    6,
    },
};

pub fn register(r: &mut Registry) {
    r.add_class(WOLFKIN.clone());
}
