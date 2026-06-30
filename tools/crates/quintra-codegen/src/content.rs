//! Pull the hand-authored content crate's registry.

use quintra_content::Registry;

pub fn build_registry() -> Registry {
    quintra_game_content::registry()
}
