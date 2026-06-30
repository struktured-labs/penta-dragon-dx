//! Biome definitions. Phase 2: 1 biome (Crystal Caverns — starting zone).

use quintra_content::{Biome, Registry};

use crate::ids::*;

pub const CRYSTAL_CAVERNS: Biome = Biome {
    id:           BIOME_CRYSTAL_CAVERNS,
    name:         "Crystal Caverns",
    depth_range:  (0, 1),
    tileset:      TILESET_CAVERN,
    bg_palettes:  [BG_PAL_CAVERN_BASE, BG_PAL_CAVERN_DEC, BG_PAL_CAVERN_ALT, BG_PAL_CAVERN_HI],
    music_track:  MUSIC_CAVERN,
    enemy_pool:   &[(ENEMY_BLUE_CRAWLER, 100)],
    room_template_pool: &[ROOM_SMALL_EMPTY],
    min_rooms:    4,
    max_rooms:    8,
    has_shop:     true,
    has_altar:    false,
    boss:         BOSS_NONE,
};

pub fn register(r: &mut Registry) {
    r.add_biome(CRYSTAL_CAVERNS.clone());
}
