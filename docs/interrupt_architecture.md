# Penta Dragon Interrupt Architecture

Documents how the ROM's interrupt service routines (ISRs) interact with our
v3.01 colorization handler, and the bank-switching protocol that ties them
all together via the FF99 shadow register. Companion to
`v301_gdma_freeze_diagnosis.md` — that doc explains a specific freeze;
this doc explains the system.

## ROM bank map (MBC1, 256KB, 16 banks)

| Bank | Range            | Purpose                                         |
|------|------------------|-------------------------------------------------|
| 0    | 0x00000-0x03FFF  | Bootstrap, ISR vectors at 0x0040-0x0060, main code, palette stub |
| 1    | 0x04000-0x07FFF  | Main game logic — default switched bank vanilla |
| 2    | 0x08000-0x0BFFF  | Level data + room transition logic              |
| 3    | 0x0C000-0x0FFFF  | **Sound engine** — Timer ISR target (bank 3:0x4000) |
| 4-12 | 0x10000-0x33FFF  | Tile graphics, sprite data, level tile maps     |
| 13   | 0x34000-0x37FFF  | **v3.01 patched bank** — colorization handler at 0x6E00, palettes at 0x6800, bg_table at 0x7000 |
| 14-15| 0x38000-0x3FFFF  | More tile data + death cinematic                |

The vanilla game keeps **bank 1 selected most of the time** during gameplay,
switching to bank 2 for room transitions, bank 3 inside the Timer ISR,
and various banks for graphics loading.

## Interrupt vectors (bank 0)

| Vector | Addr   | Bytes at vector       | Target  | Owner   |
|--------|--------|-----------------------|---------|---------|
| VBlank | 0x0040 | `C3 D1 06`            | 0x06D1  | game    |
| STAT   | 0x0048 | `C3 53 08`            | 0x0853  | game    |
| Timer  | 0x0050 | `C3 B3 06`            | 0x06B3  | game    |
| Serial | 0x0058 | `D9 7D FB ...`        | RETI    | unused  |
| Joypad | 0x0060 | `D9 EA 09 ...`        | RETI    | unused  |

The game uses three interrupts: **VBlank**, **STAT**, and **Timer**.

## The FF99 protocol (critical invariant)

**FF99 is the ROM bank shadow register.** Game code that switches banks does:

```asm
LD A, <target_bank>
LDH [FF99], A        ; update shadow FIRST
LD [0x2100], A       ; then update MBC register
```

Why both: the MBC register at 0x2100 is **write-only**. Game code that
needs to know "what bank is currently mapped" reads FF99 instead.

Each ISR (STAT, Timer) uses FF99 to restore the bank on exit:

```asm
STAT_handler:                        Timer_handler (bank 3:0x4000 target):
  PUSH AF BC DE HL                     similar pattern
  LD A, 1                              LD A, 3
  LD [0x2100], A     ; bank 1          LD [0x2100], A    ; bank 3
  CALL <work in bank 1>                CALL <sound engine work>
  CALL <work in bank 1>                ...
  LDH A, [FF99]                        LDH A, [FF99]
  LD [0x2100], A     ; restore         LD [0x2100], A    ; restore
  POP HL DE BC AF
  RETI                                 RETI
```

If FF99 is stale at the moment an ISR exits, the wrong bank is restored
and the interrupted code resumes with wrong bank mapped — **this is the
exact failure mode that produced the v3.01 freeze.**

## VBlank handler chain

```
 ┌─ CPU receives VBlank interrupt
 ├─ JP 0x06D1                                  [vector at 0x0040]
 │
 │  game's VBlank handler at 0x06D1
 │    ├─ saves regs
 │    ├─ palette / tilemap copy logic
 │    ├─ CALL 0x0824                            [joypad-read slot]
 │    │   │
 │    │   │  patched hook (us) at 0x0824:
 │    │   │    F0 99 F5             save FF99 to stack
 │    │   │    ... joypad reads (~28 bytes) ...
 │    │   │    3E 0D EA 00 20       LD A,13; LD [2100],A   ← bank switch
 │    │   │    CD <colorize_addr>   CALL into bank 13
 │    │   │
 │    │   │      colorize handler at bank 13:0x6E00:
 │    │   │        F0 99 F5         save FF99 to stack
 │    │   │        3E 0D E0 99      FF99 = 0x0D   ← critical fix
 │    │   │        ... cond_pal, bg_sweep, GDMA, attr_comp ...
 │    │   │        F1 E0 99         restore FF99
 │    │   │        C9               RET
 │    │   │
 │    │   │    F1 EA 00 20          POP AF; LD [2100],A   ← restore bank
 │    │   │    C9                   RET
 │    │
 │    ├─ ... rest of VBlank handler ...
 │    └─ RETI
 │
 └─ resume game code in main loop
```

**Hook constraints:** the joypad-read slot at 0x0824 is 47 bytes maximum.
We can't fit a full FF99 save/update/restore there alongside the bank
switch and joypad logic, so the FF99 fix lives inside the colorize
handler (no byte budget there).

## Bank-switching protocol for safe ISRs during a custom handler

If your custom handler runs with IME=1 at any point (e.g. you EI inside
attr_computation, OAM DMA, etc.), **you MUST update FF99 to match the
bank you've mapped**. Otherwise:

1. ISR fires while your handler is running
2. ISR saves regs, switches to its expected bank (1 or 3)
3. ISR does its work
4. ISR loads bank from FF99 → gets your handler's caller's bank, NOT yours
5. ISR returns; your handler resumes with the wrong bank mapped
6. Next instruction fetch reads garbage from the wrong bank

This applies even if you DI for parts of your handler — as soon as you EI,
any pending interrupt fires immediately. The Timer interrupt fires at
~89 Hz, so it's pending fairly often.

Symptoms of FF99-protocol violations:
- Game freezes at FFC1=0→1 transition (first gameplay frame)
- White screen on boot
- Crash partway through a long handler
- Cycle-precise sensitivity to handler runtime

Cure: at any point in a custom-bank handler where IME could be 1, ensure
FF99 reflects your current bank.

## What we modified vs vanilla

| Address                | Vanilla                | v3.01                                   |
|------------------------|------------------------|-----------------------------------------|
| 0x0040 (VBlank)        | JP 0x06D1              | unchanged                               |
| 0x0048 (STAT)          | JP 0x0853              | unchanged                               |
| 0x0050 (Timer)         | JP 0x06B3              | unchanged                               |
| 0x06D5-0x06D7          | game DMA               | NOP×3 (we do DMA in colorize handler)   |
| 0x0824-0x0852 (47B)    | joypad-read code       | our hook + bank switch + CALL colorize  |
| 0x003B                 | `D9` (RETI)            | `C9` (RET) — phantom-sound v288 fix     |
| 0x42A7-0x436D          | inline tile copy       | tile-only inline copy (vanilla speed)   |
| bank 13 0x6800-0x77FF  | unused                 | v3.01 colorization code + data          |
| 0x143 (CGB flag)       | 0x00                   | 0x80                                    |

The original game runs on DMG (Game Boy) without color. v3.01 sets the
CGB flag and installs a CGB-native palette+attribute pipeline.
