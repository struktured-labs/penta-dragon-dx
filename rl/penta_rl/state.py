"""State vector extraction from PyBoy memory.

WRAM/HRAM addresses come from the architecture doc and runtime probes.
Most important: D880 (scene), FFBA (level), FFBD (room), FFBF (miniboss),
DCBB (boss HP), DCDC/DCDD (player HP), entity slots DC85+.
"""
from __future__ import annotations
import numpy as np
from dataclasses import dataclass


# Memory map (verified)
ADDR = {
    # Scene / level
    "D880": 0xD880,  # Scene state (0x02 gameplay, 0x0A miniboss, 0x17 death)
    "FFBA": 0xFFBA,  # Level/boss index 0-8
    "FFBD": 0xFFBD,  # Room 1-7
    "FFBE": 0xFFBE,  # Sara form (0=Witch, 1=Dragon)
    "FFBF": 0xFFBF,  # Miniboss flag (0=normal, 1-15 valid, 16 = boss 16)
    "FFC0": 0xFFC0,  # Powerup (0/1/2/3)
    "FFC1": 0xFFC1,  # Gameplay flag
    # Combat
    "DCBB": 0xDCBB,  # Boss HP (also corridor death timer)
    "DCDC": 0xDCDC,  # Player HP sub
    "DCDD": 0xDCDD,  # Player HP main
    "DCB8": 0xDCB8,  # Section cycle counter
    "DCBA": 0xDCBA,  # Section advance arming
    # Scroll
    "FFAC": 0xFFAC,  # Spawn-table pointer LO
    "FFAD": 0xFFAD,  # Spawn-table pointer HI
    "FFCF": 0xFFCF,  # Scroll position
    "DC81": 0xDC81,  # Section scroll counter
    "DC04": 0xDC04,  # Active entity DC04
    # Hardware
    "SCY": 0xFF42, "SCX": 0xFF43,
    "BGP": 0xFF47,
    "LCDC": 0xFF40,
    # Entity slots (each 8 bytes)
    "SLOT_BASES": [0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5],
}


@dataclass
class GameState:
    """Snapshot of game state for reward computation."""
    scene: int       # D880
    level: int       # FFBA
    room: int        # FFBD
    form: int        # FFBE
    miniboss: int    # FFBF
    powerup: int     # FFC0
    gameplay: int    # FFC1
    boss_hp: int     # DCBB
    player_hp: int   # DCDD * 256 + DCDC
    section: int     # DCB8
    spawn_ptr_lo: int  # FFAC
    spawn_ptr_hi: int  # FFAD
    scroll_pos: int  # FFCF
    scy: int
    scx: int
    active_entity: int  # DC04
    slots: np.ndarray   # (5, 8)
    raw_addrs: dict     # for debug


def read_state(pb) -> GameState:
    """Extract a GameState from a PyBoy instance."""
    mem = pb.memory
    slots = np.zeros((5, 8), dtype=np.uint8)
    for i, base in enumerate(ADDR["SLOT_BASES"]):
        for j in range(8):
            slots[i, j] = mem[base + j]
    raw = {k: mem[a] for k, a in ADDR.items() if k != "SLOT_BASES" and isinstance(a, int)}
    return GameState(
        scene=mem[0xD880], level=mem[0xFFBA], room=mem[0xFFBD],
        form=mem[0xFFBE], miniboss=mem[0xFFBF], powerup=mem[0xFFC0],
        gameplay=mem[0xFFC1],
        boss_hp=mem[0xDCBB], player_hp=mem[0xDCDD] * 256 + mem[0xDCDC],
        section=mem[0xDCB8], spawn_ptr_lo=mem[0xFFAC], spawn_ptr_hi=mem[0xFFAD],
        scroll_pos=mem[0xFFCF], scy=mem[0xFF42], scx=mem[0xFF43],
        active_entity=mem[0xDC04],
        slots=slots, raw_addrs=raw,
    )


def state_to_vector(s: GameState) -> np.ndarray:
    """Flatten state to a fixed-size float32 vector for the policy.

    Returns ~80-dim vector. All bytes normalized to [0, 1].
    """
    parts = [
        # Scene/level (one-hots for known scene values + level)
        np.array([s.scene == v for v in (0x02, 0x0A, 0x17, 0x18)], dtype=np.float32),
        np.array([s.level / 8.0, s.room / 7.0, s.form, s.powerup / 3.0,
                  s.gameplay, s.miniboss / 16.0], dtype=np.float32),
        # Combat
        np.array([s.boss_hp / 255.0, s.player_hp / (23 * 256 + 255),
                  s.section / 6.0], dtype=np.float32),
        # Scroll
        np.array([s.spawn_ptr_lo / 255.0, s.spawn_ptr_hi / 255.0,
                  s.scroll_pos / 255.0, s.scy / 255.0, s.scx / 255.0,
                  s.active_entity / 255.0], dtype=np.float32),
        # Entity slots flattened (40 bytes)
        s.slots.flatten().astype(np.float32) / 255.0,
    ]
    return np.concatenate(parts)


def vector_dim() -> int:
    """Return the dimension of state_to_vector output."""
    # 4 + 6 + 3 + 6 + 40 = 59
    return 59
