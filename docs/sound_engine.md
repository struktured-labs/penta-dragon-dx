# Penta Dragon DX Sound Engine

Sound engine lives in bank 3 (ROM bank 3 = file 0xC000-0xFFFF).
Driven by the Timer interrupt at ~89 Hz.

## Timer ISR chain

Timer IRQ vector at 0x0050:
```
0x0050:  C3 B3 06     JP 0x06B3
```

Timer ISR body at 0x06B3 (bank 0):
```
0x06B3:  F5 C5 D5 E5      PUSH AF, BC, DE, HL    ; save all GPR
0x06B7:  3E 03            LD A, 3
0x06B9:  EA 00 21         LD [0x2100], A          ; MBC bank ← 3 (sound bank)
0x06BC:  CD 00 40         CALL 0x4000             ; sound engine entry
0x06BF:  3E 01            LD A, 1
0x06C1:  EA 00 21         LD [0x2100], A          ; restore bank 1 (temp)
0x06C4:  CD 79 0D         CALL 0x0D79             ; centisecond timer update
0x06C7:  F0 99            LDH A, [FF99]           ; read saved bank
0x06C9:  EA 00 21         LD [0x2100], A          ; restore actual bank
0x06CC:  E1 D1 C1 F1      POP HL, DE, BC, AF
0x06D0:  D9               RETI
```

The ISR:
1. Saves registers
2. Switches to bank 3 (sound engine)
3. Calls sound engine entry at bank 3:0x4000
4. Switches to bank 1 (for centisecond counter update)
5. Calls 0x0D79 to advance FFF5/FFF6 stopwatch
6. Restores caller's bank from FF99
7. Pops registers and RETI

## Sound engine entry

bank 3:0x4000:
```
C3 6D 41    JP 0x416D    ; main dispatch
```

bank 3:0x4003+ has handler subroutines that read sound engine state
bytes and process commands.

## Sound engine state bytes (WRAM)

| Address | Purpose |
|---|---|
| D880 | (NOT sound — this is master scene state, but historically
        considered conflated with sound state) |
| D881 | Sound engine flag (probably "active") |
| D882-D884 | Channel pointers or temp state |
| D885 | Channel index / event |
| D886 | Current command byte |
| D887 | **D887 = current sound command** — writes here trigger sound playback.
        Memory documentation: "phantom sounds" came from D887 writing
        random data when MBC bank was wrong. |
| D888-D88A | More channel state |
| D88B-D8FF | Channel data (3 channels: D802/D822/D842 base addresses
              per memory.md) |

## Why bank-switching matters

If our VBlank handler (in bank 13) doesn't preserve FF99 = game's
bank, Timer ISR's bank restore (LDH A, [FF99]; LD [0x2100], A) sets
the WRONG bank when returning. After Timer return, PC continues in
our VBlank handler — but MBC bank is now wrong → garbage execution.

Historical bug ("phantom sounds"): a trampoline at 0x42A7 set
FF99=0x0D during tile copy. Timer ISR restored to bank 13 instead
of bank 1 → garbage D887 writes → phantom sounds.

Fix: remove the trampoline (kept only inline tile+attr at 0x42A7
which DOES NOT modify FF99). FF99 stays at game's value throughout.

## Why v3.01's removed FF99 protocol is safe

The v3.01 VBlank hook + colorize handler chain has:
- DI implicit on IRQ entry (VBlank handler entered with IRQs disabled)
- No `EI` anywhere in the chain (verified by inspection)
- Therefore Timer ISR cannot fire during our VBlank work

Since Timer can't fire, FF99 doesn't need to be set to 0x0D during
our handler — the bank context is preserved by the VBlank hook's
`LD A, 0x0D; LD [0x2000], A` (which doesn't touch FF99).

The hook saves the GAME'S bank on stack via `LDH A, [FF99]; PUSH AF`,
restores it via `POP AF; LD [0x2000], A` before RETurning. FF99 is
preserved untouched throughout.

## Hardware audio requirement

memory.md: "MiSTer requires: 'Audio mode = No Pops' in Gameboy core
OSD". Setting Audio mode to "Accurate" produces audible pops on some
games; "No Pops" is the safer choice for Penta Dragon DX.

## Audio system analysis (from earlier reverse-engineering)

- Sound driver runs at ~89 Hz via Timer ISR
- Timer ISR at 0x06B3 saves NO bank from its own perspective (relies on FF99)
- Chaotic sensitivity: Even 1 M-cycle VBlank change causes TOTAL audio
  waveform divergence (per memory notes)
- Raw PCM cross-correlation is useless for audio comparison (always ~0
  with any timing change)
- Use RMS energy envelope (50ms blocks) to detect actual audio dropouts
- Vanilla silence ratio: 5.7%
- v2.84.3 silence ratio: 17.3% (degraded from palette work cost)
- v2.86 fix (hash-cached palette): 7.5% (closer to vanilla)
