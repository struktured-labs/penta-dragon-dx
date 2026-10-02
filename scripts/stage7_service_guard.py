"""Skip only non-owning Stage-7 VBlank services.

The current wrapper invokes the death/story dispatcher and the DCFD-gated
Stage-1 art loader during ordinary Stage-7 gameplay even though neither can
own exact scene ``$08``. Two tiny exact-scene guards retire those calls while
leaving the title-palette service and every non-Stage-7 route byte-for-byte.

The art guard occupies nine bytes of the menu prelude's 48-NOP timing sled.
The live menu route jumps over it and uses a balanced 46-byte continuation,
preserving the original 48 machine cycles without changing registers.
"""

from __future__ import annotations

from dataclasses import dataclass


BANK_SIZE = 0x4000
BANK = 13
STAGE7_SCENE = 0x08

DEATH_GUARD_ADDR = 0x570E
ART_GUARD_ADDR = 0x6EC6
MENU_DELAY_START = 0x6EC4
MENU_DELAY_CONTINUE = 0x6ECF
MENU_DELAY_END = 0x6EF4
PAIR_CALL_ADDR = 0x6F20
ART_CALL_ADDR = 0x6F89

DEATH_GUARD_SLOT_PREIMAGE = bytes(16)
DEATH_GUARD_BOUNDARY = bytes.fromhex("01 05 01 0B")
PAIR_CALL_PREIMAGE = bytes.fromhex("CD 00 71 CD 60 6A")
ART_CALL_PREIMAGE = bytes.fromhex("C4 0E 6A")
MENU_OWNER_PREIMAGE = bytes.fromhex(
    "F0 40 CB 77 28 04 CB 9F 18 02 CB DF E0 40"
)
MENU_DELAY_PREIMAGE = bytes(MENU_DELAY_END - MENU_DELAY_START)
MENU_DELAY_BOUNDARY = bytes.fromhex("23 2B C3 2C 57")

DEATH_GUARD = bytes.fromhex(
    "FA 80 D8 "          # LD A,[$D880]
    "FE 08 C8 "          # exact Stage 7: RET Z
    "C3 00 71"           # otherwise tail-enter death/story owner
)
ART_GUARD = bytes.fromhex(
    "FA 80 D8 "          # LD A,[$D880]
    "FE 08 C8 "          # exact Stage 7: RET Z
    "C3 0E 6A"           # otherwise tail-enter Stage-1 art owner
)


@dataclass(frozen=True)
class InstallReport:
    death_guard: int
    art_guard: int
    stage7_scene: int
    original_menu_delay_cycles: int
    guarded_menu_delay_cycles: int


def bank_offset(address: int) -> int:
    if not 0x4000 <= address < 0x8000:
        raise ValueError(f"switchable address out of range: ${address:04X}")
    return BANK * BANK_SIZE + address - 0x4000


def build_menu_delay_region() -> bytes:
    """Hide the art guard behind the register-exact 48-cycle menu path."""
    assert len(ART_GUARD) == 9
    code = bytearray([
        0x18, len(ART_GUARD),                # live menu path skips guard
    ])
    code.extend(ART_GUARD)
    assert MENU_DELAY_START + len(code) == MENU_DELAY_CONTINUE

    # JR +9 costs three cycles instead of the eleven skipped NOPs, saving
    # eight. PUSH/POP BC plus three JR +0 instructions restore 16 cycles;
    # the remaining 29 NOPs bring the complete live route back to 48.
    code.extend(bytes.fromhex("C5 C1 18 00 18 00 18 00"))
    code.extend(bytes(MENU_DELAY_END - MENU_DELAY_START - len(code)))
    assert len(code) == len(MENU_DELAY_PREIMAGE)
    return bytes(code)


def menu_delay_cycles(code: bytes) -> int:
    """Execute the live menu route and count machine cycles."""
    pc = 0
    cycles = 0
    stack: list[int] = []
    bc = 0xA55A
    while pc < len(code):
        opcode = code[pc]
        if opcode == 0x18:
            displacement = code[pc + 1]
            if displacement >= 0x80:
                displacement -= 0x100
            cycles += 3
            pc += 2 + displacement
        elif opcode == 0xC5:
            stack.append(bc)
            cycles += 4
            pc += 1
        elif opcode == 0xC1:
            bc = stack.pop()
            cycles += 3
            pc += 1
        elif opcode == 0x00:
            cycles += 1
            pc += 1
        else:
            raise AssertionError(f"unexpected live delay opcode ${opcode:02X}")
    assert not stack and bc == 0xA55A
    return cycles


def modeled_service(code: bytes, *, scene: int) -> str:
    """Return the modeled outcome of either exact-scene guard."""
    if code not in (DEATH_GUARD, ART_GUARD):
        raise ValueError("unknown service guard")
    if scene == STAGE7_SCENE:
        return "skip"
    return "death_story" if code == DEATH_GUARD else "stage1_art"


def install(rom: bytearray) -> InstallReport:
    if len(rom) != 32 * BANK_SIZE:
        raise AssertionError(f"expected expanded 512 KiB ROM, got {len(rom)}")

    def require(address: int, expected: bytes, label: str) -> int:
        offset = bank_offset(address)
        actual = bytes(rom[offset:offset + len(expected)])
        if actual != expected:
            raise AssertionError(
                f"{label} preimage changed at bank {BANK}:${address:04X}: "
                f"{actual.hex()} != {expected.hex()}"
            )
        return offset

    death_slot = require(
        DEATH_GUARD_ADDR,
        DEATH_GUARD_SLOT_PREIMAGE,
        "death-service guard slot",
    )
    require(
        DEATH_GUARD_ADDR + len(DEATH_GUARD_SLOT_PREIMAGE),
        DEATH_GUARD_BOUNDARY,
        "death-service guard boundary",
    )
    pair_call = require(
        PAIR_CALL_ADDR, PAIR_CALL_PREIMAGE, "death/title service pair"
    )
    art_call = require(ART_CALL_ADDR, ART_CALL_PREIMAGE, "Stage-1 art call")
    require(
        MENU_DELAY_START - len(MENU_OWNER_PREIMAGE),
        MENU_OWNER_PREIMAGE,
        "menu map owner",
    )
    menu_delay = require(
        MENU_DELAY_START, MENU_DELAY_PREIMAGE, "menu timing sled"
    )
    require(
        MENU_DELAY_END, MENU_DELAY_BOUNDARY, "menu timing-sled boundary"
    )

    rom[death_slot:death_slot + len(DEATH_GUARD)] = DEATH_GUARD
    delay_region = build_menu_delay_region()
    rom[menu_delay:menu_delay + len(delay_region)] = delay_region
    rom[pair_call:pair_call + 3] = bytes([
        0xCD, DEATH_GUARD_ADDR & 0xFF, DEATH_GUARD_ADDR >> 8,
    ])
    rom[art_call:art_call + 3] = bytes([
        0xC4, ART_GUARD_ADDR & 0xFF, ART_GUARD_ADDR >> 8,
    ])

    original_menu_cycles = len(MENU_DELAY_PREIMAGE)
    guarded_menu_cycles = menu_delay_cycles(delay_region)
    assert original_menu_cycles == guarded_menu_cycles == 48
    return InstallReport(
        death_guard=DEATH_GUARD_ADDR,
        art_guard=ART_GUARD_ADDR,
        stage7_scene=STAGE7_SCENE,
        original_menu_delay_cycles=original_menu_cycles,
        guarded_menu_delay_cycles=guarded_menu_cycles,
    )
