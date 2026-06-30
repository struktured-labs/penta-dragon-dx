//! Room template library. Phase 2: 1 placeholder template (empty small room
//! with all 4 doors). Real authored rooms arrive in Phase 4.

use quintra_content::{DoorMask, Registry, RoomKind, RoomSize, RoomTemplate};

use crate::ids::*;

pub const SMALL_EMPTY: RoomTemplate = RoomTemplate {
    id:          ROOM_SMALL_EMPTY,
    size:        RoomSize::Small,
    layout:      TILEMAP_SMALL_EMPTY,
    doors:       DoorMask(DoorMask::N | DoorMask::E | DoorMask::S | DoorMask::W),
    spawn_slots: &[],
    kind:        RoomKind::Combat,
};

pub fn register(r: &mut Registry) {
    r.add_room(SMALL_EMPTY.clone());
}
