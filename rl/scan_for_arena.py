"""Scan existing human recordings for stage boss arena transitions (D880 = 0x0C-0x14).

If we find one, the user has ALREADY beaten a level in their existing recordings,
and we can extract save states without asking them to play again.
"""
import json, sys

PATHS = [
    "/home/struktured/projects/penta-dragon-dx-claude/rl/bc_data/expert_human_enriched.jsonl",
    "/home/struktured/projects/penta-dragon-dx-claude/rl/bc_data/expert_v96_full.jsonl",
]

# WRAM offset in the hex string: each byte = 2 hex chars
# C000 = 0x0000 in the dump (start)
# D880 = 0xD880 - 0xC000 = 0x1880 = 6272 → char offset 12544
# DCB8 (section) = 0x1CB8 = 7352 → char 14704
# DCBB (death timer / boss HP) = 14710
# FFBA (level)  — but FFBA is in HRAM, not C000-DFFF. NOT available in this dump.
# FFBD (room) — same, HRAM.
# FFBF (miniboss) — same, HRAM.

D880_OFFSET = (0xD880 - 0xC000) * 2  # 12544
DCB8_OFFSET = (0xDCB8 - 0xC000) * 2

def get_byte(wram_hex, addr):
    o = (addr - 0xC000) * 2
    return int(wram_hex[o:o+2], 16)

for path in PATHS:
    print(f"\n=== {path} ===")
    arena_frames = []
    with_keys = 0
    total = 0
    last_d880 = -1
    for line in open(path):
        try:
            r = json.loads(line)
        except:
            continue
        total += 1
        wram = r.get("wram_C000_DFFF") or r.get("wram") or ""
        if not wram or len(wram) < 16384:
            continue
        d880 = get_byte(wram, 0xD880)
        dcb8 = get_byte(wram, 0xDCB8)
        if 0x0C <= d880 <= 0x14:
            if d880 != last_d880:
                arena_frames.append((r.get("f", total), d880, dcb8))
                if len(arena_frames) <= 10:
                    print(f"  ARENA at f={r.get('f',total)}: D880={hex(d880)} DCB8={dcb8}")
        last_d880 = d880
        if r.get("keys", 0) > 0: with_keys += 1
    print(f"  total frames: {total}, with input: {with_keys}, arena entries: {len(arena_frames)}")
    if arena_frames:
        d880_set = set(f[1] for f in arena_frames)
        print(f"  unique D880 arena values: {sorted([hex(x) for x in d880_set])}")
