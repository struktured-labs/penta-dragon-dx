//! Named ID constants for content cross-references. Keeps the actual
//! type definitions readable.

use quintra_content::{
    BiomeId, BossId, ClassId, DropTableId, EnemyId, ItemId, MusicRef,
    PaletteRef, PerkId, RoomTemplateId, SpriteRef, TilemapId, TilesetRef,
};

// ----- Classes
pub const CLASS_WOLFKIN: ClassId = ClassId::new(0);

// ----- Items
pub const ITEM_CLAW_COMBO: ItemId = ItemId::new(0);
pub const ITEM_HOWL:       ItemId = ItemId::new(1);

// ----- Enemies
pub const ENEMY_BLUE_CRAWLER: EnemyId = EnemyId::new(0);

// ----- Biomes
pub const BIOME_CRYSTAL_CAVERNS: BiomeId = BiomeId::new(0);

// ----- Bosses (placeholder)
pub const BOSS_NONE: BossId = BossId::new(0);

// ----- Rooms
pub const ROOM_SMALL_EMPTY: RoomTemplateId = RoomTemplateId::new(0);

// ----- Drop tables (placeholder slot 0 = small-coin)
pub const DROP_SMALL_COIN: DropTableId = DropTableId::new(0);

// ----- Perks
pub const PERK_NONE:                PerkId = PerkId::new(0);
pub const PERK_MOVE_SPEED_PLUS_20:  PerkId = PerkId::new(1);

// ----- Palettes / sprites / tilesets / music (engine-side index)
pub const OBJ_PAL_WOLFKIN:    PaletteRef = PaletteRef::new(1);
pub const OBJ_PAL_CRAWLER:    PaletteRef = PaletteRef::new(2);
pub const OBJ_PAL_ITEM_GOLD:  PaletteRef = PaletteRef::new(3);
pub const BG_PAL_CAVERN_BASE: PaletteRef = PaletteRef::new(0);
pub const BG_PAL_CAVERN_DEC:  PaletteRef = PaletteRef::new(1);
pub const BG_PAL_CAVERN_ALT:  PaletteRef = PaletteRef::new(2);
pub const BG_PAL_CAVERN_HI:   PaletteRef = PaletteRef::new(3);

pub const SPRITE_WOLFKIN:     SpriteRef = SpriteRef::new(0);
pub const SPRITE_CRAWLER:     SpriteRef = SpriteRef::new(1);
pub const SPRITE_ITEM_CLAW:   SpriteRef = SpriteRef::new(2);
pub const SPRITE_ITEM_HOWL:   SpriteRef = SpriteRef::new(3);

pub const TILESET_CAVERN:     TilesetRef = TilesetRef::new(0);
pub const TILEMAP_SMALL_EMPTY: TilemapId = TilemapId::new(0);
pub const MUSIC_CAVERN:       MusicRef  = MusicRef::new(0);
