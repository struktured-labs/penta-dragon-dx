# Penta Dragon HRAM Allocation Map (FF80-FFFE)

Census from static analysis of bank 0 (always mapped). Shows the most-
accessed HRAM bytes, separating reads (consumer code) from writes
(producer code). Documents what we know about each byte's purpose.

## Hardware registers (FF00-FF7F — not strictly HRAM, but accessed via LDH)

| Addr  | Name | Purpose                                      |
|-------|------|----------------------------------------------|
| FF00  | JOYP | Joypad input register                        |
| FF40  | LCDC | LCD control                                  |
| FF41  | STAT | LCD status                                   |
| FF42  | SCY  | Scroll Y                                     |
| FF43  | SCX  | Scroll X                                     |
| FF44  | LY   | Current scanline                             |
| FF45  | LYC  | Scanline compare (STAT trigger)              |
| FF47  | BGP  | DMG BG palette (we animate this in VBlank)   |
| FF48  | OBP0 | DMG sprite palette 0                         |
| FF49  | OBP1 | DMG sprite palette 1                         |
| FF4F  | VBK  | CGB VRAM bank select                         |
| FF51-55 | HDMA1-5 | CGB HDMA registers (we use for GDMA)   |
| FF68-6B | BCPS/BCPD/OCPS/OCPD | CGB palette RAM access        |
| FF70  | SVBK | CGB WRAM bank select                         |
| FFFF  | IE   | Interrupt enable                             |

## Game state HRAM (FF80-FFFE)

Sorted by descending total access count (bank 0 census). Top entries
are the hottest game-state bytes the engine touches.

| Addr   | R/W     | Purpose                                                  |
|--------|---------|----------------------------------------------------------|
| FFBF   | 19R/2W  | Mini-boss flag (1=Gargoyle, 2=Spider, 3+=spawn-table)    |
| FF94   | 16R/2W  | Joypad EDGE-detected input (from 0x00A8)                 |
| FFBA   | 14R/4W  | Level/boss counter (0-8) — indexes stage boss tables     |
| FFCA   | 12R/3W  | TBD (high read rate)                                     |
| FFE4   | 1R/12W  | TBD (write-heavy; set on death cinematic per memory)     |
| FFC4   | 0R/12W  | TBD (write-only — likely an output/control register)     |
| FFCE   | 3R/9W   | Next-room value (set from 0x0BBF table, consumed at 0x0B78) |
| FFDC   | 9R/2W   | TBD                                                      |
| FFEB   | 8R/3W   | Scroll phase toggle (0=normal, 1=alternate/bonus)        |
| FF9E   | 4R/6W   | TBD                                                      |
| FFC1   | 4R/6W   | **Gameplay active flag** (0=menu/title, 1=gameplay)      |
| FFE9   | 1R/9W   | STAT-handler scroll sub-cycle counter (0..3)             |
| FFBE   | 7R/2W   | TBD (game state)                                         |
| FFF0   | 3R/6W   | TBD                                                      |
| FFCD   | 5R/3W   | TBD                                                      |
| FFD3   | 6R/1W   | Event sequence index within current FFBA level           |
| FFD9   | 4R/3W   | TBD                                                      |
| FFB8   | 3R/3W   | 4-frame cycle counter (0x086C dispatcher)                |
| FFB2   | ~       | Mode flag for 0x086C dispatcher (0=skip, 1=branch A, 2=branch B) |
| FFE2/3 | ~       | BGP palette-animation timing                             |
| FFD4   | ~       | Frame counter (incremented in VBlank handler)            |
| FFD5   | ~       | Some 60-cycle counter (cycles 0..0x3C in VBlank)         |
| FFD1   | ~       | Centisecond counter (0..99) — wraps per second           |
| FFE8   | ~       | Scroll-active flag (gates 0x08F8)                        |
| FFF5   | ~       | Stopwatch seconds (BCD, counts UP from 0)                |
| FFF6   | ~       | Stopwatch minutes (BCD)                                  |
| FFF4   | ~       | Stopwatch enable flag                                    |
| FF99   | ~       | **ROM bank shadow** — see interrupt_architecture.md      |
| FFAC/AD | ~      | Level pointer table FFAC=lo, FFAD=hi                     |
| FFBD   | ~       | Room/section ID (1-7) — dispatch table at bank1:0x4481   |
| FFCF   | ~       | Scroll position / section index (0x10-0x16)              |
| FFC0   | ~       | TBD                                                      |
| FFFF   | -       | IE (interrupt enable) — hardware register                |

## Our v3.01 additions

| Addr   | Purpose                                                             |
|--------|---------------------------------------------------------------------|
| FFE0   | (used as scratch by attr_computation row counter; reused in handler)|
| FFE1   | Used by build_v301_iemask test scripts                              |

Both are in the "TBD" range from the census — no vanilla writes/reads to
these addresses appeared in the bank-0 scan. Safe scratch.

## Census methodology

Counts unique `LDH (n), A` (0xE0 nn) writes and `LDH A, (n)` (0xF0 nn)
reads in bank-0 ROM (0x0000-0x3FFF). Doesn't include accesses from
banked ROM (other banks could push the counts higher) or `LD A, (nn)` /
`LD (nn), A` absolute-mode accesses to HRAM range. For a full picture,
extend the scan to all 16 banks.
