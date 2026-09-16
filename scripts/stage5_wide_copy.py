"""Install the stage-private map publication router.

The canonical postcomputed copier is authoritative for Stages 2-7 because its
post-copy tail publishes their complete semantic attribute planes. Stage 1
does not need that full-plane work: its immutable pickup colors live in tile
art and its rotating hazard has a separate selective row owner. Route only
Stage 1 through an exact native copier cloned at the same CPU addresses in
expansion bank 22.

Stage 5 needs the canonical semantic tail but not its 144-window tile loop.
Clone the complete canonical copier at the same CPU addresses in bank 21,
replace only its tile-loop entry with a five-tile helper, then rejoin its
unchanged post-copy tail. The canonical semantic tail and private routing
provide the remaining cadence; no write-free tail waits are needed.

Stage 7 can optionally use a second canonical clone in bank 23.  Its
already-classified pure branch, with the LCD enabled, enters a fully unrolled
six-tile helper.  An additional experimental mode sends classified dirty
publications through the receipt-proven fused tile/attribute helper before
rejoining the unchanged semantic tail.  LCD-off pure transitions retain the
canonical loop.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from compose_stage1_wide_copy_r445 import (
    COLS,
    PATTERNS,
    ROWS,
    SRC0,
    emit,
    model_new,
    model_old,
)


BANK_SIZE = 0x4000
ROUTER_BANK = 21
NATIVE_STAGE1_BANK = 22
STAGE7_BANK = 23
ROUTER_ADDR = 0x6C80
WIDE_COPY_ADDR = 0x6D00
STAGE7_DISPATCH_ADDR = 0x6C80
STAGE7_FAST_COPY_ADDR = 0x6D00
STAGE7_FUSED_DISPATCH_ADDR = 0x6C00
STAGE7_FUSED_HELPER_ADDR = 0x6C80
CALL_SITES = (0x0AB5, 0x12DD)
FIXED_DISPATCH_ADDR = 0x0013
DX_COPY_ADDR = 0x4295
DX_TILE_LOOP_ADDR = 0x42B7
DX_POST_COPY_ADDR = 0x42EC
DX_EARLY_RETURN_ADDR = 0x42F9
DX_COPY_END = 0x436E
NATIVE_COPY_END = 0x436E
DX_EARLY_COMPLETION_ADDR = 0x437A
DX_PURE_BRANCH_ADDR = 0x42B0
MAPPER_CORE_ADDR = 0x0061
FIXED_POP_RET_ADDR = 0x03A1
FIXED_POP_RETI_ADDR = 0x06CC
STAGE5_TAIL_WAIT_GROUPS = 0
STAGE7_PURE_WINDOWS = ROWS * 4

CALL_PREIMAGE = bytes.fromhex("CD 95 42")
CALL_PATCH = bytes.fromhex("CD 13 00")
DX_ENTRY_PREIMAGE = bytes.fromhex("FA 0B DC 3C E6 01 EA 0B DC")
MAPPER_WRAPPER_ADDR = 0x0847
MAPPER_WRAPPER = bytes.fromhex("CD 61 00 CD 80 6C C3 61 00")
# Each fragment is unreachable fallthrough after a complete fixed-vector
# JP/RET/RETI.  The noncontiguous layout retains every live vector while
# making the ordinary Stage 2-7 path cheap enough for the movement contract.
DISPATCH_FRAGMENT_PREIMAGES = {
    0x000D: bytes.fromhex("00 00 00"),
    0x0013: bytes.fromhex("DF AE BB 52 7B"),
    0x0024: bytes.fromhex("D7 6E 8A 62"),
    0x002B: bytes.fromhex("FF FF F7 FE FF"),
    0x003C: bytes.fromhex("FD 3F DB FF"),
}
VECTOR_FENCES = {
    0x0008: bytes.fromhex("E0 47 C3 D5 10"),
    0x0010: bytes.fromhex("C3 DE 09"),
    0x0020: bytes.fromhex("EA 80 D8 D9"),
    0x0028: bytes.fromhex("C3 9A 09"),
    0x0038: bytes.fromhex("EA 87 D8 C9"),
}
ABSOLUTE_BRANCH_OPCODES = frozenset({
    0xC2, 0xC3, 0xC4, 0xCA, 0xCC,
    0xD2, 0xD4, 0xDA, 0xDC, 0xCD,
})
RELATIVE_BRANCH_OPCODES = frozenset({0x18, 0x20, 0x28, 0x30, 0x38})
# These four instruction-shaped records are in the header or banked data.
# Pin their exact physical positions instead of silently treating arbitrary
# mentions of the vector padding as harmless.
REVIEWED_DATA_FALSE_MENTIONS = frozenset({
    (0x000108, 0xCC, 0x000D),
    (0x01C7FE, 0xD2, 0x000F),
    (0x02542E, 0xC4, 0x003E),
    (0x03D96E, 0xCA, 0x0014),
})
FIXED_POP_RET = bytes.fromhex("E1 D1 C1 F1 C9")
FIXED_POP_RETI = bytes.fromhex("E1 D1 C1 F1 D9")
DX_COPY_SHA256 = (
    "1c7074fdd12d24d0b62b3fd6e66001eff272c78fc38dc611ef1060509feb48c3"
)
NATIVE_COPY_SHA256 = (
    "b018463e6d3f1e19948f76cb92955901d802e39e5b1e7eb685684f9dbcf5d453"
)
NATIVE_ROM = Path(__file__).resolve().parents[1] / "rom/Penta Dragon (J).gb"


@dataclass(frozen=True)
class InstallReport:
    router_bank: int
    native_stage1_bank: int
    stage7_bank: int | None
    router: int
    copy: int
    copy_size: int
    windows_per_publication: int | None
    stage7_pure_windows: int | None
    stage7_dirty_windows: int | None
    stage7_fused_entry: int | None
    stage7_fast_entry: int | None
    stage7_maximum_critical_cycles: int | None


def bank_offset(bank: int, address: int) -> int:
    return bank * BANK_SIZE + address - 0x4000


def _relative(code: bytearray, operand: int, target: int) -> None:
    displacement = target - (operand + 1)
    assert -128 <= displacement <= 127
    code[operand] = displacement & 0xFF


def _map_and_enter(bank: int, target: int = DX_COPY_ADDR) -> bytes:
    # PUSH target + JP mapper makes the mapper's RET enter the newly mapped
    # bank without requiring mirrored continuation bytes.
    return bytes([
        0x3E, bank,
        0x21, target & 0xFF, target >> 8,
        0xE5,
        0xC3, MAPPER_CORE_ADDR & 0xFF, MAPPER_CORE_ADDR >> 8,
    ])


def build_dispatch_fragments(*, stage7_pure_six: bool = False) -> dict[int, bytes]:
    """Route private stages; tail-call the native bank-1 entry otherwise.

    Without the Stage-7 optimization, masking bit 2 makes exactly Stage 1/5
    FFBA values (0 and 4) zero. With it enabled, the one-byte parity mask
    admits even selectors 0/2/4/6; the bank-21 router handles 0/4/6 exactly
    and sends selector 2 back to the canonical bank-1 entry. The complete
    classifier and mapper fit five authenticated vector-padding fragments.
    Odd-selector stages therefore pay no ROM-bank switch. The private route
    enters the existing fixed mapper wrapper; its synthetic $084D return is
    discarded by the bank-21 router.
    """
    mask = 0x01 if stage7_pure_six else 0xFB
    fragments = {
        0x0013: bytes.fromhex("F0 BA 00 18 0C"),  # read FFBA; JR $0024
        0x0024: bytes((0xE6, mask, 0x18, 0x03)),  # private class -> Z
        0x002B: bytes.fromhex("C2 95 42 18 0C"),  # ordinary JP; JR $003C
        0x003C: bytes.fromhex("3E 15 18 CD"),     # bank 21; JR back $000D
        0x000D: bytes.fromhex("C3 47 08"),        # existing mapper wrapper
    }
    assert set(fragments) == set(DISPATCH_FRAGMENT_PREIMAGES)
    assert all(
        len(fragments[address]) == len(preimage)
        for address, preimage in DISPATCH_FRAGMENT_PREIMAGES.items()
    )
    return fragments


def _cave_transfer_mentions(payload: bytes) -> tuple[
    frozenset[tuple[int, int, int]], frozenset[tuple[int, int, int]]
]:
    targets = {
        target
        for address, preimage in DISPATCH_FRAGMENT_PREIMAGES.items()
        for target in range(address, address + len(preimage))
    }
    absolute = {
        (offset, payload[offset], payload[offset + 1] | payload[offset + 2] << 8)
        for offset in range(len(payload) - 2)
        if payload[offset] in ABSOLUTE_BRANCH_OPCODES
        and (payload[offset + 1] | payload[offset + 2] << 8) in targets
    }
    relative = set()
    for offset in range(0x3FFF):
        if payload[offset] not in RELATIVE_BRANCH_OPCODES:
            continue
        displacement = payload[offset + 1]
        if displacement >= 0x80:
            displacement -= 0x100
        target = (offset + 2 + displacement) & 0xFFFF
        if target in targets:
            relative.add((offset, payload[offset], target))
    return frozenset(absolute), frozenset(relative)


def _restore_bank1(epilogue: int) -> bytes:
    """Map bank 1, then restore every register through a fixed epilogue."""
    return bytes([
        0xF5, 0xC5, 0xD5, 0xE5,             # PUSH AF/BC/DE/HL
        0x21, epilogue & 0xFF, epilogue >> 8,
        0xE5,                               # mapper RET target
        0x3E, 0x01,
        0xC3, MAPPER_CORE_ADDR & 0xFF, MAPPER_CORE_ADDR >> 8,
    ])


def build_dx_completion() -> bytes:
    """Preserve the canonical IE/AF/IME completion while restoring bank 1."""
    return bytes.fromhex("E0 FF 3E 01 BF") + _restore_bank1(
        FIXED_POP_RETI_ADDR
    )


def build_native_completion() -> bytes:
    """Replace the native RET with a register-exact bank-1 restoring RET."""
    return _restore_bank1(FIXED_POP_RET_ADDR)


def build_dx_early_branch() -> bytes:
    """Replace EI;RET with a local branch, leaving dirty entry $42FB intact."""
    displacement = DX_EARLY_COMPLETION_ADDR - (DX_EARLY_RETURN_ADDR + 2)
    assert displacement == 0x7F
    return bytes([0x18, displacement])


def build_dx_early_completion() -> bytes:
    """Restore bank 1 and reproduce the early exit's enabled-IME return."""
    return _restore_bank1(FIXED_POP_RETI_ADDR)


def build_router(
    stage5_wide: bool = True, *, stage7_pure_six: bool = False
) -> bytes:
    """Select exact private routes; reproduce the toggle for all others."""
    code = bytearray([
        0x33, 0x33,                         # discard wrapper return $084D
        0xF0, 0xBA,                         # LDH A,[FFBA]
        0xB7,                               # exact Stage 1?
        0x28, 0x00,
    ])
    stage1_jump = len(code) - 1
    if stage5_wide:
        code.extend([0xFE, 0x04, 0x28, 0x00])
        stage5_jump = len(code) - 1
    else:
        stage5_jump = None
    if stage7_pure_six:
        code.extend([0xFE, 0x06, 0x28, 0x00])
        stage7_jump = len(code) - 1
    else:
        stage7_jump = None
    # The fixed-bank trampoline replaces the first five bytes of the full
    # canonical entry. Reproduce its complete inactive-map toggle here, then
    # enter the untouched bank-1 $42A0/$42A5 page selector. Selecting the
    # entry address instead of carrying H across the mapper matters because
    # the synthetic return target itself is materialized in HL.
    code.extend(bytes([
        0xFA, 0x0B, 0xDC,                   # LD A,[$DC0B]
        0x3C,                               # INC A
        0xE6, 0x01,                         # AND 1
        0xEA, 0x0B, 0xDC,                   # LD [$DC0B],A
        0x28, 0x09,                         # JR Z, map-$9800
    ]))
    code.extend(_map_and_enter(1, 0x42A0))
    code.extend(_map_and_enter(1, 0x42A5))
    stage1 = len(code)
    code.extend(_map_and_enter(NATIVE_STAGE1_BANK))
    stage5 = len(code)
    if stage5_wide:
        code.extend([0xC3, DX_COPY_ADDR & 0xFF, DX_COPY_ADDR >> 8])
    stage7 = len(code)
    if stage7_pure_six:
        code.extend(_map_and_enter(STAGE7_BANK))
    _relative(code, stage1_jump, stage1)
    if stage5_jump is not None:
        _relative(code, stage5_jump, stage5)
    if stage7_jump is not None:
        _relative(code, stage7_jump, stage7)
    assert ROUTER_ADDR + len(code) <= WIDE_COPY_ADDR
    return bytes(code)


def build_wide_copy() -> bytes:
    """Copy the exact native 24x24 sequence and rejoin the DX semantic tail."""
    code = bytearray(
        emit(
            PATTERNS["5"],
            ei_gap=True,
            org=WIDE_COPY_ADDR,
            tail_wait_groups=STAGE5_TAIL_WAIT_GROUPS,
        )
    )
    assert model_new(bytes(code), org=WIDE_COPY_ADDR) == model_old()
    assert code[-5:] == bytes.fromhex("0E 00 3E 01 C9")
    code[-5:] = bytes([
        0x0E, 0x00,                         # canonical loop exits C=0
        0xC3, DX_POST_COPY_ADDR & 0xFF,
        DX_POST_COPY_ADDR >> 8,
    ])
    return bytes(code)


def build_stage7_dispatch() -> bytes:
    """Send LCD-on pure work to the fast body, else use the canonical loop."""
    return bytes([
        0xF0, 0x40,                         # LDH A,[LCDC]
        0x07,                               # RLCA: bit 7 -> carry
        0xDA, STAGE7_FAST_COPY_ADDR & 0xFF,
        STAGE7_FAST_COPY_ADDR >> 8,         # JP C,fast
        0xC3, DX_TILE_LOOP_ADDR & 0xFF,
        DX_TILE_LOOP_ADDR >> 8,             # JP canonical loop
    ])


def build_stage7_fused_dispatch(fast_address: int) -> bytes:
    """Send LCD-on pure work to ``fast_address``, else use the clone loop."""
    return bytes([
        0xF0, 0x40,                         # LDH A,[LCDC]
        0x07,                               # RLCA: bit 7 -> carry
        0xDA, fast_address & 0xFF,
        fast_address >> 8,                  # JP C,fast
        0xC3, DX_TILE_LOOP_ADDR & 0xFF,
        DX_TILE_LOOP_ADDR >> 8,             # JP canonical LCD-off loop
    ])


def build_stage7_fused_branch(fused_address: int) -> bytes:
    """Route the classifier's pure/dirty results to private copy bodies."""
    return bytes([
        0xCA, STAGE7_FUSED_DISPATCH_ADDR & 0xFF,
        STAGE7_FUSED_DISPATCH_ADDR >> 8,    # pure -> LCD dispatcher
        0xCD, 0x13, 0xDA,                   # canonical dirty setup
        0x11, 0xA0, 0xC1,                   # DE=$C1A0
        0x0E, 0x41,                         # C=STAT
        0xC3, fused_address & 0xFF,
        fused_address >> 8,                 # dirty -> fused tile/attr body
    ])


def build_stage7_fast_copy() -> tuple[bytes, dict[str, int]]:
    """Emit 24 rows of four timing-safe six-tile HBlank groups.

    INC E is used except at actual source-page crossings. From the final
    mode-3 observation through the last VRAM write, the worst group costs 41
    machine cycles, within the conservative 41.75-cycle mode-0+mode-2 floor.
    """
    code = bytearray.fromhex("11 A0 C1 0E 41")  # DE=$C1A0; C=STAT
    source = SRC0
    maximum_critical_cycles = 0
    page_crossing_groups = 0
    for _row in range(ROWS):
        for _group in range(4):
            poll_mode3 = len(code) + 1
            code.extend(bytes.fromhex("F3 F2 E6 03 FE 03 20 00"))
            _relative(code, len(code) - 1, poll_mode3)
            poll_mode0 = len(code)
            code.extend(bytes.fromhex("F2 0F 38 00"))
            _relative(code, len(code) - 1, poll_mode0)

            first_source = source
            critical_cycles = 11
            for tile in range(6):
                code.extend(bytes.fromhex("1A 22"))
                if tile == 5 or source & 0xFF == 0xFF:
                    code.append(0x13)        # INC DE (carry/off final path)
                    if tile != 5:
                        critical_cycles += 6
                else:
                    code.append(0x1C)        # INC E (page-local)
                    critical_cycles += 5
                source += 1
            critical_cycles += 4
            maximum_critical_cycles = max(
                maximum_critical_cycles, critical_cycles
            )
            if first_source >> 8 != (source - 1) >> 8:
                page_crossing_groups += 1
            code.extend(bytes.fromhex("FB 00"))  # EI; NOP service point
        code.extend(bytes.fromhex("7D C6 08 6F 30 01 24"))
    code.extend(bytes([
        0x0E, 0x00,                         # canonical loop exits C=0
        0xC3, DX_POST_COPY_ADDR & 0xFF,
        DX_POST_COPY_ADDR >> 8,
    ]))
    assert source == SRC0 + ROWS * COLS
    assert maximum_critical_cycles == 41
    return bytes(code), {
        "groups": ROWS * 4,
        "cells": ROWS * COLS,
        "page_crossing_groups": page_crossing_groups,
        "maximum_critical_cycles": maximum_critical_cycles,
    }


def build_stage7_fused_copies() -> tuple[
    bytes, int, bytes, int, dict[str, int]
]:
    """Build the r465-equivalent fused dirty body plus private pure body.

    The maintained emitter reproduces the qualified class-gated helper.  The
    private copy entry has already classified the publication, so the clone
    jumps directly to its fused body after canonical ``$DA13`` setup.  Only
    the fused completion is changed: it rejoins the current canonical tail
    instead of returning to r465's bank-1 caller.
    """
    helper = bytearray(emit(
        PATTERNS["5"],
        class_gate=True,
        ei_gap=True,
        fused=True,
        org=STAGE7_FUSED_HELPER_ADDR,
    ))
    fused_signature = bytes.fromhex("F0 B7 FE 02")
    assert helper.count(fused_signature) == 1
    fused_entry = STAGE7_FUSED_HELPER_ADDR + helper.index(fused_signature)
    assert helper[-5:] == bytes.fromhex("0E 00 3E 01 C9")
    helper[-5:] = bytes([
        0x0E, 0x00,
        0xC3, DX_POST_COPY_ADDR & 0xFF,
        DX_POST_COPY_ADDR >> 8,
    ])

    fast_entry = STAGE7_FUSED_HELPER_ADDR + len(helper)
    fast, evidence = build_stage7_fast_copy()
    assert fast_entry + len(fast) <= 0x8000
    return bytes(helper), fused_entry, fast, fast_entry, evidence


def install_dx_clone_completion(
    rom: bytearray, *, bank: int, dx_copy: bytes
) -> None:
    """Install a canonical clone with bank-1 restoring exit thunks."""
    dx_offset = bank_offset(bank, DX_COPY_ADDR)
    rom[dx_offset:dx_offset + len(dx_copy)] = dx_copy
    dx_completion = build_dx_completion()
    completion_offset = bank_offset(bank, DX_COPY_END - 6)
    rom[completion_offset:completion_offset + len(dx_completion)] = (
        dx_completion
    )
    early_branch_offset = bank_offset(bank, DX_EARLY_RETURN_ADDR)
    rom[early_branch_offset:early_branch_offset + 2] = build_dx_early_branch()
    early_completion = build_dx_early_completion()
    early_completion_offset = bank_offset(bank, DX_EARLY_COMPLETION_ADDR)
    rom[
        early_completion_offset:
        early_completion_offset + len(early_completion)
    ] = early_completion


def install(
    rom: bytearray, *, stage5_wide: bool = True,
    stage7_pure_six: bool = False,
    stage7_fused_dirty: bool = False,
) -> InstallReport:
    assert not stage7_fused_dirty or stage7_pure_six, (
        "Stage-7 fused dirty copy requires the private pure-six route"
    )
    assert len(rom) == 32 * BANK_SIZE, "expected expanded 512 KiB ROM"
    for call_site in CALL_SITES:
        assert rom[
            call_site:call_site + len(CALL_PREIMAGE)
        ] == CALL_PREIMAGE, "map publication call preimage changed"
    for address, preimage in DISPATCH_FRAGMENT_PREIMAGES.items():
        assert rom[address:address + len(preimage)] == preimage, (
            f"fixed dispatch fragment ${address:04X} changed"
        )
    for address, fence in VECTOR_FENCES.items():
        assert rom[address:address + len(fence)] == fence, (
            f"fixed vector fence ${address:04X} changed"
        )
    absolute, relative = _cave_transfer_mentions(bytes(rom))
    assert absolute == REVIEWED_DATA_FALSE_MENTIONS, (
        f"fixed dispatch cave gained an absolute entry: {absolute}"
    )
    assert not relative, (
        f"fixed dispatch cave gained a relative entry: {relative}"
    )
    assert rom[
        MAPPER_WRAPPER_ADDR:MAPPER_WRAPPER_ADDR + len(MAPPER_WRAPPER)
    ] == MAPPER_WRAPPER, "fixed mapper wrapper changed"
    assert rom[
        FIXED_POP_RET_ADDR:FIXED_POP_RET_ADDR + len(FIXED_POP_RET)
    ] == FIXED_POP_RET, "fixed POP/RET epilogue changed"
    assert rom[
        FIXED_POP_RETI_ADDR:FIXED_POP_RETI_ADDR + len(FIXED_POP_RETI)
    ] == FIXED_POP_RETI, "fixed POP/RETI epilogue changed"
    dx_copy = bytes(rom[DX_COPY_ADDR:DX_COPY_END])
    assert hashlib.sha256(dx_copy).hexdigest() == DX_COPY_SHA256, (
        "canonical DX copier changed"
    )
    assert dx_copy[DX_TILE_LOOP_ADDR - DX_COPY_ADDR:][:3] == bytes.fromhex(
        "11 A0 C1"
    )
    pure_branch = DX_PURE_BRANCH_ADDR - DX_COPY_ADDR
    assert dx_copy[pure_branch:pure_branch + 7] == bytes.fromhex(
        "28 05 CD 13 DA 18 00"
    ), "canonical pure/dirty branch changed"
    assert dx_copy[-6:] == bytes.fromhex("E0 FF 3E 01 BF D9"), (
        "canonical DX completion thunk changed"
    )
    early_return = DX_EARLY_RETURN_ADDR - DX_COPY_ADDR
    assert dx_copy[early_return:early_return + 2] == bytes.fromhex("FB C9"), (
        "canonical DX early completion changed"
    )
    native_rom = NATIVE_ROM.read_bytes()
    native_copy = native_rom[DX_COPY_ADDR:NATIVE_COPY_END]
    assert hashlib.sha256(native_copy).hexdigest() == NATIVE_COPY_SHA256, (
        "native copier identity changed"
    )

    private_banks = [ROUTER_BANK, NATIVE_STAGE1_BANK]
    if stage7_pure_six:
        private_banks.append(STAGE7_BANK)
    for bank in private_banks:
        start = bank * BANK_SIZE
        assert set(rom[start:start + BANK_SIZE]) == {0xFF}, (
            f"private copy bank {bank} is not empty"
        )

    router = build_router(
        stage5_wide=stage5_wide, stage7_pure_six=stage7_pure_six
    )
    router_offset = bank_offset(ROUTER_BANK, ROUTER_ADDR)
    rom[router_offset:router_offset + len(router)] = router

    native_offset = bank_offset(NATIVE_STAGE1_BANK, DX_COPY_ADDR)
    rom[native_offset:native_offset + len(native_copy)] = native_copy
    native_completion = build_native_completion()
    native_completion_offset = bank_offset(
        NATIVE_STAGE1_BANK, NATIVE_COPY_END - 1
    )
    rom[
        native_completion_offset:
        native_completion_offset + len(native_completion)
    ] = native_completion

    wide = b""
    if stage5_wide:
        install_dx_clone_completion(rom, bank=ROUTER_BANK, dx_copy=dx_copy)
        hook_offset = bank_offset(ROUTER_BANK, DX_TILE_LOOP_ADDR)
        rom[hook_offset:hook_offset + 3] = bytes([
            0xC3, WIDE_COPY_ADDR & 0xFF, WIDE_COPY_ADDR >> 8,
        ])
        wide = build_wide_copy()
        wide_offset = bank_offset(ROUTER_BANK, WIDE_COPY_ADDR)
        assert WIDE_COPY_ADDR + len(wide) <= 0x8000
        rom[wide_offset:wide_offset + len(wide)] = wide

    stage7_fast = b""
    stage7_evidence: dict[str, int] | None = None
    stage7_fused_entry = None
    stage7_fast_entry = None
    if stage7_pure_six:
        install_dx_clone_completion(rom, bank=STAGE7_BANK, dx_copy=dx_copy)
        branch_offset = bank_offset(STAGE7_BANK, DX_PURE_BRANCH_ADDR)
        if stage7_fused_dirty:
            (
                helper,
                stage7_fused_entry,
                stage7_fast,
                stage7_fast_entry,
                stage7_evidence,
            ) = build_stage7_fused_copies()
            branch = build_stage7_fused_branch(stage7_fused_entry)
            rom[branch_offset:branch_offset + len(branch)] = branch
            dispatch = build_stage7_fused_dispatch(stage7_fast_entry)
            dispatch_offset = bank_offset(
                STAGE7_BANK, STAGE7_FUSED_DISPATCH_ADDR
            )
            rom[dispatch_offset:dispatch_offset + len(dispatch)] = dispatch
            helper_offset = bank_offset(
                STAGE7_BANK, STAGE7_FUSED_HELPER_ADDR
            )
            rom[helper_offset:helper_offset + len(helper)] = helper
            fast_offset = bank_offset(STAGE7_BANK, stage7_fast_entry)
            rom[fast_offset:fast_offset + len(stage7_fast)] = stage7_fast
        else:
            rom[branch_offset:branch_offset + 7] = bytes([
                0xCA, STAGE7_DISPATCH_ADDR & 0xFF,
                STAGE7_DISPATCH_ADDR >> 8,   # JP Z,pure dispatcher
                0xCD, 0x13, 0xDA,           # dirty setup remains exact
                0x00,                        # fall through to canonical loop
            ])
            dispatch = build_stage7_dispatch()
            dispatch_offset = bank_offset(STAGE7_BANK, STAGE7_DISPATCH_ADDR)
            rom[dispatch_offset:dispatch_offset + len(dispatch)] = dispatch
            stage7_fast, stage7_evidence = build_stage7_fast_copy()
            stage7_fast_entry = STAGE7_FAST_COPY_ADDR
            fast_offset = bank_offset(STAGE7_BANK, stage7_fast_entry)
            assert stage7_fast_entry + len(stage7_fast) <= 0x8000
            rom[fast_offset:fast_offset + len(stage7_fast)] = stage7_fast

    assert rom[DX_COPY_ADDR:DX_COPY_ADDR + len(DX_ENTRY_PREIMAGE)] == (
        DX_ENTRY_PREIMAGE
    ), "full copy entry preimage changed"
    for address, fragment in build_dispatch_fragments(
        stage7_pure_six=stage7_pure_six
    ).items():
        rom[address:address + len(fragment)] = fragment
    for call_site in CALL_SITES:
        rom[call_site:call_site + len(CALL_PATCH)] = CALL_PATCH
    return InstallReport(
        router_bank=ROUTER_BANK,
        native_stage1_bank=NATIVE_STAGE1_BANK,
        stage7_bank=STAGE7_BANK if stage7_pure_six else None,
        router=ROUTER_ADDR,
        copy=WIDE_COPY_ADDR,
        copy_size=len(wide),
        windows_per_publication=(
            24 * len(PATTERNS["5"]) + STAGE5_TAIL_WAIT_GROUPS
            if stage5_wide else None
        ),
        stage7_pure_windows=(
            STAGE7_PURE_WINDOWS if stage7_pure_six else None
        ),
        stage7_dirty_windows=(
            ROWS * 6 if stage7_fused_dirty else None
        ),
        stage7_fused_entry=stage7_fused_entry,
        stage7_fast_entry=stage7_fast_entry,
        stage7_maximum_critical_cycles=(
            stage7_evidence["maximum_critical_cycles"]
            if stage7_evidence is not None else None
        ),
    )
