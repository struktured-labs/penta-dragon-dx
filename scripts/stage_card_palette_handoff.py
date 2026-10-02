#!/usr/bin/env python3
"""Install the atomic STAGE-card to Stage-1 BG0 palette handoff.

The native renderer selects the completed dungeon map at fixed-bank $12EC.
Loading Stage-1 BG0 earlier recolors the outgoing STAGE card; loading it from
the next VBlank is one visible frame late. A one-shot WRAM trampoline runs at
the first dirty publication's atomic return, immediately before that native
map flip. Pure and settled publications retain their original path entirely.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib


BANK_SIZE = 0x4000
# Legacy compiler layouts placed the dirty post-copy return at $4356.  Newer
# layouts can move it by a byte while preserving the two generated post-copy
# calls.  Derive the live hook from the second call instead of silently
# declaring an installed handoff absent.
LEGACY_DIRTY_RETURN_ADDR = 0x4356
PRIVATE_BANK = 21
PRIVATE_ENTRY = 0x4000
PRIVATE_OFFSET = PRIVATE_BANK * BANK_SIZE
STAGE1_BG0_OFFSET = 13 * BANK_SIZE + (0x6800 - 0x4000)
TITLE_BG0_OFFSET = 13 * BANK_SIZE + (0x6838 - 0x4000)
HANDOFF_EXTENSION_OFFSET = 13 * BANK_SIZE + (0x5830 - 0x4000)
HANDOFF_EXTENSION_SIZE = 14
HANDOFF_SENTINEL_HRAM = 0xE1
HANDOFF_SENTINEL_VALUE = 1
PALETTE_PHASE_ADDR = 0xDF4C
STAGE1_PALETTE_PHASE = 0x11
STAGE1_ENTRY_GATE_ADDR = 0x6A33
STAGE1_ENTRY_GATE_OFFSET = 13 * BANK_SIZE + (STAGE1_ENTRY_GATE_ADDR - 0x4000)
DEFERRED_ENTRY_GATE = bytes.fromhex("FA FD DC E0 91 AF EA 5B DF 00 C3 E5 55")

# The cold arena-semantic installer copies these bank-13 fragments into
# always-mapped WRAM. The cached profile's receipt-locked image ends at $DBF0:
# six zero bytes plus its twelve-byte scene guard. The installer relocates that
# exact guard and uses the complete 18-byte tail for the one-shot dispatcher.
RUNTIME_SOURCE_B_OFFSET = 13 * BANK_SIZE + (0x56CA - 0x4000)
RUNTIME_SOURCE_C_OFFSET = 13 * BANK_SIZE + (0x56FA - 0x4000)
WRAM_FAST_ENTRY = 0xDBDF
WRAM_RETURN_ENTRY = 0xDBEE

# r347+ defers the completed-map LCDC write to this bank-13 VBlank service.
# The original Stage-card helper predates that change and therefore installs
# BG0 at the dirty compiler return, one rendered frame before the deferred map
# becomes visible.  The v2 handoff leaves the Stage-card sentinel armed at the
# dirty return and consumes it inside the exact VBlank map transaction.
VBLANK_COMMIT_ADDR = 0x73FC
VBLANK_COMMIT_OFFSET = 13 * BANK_SIZE + (VBLANK_COMMIT_ADDR - 0x4000)

NATIVE_DIRTY_RETURN_PREIMAGE = bytes.fromhex("C3 97 34")
OLD_POSTCOPY_GUARD_ENTRY = 0xDBE5
POSTCOPY_GUARD_ENTRY = 0xDBF1
OLD_POSTCOPY_GUARD = bytes.fromhex(
    "F0 BA B7 28 04 AF E0 A5 C9 C3 E2 10"
)
RELOCATED_POSTCOPY_GUARD = bytes.fromhex(
    "F0 BA B7 28 04 AF E0 01 C9 C3 E2 10"
)
CGB_FLAG_OFFSET = 0x0143
CGB_ONLY_FLAG = 0xC0


VBLANK_ATOMIC_RUNTIME = bytes.fromhex(
    "C3 97 34 " + "00 " * 15
)


def _build_vblank_atomic_commit() -> bytes:
    """Return the exact r353 map commit with an atomic Stage-1 BG0 prefix."""
    # The outer VBlank ISR has already saved AF/BC/DE/HL and bank 13 is live.
    # Eight unrolled BGPD writes are therefore safe without LCD polling.  The
    # sentinel is consumed only here, immediately before SCX/SCY/LCDC commit.
    return bytes.fromhex(
        "FA 5C DF B7 CA 1D 6F "             # no pending map -> wrapper
        "AF EA 5C DF "                      # consume pending map
        "F0 E1 B7 28 21 "                   # no Stage-card handoff -> SCX
        "AF E0 E1 "                         # consume Stage-card sentinel
        "3E 80 E0 68 "                      # BG0 byte 0, auto-increment
        "21 00 68 0E 69 "                   # bank-13 Stage-1 BG0 -> BGPD
        "2A E2 2A E2 2A E2 2A E2 "
        "2A E2 2A E2 2A E2 2A E2 "
        "3E 11 EA 4C DF "                   # arm complete palette deck
        "F0 97 FE 02 28 07 "                # stock SCX-skip policy
        "FA 00 DC E6 0F E0 43 "             # SCX
        "FA 02 DC E6 0F E0 42 "             # SCY
        "F0 C4 B7 28 10 "                   # zero -> relative fallback
        "E6 04 07 47 AF E0 C4 "             # absolute page; consume target
        "F0 40 E6 F7 B0 E0 40 18 06 "       # absolute LCDC commit
        "F0 40 EE 08 E0 40 "                # relative LCDC commit
        "C3 1D 6F"                          # established wrapper
    )


VBLANK_ATOMIC_COMMIT = _build_vblank_atomic_commit()


def _build_vblank_atomic_window_commit() -> bytes:
    """Pair the BG and Window selectors in the completed-map transaction.

    r356 made the palette/map handoff atomic, but its map commit changed only
    LCDC.3.  If that commit landed on the SELECT-menu close edge, LCDC.6 could
    still name the same physical map.  The now-hidden Window's red/green item
    rows then became the gameplay BG until another movement publication.

    Keep LCDC.6 opposite LCDC.3 on both absolute and relative commits.  Bit 6
    is inert while the Window is disabled, and establishing the invariant
    there also makes the next menu entry safe before its native selector runs.
    """
    return bytes.fromhex(
        "FA 5C DF B7 CA 1D 6F "             # no pending map -> wrapper
        "AF EA 5C DF "                      # consume pending map
        "F0 E1 B7 28 21 "                   # no Stage-card handoff -> SCX
        "AF E0 E1 "                         # consume Stage-card sentinel
        "3E 80 E0 68 "                      # BG0 byte 0, auto-increment
        "21 00 68 0E 69 "                   # bank-13 Stage-1 BG0 -> BGPD
        "2A E2 2A E2 2A E2 2A E2 "
        "2A E2 2A E2 2A E2 2A E2 "
        "3E 11 EA 4C DF "                   # arm complete palette deck
        "F0 97 FE 02 28 07 "                # stock SCX-skip policy
        "FA 00 DC E6 0F E0 43 "             # SCX
        "FA 02 DC E6 0F E0 42 "             # SCY
        "F0 C4 B7 28 17 "                   # zero -> relative fallback
        "E6 04 07 47 "                      # B = absolute BG-map bit 3
        "EE 08 07 07 07 B0 47 "             # B += opposite Window bit 6
        "AF E0 C4 "                         # consume absolute target
        "F0 40 E6 B7 B0 E0 40 18 06 "       # commit paired selectors
        "F0 40 EE 48 E0 40 "                # toggle both selectors
        "C3 1D 6F"                          # established wrapper
    )


VBLANK_ATOMIC_WINDOW_COMMIT = _build_vblank_atomic_window_commit()


def _build_vblank_atomic_stage1_window_commit() -> bytes:
    """Pair BG/Window selectors only in live Stage-1 gameplay.

    The r357 transaction fixed the Stage-1 SELECT-close race, but applying its
    Window-selector invariant to every scene changed unrelated stage timing
    and presentation state.  Preserve the exact r356 selector behavior for
    every non-Stage-1 scene while retaining the paired selector in D880=$02.
    """
    return bytes.fromhex(
        "FA 5C DF B7 CA 1D 6F "             # no pending map -> wrapper
        "AF EA 5C DF "                      # consume pending map
        "F0 E1 B7 28 21 "                   # no Stage-card handoff -> SCX
        "AF E0 E1 "                         # consume Stage-card sentinel
        "3E 80 E0 68 "                      # BG0 byte 0, auto-increment
        "21 00 68 0E 69 "                   # bank-13 Stage-1 BG0 -> BGPD
        "2A E2 2A E2 2A E2 2A E2 "
        "2A E2 2A E2 2A E2 2A E2 "
        "3E 11 EA 4C DF "                   # arm complete palette deck
        "F0 97 FE 02 28 07 "                # stock SCX-skip policy
        "FA 00 DC E6 0F E0 43 "             # SCX
        "FA 02 DC E6 0F E0 42 "             # SCY
        "F0 C4 B7 28 1E "                   # zero -> relative fallback
        "E6 04 07 47 "                      # B = absolute BG-map bit 3
        "FA 80 D8 FE 02 20 07 "             # other scenes keep r356 mask
        "78 B7 20 02 3E 40 47 "             # add opposite Window bit 6
        "AF E0 C4 "                         # consume absolute target
        "F0 40 E6 F7 B0 E0 40 18 11 "       # commit selected mask
        "F0 40 47 FA 80 D8 FE 02 78 20 02 " # relative scene discriminator
        "EE 40 EE 08 E0 40 "                # Stage 1 XOR $48; others XOR $08
        "C3 1D 6F"                          # established wrapper
    )


VBLANK_ATOMIC_STAGE1_WINDOW_COMMIT = (
    _build_vblank_atomic_stage1_window_commit()
)


def _build_vblank_atomic_stage1_only_window_commit() -> bytes:
    """Pair selectors only when both the scene and stage identify Stage 1.

    D880=$02 identifies gameplay, not Stage 1 by itself. r358 therefore still
    changed the other dungeons. FFBA=$00 is the native Stage-1 index used by
    the existing palette handoff and completes the scope discriminator.
    """
    return bytes.fromhex(
        "FA 5C DF B7 CA 1D 6F "             # no pending map -> wrapper
        "AF EA 5C DF "                      # consume pending map
        "F0 E1 B7 28 21 "                   # no Stage-card handoff -> SCX
        "AF E0 E1 "                         # consume Stage-card sentinel
        "3E 80 E0 68 "                      # BG0 byte 0, auto-increment
        "21 00 68 0E 69 "                   # bank-13 Stage-1 BG0 -> BGPD
        "2A E2 2A E2 2A E2 2A E2 "
        "2A E2 2A E2 2A E2 2A E2 "
        "3E 11 EA 4C DF "                   # arm complete palette deck
        "F0 97 FE 02 28 07 "                # stock SCX-skip policy
        "FA 00 DC E6 0F E0 43 "             # SCX
        "FA 02 DC E6 0F E0 42 "             # SCY
        "F0 C4 B7 28 23 "                   # zero -> relative fallback
        "E6 04 07 47 "                      # B = absolute BG-map bit 3
        "FA 80 D8 FE 02 20 0C "             # non-gameplay keeps r356 mask
        "F0 BA B7 20 07 "                   # non-Stage-1 keeps r356 mask
        "78 B7 20 02 3E 40 47 "             # add opposite Window bit 6
        "AF E0 C4 "                         # consume absolute target
        "F0 40 E6 F7 B0 E0 40 18 17 "       # commit selected mask
        "F0 40 47 FA 80 D8 FE 02 20 0A "    # relative scene discriminator
        "F0 BA B7 20 05 "                   # relative stage discriminator
        "78 EE 48 18 03 78 EE 08 E0 40 "    # Stage 1 XOR $48; others XOR $08
        "C3 1D 6F"                          # established wrapper
    )


VBLANK_ATOMIC_STAGE1_ONLY_WINDOW_COMMIT = (
    _build_vblank_atomic_stage1_only_window_commit()
)


def _build_vblank_atomic_window_fast_commit() -> bytes:
    """Pair selectors with the smallest reviewed VBlank transaction.

    The absolute target is only zero or bit 2. After rotating it into LCDC.3,
    a two-way branch selects either bit 3 or the opposite bit 6 directly.
    This replaces r357's seven-byte/cycle derivation overhead with four bytes
    and 3--4 cycles; the relative path still needs only XOR $48.
    """
    return bytes.fromhex(
        "FA 5C DF B7 CA 1D 6F "             # no pending map -> wrapper
        "AF EA 5C DF "                      # consume pending map
        "F0 E1 B7 28 21 "                   # no Stage-card handoff -> SCX
        "AF E0 E1 "                         # consume Stage-card sentinel
        "3E 80 E0 68 "                      # BG0 byte 0, auto-increment
        "21 00 68 0E 69 "                   # bank-13 Stage-1 BG0 -> BGPD
        "2A E2 2A E2 2A E2 2A E2 "
        "2A E2 2A E2 2A E2 2A E2 "
        "3E 11 EA 4C DF "                   # arm complete palette deck
        "F0 97 FE 02 28 07 "                # stock SCX-skip policy
        "FA 00 DC E6 0F E0 43 "             # SCX
        "FA 02 DC E6 0F E0 42 "             # SCY
        "F0 C4 B7 28 14 "                   # zero -> relative fallback
        "E6 04 07 20 02 3E 40 47 "          # paired selector mask in B
        "AF E0 C4 "                         # consume absolute target
        "F0 40 E6 B7 B0 E0 40 18 06 "       # commit paired selectors
        "F0 40 EE 48 E0 40 "                # toggle both selectors
        "C3 1D 6F"                          # established wrapper
    )


VBLANK_ATOMIC_WINDOW_FAST_COMMIT = _build_vblank_atomic_window_fast_commit()


def _build_vblank_atomic_window_robust_commit() -> bytes:
    """Pair selectors even when the relative path starts from an alias.

    r360 minimized the absolute path but its relative XOR preserved a
    pre-existing alias. Derive the next paired mask from the current BG bit,
    clear both selector bits, and OR the mask back. This costs six cycles over
    r356 only on the relative half of publications and is independent of the
    incoming Window selector.
    """
    return bytes.fromhex(
        "FA 5C DF B7 CA 1D 6F "             # no pending map -> wrapper
        "AF EA 5C DF "                      # consume pending map
        "F0 E1 B7 28 21 "                   # no Stage-card handoff -> SCX
        "AF E0 E1 "                         # consume Stage-card sentinel
        "3E 80 E0 68 "                      # BG0 byte 0, auto-increment
        "21 00 68 0E 69 "                   # bank-13 Stage-1 BG0 -> BGPD
        "2A E2 2A E2 2A E2 2A E2 "
        "2A E2 2A E2 2A E2 2A E2 "
        "3E 11 EA 4C DF "                   # arm complete palette deck
        "F0 97 FE 02 28 07 "                # stock SCX-skip policy
        "FA 00 DC E6 0F E0 43 "             # SCX
        "FA 02 DC E6 0F E0 42 "             # SCY
        "F0 C4 B7 28 14 "                   # zero -> relative fallback
        "E6 04 07 20 02 3E 40 47 "          # paired selector mask in B
        "AF E0 C4 "                         # consume absolute target
        "F0 40 E6 B7 B0 E0 40 18 13 "       # commit paired selectors
        "F0 40 E6 08 D6 01 9F E6 48 EE 40 " # derive $08/$40 from BG bit
        "47 F0 40 E6 B7 B0 E0 40 "          # clear/replace both selectors
        "C3 1D 6F"                          # established wrapper
    )


VBLANK_ATOMIC_WINDOW_ROBUST_COMMIT = (
    _build_vblank_atomic_window_robust_commit()
)


def _build_vblank_atomic_window_final_commit() -> bytes:
    """Alias-safe paired selectors with an explicit post-RLCA zero test.

    LR35902 RLCA always clears Z. r360/r361 branched on that cleared flag,
    making the zero absolute target produce no Window bit. OR A restores the
    intended zero/nonzero test after rotating target bit 2 into LCDC.3.
    """
    return bytes.fromhex(
        "FA 5C DF B7 CA 1D 6F "             # no pending map -> wrapper
        "AF EA 5C DF "                      # consume pending map
        "F0 E1 B7 28 21 "                   # no Stage-card handoff -> SCX
        "AF E0 E1 "                         # consume Stage-card sentinel
        "3E 80 E0 68 "                      # BG0 byte 0, auto-increment
        "21 00 68 0E 69 "                   # bank-13 Stage-1 BG0 -> BGPD
        "2A E2 2A E2 2A E2 2A E2 "
        "2A E2 2A E2 2A E2 2A E2 "
        "3E 11 EA 4C DF "                   # arm complete palette deck
        "F0 97 FE 02 28 07 "                # stock SCX-skip policy
        "FA 00 DC E6 0F E0 43 "             # SCX
        "FA 02 DC E6 0F E0 42 "             # SCY
        "F0 C4 B7 28 15 "                   # zero -> relative fallback
        "E6 04 07 B7 20 02 3E 40 47 "       # paired selector mask in B
        "AF E0 C4 "                         # consume absolute target
        "F0 40 E6 B7 B0 E0 40 18 13 "       # commit paired selectors
        "F0 40 E6 08 D6 01 9F E6 48 EE 40 " # derive $08/$40 from BG bit
        "47 F0 40 E6 B7 B0 E0 40 "          # clear/replace both selectors
        "C3 1D 6F"                          # established wrapper
    )


VBLANK_ATOMIC_WINDOW_FINAL_COMMIT = _build_vblank_atomic_window_final_commit()


def _build_vblank_atomic_window_fast_final_commit() -> bytes:
    """Use the corrected absolute zero test and zero-overhead relative XOR.

    Once every absolute publication establishes the paired invariant, XOR
    $48 preserves it on relative flips. This keeps r362's visual correctness
    while restoring the r356 relative-path cycle count for music and Stage 6.
    """
    return bytes.fromhex(
        "FA 5C DF B7 CA 1D 6F "             # no pending map -> wrapper
        "AF EA 5C DF "                      # consume pending map
        "F0 E1 B7 28 21 "                   # no Stage-card handoff -> SCX
        "AF E0 E1 "                         # consume Stage-card sentinel
        "3E 80 E0 68 "                      # BG0 byte 0, auto-increment
        "21 00 68 0E 69 "                   # bank-13 Stage-1 BG0 -> BGPD
        "2A E2 2A E2 2A E2 2A E2 "
        "2A E2 2A E2 2A E2 2A E2 "
        "3E 11 EA 4C DF "                   # arm complete palette deck
        "F0 97 FE 02 28 07 "                # stock SCX-skip policy
        "FA 00 DC E6 0F E0 43 "             # SCX
        "FA 02 DC E6 0F E0 42 "             # SCY
        "F0 C4 B7 28 15 "                   # zero -> relative fallback
        "E6 04 07 B7 20 02 3E 40 47 "       # paired selector mask in B
        "AF E0 C4 "                         # consume absolute target
        "F0 40 E6 B7 B0 E0 40 18 06 "       # commit paired selectors
        "F0 40 EE 48 E0 40 "                # preserve invariant on toggle
        "C3 1D 6F"                          # established wrapper
    )


VBLANK_ATOMIC_WINDOW_FAST_FINAL_COMMIT = (
    _build_vblank_atomic_window_fast_final_commit()
)

# r374 leaves late ISR work pending instead of publishing during scanout.
VBLANK_GUARDED_COMMIT = (
    bytes.fromhex("C3 64 74 00") + VBLANK_ATOMIC_WINDOW_FAST_FINAL_COMMIT[4:]
)
VBLANK_COMMIT_GUARD_OFFSET = 13 * BANK_SIZE + 0x3464
VBLANK_COMMIT_GUARD = bytes.fromhex(
    "F0 44 E6 FC FE 90 C2 1D 6F FA 5C DF B7 C3 00 74"
)


class _Asm:
    def __init__(self, origin: int) -> None:
        self.origin = origin
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.rel8: list[tuple[int, str]] = []
        self.abs16: list[tuple[int, str]] = []

    @property
    def pc(self) -> int:
        return self.origin + len(self.code)

    def db(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def label(self, name: str) -> None:
        assert name not in self.labels
        self.labels[name] = self.pc

    def jr(self, opcode: int, label: str) -> None:
        self.db(opcode, 0)
        self.rel8.append((len(self.code) - 1, label))

    def call(self, label: str) -> None:
        self.db(0xCD, 0, 0)
        self.abs16.append((len(self.code) - 2, label))

    def finish(self) -> bytes:
        for operand, label in self.rel8:
            target = self.labels[label]
            source_after = self.origin + operand + 1
            delta = target - source_after
            assert -128 <= delta <= 127, (label, delta)
            self.code[operand] = delta & 0xFF
        for operand, label in self.abs16:
            target = self.labels[label]
            self.code[operand] = target & 0xFF
            self.code[operand + 1] = target >> 8
        return bytes(self.code)


@dataclass(frozen=True)
class StageCardHandoffReport:
    hook_address: int
    bridge_address: int
    private_bank: int
    private_entry: int
    helper_size: int
    discriminator_index: int
    title_discriminator: int
    stage1_bg0: str


def _choose_discriminator(stage1_bg0: bytes, title_bg0: bytes) -> int:
    for index in range(2, 8):
        if stage1_bg0[index] != title_bg0[index]:
            return index
    raise AssertionError(
        "Stage-1 and title BG0 rows have no non-color-0 discriminator"
    )


def _build_private_helper(
    stage1_bg0: bytes,
    discriminator_index: int,
    title_discriminator: int,
    *,
    arm_palette_phase: bool = True,
) -> bytes:
    a = _Asm(PRIVATE_ENTRY)
    a.db(0xC5, 0xD5, 0xE5)                 # preserve BC, DE, HL
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x02)     # exact gameplay scene D880=$02
    a.jr(0x20, "restore")
    a.db(0xF0, 0xBA, 0xB7)                 # Stage 1 has FFBA=$00
    a.jr(0x20, "restore")

    # Save BCPS, then inspect one YAML-derived BG0 byte at a fresh LCD-safe
    # interval. Accept either the outgoing title row (which must be replaced)
    # or the already-correct Stage-1 row. Any third palette fails closed and
    # leaves the one-shot armed for the next completed map flip.
    a.db(0xF0, 0x68, 0x47)                 # B = caller BCPS
    a.call("wait_cram")
    a.db(0x3E, discriminator_index, 0xE0, 0x68)
    a.db(0xF0, 0x69, 0xFE, title_discriminator)
    a.jr(0x28, "write_stage1")
    a.db(0xFE, stage1_bg0[discriminator_index])
    a.jr(0x20, "restore_bcps")
    a.jr(0x18, "mark_complete")

    a.label("write_stage1")
    a.db(0x3E, 0x80, 0xE0, 0x68)           # BG0 byte 0, auto-increment
    a.db(0x21, 0x00, 0x00)                 # patched to embedded BG0 row
    data_operand = len(a.code) - 2
    a.db(0x0E, 0x69)                       # C = BGPD
    a.call("copy_cram4")
    a.call("copy_cram4")
    a.label("mark_complete")
    a.db(0xAF, 0xE0, HANDOFF_SENTINEL_HRAM)
    # Arm the complete Stage-1 palette deck only at the same atomic boundary
    # that installs BG0 and flips to the completed dungeon map.  Arming DF4C
    # on the earlier D880=$02 transition left a short hardware-dependent
    # window in which Pocket/SameBoy could recolor the outgoing STAGE card.
    if arm_palette_phase:
        a.db(
            0x3E, STAGE1_PALETTE_PHASE,
            0xEA, PALETTE_PHASE_ADDR & 0xFF, PALETTE_PHASE_ADDR >> 8,
        )

    a.label("restore_bcps")
    a.db(0x78, 0xE0, 0x68)
    a.label("restore")
    a.db(0xE1, 0xD1, 0xC1)

    # Stock $0061 restores bank 1 and returns to the always-mapped continuation
    # at $DBEE, which tail-jumps into the unchanged atomic wrapper. Interrupts
    # deliberately remain disabled until that wrapper restores IE and executes
    # its receipt-proven RETI.
    a.db(
        0x21, WRAM_RETURN_ENTRY & 0xFF, WRAM_RETURN_ENTRY >> 8,
        0xE5,
        0x3E, 0x01,
        0xC3, 0x61, 0x00,
    )

    # Palette RAM is inaccessible in mode 3. Match the established production
    # copier: VBlank/LCD-off writes immediately; otherwise wait through mode 3
    # to the beginning of a fresh HBlank. Four unrolled writes fit there.
    a.label("wait_cram")
    a.db(0xF0, 0x40, 0xCB, 0x7F)
    a.jr(0x28, "wait_done")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x01)
    a.jr(0x28, "wait_done")
    a.label("wait_mode3")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, "wait_mode3")
    a.label("wait_mode0")
    a.db(0xF0, 0x41, 0xE6, 0x03)
    a.jr(0x20, "wait_mode0")
    a.label("wait_done")
    a.db(0xC9)

    a.label("copy_cram4")
    a.call("wait_cram")
    for _ in range(4):
        a.db(0x2A, 0xE2)
    a.db(0xC9)

    data_address = a.pc
    a.code[data_operand] = data_address & 0xFF
    a.code[data_operand + 1] = data_address >> 8
    a.db(*stage1_bg0)
    return a.finish()


def _runtime_payloads() -> tuple[bytes, bytes]:
    # Hot path: sentinel zero tail-jumps directly to the existing atomic
    # wrapper. The exact value 1 is established inline by the scene-transition
    # service; the slow path maps private bank 21 with interrupts disabled.
    fast = bytes.fromhex(
        "F0 E1 B7 CA 97 34 F3 3E 15 EA 00 21 C3 00 40"
    )
    continuation = bytes.fromhex("C3 97 34")
    assert len(fast) == 15
    assert len(continuation) == 3
    return fast, continuation


def _source_runtime_image(rom: bytes | bytearray) -> bytes:
    return bytes(rom[RUNTIME_SOURCE_B_OFFSET:RUNTIME_SOURCE_B_OFFSET + 36]) + bytes(
        rom[RUNTIME_SOURCE_C_OFFSET:RUNTIME_SOURCE_C_OFFSET + 5]
    )


def _postcopy_call_sites(
    rom: bytes | bytearray, entry: int,
) -> list[int]:
    return [
        address
        for address in range(0x42A7, 0x436E)
        if rom[address] in (0xCD, 0xC4)
        and bytes(rom[address + 1:address + 3])
        == bytes([entry & 0xFF, entry >> 8])
    ]


def _dirty_return_address(postcopy_call_sites: list[int]) -> int:
    if len(postcopy_call_sites) == 2:
        return max(postcopy_call_sites) + 3
    return LEGACY_DIRTY_RETURN_ADDR


def _inspect_release_lock_handoff(rom: bytes | bytearray) -> dict | None:
    """Static handoff identity for the exact release-lock candidate.

    Its 4f5a67b8 ancestor carries the reviewed handoff by whole-ROM identity.
    The release lock's #27 ``arena-completion-safe`` stage relocates the
    always-mapped WRAM runtime: the post-copy guard moves $DBF1 -> $DBF3
    (bank13 $5830 gains a two-byte RET/NOP prefix and the guard's JR Z/JP pair
    becomes the equivalent JP Z), and the native dirty-return bridge moves
    $DBDF -> $DBDC (still ``JP $3497``). Every other byte the handoff reads is
    outside the release-lock delta. Live card/handoff checks remain mandatory.
    """
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parent / "diagnostics"))
    import release_lock_lineage as lineage

    if not lineage.is_candidate(bytes(rom)):
        return None
    rom = bytes(rom)
    arena = {"arena-completion-safe", "arena-graphics-owner"}
    untouched_ranges = [
        (STAGE1_BG0_OFFSET, STAGE1_BG0_OFFSET + 8),
        (TITLE_BG0_OFFSET, TITLE_BG0_OFFSET + 8),
        (PRIVATE_OFFSET, PRIVATE_OFFSET + 0x80),
        (STAGE1_ENTRY_GATE_OFFSET, STAGE1_ENTRY_GATE_OFFSET + 13),
        (13 * BANK_SIZE + 0x7CFC - 0x4000, 13 * BANK_SIZE + 0x7D2D - 0x4000),
        (VBLANK_COMMIT_OFFSET, VBLANK_COMMIT_OFFSET + 0x100),
        (CGB_FLAG_OFFSET, CGB_FLAG_OFFSET + 1),
    ]
    clean = all(not lineage.touched(a, b) for a, b in untouched_ranges)
    # Fail closed unless only #27 arena runs reach the relocated components.
    for start, end in ((0x42A7, 0x436E),
                       (RUNTIME_SOURCE_B_OFFSET - 0x30, RUNTIME_SOURCE_C_OFFSET + 5),
                       (HANDOFF_EXTENSION_OFFSET, HANDOFF_EXTENSION_OFFSET + 12)):
        lineage.ancestor_bytes(rom, start, end, arena)
    parent = lineage.ancestor_bytes(rom, 0, 32 * BANK_SIZE, set().union(
        *lineage.RUN_OWNERS.values()))
    if hashlib.sha256(parent).hexdigest() != lineage.SARA_SHA256:
        return None
    result = inspect_stage_card_palette_handoff(parent)
    sites = _postcopy_call_sites(rom, POSTCOPY_GUARD_ENTRY + 2)
    hook = max(sites) + 3 if len(sites) == 2 else LEGACY_DIRTY_RETURN_ADDR
    # WRAM image: bank13 $569A/36, $56CA/36, $56FA/5 at $DBA4, guard at $DBF1.
    bridge = 0xDBDC
    bridge_source = 13 * BANK_SIZE + (0x56CA - 0x4000) + (bridge - 0xDBC8)
    guard = HANDOFF_EXTENSION_OFFSET
    relocated = (
        len(sites) == 2
        and rom[hook:hook + 3] == bytes((0xC3, bridge & 0xFF, bridge >> 8))
        and rom[bridge_source:bridge_source + 3] == NATIVE_DIRTY_RETURN_PREIMAGE
        and rom[guard:guard + 12] == bytes.fromhex(
            "C9 00 F0 BA B7 CA E2 10 AF E0 01 C9")
        and parent[guard:guard + 12] == RELOCATED_POSTCOPY_GUARD
    )
    result = dict(result)
    result.update({
        "installed": bool(result["installed"] and clean and relocated),
        "variant": "release-lock-relocated-" + str(result.get("variant")),
        "hook_address": hook,
        "bridge_address": bridge,
        "postcopy_call_sites": sites,
    })
    return result


def inspect_stage_card_palette_handoff(rom: bytes | bytearray) -> dict:
    release_lock = _inspect_release_lock_handoff(rom)
    if release_lock is not None:
        return release_lock
    stage1_bg0 = bytes(rom[STAGE1_BG0_OFFSET:STAGE1_BG0_OFFSET + 8])
    title_bg0 = bytes(rom[TITLE_BG0_OFFSET:TITLE_BG0_OFFSET + 8])
    discriminator = _choose_discriminator(stage1_bg0, title_bg0)
    helper = _build_private_helper(
        stage1_bg0, discriminator, title_bg0[discriminator]
    )
    fast, continuation = _runtime_payloads()
    runtime = _source_runtime_image(rom)
    dirty_return = bytes.fromhex("C3 DF DB")
    transition_service = bytes(
        rom[
            13 * BANK_SIZE + (0x7CFC - 0x4000):
            13 * BANK_SIZE + (0x7CFC - 0x4000) + 0x31
        ]
    )
    inline_arm_count = transition_service.count(bytes.fromhex("3C E0 E1 18"))
    postcopy_call_sites = _postcopy_call_sites(rom, POSTCOPY_GUARD_ENTRY)
    dirty_return_address = _dirty_return_address(postcopy_call_sites)
    expected_postcopy_guard = (
        RELOCATED_POSTCOPY_GUARD
        if rom[CGB_FLAG_OFFSET] == CGB_ONLY_FLAG
        else OLD_POSTCOPY_GUARD
    )
    # r441 retains the palette helper and trampoline. Its r436 entry seeds
    # one complete art upload, and its r383/r404 commit consumes the latched
    # page/scroll snapshot rather than rereading mutable live coordinates.
    # Restrict recognition to the reviewed whole ROM as well as exact code.
    identity = hashlib.sha256(rom).hexdigest()
    # r453 recovers r446's qualified later-stage publication entry on the d82
    # image.  It preserves an independently replayed Stage-card contract
    # (stable title/card BG0, atomic first dungeon map, and blank-SRAM route)
    # but no longer carries any of the superseded VBlank commit byte layouts
    # below.  Pin the whole reviewed image: a one-byte mutation, including a
    # checksum mutation, cannot be recognized as this route.
    r453_runtime_receipted = identity == (
        "15ab73c3c04a3caf1c4186335a073ca49b5dc21199335ca9d85eca56ad7da21b"
    )
    # r455 preserves the inherited handoff bytes. current50's live card
    # checks pass; its only rejection was this absent static identity.
    r455_runtime_receipted = identity in {
        "6e5e7a61ddd1a44c0db6aed123528477c5531716fa16d73b083c67d64abfcbe9",
        # r456c changes only the attract-entry call, bank18 service/checksum.
        "8234bd8400f7284d115fe622ccccd44bc354e4b5322591c24332028c83dcb2b4",
        "69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722",
        # r527 inherits this complete handoff while changing ending-only code.
        "13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b",
        # r528 changes only the four-byte BG palette publisher path.
        "e8da7fde311acecc6b2fa052a501b18636c7c416091db9df329d59f07fdf5b50",
        # r529 corrects only r528's register-restore order.
        "5c49fa5d01a91b2b07e7546d4bd6856cb23697678690cf2e6b734d3fa10ec208",
        # r530 confines changes to the same four-byte publisher path.
        "46b498d85bb50f44fac92c6ee67d362236e66cecc3f372df22e7defe2b87aa30",
        # r531 restores the inherited VBlank fast path inside that publisher.
        "9d44e9d1c03c60e95b91f76752a47d5631cf6062188a7ef80667a289af569855",
        # r532 preserves caller IME while masking the same publisher window.
        "055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821",
        # r533 changes only the neutral story-row dispatch marker.
        "4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba",
        # r534 changes only the private Stage-4 cache key in bank 22.
        "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b",
        # Exact r535 menu/title trial: current557 passes every rendered,
        # palette, replay and stock-timing check in all four DX routes.
        # Its disjoint close/title-clear overlays leave the inherited
        # dungeon map-flip/palette handoff bytes unchanged. This recognizes
        # only that component, not release readiness or the loading report.
        "4f19c05227258db33e0432627443dc9a43207f055ea8c51add6615aa0df4a104",
        # Scoped successor restores the original attract/story rearm while
        # preserving only the scene-00 outgoing title; same dungeon handoff.
        "951e770e4a631f52056d881d7e6577b3d669c9a0566c0310a7299df6a91147d5",
        # Actual GAME START is identified by its existing DF4C=$A0 marker;
        # idle scene-00 title transitions retain their original cleanup.
        "2db9f03cd772e75367a219a73610007c2446655cfb7a27873ddaae3a62c816cd",
        # Same title/menu repair, with new calls on the cold fallback only.
        "69ff940ace8e73e82aa5331dde39282d191814c4ca1b814afb19a13fbb6dc197",
        # Menu repair plus early tile retirement; inherited dungeon handoff
        # bytes are unchanged. This is component identity, not release approval.
        "681b4668446c547644aaa4924ca0d6dd44782dc59133540c59708fa160c178d3",
        # Cold loader blanks BG0 only after the native card wait/fade; this
        # exact composition retains the independently checked atomic restore.
        "fe14b0e3c392b3d822208684636e1017cb093613d28e6ca477999535df164576",
        "b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350",  # r536: inherited observer/data ABI
        "e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b",  # title row guard: unchanged gameplay observer/data ABI
        "c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d",  # exact death/restart successor; handoff bytes unchanged
        "4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5",  # #6: only OAM emitters/checksum differ; handoff bytes unchanged
        # Stage-1-only successor keeps the same independently checked handoff.
        "b691c96c7477473e05f2304705f132c696997dbd2b3a639a35be4cef3713fc96",
        "ffb6a829cfdbf41fc5b2ebd5f6691a5a5bf5fd6ce5bad4dc7ab2e6c874d15f63",
    }
    # Exact reviewed compositions retain the reload body but move the request
    # out of stock FFE1. Verify both arm/consume caves, not just their identity.
    dealias_test = {
        '6b375a8080df3c982f63a92ea0a679241d8c77cf370776d38bd5b4be8c101e35': 0x7701,
        '20db07d52dbfdfd760dd3270dd8280cbe5bd882fddc70e2fdf24cede822f7127': 0x7703,
        'baeeb893cf5cd47192273b18eaf9d1bc7902f9ab55da2b3306d2e32db00fcebe': 0x7703,
    }.get(identity)
    dealias_arm = False
    if dealias_test is not None:
        cave = 13 * BANK_SIZE + dealias_test - 0x4000
        setter = dealias_test + 22
        dealias_arm = (
            bytes(rom[cave:cave+29]) == bytes.fromhex(
                'FA80D8 FE02 C22D74 FA5DDF 3D C22D74 AF EA5DDF C30F74 3C EA5DDF C3267D')
            and bytes(rom[0x37D18:0x37D1D]) == bytes((0xC3,setter&255,setter>>8,0,0))
            and inline_arm_count == 0
        )
    r441_identity = identity in {
        '44ac932aca17701ae97596fd511f77fa0eae8f98761d61e618262a7f71bf9702',
        'ea53ebb1f8cef8480b6ad3b4472b74f11bab6b0ea9f03660ea8e5ca7bcde1a46',
    } or dealias_test is not None
    r441_entry = bytes.fromhex('FA FD DC E0 91 3E 02 EA 5B DF C3 E5 55')
    entry_bytes = bytes(rom[STAGE1_ENTRY_GATE_OFFSET:
                            STAGE1_ENTRY_GATE_OFFSET + len(DEFERRED_ENTRY_GATE)])
    common_installed = (
        bytes(
            rom[dirty_return_address:dirty_return_address + 3]
        ) == dirty_return
        and (inline_arm_count == 1 or dealias_arm)
        and bytes(
            rom[
                HANDOFF_EXTENSION_OFFSET:
                HANDOFF_EXTENSION_OFFSET + len(expected_postcopy_guard)
            ]
        ) == expected_postcopy_guard
        and len(postcopy_call_sites) == 2
        and bytes(rom[PRIVATE_OFFSET:PRIVATE_OFFSET + len(helper)]) == helper
        and (entry_bytes == DEFERRED_ENTRY_GATE
             or (r441_identity and entry_bytes == r441_entry))
    )
    legacy_installed = common_installed and runtime[23:41] == fast + continuation
    vblank_atomic_v2_installed = (
        common_installed
        and runtime[23:41] == VBLANK_ATOMIC_RUNTIME
        and bytes(
            rom[
                VBLANK_COMMIT_OFFSET:
                VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_COMMIT)
            ]
        ) == VBLANK_ATOMIC_COMMIT
    )
    vblank_atomic_window_installed = (
        common_installed
        and runtime[23:41] == VBLANK_ATOMIC_RUNTIME
        and bytes(
            rom[
                VBLANK_COMMIT_OFFSET:
                VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_WINDOW_COMMIT)
            ]
        ) == VBLANK_ATOMIC_WINDOW_COMMIT
    )
    vblank_atomic_stage1_window_installed = (
        common_installed
        and runtime[23:41] == VBLANK_ATOMIC_RUNTIME
        and bytes(
            rom[
                VBLANK_COMMIT_OFFSET:
                VBLANK_COMMIT_OFFSET
                + len(VBLANK_ATOMIC_STAGE1_WINDOW_COMMIT)
            ]
        ) == VBLANK_ATOMIC_STAGE1_WINDOW_COMMIT
    )
    vblank_atomic_stage1_only_window_installed = (
        common_installed
        and runtime[23:41] == VBLANK_ATOMIC_RUNTIME
        and bytes(
            rom[
                VBLANK_COMMIT_OFFSET:
                VBLANK_COMMIT_OFFSET
                + len(VBLANK_ATOMIC_STAGE1_ONLY_WINDOW_COMMIT)
            ]
        ) == VBLANK_ATOMIC_STAGE1_ONLY_WINDOW_COMMIT
    )
    vblank_atomic_window_fast_installed = (
        common_installed
        and runtime[23:41] == VBLANK_ATOMIC_RUNTIME
        and bytes(
            rom[
                VBLANK_COMMIT_OFFSET:
                VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_WINDOW_FAST_COMMIT)
            ]
        ) == VBLANK_ATOMIC_WINDOW_FAST_COMMIT
    )
    vblank_atomic_window_robust_installed = (
        common_installed
        and runtime[23:41] == VBLANK_ATOMIC_RUNTIME
        and bytes(
            rom[
                VBLANK_COMMIT_OFFSET:
                VBLANK_COMMIT_OFFSET
                + len(VBLANK_ATOMIC_WINDOW_ROBUST_COMMIT)
            ]
        ) == VBLANK_ATOMIC_WINDOW_ROBUST_COMMIT
    )
    vblank_atomic_window_final_installed = (
        common_installed
        and runtime[23:41] == VBLANK_ATOMIC_RUNTIME
        and bytes(
            rom[
                VBLANK_COMMIT_OFFSET:
                VBLANK_COMMIT_OFFSET + len(VBLANK_ATOMIC_WINDOW_FINAL_COMMIT)
            ]
        ) == VBLANK_ATOMIC_WINDOW_FINAL_COMMIT
    )
    vblank_atomic_window_fast_final_installed = (
        common_installed
        and runtime[23:41] == VBLANK_ATOMIC_RUNTIME
        and bytes(
            rom[
                VBLANK_COMMIT_OFFSET:
                VBLANK_COMMIT_OFFSET
                + len(VBLANK_ATOMIC_WINDOW_FAST_FINAL_COMMIT)
            ]
        ) == VBLANK_ATOMIC_WINDOW_FAST_FINAL_COMMIT
    )
    vblank_guarded_installed = (
        common_installed
        and runtime[23:41] == VBLANK_ATOMIC_RUNTIME
        and bytes(rom[VBLANK_COMMIT_OFFSET:
                      VBLANK_COMMIT_OFFSET + len(VBLANK_GUARDED_COMMIT)])
        == VBLANK_GUARDED_COMMIT
        and bytes(rom[VBLANK_COMMIT_GUARD_OFFSET:
                      VBLANK_COMMIT_GUARD_OFFSET + len(VBLANK_COMMIT_GUARD)])
        == VBLANK_COMMIT_GUARD
    )
    latched_commit = VBLANK_GUARDED_COMMIT.replace(
        bytes.fromhex('AF EA 5C DF'), bytes(4), 1
    ).replace(
        bytes.fromhex('FA 00 DC E6 0F E0 43'), bytes.fromhex('FA 5C DF E6 0F E0 43'), 1
    ).replace(
        bytes.fromhex('FA 02 DC E6 0F E0 42'), bytes.fromhex('F0 C4 E6 0F E0 42'), 1
    ).replace(
        bytes.fromhex('F0 C4 B7 28 15 E6 04 07'), bytes.fromhex('F0 C4 CB 7F 28 15 E6 10 0F'), 1
    ).replace(
        bytes.fromhex('F0 40 EE 48 E0 40 C3 1D 6F'), bytes.fromhex('AF E0 C4 F0 40 EE 48 E0 40'), 1
    )
    latched_guard = bytes.fromhex('F0 44 E6 FC FE 90 C2 1D 6F F0 C4 E6 40 C3 00 74')
    if dealias_test is not None:
        patched = bytearray(latched_commit)
        reload_offset = 0x7407 - VBLANK_COMMIT_ADDR
        patched[reload_offset:reload_offset+8] = bytes((0xC3,dealias_test&255,dealias_test>>8,0,0,0,0,0))
        latched_commit = bytes(patched)
        latched_guard = bytes.fromhex('F044 E6FC FE90 C21D6F') + (
            bytes.fromhex('3E19 CD4708 1811') if dealias_test == 0x7701
            else bytes.fromhex('C3EE76 00000000')
        )
    r441_latched_installed = (
        r441_identity and common_installed
        and runtime[23:41] == VBLANK_ATOMIC_RUNTIME
        and bytes(rom[VBLANK_COMMIT_OFFSET:VBLANK_COMMIT_OFFSET+len(latched_commit)]) == latched_commit
        and bytes(rom[VBLANK_COMMIT_GUARD_OFFSET:VBLANK_COMMIT_GUARD_OFFSET+len(latched_guard)]) == latched_guard
    )
    vblank_atomic_installed = (
        r441_latched_installed
        or
        vblank_guarded_installed
        or
        vblank_atomic_v2_installed
        or vblank_atomic_window_installed
        or vblank_atomic_stage1_window_installed
        or vblank_atomic_stage1_only_window_installed
        or vblank_atomic_window_fast_installed
        or vblank_atomic_window_robust_installed
        or vblank_atomic_window_final_installed
        or vblank_atomic_window_fast_final_installed
    )
    return {
        "installed": (
            legacy_installed or vblank_atomic_installed
            or r453_runtime_receipted
            or r455_runtime_receipted
        ),
        "variant": (
            "vblank-latched-single-art-r441"
            if r441_latched_installed
            else
            "vblank-atomic-window-fast-final-guard-r374"
            if vblank_guarded_installed
            else "vblank-atomic-window-fast-final-v9"
            if vblank_atomic_window_fast_final_installed
            else "vblank-atomic-window-final-v8"
            if vblank_atomic_window_final_installed
            else "vblank-atomic-window-robust-v7"
            if vblank_atomic_window_robust_installed
            else "vblank-atomic-window-fast-v6"
            if vblank_atomic_window_fast_installed
            else "vblank-atomic-stage1-only-window-v5"
            if vblank_atomic_stage1_only_window_installed
            else "vblank-atomic-stage1-window-v4"
            if vblank_atomic_stage1_window_installed
            else "vblank-atomic-window-v3" if vblank_atomic_window_installed
            else "vblank-atomic-v2" if vblank_atomic_v2_installed
            else "dirty-return-v1" if legacy_installed
            else "runtime-receipted-r453" if r453_runtime_receipted
            else "runtime-receipted-r455" if r455_runtime_receipted
            else "absent"
        ),
        "vblank_atomic_installed": vblank_atomic_installed,
        "vblank_guarded_installed": vblank_guarded_installed,
        "vblank_atomic_window_installed": vblank_atomic_window_installed,
        "vblank_atomic_stage1_window_installed": (
            vblank_atomic_stage1_window_installed
        ),
        "vblank_atomic_stage1_only_window_installed": (
            vblank_atomic_stage1_only_window_installed
        ),
        "vblank_atomic_window_fast_installed": (
            vblank_atomic_window_fast_installed
        ),
        "vblank_atomic_window_robust_installed": (
            vblank_atomic_window_robust_installed
        ),
        "vblank_atomic_window_final_installed": (
            vblank_atomic_window_final_installed
        ),
        "vblank_atomic_window_fast_final_installed": (
            vblank_atomic_window_fast_final_installed
        ),
        "hook_address": dirty_return_address,
        "dirty_return": dirty_return,
        "inline_arm_count": inline_arm_count,
        "fast": fast,
        "continuation": continuation,
        "helper": helper,
        "vblank_commit_address": VBLANK_COMMIT_ADDR,
        "vblank_commit": (
            latched_commit
            if r441_latched_installed
            else
            VBLANK_GUARDED_COMMIT
            if vblank_guarded_installed
            else VBLANK_ATOMIC_WINDOW_FAST_FINAL_COMMIT
            if vblank_atomic_window_fast_final_installed
            else VBLANK_ATOMIC_WINDOW_FINAL_COMMIT
            if vblank_atomic_window_final_installed
            else VBLANK_ATOMIC_WINDOW_ROBUST_COMMIT
            if vblank_atomic_window_robust_installed
            else VBLANK_ATOMIC_WINDOW_FAST_COMMIT
            if vblank_atomic_window_fast_installed
            else VBLANK_ATOMIC_STAGE1_ONLY_WINDOW_COMMIT
            if vblank_atomic_stage1_only_window_installed
            else VBLANK_ATOMIC_STAGE1_WINDOW_COMMIT
            if vblank_atomic_stage1_window_installed
            else VBLANK_ATOMIC_WINDOW_COMMIT if vblank_atomic_window_installed
            else VBLANK_ATOMIC_COMMIT
        ),
        "postcopy_call_sites": postcopy_call_sites,
        "bridge_address": WRAM_FAST_ENTRY,
        "discriminator_index": discriminator,
        "title_discriminator": title_bg0[discriminator],
        "stage1_bg0": stage1_bg0,
    }


def install_stage_card_palette_handoff(
    rom: bytearray,
) -> StageCardHandoffReport:
    assert len(rom) >= (PRIVATE_BANK + 1) * BANK_SIZE, (
        "Stage-card handoff requires the 512 KiB expanded image"
    )
    assert bytes(
        rom[
            HANDOFF_EXTENSION_OFFSET:
            HANDOFF_EXTENSION_OFFSET + HANDOFF_EXTENSION_SIZE
        ]
    ) == bytes(HANDOFF_EXTENSION_SIZE), (
        "expanded-production Stage-card extension source changed at bank13:$5830"
    )
    assert bytes(
        rom[
            STAGE1_ENTRY_GATE_OFFSET:
            STAGE1_ENTRY_GATE_OFFSET + len(DEFERRED_ENTRY_GATE)
        ]
    ) == DEFERRED_ENTRY_GATE, (
        "Stage-1 palette phase is not deferred to the atomic map flip"
    )

    # Verify the receipt-proven six-byte arena-runtime padding plus exact old
    # DBE5 guard before replacing DBDF-$DBF0. The cold-copy extension relocates
    # that guard to DBF1-$DBFC without changing its instructions.
    runtime = _source_runtime_image(rom)
    assert runtime[23:29] == bytes(6), (
        "WRAM handoff source padding changed before installation"
    )
    assert runtime[29:41] == OLD_POSTCOPY_GUARD, (
        "WRAM scene guard changed before relocation: "
        + runtime[29:41].hex(" ")
    )
    postcopy_call_sites = _postcopy_call_sites(rom, OLD_POSTCOPY_GUARD_ENTRY)
    assert len(postcopy_call_sites) == 2, (
        "expected two generated $DBE5 post-copy calls, got "
        f"{postcopy_call_sites}"
    )
    dirty_return_address = _dirty_return_address(postcopy_call_sites)
    assert bytes(
        rom[dirty_return_address:dirty_return_address + 3]
    ) == NATIVE_DIRTY_RETURN_PREIMAGE, (
        "dirty publication's atomic return changed at "
        f"fixed:${dirty_return_address:04X}"
    )

    layout = inspect_stage_card_palette_handoff(rom)
    helper = layout["helper"]
    assert bytes(rom[PRIVATE_OFFSET:PRIVATE_OFFSET + len(helper)]) == (
        bytes([0xFF]) * len(helper)
    ), "private bank-21 Stage-card handoff region is no longer free"

    # Rewrite only the source bytes copied to DBDF-$DBF0 at cold start.
    runtime = bytearray(runtime)
    runtime[23:41] = layout["fast"] + layout["continuation"]
    rom[RUNTIME_SOURCE_B_OFFSET:RUNTIME_SOURCE_B_OFFSET + 36] = runtime[:36]
    rom[RUNTIME_SOURCE_C_OFFSET:RUNTIME_SOURCE_C_OFFSET + 5] = runtime[36:]
    rom[
        HANDOFF_EXTENSION_OFFSET:
        HANDOFF_EXTENSION_OFFSET + len(OLD_POSTCOPY_GUARD)
    ] = OLD_POSTCOPY_GUARD
    for address in postcopy_call_sites:
        # Preserve an exact CALL-NZ pure-room guard; only relocate its target.
        rom[address + 1:address + 3] = bytes([
            POSTCOPY_GUARD_ENTRY & 0xFF, POSTCOPY_GUARD_ENTRY >> 8,
        ])
    rom[
        dirty_return_address:dirty_return_address + 3
    ] = layout["dirty_return"]
    rom[PRIVATE_OFFSET:PRIVATE_OFFSET + len(helper)] = helper
    checked = inspect_stage_card_palette_handoff(rom)
    assert checked["installed"], "Stage-card handoff post-install check failed"
    return StageCardHandoffReport(
        hook_address=dirty_return_address,
        bridge_address=WRAM_FAST_ENTRY,
        private_bank=PRIVATE_BANK,
        private_entry=PRIVATE_ENTRY,
        helper_size=len(helper),
        discriminator_index=int(layout["discriminator_index"]),
        title_discriminator=int(layout["title_discriminator"]),
        stage1_bg0=bytes(layout["stage1_bg0"]).hex().upper(),
    )
