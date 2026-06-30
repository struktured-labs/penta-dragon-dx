//! Quintra content schema.
//!
//! Pure type definitions for all game content (classes, items, enemies,
//! biomes, room templates, AI scripts, item effects). The `content/`
//! directory in the project root authors instances of these types; the
//! `quintra-codegen` crate consumes those instances and emits matching
//! GBDK-compatible C tables under `src/generated/`.
//!
//! The runtime never sees Rust. Invalid content (orphan IDs, oversize
//! tables, palette overflow) fails at `cargo build` time, never at the
//! Game Boy.

#![forbid(unsafe_code)]
#![warn(missing_debug_implementations)]

pub mod refs;
pub mod stats;
pub mod effects;
pub mod class;
pub mod item;
pub mod enemy;
pub mod biome;
pub mod room;
pub mod registry;

pub use class::{Class, FormTheme};
pub use item::{Item, ItemKind, Rarity};
pub use enemy::{Enemy, EnemyStats, AiScriptId, ShotPattern};
pub use biome::Biome;
pub use room::{RoomTemplate, RoomSize, RoomKind, DoorMask, SpawnSlot, SpawnRole};
pub use effects::{Effect, Trigger, Status, Stat, ProjectileKind};
pub use stats::BaseStats;
pub use refs::{
    ClassId, ItemId, EnemyId, BiomeId, BossId, RoomTemplateId,
    PaletteRef, SpriteRef, TilesetRef, TilemapId, MusicRef, DropTableId,
    PerkId,
};
pub use registry::Registry;
