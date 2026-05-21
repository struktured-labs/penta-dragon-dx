# Penta Dragon WRAM Allocation Map (C000-DFFF)

Static-analysis census of `LD (nn),A` / `LD A,(nn)` accesses to WRAM
across all 16 ROM banks. Companion to `hram_allocation_map.md`.

The vanilla game does NOT switch WRAM banks (zero FF70 writes in code),
so D000-DFFF always refers to bank 1 from the game's perspective. Our
v3.01 colorization handler is the only thing that briefly maps bank 2.

## Page heatmap (cross-bank census)

| Page         | R    | W    | Total | Purpose                                    |
|--------------|------|------|-------|--------------------------------------------|
| 0xC000-0xC0FF| 1    | 5    | 6     | Sparse — maybe early game state            |
| 0xC100-0xC1FF| 0    | 2    | 2     | **Tile buffer 0xC1A0-0xC3DF** (576 bytes; loaded via memcpy not LD (nn),A) |
| 0xC700-0xC7FF| 17   | 13   | 30    | Likely OAM mirror or shadow                |
| 0xD000-0xD2FF| 3    | 14   | 17    | (sparse vanilla; our attr buffer lands here in bank 2) |
| 0xD500-0xD5FF| 8    | 31   | 39    | Moderate — TBD                             |
| **0xD800-0xD8FF** | 42 | 105 | **147** | Sound channels D800-D85F + engine state D880-D88A |
| **0xDC00-0xDCFF** | 242 | 234 | **476** | Primary game state — Sara, camera, scroll, FFBA shadow, DCBB boss HP, entity slots |
| **0xDD00-0xDDFF** | 173 | 304 | **477** | Secondary game state — enemy slots, projectile state, palette anim timing |
| 0xDE00-0xDEFF| 31   | 29   | 60    | Animation/sprite state                     |
| 0xDF00-0xDFFF| 8    | 5    | 13    | Sparse — our control bytes (DF00 hash, DF02 magic, DF03 GDMA-ready) live here |

The DCxx and DDxx pages together are 953 hits — they are where the
game *lives* in memory. Anything you patch into the game must respect
these regions.

## Hot WRAM addresses (sorted by total accesses)

### DCxx — primary game state

| Addr   | R/W      | Purpose                                                  |
|--------|----------|----------------------------------------------------------|
| DC00   | 8/4      | Camera Y, low byte (sub-pixel nibble used by STAT scroll handler) |
| DC01   | ~        | Camera Y, high byte                                      |
| DC02   | 8/4      | Camera X, low byte (sub-pixel nibble used by STAT scroll handler) |
| DC03   | ~        | Camera X, high byte                                      |
| DC04   | ~        | Spawn-table boss-type byte (e.g. 0x30=Gargoyle, 0x35=Spider) |
| DC0B   | 7/2      | TBD                                                      |
| DC18   | 14/16    | Sara X position (low byte, OAM-driven)                   |
| DC19   | **23/21**| **Sara X position** (high byte / current logical X)      |
| DC1A   | 7/3      | Sara Y position (low byte)                               |
| DC1B   | 5/7      | Sara Y position; cleared with FFC0/DCF8 on state reset   |
| DC1D-1E| 4/5-6    | Sara additional state (facing direction?)                |
| DC22   | **17/17**| Sara hit-flash or invuln timer                           |
| DC81   | ~        | Section scroll counter (0xC8 init, -=4 per scroll tick)  |
| DC82   | ~        | Section scroll max (0xC8 constant)                       |
| DC85+  | ~        | 5 enemy slots at DC85, DC8D, DC95, DC9D, DCA5 (8 bytes each) |
| DCB3   | 9/3      | TBD (game state, read-heavy)                             |
| DCB8   | ~        | Section cycle counter 0-5 (mini-boss spawn index)        |
| DCBB   | 7/9      | **Boss HP in arena, corridor timer elsewhere**           |
| DCDB   | 5/7      | TBD                                                      |
| DCDC/DD| ~        | Player HP (sub-counter / main HP)                        |
| DCDE/DF| ~        | Timer cascade (godmode pumps these)                      |
| DCF0   | 6/4      | TBD                                                      |
| DCF2   | 12/6     | TBD (high read rate; possibly current spawn index?)      |
| DCF8   | 13/3     | TBD; cleared with FFC0/DC1B on state reset               |

### DDxx — enemy/projectile/anim state

| Addr   | R/W      | Purpose                                                  |
|--------|----------|----------------------------------------------------------|
| DD06   | ~        | Scroll lock (godmode clears this)                        |
| DD80-91| many writes | Enemy slot data (8-9 bytes/slot × multiple slots)     |
| DD85-88| 7-10 ea  | Specific slot bytes (TBD which slot field)               |
| DD96/97| 7/8      | Possibly projectile pair (paired writes)                 |
| DD9F-A1| 1/9 ea   | Write-heavy block — initialization burst?                |
| DDAD   | ~        | OBP1 palette-animation timing counter                    |
| DDAE   | ~        | OBP1 palette-animation flag                              |

### D8xx — sound engine

| Addr      | Purpose                                                  |
|-----------|----------------------------------------------------------|
| D800-D81F | Sound channel 0 (32 bytes)                               |
| D820-D83F | Sound channel 1 (32 bytes)                               |
| D840-D85F | Sound channel 2 (32 bytes)                               |
| D880      | **Master scene state** (0x02=dungeon, 0x0A=mini-boss, 0x0C-14=arenas, 0x17=death, 0x18=splash) |
| D881      | Previous master scene (transition detector)              |
| D882      | Sound engine delta accumulator                           |
| D883      | Sound engine delta increment                             |
| D884      | Per-frame channel-processing flag (3=done)               |
| D885      | Engine status (non-zero = jump-to-handler)               |
| D886      | TBD                                                      |
| D887      | **Sound command byte** — RST 38 writes here (phantom-sound v2.88 fix patches RETI→RET at 0x003B) |
| D888-89   | Sound state extension                                    |
| D88A      | Special flag (triggers 0x422D when non-zero)             |
| D894      | TBD (5/5 — sound state)                                  |

### DFxx — our v3.01 control bytes + sparse game state

| Addr   | Owner      | Purpose                                                  |
|--------|------------|----------------------------------------------------------|
| DF00   | v3.01      | Per-frame hash for cond_pal change detection             |
| DF02   | v3.01      | Magic byte (0x5A) — cold-boot init guard                 |
| DF03   | v3.01      | GDMA-ready flag (set after attr_computation completes)   |
| DF05   | v3.01 (historical) | Was chunk counter in 8-chunk attr_comp (no longer used in per-row design) |

The DFxx region appears safe (only 13 accesses cross-bank, mostly our
v3.01 additions). Vanilla writes to DF05 only happen if the game uses
this byte for something else — unconfirmed.

### DAxx — our v3.01 bg_table copy

| Addr        | Purpose                                            |
|-------------|----------------------------------------------------|
| DA00-DAFF   | bg_table runtime copy (256 bytes from ROM bank 13 0x7000) |

The 1 read seen in the census is from our own inline-hook lookup
(in the v3.01 build). Vanilla doesn't touch this.

## Key observations for further patching

1. **DCxx + DDxx are sacred** — together 953 accesses. Any patch
   that touches these addresses risks breaking gameplay.
2. **C700 page is moderately used (30 hits)** — likely an OAM mirror
   updated by VBlank's `CALL 0xFF80` DMA-from-WRAM routine. We NOP'd
   0x06D5 to avoid double-DMA in v3.01.
3. **DFxx is sparse** — good for our v3.01 control bytes.
4. **D800-D8FF is sound-only** — leave alone unless modifying audio.

## How this connects to the v3.01 fix

- Our attr_computation writes to D000-D2FF (bank 2). Vanilla writes to
  same addresses in bank 1 (the game's only mapped WRAM bank). Without
  the FF99 fix, an ISR firing during our handler restores bank 1, and
  any subsequent attr_comp write would hit BANK 1 D000-D2FF — bank 1's
  D200 area has 8 writes from vanilla per the census, so this would
  corrupt some state. The FF99 fix prevents this entirely.
