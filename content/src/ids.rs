//! Named ID constants for content cross-references. Keeps the actual
//! type definitions readable.

use quintra_content::{
    BiomeId, BossId, ClassId, DropTableId, EnemyId, ItemId, MusicRef,
    PaletteRef, PerkId, RoomTemplateId, SpriteRef, TilemapId, TilesetRef,
};

// ----- Classes
pub const CLASS_WOLFKIN: ClassId = ClassId::new(0);
pub const CLASS_SAURAN:  ClassId = ClassId::new(1);
pub const CLASS_CORVIN:  ClassId = ClassId::new(2);
pub const CLASS_PICSEAN: ClassId = ClassId::new(3);
pub const CLASS_VESPINE: ClassId = ClassId::new(4);

// ----- Items (weapons 0-9, actives 10-19, passives 20+)
pub const ITEM_CLAW_COMBO:   ItemId = ItemId::new(0);
pub const ITEM_TAIL_SPIKE:   ItemId = ItemId::new(1);
pub const ITEM_FEATHER_SHURI:ItemId = ItemId::new(2);
pub const ITEM_BUBBLE_BOLT:  ItemId = ItemId::new(3);
pub const ITEM_STINGER:      ItemId = ItemId::new(4);

pub const ITEM_HOWL:         ItemId = ItemId::new(10);
pub const ITEM_STONESKIN:    ItemId = ItemId::new(11);
pub const ITEM_MURDER:       ItemId = ItemId::new(12);
pub const ITEM_TIDAL_WAVE:   ItemId = ItemId::new(13);
pub const ITEM_SWARM:        ItemId = ItemId::new(14);

pub const ITEM_IRON_HEART:   ItemId = ItemId::new(20);   // +2 HP
pub const ITEM_SPEED_RING:   ItemId = ItemId::new(21);   // +1 SPD
pub const ITEM_POWER_STONE:  ItemId = ItemId::new(22);   // +1 ATK
pub const ITEM_TOUGH_SKIN:   ItemId = ItemId::new(23);   // +1 DEF
pub const ITEM_LUCKY_COIN:   ItemId = ItemId::new(24);   // +2 LCK

// ----- Enemies
pub const ENEMY_BLUE_CRAWLER:    EnemyId = EnemyId::new(0);
pub const ENEMY_STONE_SENTINEL:  EnemyId = EnemyId::new(1);    // Crystal Caverns boss
pub const ENEMY_HORNET:          EnemyId = EnemyId::new(2);    // fast flyer
pub const ENEMY_SKELETON:        EnemyId = EnemyId::new(3);    // chaser
pub const ENEMY_ORC:             EnemyId = EnemyId::new(4);    // tank

// ----- Biomes
pub const BIOME_CRYSTAL_CAVERNS: BiomeId = BiomeId::new(0);

// ----- Bosses (placeholder — boss data currently lives in enemies table)
pub const BOSS_NONE:             BossId = BossId::new(0);
pub const BOSS_STONE_SENTINEL:   BossId = BossId::new(1);

// ----- Rooms
pub const ROOM_SMALL_EMPTY: RoomTemplateId = RoomTemplateId::new(0);

// ----- Drop tables (placeholder slot 0 = small-coin)
pub const DROP_SMALL_COIN: DropTableId = DropTableId::new(0);

// ----- Perks (engine-recognized; runtime hooks per perk-id)
pub const PERK_NONE:                PerkId = PerkId::new(0);
pub const PERK_MOVE_SPEED_PLUS_20:  PerkId = PerkId::new(1);  // Wolfkin
pub const PERK_HP_PLUS_2_SLOW_REGEN: PerkId = PerkId::new(2); // Sauran
pub const PERK_SEE_HP_REVEAL:       PerkId = PerkId::new(3);  // Corvin
pub const PERK_MP_REGEN_SWIM:       PerkId = PerkId::new(4);  // Picsean
pub const PERK_POISON_SYNERGY:      PerkId = PerkId::new(5);  // Vespine

// ----- Palettes / sprites / tilesets / music (engine-side index)
pub const OBJ_PAL_WOLFKIN:    PaletteRef = PaletteRef::new(1);
pub const OBJ_PAL_CRAWLER:    PaletteRef = PaletteRef::new(2);
pub const OBJ_PAL_ITEM_GOLD:  PaletteRef = PaletteRef::new(3);
pub const OBJ_PAL_SAURAN:     PaletteRef = PaletteRef::new(1);    // reuses pal 1 (green tint at runtime)
pub const OBJ_PAL_CORVIN:     PaletteRef = PaletteRef::new(1);
pub const OBJ_PAL_PICSEAN:    PaletteRef = PaletteRef::new(1);
pub const OBJ_PAL_VESPINE:    PaletteRef = PaletteRef::new(1);
pub const BG_PAL_CAVERN_BASE: PaletteRef = PaletteRef::new(0);
pub const BG_PAL_CAVERN_DEC:  PaletteRef = PaletteRef::new(1);
pub const BG_PAL_CAVERN_ALT:  PaletteRef = PaletteRef::new(2);
pub const BG_PAL_CAVERN_HI:   PaletteRef = PaletteRef::new(3);

pub const SPRITE_WOLFKIN:     SpriteRef = SpriteRef::new(0);
pub const SPRITE_CRAWLER:     SpriteRef = SpriteRef::new(1);
pub const SPRITE_SENTINEL:    SpriteRef = SpriteRef::new(4);
pub const SPRITE_ITEM_CLAW:   SpriteRef = SpriteRef::new(2);
pub const SPRITE_ITEM_HOWL:   SpriteRef = SpriteRef::new(3);

// OBJ palette index for Stone Sentinel (loaded at room enter)
pub const OBJ_PAL_SENTINEL:   PaletteRef = PaletteRef::new(6);

pub const TILESET_CAVERN:     TilesetRef = TilesetRef::new(0);
pub const TILEMAP_SMALL_EMPTY: TilemapId = TilemapId::new(0);
pub const MUSIC_CAVERN:       MusicRef  = MusicRef::new(0);
