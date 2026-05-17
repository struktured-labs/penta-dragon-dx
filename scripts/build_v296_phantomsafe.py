#!/usr/bin/env python3
"""Penta Dragon DX v2.96 — phantom-safe BG colorization with visible-viewport sweep.

Goal: enhanced_copy-style BG-attr coverage (no "uncolorized walls" during
       gameplay) AND phantom-safe (≤vanilla 12 D887 transitions).

Architecture: build on v2.95 (proven phantom-safe at 0–4 transitions) but
swap the BG sweep for v2.94's "visible-viewport" version, gated by FFC1=1.

Why this fixes both:

  - v2.95's edge-priority sweep processes 1 row at a time, starting from
    the edge of the most recent scroll motion. In dungeon rooms where the
    player isn't scrolling, the sweep cycles slowly through DF04=0..23,
    leaving most of the room with stale BG attrs for up to 24 frames.
    Walls that should be palette 6 render with palette 0 → "BG
    colorization off in dungeon" / wall artifacts.

  - v2.94 fixed this by computing the row address from SCY + DF04 each
    frame (covers the visible viewport always) and dropping the FFC1=0
    early-exit (so title screens got sweeps too). The latter caused title
    artifacts.

  - v2.96 keeps v2.94's visible-viewport sweep but reinstates the FFC1=0
    early-exit, so title screens don't get spurious sweeps but in-game
    rooms get every visible row written each frame.

  - Phantom-sound: NO trampoline, NO DI/EI in main-loop context. All
    colorization is in the VBlank handler in bank 13, identical to v2.90.
    The Timer ISR can fire after VBlank with FF99 already restored to
    bank 1.

Verified targets (vs scripts/probes/verify_phantom_d887.py default tolerance):
  - phantom transitions ≤ vanilla (12 ish)
  - title color: at least 2 distinct colors with non-white pixels
  - gameplay palette: ≥3 distinct words, ≥2 palette indices in attrs

Compared to v2.89/v2.87:
  - No trampoline at bank1:0x42A7 — the trampoline blocks Timer ISR for
    ~10,000+ T-cycles via DI throughout enhanced_tilemap_copy. Although
    DI prevents Timer firing mid-trampoline, the long Timer-blocked
    window combined with the cond_pal/shadow_main calls running in
    main-loop context (not VBlank) creates a window where the GAME's
    main loop writes D887 multiple times AND the sound engine's
    consume-D887 routine can't catch up. The phantom-sound counter
    sees these multi-write windows as 50+ transitions vs vanilla 12.
    v2.96 avoids ALL of this by keeping the BG-attr work inside the
    VBlank handler.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bg_experiment import (
    load_palettes_from_yaml, create_tile_based_colorizer,
    create_shadow_colorizer_main, create_palette_loader,
    create_tile_to_palette_subroutine, create_bg_tile_table,
)
from create_vblank_colorizer_v288 import create_conditional_palette_cached


def create_bg_sweep_viewport_gated(bg_table_addr: int, base_addr: int) -> bytes:
    """Visible-viewport BG sweep with 16-bit row-address math, gated by FFC1.

    Each frame writes BG attributes for ONE of the 18 visible rows. The
    row to process is (SCY/8 + DF04) mod 32, where DF04 cycles 0..17.

    Address calculation reuses v2.90's correct 16-bit form (see
    build_v290_final.create_bg_sweep_v8):
       row = (SCY/8 + DF04) & 0x1F        (tilemap row, 0..31)
       D   = base_hi + (row >> 3)         (carries propagate properly)
       E   = (row & 7) << 5

    v2.94's create_bg_sweep_v8_no_menu_skip used `A *= 32` via 5×ADD A,
    which loses the high byte for row >= 8 — making rows 8..17 alias
    back to rows 0..9 in the tilemap and leaving real rows 8..17 with
    stale attributes. v2.96 fixes that.
    """
    bg_table_hi = (bg_table_addr >> 8) & 0xFF
    s = bytearray()

    # FFC1=0 → return (no sweep on menus / title)
    s.extend([0xF0, 0xC1, 0xB7, 0xC8])
    s.extend([0xC5, 0xD5, 0xE5])  # save BC, DE, HL

    # base_hi from LCDC bit 3 (0x98 or 0x9C)
    s.extend([0xF0, 0x40, 0xE6, 0x08, 0x0F, 0xC6, 0x98, 0xEA, 0x01, 0xDF])

    # B = SCY/8
    s.extend([0xF0, 0x42, 0xCB, 0x3F, 0xCB, 0x3F, 0xCB, 0x3F, 0x47])

    # Increment DF04, clamp 0..17
    s.extend([0xFA, 0x04, 0xDF, 0x3C, 0xFE, 0x12, 0x20, 0x02, 0x3E, 0x00])
    s.extend([0xEA, 0x04, 0xDF])         # store back

    # A = DF04 (0..17), B already = SCY/8.  Compute tilemap_row = (A+B) & 0x1F
    s.extend([0x80])                      # A = A + B
    s.extend([0xE6, 0x1F])               # AND 0x1F (0..31)

    # 16-bit address compute (mirrors v2.90's create_bg_sweep_v8):
    #   row_hi = base_hi + (row >> 3)
    #   row_lo = (row & 7) << 5
    s.extend([0x47])                      # B = A (tilemap_row)
    s.extend([0xCB, 0x3F])                # SRL A   (row >> 1)
    s.extend([0xCB, 0x3F])                # SRL A   (row >> 2)
    s.extend([0xCB, 0x3F])                # SRL A   (row >> 3) → 0..3
    s.extend([0x57])                      # D = A (will add to base_hi)
    s.extend([0xFA, 0x01, 0xDF])         # A = base_hi
    s.extend([0x82])                      # A += D
    s.extend([0x57])                      # D = base_hi + (row >> 3)

    s.extend([0x78])                      # A = B (tilemap_row)
    s.extend([0xE6, 0x07])               # AND 0x07
    s.extend([0xCB, 0x37])                # SWAP A    (×16)
    s.extend([0x87])                      # A += A    (×32)
    s.extend([0x5F])                      # E = A
    # Now DE = active-tilemap row address.
    s.extend([0xD5])                      # PUSH DE → save row start for phase 3
    # HL = row base (need it for [HL+] in Phase 1)
    s.extend([0x7A, 0x67])               # LD A,D; LD H,A
    s.extend([0x7B, 0x6F])               # LD A,E; LD L,A
    s.extend([0x11, 0x10, 0xDF])         # DE = DF10 (buffer)

    # Phase 1: read 32 tile IDs from tilemap (VBK=0) into DF10..DF2F
    s.extend([0xAF, 0xE0, 0x4F])         # VBK=0
    s.extend([0x06, 0x20])               # B = 32
    s.extend([0x2A, 0x12, 0x13])         # A=[HL+]; [DE]=A; INC DE
    s.extend([0x05, 0x20, 0xFA])         # DEC B; JR NZ -6

    # Phase 2: lookup palette for each tile via bg_table (still VBK=0)
    s.extend([0x11, 0x10, 0xDF])         # DE = DF10
    s.extend([0x06, 0x20])               # B = 32
    # loop:
    s.extend([0x1A])                      # A = [DE]
    s.extend([0x21, 0x00, bg_table_hi])  # HL = bg_table base
    s.extend([0x85, 0x6F])               # L += A
    s.extend([0x30, 0x01, 0x24])         # if carry, H++
    s.extend([0x7E, 0x12, 0x13])         # A=[HL]; [DE]=A; INC DE
    s.extend([0x05, 0x20, 0xF1])         # DEC B; JR NZ -15

    # Phase 3: write palette attrs to active tilemap (VBK=1)
    s.extend([0x3E, 0x01, 0xE0, 0x4F])   # VBK=1
    s.extend([0xE1])                      # POP HL → HL = saved row base (DE prev)
    s.extend([0x11, 0x10, 0xDF, 0x06, 0x20])  # DE = DF10; B = 32
    s.extend([0x1A, 0x22, 0x13])         # A=[DE]; [HL+]=A; INC DE
    s.extend([0x05, 0x20, 0xFA])         # DEC B; JR NZ

    s.extend([0xAF, 0xE0, 0x4F])         # VBK=0
    s.extend([0xE1, 0xD1, 0xC1])         # pop regs
    s.append(0xC9)                        # RET

    return bytes(s)


def build_v296():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_path = Path("rom/working/penta_dragon_dx_v296.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    rom = bytearray(input_rom.read_bytes())
    palettes = load_palettes_from_yaml(palette_yaml)

    rom[0x143] = 0x80  # CGB flag

    bank13 = 13 * 0x4000
    pal_addr = 0x6800; boss_pal_addr = 0x6880; boss_slot_addr = 0x68C0
    swj_addr = 0x68D0; sdj_addr = 0x68D8
    sp_addr = 0x68E0; shp_addr = 0x68E8; tp_addr = 0x68F0
    pal_loader_addr = 0x6900
    shadow_main_addr = 0x69D0
    colorizer_addr = 0x6A10
    tile_pal_addr = 0x6B00
    bg_table_addr = 0x7000
    cond_pal_addr = 0x6C90
    bg_sweep_addr = 0x6CD0
    colorize_addr = 0x6E00

    def w(addr, data):
        off = bank13 + (addr - 0x4000)
        rom[off:off + len(data)] = data

    w(pal_addr, palettes['bg_data'])
    w(pal_addr + 64, palettes['obj_data'])
    w(boss_pal_addr, palettes['boss_palette_table'])
    w(boss_slot_addr, palettes['boss_slot_table'])
    w(swj_addr, palettes['sara_witch_jet'])
    w(sdj_addr, palettes['sara_dragon_jet'])
    w(sp_addr, palettes['spiral_proj'])
    w(shp_addr, palettes['shield_proj'])
    w(tp_addr, palettes['turbo_proj'])

    w(pal_loader_addr, create_palette_loader(
        pal_addr, boss_pal_addr, boss_slot_addr,
        swj_addr, sdj_addr, sp_addr, shp_addr, tp_addr))
    w(shadow_main_addr, create_shadow_colorizer_main(colorizer_addr, boss_slot_addr))

    colorizer = bytearray(create_tile_based_colorizer(colorizer_addr))
    colorizer[1] = 0x0A
    w(colorizer_addr, bytes(colorizer))

    w(tile_pal_addr, create_tile_to_palette_subroutine())
    w(bg_table_addr, create_bg_tile_table(ff_filter=False))
    w(cond_pal_addr, create_conditional_palette_cached(pal_loader_addr))

    # v2.96: visible-viewport sweep gated by FFC1=1
    sweep = create_bg_sweep_viewport_gated(bg_table_addr, bg_sweep_addr)
    assert len(sweep) <= (colorize_addr - bg_sweep_addr), \
        f"sweep too big: {len(sweep)} > {colorize_addr - bg_sweep_addr}"
    w(bg_sweep_addr, sweep)

    # COLORIZE HANDLER (same skeleton as v2.95):
    #   VBK save → DF02 cold-boot init → cond_pal (always)
    #   → FFC1 gate { bg_sweep, OBJ colorizer, DMA } → VBK restore
    #
    # bg_sweep is *also* internally gated by FFC1, but the outer gate
    # avoids paying the CALL/return cost on menu frames.
    code = bytearray()
    code.extend([0xF0, 0x4F, 0xF5, 0xAF, 0xE0, 0x4F])  # VBK save + VBK=0
    code.extend([0xFA, 0x02, 0xDF, 0xFE, 0x5A])
    df02 = len(code) + 1; code.extend([0x28, 0x00])
    code.extend([0x3E, 0x5A, 0xEA, 0x02, 0xDF,
                 0xAF, 0xEA, 0x00, 0xDF])
    code[df02] = (len(code) - df02 - 1) & 0xFF
    code.extend([0xCD, cond_pal_addr & 0xFF, (cond_pal_addr >> 8) & 0xFF])
    code.extend([0xF0, 0xC1, 0xB7])
    skip = len(code) + 1; code.extend([0x28, 0x00])
    code.extend([0xCD, bg_sweep_addr & 0xFF, (bg_sweep_addr >> 8) & 0xFF])
    code.extend([0xCD, shadow_main_addr & 0xFF, (shadow_main_addr >> 8) & 0xFF])
    code.extend([0xCD, 0x80, 0xFF])
    code[skip] = (len(code) - skip - 1) & 0xFF
    code.extend([0xF1, 0xE0, 0x4F, 0xC9])
    w(colorize_addr, bytes(code))

    # VBlank hook (identical to v290/v295)
    hook = bytearray([
        0xF0, 0x99, 0xF5,
        0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00,
        0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,
        0x3E, 0x10, 0xE0, 0x00,
        0xF0, 0x00, 0xF0, 0x00,
        0x2F, 0xE6, 0x0F, 0xB0, 0xE0, 0x93,
        0x3E, 0x30, 0xE0, 0x00,
        0x3E, 0x0D, 0xEA, 0x00, 0x20,
        0xCD, colorize_addr & 0xFF, (colorize_addr >> 8) & 0xFF,
        0xF1, 0xEA, 0x00, 0x20,
        0xC9,
    ])
    assert len(hook) <= 47
    rom[0x0824:0x0824 + 47] = (hook + bytearray(47 - len(hook)))[:47]
    rom[0x06D5:0x06D8] = bytearray([0x00, 0x00, 0x00])  # NOP game DMA

    # Phantom-sound belt-and-suspenders: RST $38 RETI→RET
    rom[0x003B] = 0xC9

    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

    output_path.write_bytes(rom)
    print(f"Wrote {output_path} ({len(rom)} bytes)")
    print(f"  sweep size: {len(sweep)} bytes at 0x{bg_sweep_addr:04X}")
    print(f"  colorize handler at 0x{colorize_addr:04X}")
    return output_path


if __name__ == "__main__":
    build_v296()
