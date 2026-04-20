# Gap: Scroll Engine State (DC0B-DC0F + FFC2-FFC5)

## DC0B — Tilemap Buffer Toggle

Verified disassembly of toggle at 0x4295:
```z80
4295: FA 0B DC      LD A,(DC0B)
4298: 3C            INC A
4299: E6 01         AND $01
429B: EA 0B DC      LD (DC0B),A     ; toggle bit 0
429E: 28 05         JR Z, +5        → 0x42A5
42A0: 26 9C         LD H,$9C        ; new buffer = $9C00
42A2: C3 A7 42      JP $42A7        ; full tilemap copy
42A5: 26 98         LD H,$98        ; new buffer = $9800
42A7: ...           (tilemap copy)
```

Semantics:
- DC0B alternates 0 ↔ 1 each scroll tick
- After increment+mask: if result is 1 (was 0) → write to $9C00; if result is 0 (was 1) → write to $98
- Implements double-buffered full-tilemap rewrites — game writes the **next** frame to the off-screen buffer

Writes: 0x429B (toggle), 0x803E (init).

## DC0C / DC0D — Fine Scroll X / Y (verified)

Bytes at 0x4372 (writers in sequence):
```z80
4372: CD 7D 43      CALL $437D       ; compute Y
4375: 7B            LD A,E
4376: EA 0D DC      LD (DC0D),A      ; DC0D = fine Y
4379: CD 8E 43      CALL $438E       ; compute X
437C: 7D            LD A,L
437D: EA 0C DC      LD (DC0C),A      ; DC0C = fine X
```

- DC0C = fine pixel X offset within tile (low 4 bits of scroll position)
- DC0D = fine pixel Y offset within tile
- Both consumed by edge-offset computation at 0x48C2

## DC0E / DC0F — VRAM Edge Pointer (16-bit LE)

Computed at 0x48C2 from DC0C/DC0D. Writers: 0x48E1 (DC0E low), 0x48E5 (DC0F high).

Effective formula:
```
ptr = 0xC3E0 + ((DC0C & 1) << 4) + (DC0D & 1) + 0x0022
DC0F:DC0E = ptr
```

Result space: {0xC3E0, 0xC3E1, 0xC402, 0xC403} — 4 possible sub-tile-offset destinations within the C3E0 tile buffer.

Readers: 0x139C, 0x23D6, 0x4825, 0x487B, 0x5EEC (DC0E); 0x13A0, 0x23DA, 0x4829, 0x487F, 0x5EF0 (DC0F).

## FFC2-FFC5 — Edge Visibility Flags

All four written by routine at 0x5096. Pattern (per byte):
```z80
5096: F5 C5 D5 E5         ; save regs
      ...
50A5: 28 06 3E 01 E0 C2   ; JR Z,+6; LD A,$01; LDH (FFC2),A
      18 03 AF E0 C2      ; JR +3; XOR A; LDH (FFC2),A
      ; ... repeats for FFC3, FFC4, FFC5
```

Each byte = 0 (hidden) or 1 (visible) for one screen edge.

| Address | Edge | Writer site |
|---------|------|-------------|
| FFC2 | Top | 0x50A9, 0x50AE |
| FFC3 | Bottom | 0x50B7, 0x50BC |
| FFC4 | Left | (multiple writers) |
| FFC5 | Right | 0x50D3, 0x50D8 |

Boundary check at 0x50DF compares scroll position vs room dimensions; sets each edge flag based on whether next-room transition is reachable in that direction.

Readers found: only FFC2 has explicit `F0 C2` reads (at 0x2D07F and 0x2EFAA). FFC3-FFC5 are likely consumed via indexed access (`F0 C2 + offset`) or via the bit-pattern across all 4 bytes reads as a 32-bit value.

## Scroll Engine State Machine (synthesized)

Per scroll tick:
1. Compute fine offsets DC0C/DC0D from DC00-DC03 absolute position
2. Compute VRAM edge pointer DC0E/DC0F from fine offsets
3. Update edge visibility flags FFC2-FFC5 based on room boundaries
4. Toggle DC0B and call full tilemap copy 0x42A7 to the now-inactive VRAM buffer
5. Hardware SCX/SCY register update from absolute scroll for fine-pixel smoothness

The double-buffer + full-rewrite design is what makes scroll modifications expensive (~80K T-cycles per copy) — the game pays the cost every scroll tick instead of incrementally updating only changed tiles.
