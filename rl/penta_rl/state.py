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


def _oam_features(pb) -> dict:
    """Extract OAM-derived screen-space features.

    OAM = 40 sprites × 4 bytes (Y, X, tile, attr) at 0xFE00.
    Sara uses OAM slots 0-3 (4-tile sprite). Enemy bodies use tiles 0x30-0x7F.
    """
    OAM_X_OFFSET = 8   # GB sprite X offset (tile is rendered at X-8)
    OAM_Y_OFFSET = 16  # GB sprite Y offset (tile is rendered at Y-16)
    SARA_SLOTS = 4
    BODY_MIN, BODY_MAX = 0x30, 0x7F
    PROJ_TILES = {0x06, 0x09, 0x0A, 0x0F, 0x00, 0x01}

    sara_x = sara_y = sara_n = 0
    boss_x = boss_y = boss_n = 0
    near_x = near_y = 0; near_dist = 999
    proj_n = 0
    sprites = []  # all (Y, X, tile)
    mem = pb.memory
    for i in range(40):
        y = mem[0xFE00 + i*4]
        x = mem[0xFE00 + i*4 + 1]
        tile = mem[0xFE00 + i*4 + 2]
        if y == 0 or y >= 160:  # off-screen
            continue
        sx = x - OAM_X_OFFSET
        sy = y - OAM_Y_OFFSET
        sprites.append((sy, sx, tile))
        if i < SARA_SLOTS:
            sara_x += sx; sara_y += sy; sara_n += 1
        elif BODY_MIN <= tile <= BODY_MAX:
            boss_x += sx; boss_y += sy; boss_n += 1
        elif tile in PROJ_TILES:
            proj_n += 1

    sara_x = sara_x / max(sara_n, 1)
    sara_y = sara_y / max(sara_n, 1)
    boss_x = boss_x / max(boss_n, 1) if boss_n else -1
    boss_y = boss_y / max(boss_n, 1) if boss_n else -1
    # Nearest enemy distance
    if sara_n > 0:
        for sy, sx, tile in sprites:
            if BODY_MIN <= tile <= BODY_MAX:
                d = ((sx - sara_x) ** 2 + (sy - sara_y) ** 2) ** 0.5
                if d < near_dist:
                    near_dist = d; near_x = sx; near_y = sy
    if near_dist == 999: near_dist = -1
    return {
        "sara_x": sara_x, "sara_y": sara_y,
        "boss_x": boss_x, "boss_y": boss_y, "boss_count": boss_n,
        "near_x": near_x, "near_y": near_y, "near_dist": near_dist,
        "proj_count": proj_n,
    }


def read_state(pb) -> GameState:
    """Extract a GameState from a PyBoy instance."""
    mem = pb.memory
    slots = np.zeros((5, 8), dtype=np.uint8)
    for i, base in enumerate(ADDR["SLOT_BASES"]):
        for j in range(8):
            slots[i, j] = mem[base + j]
    raw = {k: mem[a] for k, a in ADDR.items() if k != "SLOT_BASES" and isinstance(a, int)}
    raw["oam"] = _oam_features(pb)
    # Inventory region (probed candidates: D840-D85F + D880-D89F)
    raw["inv"] = bytes(mem[a] for a in range(0xD840, 0xD8A0))
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

    Returns 167-dim vector. All bytes normalized to [0, 1].
    """
    oam = s.raw_addrs.get("oam", {}) if s.raw_addrs else {}
    sara_x = oam.get("sara_x", -1); sara_y = oam.get("sara_y", -1)
    boss_x = oam.get("boss_x", -1); boss_y = oam.get("boss_y", -1)
    near_x = oam.get("near_x", -1); near_y = oam.get("near_y", -1)
    near_d = oam.get("near_dist", -1); proj_n = oam.get("proj_count", 0)
    boss_count = oam.get("boss_count", 0)
    # Relative offsets (boss relative to sara)
    if boss_x >= 0 and sara_x >= 0:
        bsx = (boss_x - sara_x) / 160.0
        bsy = (boss_y - sara_y) / 144.0
    else:
        bsx = 0.0; bsy = 0.0
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
        # OAM-derived features (12 dims)
        np.array([
            max(sara_x, 0) / 160.0, max(sara_y, 0) / 144.0,
            max(boss_x, 0) / 160.0, max(boss_y, 0) / 144.0,
            max(near_x, 0) / 160.0, max(near_y, 0) / 144.0,
            max(near_d, 0) / 200.0,  # max ~283 (sqrt(160^2+144^2))
            proj_n / 10.0,
            boss_count / 8.0,
            bsx, bsy,  # signed in [-1, 1]
            1.0 if boss_count > 0 else 0.0,  # has_boss flag
        ], dtype=np.float32),
        # Inventory region (96 bytes from D840-D89F, /255 normalized)
        np.frombuffer(s.raw_addrs.get("inv", bytes(96)), dtype=np.uint8).astype(np.float32) / 255.0,
    ]
    return np.concatenate(parts)


def vector_dim() -> int:
    """Return the dimension of state_to_vector output."""
    # 4 + 6 + 3 + 6 + 40 + 12 + 96 = 167
    return 167
