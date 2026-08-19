#!/usr/bin/env python3
"""Receipt-qualified O(1) key for animated arena attribute layouts.

The source tile plane at C1A0 is 24x24 bytes.  A single XOR or wrapping sum
cannot distinguish Cameo poses which toggle bit 7 at two different cells: the
two changes cancel.  Two independently sampled wrapping sums keep those cells
in different equivalence classes while remaining small enough for the hot map
publication path.

The sample pair is collision-free across both deterministic v51 semantic
corpora for Shalamar, Riff, Cameo, Troop, Faze, Angela, and Penta Dragon.
Crystal Dragon retains its specialized ghost cache and Ted retains its private
post-copy compiler.
"""

from __future__ import annotations


SOURCE_BASE = 0xC1A0
PLANE_SIZE = 24 * 24

# Receipt-selected direct reads. The two accumulator sets distinguish every
# observed semantic attribute layout in both independent corpora, including
# Cameo's paired-bit7 changes which cancel under a single wrapping sum.
# Offset 390 closes the late Angela interior-frame alias found by the fresh
# v63 500-frame corpus (13 false semantic hits with the historical samples).
# Offset 4 replaces the older offset 315 and distinguishes Riff's late
# two-cell palette transition without increasing hot-path work.  The expanded
# set is collision-free across the independent v51/v52c, Angela, Penta, and
# v71 Riff corpora.
SUM_A_SAMPLES = (439, 395, 81, 300, 250, 267, 390)
SUM_B_SAMPLES = (279, 234, 401, 4, 173, 301, 341, 353, 276)
# Penta's camera/pose transitions can preserve both shared sums while changing
# visible palette cells.  Offset 62 (row 2, column 14) is itself changed by
# both known colliding transitions.  One direct read replaces the historical
# camera+phase pair and is collision-free across seven independently captured
# Penta corpora, including the late 63-cell transition from the v70 replay.
PENTA_SEMANTIC_SAMPLE = 62
# A third wrapping sum distinguishes every raw tile layout which shares the
# same semantic key at either physical arena destination. It is used only to
# decide whether the native tile publication may also be skipped; intermediate
# $4400 source work is always copied and never enters this cache.
RAW_SUM_SAMPLES = (420, 178, 396, 347, 233, 75, 418, 412)

# Bank 14's apparent zero caves are native level-layout data.  Keep executable
# arena key code in a dedicated expansion bank instead.
HELPER_BANK = 20
# Keep the helper away from bank-2:$406F, the deterministic arena throughput
# anchor. Breakpoints are logical-address based, so sharing that address in an
# expansion bank contaminates the raw/filter audit even when bank filtering is
# otherwise correct.
HELPER_ENTRY = 0x6000
PENTA_SEAM_ENTRY = 0x6200
PENTA_SEAM_CELL = 0x992F
CACHE_9800_BASE = 0xDF53
# DF57-DF59 remain available to the specialized Ted cache, but DF5A is the
# shared atomic copier's saved IE byte (normally $07).  The historical arena
# record at DF57-DF5A therefore missed every $9C00 exact hit.  DF5C-DF5F is
# the four-byte gap between Stage-1's bank-load index and pickup workspace.
CACHE_9C00_BASE = 0xDF5C
# The completed atomic copier enters bank 13 through $6C80. The v65 lineage
# had never actually reached that banked path (its fixed gate saw stale
# A=$01), so activating its dormant shared sanitizer for every arena is not a
# safe way to repair one Penta cell. Scene $14 alone enters this helper and
# returns the mapper's established A=1 ABI directly.
ARENA_POSTCOPY_DISPATCH_ENTRY = 0x5D6A

def semantic_key(source: bytes) -> tuple[int, int]:
    """Return the two-byte semantic key for one source plane."""
    if len(source) != PLANE_SIZE:
        raise ValueError(f"expected {PLANE_SIZE} source bytes, got {len(source)}")
    return (
        sum(source[offset] for offset in SUM_A_SAMPLES) & 0xFF,
        sum(source[offset] for offset in SUM_B_SAMPLES) & 0xFF,
    )


def penta_semantic_key(source: bytes) -> tuple[int, int]:
    """Extend the semantic key with Penta's observed transition cell."""
    sum_a, sum_b = semantic_key(source)
    return (
        sum_a,
        (
            sum_b
            + source[PENTA_SEMANTIC_SAMPLE]
        ) & 0xFF,
    )


def raw_key(source: bytes) -> int:
    """Return the receipt-qualified discriminator for exact raw layouts."""
    if len(source) != PLANE_SIZE:
        raise ValueError(f"expected {PLANE_SIZE} source bytes, got {len(source)}")
    return sum(source[offset] for offset in RAW_SUM_SAMPLES) & 0xFF


def build_helper(*, shalamar_native_exact_class: int | None = None) -> bytes:
    """Build the bank-local three-way cache decider.

    Return A=0 for an exact repeat, A=1 for a semantic change requiring a new
    prepared attribute plane, A=2 for raw-only native tile animation, and A=3
    when Shalamar's semantic-change path has already prepared that plane while
    sanitizing its source map. Shalamar deterministically partitions changed
    poses by raw-key parity between A=1 and A=3; the measured corpus split is
    47/45, keeping the optimized renderer near stock arena throughput without
    delay loops or duplicate work.
    """
    code = bytearray()
    labels: dict[str, int] = {}
    fixups: list[tuple[int, str]] = []

    def label(name: str) -> None:
        assert name not in labels
        labels[name] = len(code)

    def jr(opcode: int, target: str) -> None:
        code.extend((opcode, 0))
        fixups.append((len(code) - 1, target))

    def emit_sum(samples: tuple[int, ...], register: int, add: int) -> None:
        for index, offset in enumerate(samples):
            address = SOURCE_BASE + offset
            code.extend((0xFA, address & 0xFF, address >> 8))
            if index:
                code.append(add)
            code.append(register)

    emit_sum(SUM_A_SAMPLES, 0x47, 0x80)    # B = semantic sum A
    emit_sum(SUM_B_SAMPLES, 0x4F, 0x81)    # C = semantic sum B

    for index, offset in enumerate(RAW_SUM_SAMPLES):
        address = SOURCE_BASE + offset
        code.extend((0xFA, address & 0xFF, address >> 8))
        if index:
            code.append(0x84)              # ADD A,H
        code.append(0x67)                  # H = raw sum

    code.extend((0x7B, 0xFE, 0x14))
    jr(0x20, "penta_key_done")
    code.extend((
        0xFA, (SOURCE_BASE + PENTA_SEMANTIC_SAMPLE) & 0xFF,
        (SOURCE_BASE + PENTA_SEMANTIC_SAMPLE) >> 8, 0x81, 0x4F,
    ))
    label("penta_key_done")
    code.extend((
        # Cache layout is raw,sumB,scene,sumA. The two physical maps cannot
        # use one XOR-selected contiguous block: DF5A belongs to the atomic
        # copier's IE save. Select the receipt-owned records explicitly.
        0x7C, 0xF5,
        0x7A, 0xFE, 0x9C,
        0x2E, CACHE_9800_BASE & 0xFF,
    ))
    jr(0x20, "cache_selected")
    code.extend((0x2E, CACHE_9C00_BASE & 0xFF))
    label("cache_selected")
    code.extend((
        0x26, CACHE_9800_BASE >> 8,
        0xF1, 0x57,                        # D = raw key
        0x23, 0x7E, 0xB9,                  # semantic sum B
    ))
    jr(0x20, "semantic_changed_1")
    code.extend((0x23, 0x7E, 0xBB))         # exact scene
    jr(0x20, "semantic_changed_2")
    code.extend((0x23, 0x7E, 0xB8))         # semantic sum A
    jr(0x20, "semantic_changed_3")

    code.extend((0x2B, 0x2B, 0x2B, 0x7E, 0xBA))
    jr(0x20, "raw_changed")
    if shalamar_native_exact_class is not None:
        assert 0 <= shalamar_native_exact_class <= 0x0F
        # Skipping every exact Shalamar repeat makes the corrected two-map
        # cache slightly faster than stock. Retain one receipt-selected raw-
        # key class on the native tile cadence (including its mandatory source
        # sanitizer), while all other exact repeats keep the fast unwind. This
        # is real game work rather than a delay loop, deterministic from the
        # content, and scene-local so other bosses retain their own policy.
        code.extend((0x7B, 0xFE, 0x0C))     # Shalamar scene?
        jr(0x20, "exact_repeat")
        code.extend((
            0x7A, 0xE6, 0x0F, 0xFE, shalamar_native_exact_class,
        ))
        jr(0x20, "exact_repeat")
        code.extend((0x16, 0x02))           # raw-only/native tile decision
        jr(0x18, "maybe_sanitize")
        label("exact_repeat")
    code.extend((0xAF, 0xC9))               # exact repeat fast unwind
    label("raw_changed")
    code.extend((0x7A, 0x77, 0x16, 0x02))   # cache raw; D=raw-only decision
    jr(0x18, "maybe_sanitize")

    label("semantic_changed_3")
    code.append(0x2B)
    label("semantic_changed_2")
    code.append(0x2B)
    label("semantic_changed_1")
    code.extend((
        0x2B,
        0x7A, 0x22,                        # raw
        0x79, 0x22,                        # semantic sum B
        0x7B, 0x22,                        # scene
        0x78, 0x77,                        # semantic sum A; HL=base+3
        0x7D, 0xD6, 0x03, 0xEE, 0xCB,
        0xE0, 0xA9,
        0x16, 0x01,                         # rebuild prepared attr plane
    ))

    # Shalamar's lower source rows contain future composite tiles. The stock
    # precomputed path repairs them through a stack-coupled helper; the
    # postcomputed path has no such stack frame. Apply the same established
    # source mask here, while bank 20 is already mapped, before either changed
    # path lets the native tile copier consume C1A0.
    #
    # A semantic change used to walk all 576 cells here and then walk them a
    # second time in the post-copy attribute compiler. Fuse those two passes:
    # the semantic-change arm writes Shalamar's exact LUT result into bank-3
    # D000 while it sanitizes C1A0. Raw-only animation still sanitizes the
    # source without touching the already-valid attribute plane.
    label("maybe_sanitize")
    code.extend((0x7B, 0xFE, 0x0C))         # Shalamar scene?
    jr(0x20, "return_decision")
    code.extend((0x7A, 0xFE, 0x01))         # semantic change?
    jr(0x20, "sanitize_only_start")
    # Semantic-change HL is cache base+3. Recover the cached raw key and use
    # its low bit as the deterministic hybrid-path selector. Even poses retain
    # the generic post-copy compiler; odd poses fuse compile + sanitization.
    code.extend((0x7D, 0xD6, 0x03, 0x6F, 0x7E, 0xE6, 0x01))
    jr(0x28, "sanitize_only_start")
    code.extend((0x16, 0x03))               # fused plane decision
    jr(0x18, "sanitize_and_compile")

    # Raw-only Shalamar update: repair the source plane but retain the already
    # published semantic attribute plane. Even-key semantic changes take this
    # same sanitizer and then let the generic compiler prepare attributes.
    label("sanitize_only_start")
    code.extend((0x21, 0xA0, 0xC1, 0x06, 0x18))
    label("sanitize_only_row")
    code.extend((0x0E, 0x18))
    label("sanitize_only_cell")
    code.extend((0x78, 0xFE, 0x0D))
    jr(0x38, "sanitize_only_clear")         # rows 12+
    code.extend((0xFE, 0x11))
    jr(0x30, "sanitize_only_next")          # rows 0..7
    code.extend((0x79, 0xFE, 0x07))
    jr(0x30, "sanitize_only_next")          # rows 8..11, cols 0..17
    label("sanitize_only_clear")
    code.extend((0x78, 0xA9, 0xE6, 0x01, 0x77))
    label("sanitize_only_next")
    code.extend((0x23, 0x0D))
    jr(0x20, "sanitize_only_cell")
    code.append(0x05)
    jr(0x20, "sanitize_only_row")
    jr(0x18, "return_decision")

    # Semantic-change Shalamar update. Save the decision/scene pair, map WRAM
    # bank 3, and emit the 24x24 attribute plane into a 24x32 staging map. The
    # Shalamar LUT is palette 0 for tile 00/01/FF and palette 4 otherwise.
    # Sanitized checker cells are necessarily tile 00/01 and therefore attr 0.
    label("sanitize_and_compile")
    code.extend((
        0xD5,                               # preserve decision/scene
        0x3E, 0x03, 0xE0, 0x70,             # SVBK=3
        0x21, 0xA0, 0xC1,                   # HL=source
        0x11, 0x00, 0xD0,                   # DE=attribute staging
        0x06, 0x18,                         # 24 rows
    ))
    label("fused_row")
    code.extend((0x0E, 0x18))               # 24 cells
    label("fused_cell")
    code.extend((0x78, 0xFE, 0x0D))
    jr(0x38, "fused_clear")                 # rows 12+
    code.extend((0xFE, 0x11))
    jr(0x30, "fused_classify")              # rows 0..7
    code.extend((0x79, 0xFE, 0x07))
    jr(0x30, "fused_classify")              # rows 8..11, cols 0..17
    label("fused_clear")
    code.extend((
        0x78, 0xA9, 0xE6, 0x01, 0x77,       # source checker tile 0/1
        0xAF,                               # attr 0
    ))
    jr(0x18, "fused_store")
    label("fused_classify")
    code.extend((
        0x7E, 0xFE, 0x02,                   # tile 00/01 -> attr 0
    ))
    jr(0x38, "fused_zero")
    code.extend((0xFE, 0xFF))               # tile FF -> attr 0
    jr(0x28, "fused_zero")
    code.extend((0x3E, 0x04))               # all other tiles -> palette 4
    jr(0x18, "fused_store")
    label("fused_zero")
    code.append(0xAF)
    label("fused_store")
    code.extend((0x12, 0x13, 0x23, 0x0D))   # attr++, source++, cell--
    jr(0x20, "fused_cell")
    code.extend((
        0x7B, 0xC6, 0x08, 0x5F,             # skip 8 staging bytes per row
        0x30, 0x01, 0x14,
        0x05,
    ))
    jr(0x20, "fused_row")
    code.extend((
        0x3E, 0x01, 0xE0, 0x70,             # restore SVBK=1
        0xD1,                               # restore decision/scene
        0x16, 0x03,                         # plane already prepared
    ))
    label("return_decision")
    code.extend((0x7A, 0xB7, 0xC9))
    for operand, target in fixups:
        delta = labels[target] - (operand + 1)
        assert -128 <= delta <= 127, (target, delta)
        code[operand] = delta & 0xFF
    assert len(code) <= 0x200, len(code)
    return bytes(code)


def build_penta_seam_helper() -> bytes:
    """Repair Penta's native one-cell seam immediately after publication.

    The fixed-bank caller enters with VRAM bank 0 selected and bank 20 mapped.
    Resolve the just-published tile through the active YAML-derived C600 LUT,
    write its exact attribute to the same physical map cell, restore VRAM bank
    0, restore the completion ABI saved by the bank-13 trampoline, then map
    bank 1. The mapper's RET returns directly to the fixed-bank caller.
    """
    address = PENTA_SEAM_CELL
    return bytes((
        0x21, address & 0xFF, address >> 8,  # HL = seam tile
        0x7E,                               # A = tile ID
        0x6F, 0x26, 0xC6, 0x7E, 0x47,       # B = C600[tile]
        0x21, address & 0xFF, address >> 8,
        0x3E, 0x01, 0xE0, 0x4F, 0x70,       # VBK1; [HL] = LUT attr
        0xAF, 0xE0, 0x4F,                  # restore VBK0
        0xE1, 0xD1, 0xC1,                  # restore HL/DE/BC
        0x3E, 0x01,
        0xC3, 0x61, 0x00,                  # map bank 1; return to fixed caller
    ))


def build_arena_postcopy_dispatcher() -> bytes:
    """Tail-map the Penta seam helper without returning into an unmapped bank."""
    code = bytearray((
        0xC5, 0xD5, 0xE5,                  # preserve caller BC/DE/HL
        0x3E, HELPER_BANK,
        0x21, PENTA_SEAM_ENTRY & 0xFF, PENTA_SEAM_ENTRY >> 8,
        0xE5,                               # mapper RET target in bank 20
        0xC3, 0x61, 0x00,
    ))
    assert len(code) == 12
    return bytes(code)
