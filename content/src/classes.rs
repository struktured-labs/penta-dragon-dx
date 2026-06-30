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

pub const SAURAN: Class = Class {
    id:            CLASS_SAURAN,
    name:          "Sauran",
    form_theme:    FormTheme::Sauran,
    palette:       OBJ_PAL_SAURAN,
    sprite_set:    SPRITE_WOLFKIN,
    starter_weapon: ITEM_TAIL_SPIKE,
    signature_active: ITEM_STONESKIN,
    passive_perk:  PERK_HP_PLUS_2_SLOW_REGEN,
    base_stats: BaseStats { hp_max: 12, mp_max: 3, atk: 2, def: 3, spd: 4 },
};

pub const CORVIN: Class = Class {
    id:            CLASS_CORVIN,
    name:          "Corvin",
    form_theme:    FormTheme::Corvin,
    palette:       OBJ_PAL_CORVIN,
    sprite_set:    SPRITE_WOLFKIN,
    starter_weapon: ITEM_FEATHER_SHURI,
    signature_active: ITEM_MURDER,
    passive_perk:  PERK_SEE_HP_REVEAL,
    base_stats: BaseStats { hp_max: 6, mp_max: 8, atk: 2, def: 0, spd: 5 },
};

pub const PICSEAN: Class = Class {
    id:            CLASS_PICSEAN,
    name:          "Picsean",
    form_theme:    FormTheme::Picsean,
    palette:       OBJ_PAL_PICSEAN,
    sprite_set:    SPRITE_WOLFKIN,
    starter_weapon: ITEM_BUBBLE_BOLT,
    signature_active: ITEM_TIDAL_WAVE,
    passive_perk:  PERK_MP_REGEN_SWIM,
    base_stats: BaseStats { hp_max: 6, mp_max: 10, atk: 1, def: 1, spd: 5 },
};

pub const VESPINE: Class = Class {
    id:            CLASS_VESPINE,
    name:          "Vespine",
    form_theme:    FormTheme::Vespine,
    palette:       OBJ_PAL_VESPINE,
    sprite_set:    SPRITE_WOLFKIN,
    starter_weapon: ITEM_STINGER,
    signature_active: ITEM_SWARM,
    passive_perk:  PERK_POISON_SYNERGY,
    base_stats: BaseStats { hp_max: 7, mp_max: 5, atk: 3, def: 1, spd: 7 },
};

pub fn register(r: &mut Registry) {
    r.add_class(WOLFKIN.clone());
    r.add_class(SAURAN.clone());
    r.add_class(CORVIN.clone());
    r.add_class(PICSEAN.clone());
    r.add_class(VESPINE.clone());
}
