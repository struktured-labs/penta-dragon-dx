# Research Notes

## Immediate Tasks
- Confirm exact ROM size and banking (MBC type) via header.
- Disassemble with `mgbdis` or convert to RGBDS compatible assembly for searching init routines.
- Identify where hardware detection (CGB vs DMG) occurs (often checks `FF4D` or similar sequence).
- Plan injection site: early init after CGB detection, before main loop.

## Memory / Registers of Interest
- CGB Background Palettes: Index `FF68` (BCPS), Data `FF69` (BCPD)
- CGB Object Palettes: Index `FF6A` (OCPS), Data `FF6B` (OCPD)
- VRAM: `8000-9FFF`
- OAM: `FE00-FE9F`

## Strategy Outline
1. Locate free space (sequence of 0xFF padding or repetitive bytes) for palette table & stub.
2. Assemble small routine to iterate YAML-defined palettes and write them via auto-increment palette registers.
3. Hook routine by patching a CALL at an unused location in init sequence.
4. Preserve DMG fallback by gating on CGB flag (bit 0 of `FF4F` or header check code path).

## Tools
- SameBoy debugger: breakpoints on writes to `FF69` / `FF6B`.
- BGB: VRAM viewer & real-time palette inspection.
- rgbasm / rgblink (RGBDS) if building custom stub.

## Palette Encoding (BGR555)
Each color: 0-31 per channel. Order: lower bits contain Blue, then Green, then Red. Example: `7FFF` = white (all channels max).

## Patch Considerations
- IPS cannot extend ROM safely; ensure space already exists.
- For banked addressing, ensure stub resides in fixed bank if called early.

## Open Questions
- Does Penta Dragon already read hardware type? If not, we add detection logic.
- Amount of static vs dynamically composed background tiles? Impacts palette granularity.
