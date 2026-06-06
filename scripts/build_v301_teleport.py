#!/usr/bin/env python3
"""v3.01-teleport (v4): stack-redirect approach.

The earlier attempts (CALL 0x1A2B / JP 0x1A2B from inside the VBlank IRQ)
freeze because arena init has dependencies that the IRQ context breaks:
  - 0x1A2B's CALL 0x759B + bank2:0x4000 → eventual RET wants bank 1 mapped
    (RST 0x28 inside the flow) and clean stack; we can't satisfy both from
    inside the IRQ without bank-0 space (which doesn't exist).
  - The arena per-frame loop at 0x4073 wants IRQs to drive its HALT/sync.

The PyBoy "proof" worked in MAIN-LOOP context (forced PC from a dungeon
frame). To match that in-ROM, we let the VBlank IRQ chain unwind and
execute the teleport AFTER the RETI, from a WRAM landing pad.

Architecture:
  1. Cold-boot once: copy the ~37-byte landing pad code from bank 13 ROM
     to WRAM 0xDB00 (which is executable on CGB). Sentinel: DF1E = 0x5A.
  2. Teleport routine (called every VBlank from our hook): detect combo,
     debounce, cycle boss counter, set FFBA/FFBF. Then modify the stack:
       - Read the CPU-pushed PC at SP+14 (main-loop return), save to DF20/21.
       - Overwrite SP+14 with 0xDB00 (landing pad address).
     RET normally.
  3. The IRQ chain unwinds: our routine RETs → hook tail RETs → 0x06D1
     pops its 4 saved regs → RETI. CPU pops the modified PC (= 0xDB00),
     execution resumes at the landing pad — in MAIN-LOOP context (IME=1).
  4. Landing pad at DB00: disables VBlank IRQ (so the colorize handler
     can't re-enter the teleport), keeps other IRQs, maps bank 3, EIs,
     CALLs 0x1A2B (proven safe in main-loop context). If 0x1A2B returns,
     restore IE and JP the saved main-loop PC.

WRAM allocation (DF1E-DF22):
  DF1E — landing pad copy sentinel (0x5A = copied)
  DF20/21 — saved main-loop PC low/high (for the JP back)
  DF22 — saved IE
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_v301_gdma import build_v301

BASE_OUT = Path("rom/working/penta_dragon_dx_v301.gb")
TP_OUT = Path("rom/working/penta_dragon_dx_teleport.gb")

BANK13 = 13 * 0x4000
COLORIZE_ADDR = 0x6E00
TELEPORT_ADDR = 0x6E80     # teleport check + state setup + stack redirect
LANDING_PAD_ROM_ADDR = 0x6F80  # landing pad source (gets copied to WRAM DB00)
                              # — moved from 0x6F00 because the teleport
                              # routine grew past 128 bytes and was
                              # overwriting the landing pad source.
LANDING_PAD_WRAM = 0xDB00      # runtime landing pad location

# ---- scene-aware bg_table (Phase 1a: Shalamar only) ----
# Scene-detect routine sits in the gap between landing pad and bg_table.
# bg_table variants live after attr_comp (which ends ~0x713A).
SCENE_DETECT_ADDR = 0x6FB0     # ~33 bytes; landing pad source ends ~0x6FA8
DUNGEON_TABLE_ADDR = 0x7000    # existing bg_table (unchanged)
SHALAMAR_TABLE_ADDR = 0x7200   # Shalamar arena bg_table (D880=0x0C)
# Reserve 0x7300, 0x7400, ... for additional arena tables when designed.
DF23_PREV_SCENE = 0xDF23       # WRAM byte: previous D880 value
                              # (uninitialized → first frame triggers copy
                              # to whatever the current D880 maps to)


def _bg_table_shalamar() -> bytes:
    """Scene-specific bg_table for Shalamar arena (D880=0x0C).

    Phase 1b: split body into 4 distinct palettes per part so the user
    can tune each independently (head crest, shell, upper claws, lower
    claws) in the live editor.

    Tile-ID groups derived from row positions in the initial probe:
      Rows 0-1  tiles 0x11-0x26 : head crest  → pal 4
      Rows 2-4  tiles 0x27-0x49 : upper shell → pal 6
      Rows 5-7  tiles 0x4A-0x71 : upper claws → pal 5
      Row  8    tiles 0x72-0x87 : lower body  → pal 6 (matches shell)
      Rows 9-12 tiles 0x88-0xA4 : lower claws → pal 3
    Floor (0x00, 0x01) and unused ranges default to pal 0.

    Palette choice rationale:
      pal 3 — unused in dungeon → safe "claw tip" palette
      pal 4 — unused in dungeon → safe "crest" palette
      pal 5 — hazards in dungeon (shared CRAM — tuning affects both)
      pal 6 — walls in dungeon   (shared CRAM — tuning affects both)
    Phase 2 (scene-aware CRAM contents) needed for true independence.
    """
    t = bytearray(256)
    # Head crest (rows 0-1, tiles 0x11-0x26) → pal 4
    for i in range(0x11, 0x27):
        t[i] = 4
    # Upper shell (rows 2-4, tiles 0x27-0x49) → pal 6
    for i in range(0x27, 0x4A):
        t[i] = 6
    # Upper claws (rows 5-7, tiles 0x4A-0x71) → pal 5
    for i in range(0x4A, 0x72):
        t[i] = 5
    # Lower body (row 8, tiles 0x72-0x87) → pal 6 (matches shell)
    for i in range(0x72, 0x88):
        t[i] = 6
    # Lower claws (rows 9-12, tiles 0x88-0xA4) → pal 3
    for i in range(0x88, 0xA5):
        t[i] = 3
    # 0xFF sentinel: 0 (per attrinit fix)
    t[0xFF] = 0
    return bytes(t)


def build_scene_detect(dungeon_addr: int, shalamar_addr: int) -> bytes:
    """Detect D880 scene change, swap WRAM 0xDA00 with the right bg_table.

    Reads D880 (WRAM scene state). Compares to DF23 (previous). If same,
    early RET. If different, dispatches:
      D880 == 0x0C → Shalamar table
      else         → dungeon table (default)
    Copies 256 bytes from ROM table → WRAM 0xDA00. Updates DF23.

    Called from the teleport routine (which runs every VBlank with bank
    13 mapped). Cost when scene unchanged: ~16T (read+compare+RET).
    Cost on scene change: ~16T + 256 bytes copy ≈ 4100T (well under VBlank).

    Layout: ~33 bytes.
    """
    c = bytearray()
    c.extend([0xFA, 0x80, 0xD8])          # LD A, [D880]
    c.extend([0x21, DF23_PREV_SCENE & 0xFF, (DF23_PREV_SCENE >> 8) & 0xFF])
    c.extend([0xBE])                      # CP [HL]
    c.extend([0xC8])                      # RET Z (no change — fast path)

    # Scene changed: save new value, dispatch
    c.extend([0x77])                      # LD [HL], A   (DF23 = new D880)
    c.extend([0xFE, 0x0C])                # CP 0x0C   (Shalamar?)
    j_not_shalamar = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ, not_shalamar
    c.extend([0x21, shalamar_addr & 0xFF, (shalamar_addr >> 8) & 0xFF])
    c.extend([0x18, 0x03])                # JR +3   (skip the dungeon LD HL)
    # not_shalamar target
    c[j_not_shalamar] = (len(c) - j_not_shalamar - 1) & 0xFF
    c.extend([0x21, dungeon_addr & 0xFF, (dungeon_addr >> 8) & 0xFF])

    # Copy 256 bytes: HL → DE = 0xDA00
    c.extend([0x11, 0x00, 0xDA])          # LD DE, 0xDA00
    c.extend([0x06, 0x00])                # LD B, 0   (256 iterations)
    copy_loop = len(c)
    c.extend([0x2A, 0x12, 0x13, 0x05])    # LD A,[HL+]; LD [DE],A; INC DE; DEC B
    offset = copy_loop - (len(c) + 2)
    c.extend([0x20, offset & 0xFF])       # JR NZ, copy_loop
    c.extend([0xC9])                      # RET
    return bytes(c)


def build_landing_pad() -> bytes:
    """Executable code that runs in main-loop context AFTER the RETI.

    v4 disabled VBlank IRQ to prevent colorize-handler re-entry — but that
    caused the arena loop's HALT-for-VBlank to never wake. v5: leave IRQs
    alone. The debounce flag (DF0C, set by the teleport routine before
    redirect) makes re-entrant calls to the teleport routine a no-op, so
    VBlank can fire freely during arena init / arena loop.

    Pre-conditions:
      - FFBA = target boss, FFBF = 0
      - DF20/21 = saved main-loop PC (for the fall-through JP back)
      - IME = 1 (RETI just enabled it)
      - debounce DF0C = 1 (set by teleport routine — prevents recursion)
    """
    c = bytearray()
    # Map ROM bank 3 (0x1A2B's internal CALL 0x759B is bank-3 code)
    c.extend([0x3E, 0x03])                # LD A, 3
    c.extend([0xEA, 0x00, 0x21])          # LD [0x2100], A
    c.extend([0xE0, 0x99])                # LDH [FF99], A
    # CALL the natural event-0x29 boss-entry handler. In PyBoy this never
    # returned (arena per-frame loop took over at 0x4073); if it does
    # return in mgba, we JP back to the original main-loop PC.
    c.extend([0xCD, 0x2B, 0x1A])          # CALL 0x1A2B
    # ---- post-arena: JP HL with HL = saved main-loop PC ----
    c.extend([0xFA, 0x20, 0xDF])          # LD A, [DF20]
    c.extend([0x6F])                      # LD L, A
    c.extend([0xFA, 0x21, 0xDF])          # LD A, [DF21]
    c.extend([0x67])                      # LD H, A
    c.extend([0xE9])                      # JP HL
    return bytes(c)


def build_teleport_routine() -> bytes:
    """The teleport check routine called every VBlank from our hook.

    Combo: SELECT+START (FF93 bits 2,3 = 0x0C, active high).
    Guarded to D880=0x02 (dungeon). Debounce via DF0C.
    On fire: cycle FFBA (DF0B 0..8), FFBF=0, then redirect the IRQ return.

    Stack offset to the CPU-pushed PC:
      SP+0:  return to hook (post CD 80 6E)
      SP+2:  hook's PUSH AF (saved FF99)
      SP+4:  return to 0x06D1 handler (= 0x06DF)
      SP+6:  HL pushed at 0x06D4
      SP+8:  DE pushed at 0x06D3
      SP+10: BC pushed at 0x06D2
      SP+12: AF pushed at 0x06D1
      SP+14: CPU-pushed PC (main-loop return — what RETI pops)
    """
    c = bytearray()

    # ---- Per-frame scene-detect: swap bg_table if D880 changed ----
    # Bank 13 is mapped (we're inside the colorize call chain). Reads
    # D880, compares to DF23, copies the right table to WRAM 0xDA00 on
    # change. Fast path (~16T) when scene unchanged.
    c.extend([0xCD, SCENE_DETECT_ADDR & 0xFF, (SCENE_DETECT_ADDR >> 8) & 0xFF])

    # ---- One-shot: ensure landing pad is copied to WRAM 0xDB00 ----
    # Check sentinel DF1E
    c.extend([0xFA, 0x0E, 0xDF])          # LD A, [DF1E]
    c.extend([0xFE, 0x5A])                # CP 0x5A
    j_copy_done = len(c) + 1
    c.extend([0x28, 0x00])                # JR Z, copy_done
    # Copy 40 bytes from bank13 ROM to WRAM DB00
    c.extend([0x21, LANDING_PAD_ROM_ADDR & 0xFF, (LANDING_PAD_ROM_ADDR >> 8) & 0xFF])  # LD HL, ROM_SRC
    c.extend([0x11, LANDING_PAD_WRAM & 0xFF, (LANDING_PAD_WRAM >> 8) & 0xFF])          # LD DE, WRAM_DST
    c.extend([0x06, 40])                  # LD B, 40 (max landing pad bytes)
    copy_loop = len(c)
    c.extend([0x2A])                      # LD A, [HL+]
    c.extend([0x12])                      # LD [DE], A
    c.extend([0x13])                      # INC DE
    c.extend([0x05])                      # DEC B
    offset = copy_loop - (len(c) + 2)
    c.extend([0x20, offset & 0xFF])       # JR NZ, copy_loop
    # Set sentinel only. Do NOT touch FFBA in cold-boot — writing 0xFF
    # there causes the game's dispatch tables (FFBA-indexed) to read
    # garbage and crash. First user press goes to Riff (FFBA 0→1);
    # to reach Shalamar, cycle 9 times around to wrap.
    c.extend([0x3E, 0x5A, 0xEA, 0x0E, 0xDF])  # LD A,0x5A; LD [DF0E],A
    # copy_done:
    copy_done_pos = len(c)

    # ---- Combo + guard + debounce checks ----
    # SELECT+START (bits 2,3 = 0x0C). mgba defaults: Backspace + Enter.
    c.extend([0xF0, 0x93])                # LDH A, [FF93]
    c.extend([0xE6, 0x0C])                # AND 0x0C
    c.extend([0xFE, 0x0C])                # CP 0x0C
    j_not_combo_1 = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ, not_combo

    # D880 guard: accept dungeon (0x02), splash (0x18), and any arena
    # (0x0C..0x14) so cycling between bosses works. Reject only the very
    # early uninitialized / title states (0x00, 0x01).
    c.extend([0xFA, 0x80, 0xD8])          # LD A, [D880]
    c.extend([0xFE, 0x02])                # CP 0x02
    j_not_combo_2 = len(c) + 1
    c.extend([0x38, 0x00])                # JR C, not_combo  (D880 < 2: too early)

    # Debounce: DF0C
    c.extend([0xFA, 0x0C, 0xDF])          # LD A, [DF0C]
    c.extend([0xB7])                      # OR A
    j_end_debounced = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ, end

    # Re-fire sit-out: DF1D >0 means previous arena init still settling
    # (separate from DF1F which is the colorize-skip counter).
    c.extend([0xFA, 0x1D, 0xDF])          # LD A, [DF1D]
    c.extend([0xB7])                      # OR A
    j_end_sitout = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ, end

    # ---- FIRE ----
    # Set debounce
    c.extend([0x3E, 0x01, 0xEA, 0x0C, 0xDF])  # LD A,1; LD [DF0C], A
    # Set colorize-skip frame counter DF1F = 60 (≈ 1 sec; arena init takes
    # ~10 frames in PyBoy, 60 is a safe margin before colorize re-engages)
    c.extend([0x3E, 0x3C, 0xEA, 0x1F, 0xDF])  # LD A, 60; LD [DF1F], A
    # Cycle: read FFBA, INC, wrap, write back. v11-style. With FFBA
    # initialized to 0xFF in cold-boot, first INC wraps to 0 = Shalamar.
    c.extend([0xF0, 0xBA])                # LDH A, [FFBA]
    c.extend([0x3C])                      # INC A
    c.extend([0xFE, 0x09])                # CP 9
    c.extend([0x38, 0x01])                # JR C, no_wrap
    c.extend([0xAF])                      # XOR A
    c.extend([0xE0, 0xBA])                # LDH [FFBA], A
    # Set re-fire sit-out (DF1D = 30 frames). Use DF1D so it can't be
    # accidentally re-set by the colorize-skip DF1F path.
    c.extend([0x3E, 0x1E, 0xEA, 0x1D, 0xDF])  # LD A, 30; LD [DF1D], A

    # Give the boss HP so it doesn't instantly die (which would trigger
    # the post-arena FFBA++ flow and make the cycle order weird).
    # DCBB = boss HP per CLAUDE.md.
    c.extend([0x3E, 0x80])                # LD A, 0x80
    c.extend([0xEA, 0xBB, 0xDC])          # LD [DCBB], A
    # Sara HP (DCDC = sub, DCDD = main) — give max so she doesn't die.
    c.extend([0x3E, 0xFF])                # LD A, 0xFF
    c.extend([0xEA, 0xDC, 0xDC])          # LD [DCDC], A
    c.extend([0xEA, 0xDD, 0xDC])          # LD [DCDD], A
    # FFBF = 0
    c.extend([0xAF])                      # XOR A
    c.extend([0xE0, 0xBF])                # LDH [FFBF], A

    # ---- STACK REDIRECT ----
    c.extend([0xF8, 0x0E])                # LD HL, SP+14
    c.extend([0x2A])                      # LD A, [HL+] (low byte of PC)
    c.extend([0xEA, 0x20, 0xDF])          # LD [DF20], A
    c.extend([0x7E])                      # LD A, [HL]  (high byte)
    c.extend([0xEA, 0x21, 0xDF])          # LD [DF21], A
    c.extend([0xF8, 0x0E])                # LD HL, SP+14
    c.extend([0x3E, LANDING_PAD_WRAM & 0xFF])
    c.extend([0x22])                      # LD [HL+], A
    c.extend([0x3E, (LANDING_PAD_WRAM >> 8) & 0xFF])
    c.extend([0x77])                      # LD [HL], A

    # Fire path: RET directly (skip colorize this frame too — IRQ chain
    # unwinds, RETI to landing pad → arena init runs in main-loop context)
    c.extend([0xC9])                      # RET  (fire path ends here)

    # ---- not_combo: clear debounce ----
    not_combo_pos = len(c)
    c.extend([0xAF, 0xEA, 0x0C, 0xDF])    # XOR A; LD [DF0C], A

    # ---- end ----
    # Decrement DF1D (re-fire sit-out) if > 0.
    # Decrement DF1F (colorize-skip) if > 0 — if so, RET (skip colorize).
    end_pos = len(c)
    # DF1D decrement
    c.extend([0xFA, 0x1D, 0xDF])          # LD A, [DF1D]
    c.extend([0xB7])                      # OR A
    c.extend([0x28, 0x05])                # JR Z, +5 skip dec
    c.extend([0x3D])                      # DEC A
    c.extend([0xEA, 0x1D, 0xDF])          # LD [DF1D], A
    # DF1F gate (skip colorize while > 0)
    c.extend([0xFA, 0x1F, 0xDF])          # LD A, [DF1F]
    c.extend([0xB7])                      # OR A
    c.extend([0x28, 0x05])                # JR Z, +5 → JP COLORIZE patch
    c.extend([0x3D])                      # DEC A
    c.extend([0xEA, 0x1F, 0xDF])          # LD [DF1F], A
    c.extend([0xC9])                      # RET (skip colorize)
    c.extend([0xC9])                      # RET (will be patched to JP)

    # Patch JR offsets
    def patch(pos, target):
        off = target - (pos + 1)
        assert -128 <= off <= 127, f"JR offset {off} out of range at {pos}"
        c[pos] = off & 0xFF

    patch(j_copy_done, copy_done_pos)
    patch(j_not_combo_1, not_combo_pos)
    patch(j_not_combo_2, not_combo_pos)
    patch(j_end_debounced, end_pos)
    if j_end_sitout is not None:
        patch(j_end_sitout, end_pos)

    return bytes(c)


def main():
    # 1. Build the base v3.01 production ROM
    build_v301()
    rom = bytearray(BASE_OUT.read_bytes())

    # 2. Write the landing pad source bytes in bank13 ROM at 0x6F00
    lp = build_landing_pad()
    print(f"  landing pad source: {len(lp)} bytes at bank13:0x{LANDING_PAD_ROM_ADDR:04X}")
    assert len(lp) <= 40, f"landing pad too big: {len(lp)} > 40"
    off = BANK13 + (LANDING_PAD_ROM_ADDR - 0x4000)
    rom[off:off + len(lp)] = lp

    # 2a. Scene-aware bg_table system (Phase 1a: Shalamar)
    # Write Shalamar's bg_table at the reserved ROM address.
    shalamar_table = _bg_table_shalamar()
    assert len(shalamar_table) == 256
    off = BANK13 + (SHALAMAR_TABLE_ADDR - 0x4000)
    rom[off:off + 256] = shalamar_table
    print(f"  Shalamar bg_table: 256 bytes at bank13:0x{SHALAMAR_TABLE_ADDR:04X}")

    # Write scene-detect routine. Verify we don't overrun the landing pad.
    sd = build_scene_detect(DUNGEON_TABLE_ADDR, SHALAMAR_TABLE_ADDR)
    assert SCENE_DETECT_ADDR + len(sd) <= DUNGEON_TABLE_ADDR, \
        f"scene-detect overruns dungeon table: 0x{SCENE_DETECT_ADDR + len(sd):04X} > 0x{DUNGEON_TABLE_ADDR:04X}"
    off = BANK13 + (SCENE_DETECT_ADDR - 0x4000)
    rom[off:off + len(sd)] = sd
    print(f"  scene-detect routine: {len(sd)} bytes at bank13:0x{SCENE_DETECT_ADDR:04X}")

    # 3. Write the teleport routine at bank13:0x6E80, ending with JP COLORIZE
    tp = build_teleport_routine()
    tp = bytearray(tp)
    assert tp[-1] == 0xC9, "expected RET at end"
    tp[-1] = 0xC3
    tp.append(COLORIZE_ADDR & 0xFF)
    tp.append((COLORIZE_ADDR >> 8) & 0xFF)
    print(f"  teleport routine (with JP colorize): {len(tp)} bytes at bank13:0x{TELEPORT_ADDR:04X}")
    off = BANK13 + (TELEPORT_ADDR - 0x4000)
    rom[off:off + len(tp)] = tp

    # 4. Patch VBlank hook: CALL 0x6E00 → CALL 0x6E80
    hook = rom[0x0824:0x0824 + 47]
    patched = False
    for i in range(len(hook) - 2):
        if hook[i] == 0xCD and hook[i + 1] == 0x00 and hook[i + 2] == 0x6E:
            rom[0x0824 + i + 1] = TELEPORT_ADDR & 0xFF
            rom[0x0824 + i + 2] = (TELEPORT_ADDR >> 8) & 0xFF
            patched = True
            print(f"  VBlank hook patched at 0x0824+{i}: CALL → 0x{TELEPORT_ADDR:04X}")
            break
    if not patched:
        raise SystemExit("could not find CALL 0x6E00 in VBlank hook")

    # Header checksum (recompute for safety)
    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

    TP_OUT.write_bytes(rom)
    print(f"Wrote {TP_OUT} ({len(rom)} bytes)")
    print()
    print("=== HOW TO PLAY ===")
    print("  Combo: SELECT + START (Backspace + Enter in mgba defaults)")
    print("  Cycles boss: 0 Shalamar → 1 Riff → 2 Crystal Dragon → 3 Cameo")
    print("               → 4 Ted → 5 Troop → 6 Faze → 7 Angela → 8 Penta Dragon → 0...")
    print("  Only fires in normal dungeon (D880=0x02).")


if __name__ == "__main__":
    main()
