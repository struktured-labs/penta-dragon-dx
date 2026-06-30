//! Quintra game content — hand-authored entries assembled into a Registry
//! at codegen time. The build's source of truth for all classes, items,
//! enemies, biomes, and room templates.
//!
//! Add a new entry by:
//!   1. Defining the `Class` / `Item` / `Enemy` / `Biome` / `RoomTemplate`
//!      const in the corresponding module
//!   2. Adding it to that module's `register(reg)` function
//!   3. `cargo run -p quintra-codegen` — validation runs first

#![forbid(unsafe_code)]

pub mod ids;
pub mod classes;
pub mod items;
pub mod enemies;
pub mod biomes;
pub mod rooms;

use quintra_content::Registry;

pub fn registry() -> Registry {
    let mut r = Registry::new();
    items::register(&mut r);          // items first — classes reference items
    classes::register(&mut r);
    rooms::register(&mut r);          // rooms before biomes (biomes reference rooms)
    enemies::register(&mut r);        // enemies before biomes
    biomes::register(&mut r);
    r
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_validates() {
        let r = registry();
        if let Err(errs) = r.validate() {
            panic!("content validation failed:\n  {}", errs.join("\n  "));
        }
    }

    #[test]
    fn registry_counts() {
        let r = registry();
        assert_eq!(r.n_classes(),        5);   // Wolfkin/Sauran/Corvin/Picsean/Vespine
        assert_eq!(r.n_items(),         15);   // 5 weapons + 5 actives + 5 passives
        assert_eq!(r.n_enemies(),        5);   // Crawler+Sentinel+Hornet+Skeleton+Orc
        assert_eq!(r.n_biomes(),         1);
        assert_eq!(r.n_room_templates(), 1);
    }
}
