#!/usr/bin/env python3
"""r517: page-local CGB mirror for the native ending BGP fades.

The DMG ending hides page construction with BGP=$FF/$FE/$F9.  BGP does not
remap CGB palette RAM, so the colorized ROM needs to mirror those three
values into all eight BG rows.  The earlier r459t proof did that correctly
but spent about 3.8k T before the bounded attribute writer.  This revision:

* emits mode-safe, sub-frame 64-byte FF/FE/F9 fills;
* restores only the rows the revealed story art can display;
* aliases the cleaner's temporary BG6 cells to BG0 until the 18-row story
  pass is complete;
* aliases every ending row to its uniform BG1/BG2/BG0/BG3 owner until the
  96-row absolute pass is complete; and
* restores the exact eight-row deck incrementally, using the tuned story BG7
  source at $68F8 rather than the unrelated raw $6838 alias.

The three already-reviewed story-sweep guards in banks 13 and 16 are hooked,
plus the post-final scene publication. The palette-loader entry and global
fixed-bank fade service remain byte-for-byte native; the loader's shared
four-byte CRAM publisher emits black only while scene $1A is hidden by BGP=$FF.
The credits hook publishes its complete 20x18 visible attribute page after the
native absolute writer reaches row $60. Private fixed-bank callers for the
credits and shared ending-story transitions use equivalent bank-20 copies of
their native fade entries so each next CGB CRAM deck is prepared before its BGP
value is published in the same frame.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "tmp/boss-stage7-r475/candidate.gb"
BASE_SHA256 = (
    "59384e3c0ea5508ade2ff8d08af2f3012c4eff1f5f9cf1cebb2f04273cd1693f"
)
OUT = ROOT / "tmp/ending-bgp-handoff-r517"

BS = 0x4000
CAVE_BANK = 20
BODY = 0x7400
FIXED_SWITCH = 0x0061
FIXED_SWITCH_RET = 0x09C0
INACTIVE = 0x7E89

STATE = 0xDF50
ROW = 0xDF4A
MIRROR_FF = 0x01
MIRROR_FE = 0x02
MIRROR_F9 = 0x03
MIRROR_00 = 0x04
MIRROR_40 = 0x05
MIRROR_84 = 0x06
MIRROR_90 = 0x07
MIRROR_C4 = 0x08
MIRROR_D9 = 0x09
MIRROR_EE = 0x0A
MIRROR_LIMIT = 0x0B
CREDITS_BLACK_SETTLED = 0x11
STORY_RESTORE = 0x80
ENDING_WAIT = 0x90
ENDING_RESTORE = 0xA0
STORY_DONE_ROW = 0x12
ENDING_DONE_ROW = 0x60
CREDITS_REVEAL_ROW = 0x49
POSTFINAL_SCENE = 0x5513
POSTFINAL_CONT = 0x5519
POSTFINAL_BANK20_ENTRY = 0x5519
CREDITS_FADE_CALL = 0x3E72
CREDITS_FADE_WRAPPER = 0x4289
CREDITS_FADE_BANK20_CONT = CREDITS_FADE_WRAPPER + 6
CREDITS_FADE_OUT_CALL = 0x3E84
CREDITS_FADE_OUT_WRAPPER = CREDITS_FADE_WRAPPER
CREDITS_FADE_OUT_BANK20_CONT = CREDITS_FADE_BANK20_CONT
STORY_FADE_OUT_CALL = 0x371E
STORY_FADE_IN_JUMP = 0x3735
STORY_COMBINED_FADE_OUT_CALL = 0x5523
EPILOGUE_COMBINED_FADE_OUT_CALL = 0x3DD4
EPILOGUE_FADE_OUT_CALL = 0x5553
STORY_FADE_WRAPPER = CREDITS_FADE_WRAPPER + 6
STORY_FADE_BANK20_CONT = STORY_FADE_WRAPPER + 6
PALETTE_PUBLISHER = 0x71DB
PALETTE_QUAD_WRITE = 0x71F7
PALETTE_RESUME_STUB = 0x71F0
PALETTE_BANK20_ENTRY = 0x71E3

SITES = {
    # name: (address, exact preimage, exact success continuation, bank20 entry)
    "S1": (0x7E67, bytes.fromhex("FA E8 DC B8 20 1C"), 0x7E6D, 0x7E6C),
    "S2": (0x7E8C, bytes.fromhex("F0 E4 FE 01 20 F7"), 0x7E92, 0x7E91),
    "S3": (0x7EAA, bytes.fromhex("F0 E4 FE 01 20 D9"), 0x7EB0, 0x7EAF),
}


def off(bank: int, address: int) -> int:
    return bank * BS + address - 0x4000


class Asm:
    def __init__(self, base: int):
        self.base = base
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.rel: list[tuple[int, str]] = []
        self.abs: list[tuple[int, str]] = []

    def db(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def label(self, name: str) -> None:
        assert name not in self.labels, name
        self.labels[name] = self.base + len(self.code)

    def jr(self, opcode: int, target: str) -> None:
        self.db(opcode, 0)
        self.rel.append((len(self.code) - 1, target))

    def absolute(self, opcode: int, target: str) -> None:
        self.db(opcode, 0, 0)
        self.abs.append((len(self.code) - 2, target))

    def finish(self) -> bytes:
        for position, target in self.rel:
            distance = self.labels[target] - (self.base + position + 1)
            assert -128 <= distance <= 127, (target, distance)
            self.code[position] = distance & 0xFF
        for position, target in self.abs:
            address = self.labels[target]
            self.code[position] = address & 0xFF
            self.code[position + 1] = address >> 8
        return bytes(self.code)


def build_body(deck: bytes) -> tuple[bytes, dict[str, int]]:
    assert len(deck) == 64
    a = Asm(BODY)

    # The production post-final continuation publishes scene $1A while the
    # inherited BGP is already black. Commit the matching CGB black deck
    # before that scene byte becomes visible, then resume at the untouched
    # POP AF. This also makes the verifier's authentic title-to-$5513 entry
    # obey the same blanking invariant as the natural final-boss route.
    a.label("postfinal_blank")
    a.db(0xF0, 0x99, 0xF5, 0x3E, CAVE_BANK, 0xCD, 0x61, 0x00)
    a.db(0xC5, 0xD5, 0xE5)
    a.db(0xF0, 0x70, 0xF5, 0x3E, 0x01, 0xE0, 0x70)
    a.db(0x3E, 0xFF)
    a.absolute(0xCD, "mirror_story_value")
    a.db(0x3E, 0x1A, 0xEA, 0x80, 0xD8)
    a.db(0xF1, 0xE0, 0x70, 0xE1, 0xD1, 0xC1)
    a.db(0xF1, 0x21, POSTFINAL_CONT & 0xFF, POSTFINAL_CONT >> 8,
         0xE5, 0xC3, 0xBE, 0x09)

    # The shared bank-1 trampoline serves the credits-only callers at $3E72
    # and $3E84. Their original return addresses remain on the stack, so the
    # bank-20 continuation can select the matching native entry without adding
    # another fixed-bank cave.
    a.label("credits_fade_dispatch")
    a.db(0xE5, 0xF8, 0x02, 0x7E, 0xFE, 0x75)
    a.jr(0x28, "credits_fade_dispatch_in")
    a.db(0xFE, 0x87)
    a.jr(0x28, "credits_fade_dispatch_out")
    a.label("credits_fade_dispatch_in")
    a.db(0xE1)
    a.absolute(0xC3, "credits_fade_sync")
    a.label("credits_fade_dispatch_out")
    a.db(0xE1)
    a.absolute(0xC3, "credits_fade_out_sync")

    # Duplicate the native entries and their $406F wait helper exactly, adding
    # only a register-safe ending mirror immediately before each RST-$08 write.
    # Publishing BGP last prevents a frame-boundary observer from seeing the
    # next DMG mapping while the 64-byte CGB palette fill is still in flight.
    # The bank-1 trampoline selects this bank through $0061, so FF99 remains
    # coherent while the copied wait admits VBlank/Timer interrupts.
    a.label("credits_fade_sync")
    a.db(0xE5, 0xC5, 0x06, 0x04, 0xAF,
         0x21, 0xD4, 0x0F, 0xD7)           # native $0F47 prologue
    a.jr(0x18, "credits_fade_sync_loop")
    a.label("credits_fade_out_sync")
    a.db(0xE5, 0xC5, 0x06, 0x04, 0xAF,
         0x21, 0xD0, 0x0F, 0xD7)           # native $0F3D prologue
    a.label("credits_fade_sync_loop")
    a.absolute(0xCD, "wait_vblank")
    a.db(0x2A, 0xF5, 0xC5, 0xD5, 0xE5)    # preserve next BGP + loop ABI
    a.absolute(0xCD, "mirror_credits_value")
    a.db(0xE1, 0xD1, 0xC1, 0xF1, 0xCF)    # publish BGP only after CRAM
    a.db(0x05)
    a.jr(0x20, "credits_fade_sync_loop")
    a.db(0xC1, 0xE1, 0x3E, 0x01,
         0xC3, 0x61, 0x00)                 # restore bank 1; mapper RET

    # Fixed:$371E CALLs native story fade-out $0F33, while fixed:$3735
    # tail-jumps to native fade-in $0F51. The latter therefore retains the
    # enclosing routine's $371B return address. Dispatch on those low bytes,
    # then reproduce both native entries with the same CRAM-before-BGP rule.
    a.label("story_fade_dispatch")
    a.db(0xE5, 0xF8, 0x02, 0x7E, 0xFE, 0x21)
    a.jr(0x28, "story_fade_dispatch_out")
    a.db(0xFE, 0x1B)
    a.jr(0x28, "story_fade_dispatch_in")
    a.db(0xFE, 0x26)
    a.jr(0x28, "story_fade_dispatch_combined")
    a.db(0xFE, 0xD7)
    a.jr(0x28, "story_fade_dispatch_combined")
    a.db(0xFE, 0x56)
    a.jr(0x28, "story_fade_dispatch_out")
    a.label("story_fade_dispatch_out")
    a.db(0xE1)
    a.absolute(0xC3, "story_fade_out_sync")
    a.label("story_fade_dispatch_in")
    a.db(0xE1)
    a.absolute(0xC3, "story_fade_in_sync")
    a.label("story_fade_dispatch_combined")
    a.db(0xE1)
    a.absolute(0xC3, "story_combined_fade_out_sync")

    a.label("story_fade_out_sync")
    a.db(0xE5, 0xC5, 0x06, 0x04, 0xAF,
         0x21, 0xCC, 0x0F, 0xD7)           # native $0F33 prologue
    a.jr(0x18, "story_fade_sync_loop")
    a.label("story_fade_in_sync")
    a.db(0xE5, 0xC5, 0x06, 0x04, 0xAF,
         0x21, 0xC8, 0x0F, 0xD7)           # native $0F51 prologue
    a.label("story_fade_sync_loop")
    a.absolute(0xCD, "wait_vblank")
    a.db(0x2A, 0xF5, 0xC5, 0xD5, 0xE5)
    a.absolute(0xCD, "mirror_routed_combined_value")
    a.db(0xE1, 0xD1, 0xC1, 0xF1, 0xCF)
    a.db(0x05)
    a.jr(0x20, "story_fade_sync_loop")
    a.db(0xC1, 0xE1, 0x3E, 0x01,
         0xC3, 0x61, 0x00)                 # restore bank 1; mapper RET

    # Post-final fixed:$5523 calls the combined BG/OBJ fade at $0F9D. Keep
    # its OBP table and 30-frame cadence native while preparing the matching
    # CGB BG deck before each BGP write.
    a.label("story_combined_fade_out_sync")
    a.db(0xE5, 0xD5, 0xC5, 0xAF, 0xE0, 0x49, 0x06, 0x04,
         0x21, 0xD0, 0x0F, 0x11, 0xC4, 0x0F)
    a.label("story_combined_fade_out_loop")
    a.db(0xC5, 0x06, 0x1E)
    a.absolute(0xCD, "wait_30_frames")
    a.db(0xC1, 0x2A, 0xF5, 0xC5, 0xD5, 0xE5)
    a.absolute(0xCD, "mirror_routed_combined_value")
    a.db(0xE1, 0xD1, 0xC1, 0xF1, 0xE0, 0x47)
    a.db(0x1A, 0x13, 0xE0, 0x48, 0x05)
    a.jr(0x20, "story_combined_fade_out_loop")
    a.db(0xC1, 0xD1, 0xE1, 0x3E, 0x01,
         0xC3, 0x61, 0x00)

    # The fixed routine is shared by the two ending-story scene IDs. Keep any
    # unexpected caller native apart from its byte-identical fade cadence.
    a.label("mirror_routed_story_value")
    a.db(0xF5, 0xFA, 0x80, 0xD8, 0xFE, 0x19)
    a.jr(0x28, "mirror_routed_story_yes")
    a.db(0xFE, 0x1A)
    a.jr(0x28, "mirror_routed_story_yes")
    a.db(0xF1, 0xC9)
    a.label("mirror_routed_story_yes")
    a.db(0xF1)
    a.absolute(0xC3, "mirror_story_value")

    # The combined fade also owns the credits-to-epilogue handoff. Route its
    # scene-$16 and committed epilogue contexts through the uniform-ending
    # mirror; story scene IDs retain the page-aware mirror above.
    a.label("mirror_routed_combined_value")
    a.db(0xF5, 0xFA, 0x80, 0xD8, 0xFE, 0x19)
    a.jr(0x28, "mirror_routed_combined_story")
    a.db(0xFE, 0x1A)
    a.jr(0x28, "mirror_routed_combined_story")
    a.db(0xFE, 0x16)
    a.jr(0x28, "mirror_routed_combined_ending")
    a.db(0xB7)
    a.jr(0x20, "mirror_routed_combined_no")
    a.db(0xFA, 0x89, 0xD8, 0xFE, 0x0C)
    a.jr(0x28, "mirror_routed_combined_ending")
    a.label("mirror_routed_combined_no")
    a.db(0xF1, 0xC9)
    a.label("mirror_routed_combined_story")
    a.db(0xF1)
    a.absolute(0xC3, "mirror_story_value")
    a.label("mirror_routed_combined_ending")
    a.db(0xF1)
    a.absolute(0xC3, "mirror_ending_value")

    # Each entry is reached after a raw switch-under-self.  Preserve every
    # register used by the displaced story guard and by its continuation.
    a.label("s1")
    a.db(0xC5, 0xD5, 0xE5)                  # PUSH BC/DE/HL
    a.db(0x78, 0xFE, 0x02)                  # opening is intentionally native
    a.jr(0x20, "s1_mirror")
    a.db(0xAF, 0xEA, STATE & 0xFF, STATE >> 8)
    a.jr(0x18, "s1_after")
    a.label("s1_mirror")
    a.absolute(0xCD, "mirror_story")
    a.label("s1_after")
    a.db(0xE1, 0xD1, 0xC1)
    a.db(0xFA, 0xE8, 0xDC, 0xB8)            # displaced DCE8 == B guard
    a.jr(0x20, "to_inactive")
    a.db(0x21, SITES["S1"][2] & 0xFF, SITES["S1"][2] >> 8)
    a.jr(0x18, "leave_to_hl")

    a.label("s2")
    a.db(0xC5, 0xD5, 0xE5)
    a.db(0xF0, 0xE4, 0xFE, 0x01)            # title/other never mirrors
    a.jr(0x20, "s2_after")
    a.absolute(0xCD, "mirror_ending")
    a.label("s2_after")
    a.db(0xE1, 0xD1, 0xC1)
    a.db(0xF0, 0xE4, 0xFE, 0x01)            # displaced FFE4 == 1 guard
    a.jr(0x20, "to_inactive")
    a.db(0x21, SITES["S2"][2] & 0xFF, SITES["S2"][2] >> 8)
    a.jr(0x18, "leave_to_hl")

    a.label("s3")
    a.db(0xC5, 0xD5, 0xE5)
    a.db(0xF0, 0xE4, 0xFE, 0x01)
    a.jr(0x20, "s3_after")
    a.db(0xFA, 0x89, 0xD8, 0xFE, 0x0C)
    a.jr(0x20, "s3_after")
    a.absolute(0xCD, "mirror_ending")
    a.label("s3_after")
    a.db(0xE1, 0xD1, 0xC1)
    a.db(0xF0, 0xE4, 0xFE, 0x01)            # displaced FFE4 == 1 guard
    a.jr(0x20, "to_inactive")
    a.db(0x21, SITES["S3"][2] & 0xFF, SITES["S3"][2] >> 8)
    a.jr(0x18, "leave_to_hl")

    a.label("to_inactive")
    a.db(0x21, INACTIVE & 0xFF, INACTIVE >> 8)
    a.label("leave_to_hl")
    a.db(0xE5, 0xF0, 0x99, 0xC3,
         FIXED_SWITCH_RET & 0xFF, FIXED_SWITCH_RET >> 8)

    # Story and uniform-ending mirrors share only the three native fade
    # values in the four native transition tables. E4 is the artistic deck;
    # E7 and every other raster-only value are normal display states.
    a.label("mirror_story")
    a.db(0xF0, 0x47)
    a.label("mirror_story_value")
    for value, target in (
        (0x00, "fade_00"), (0x40, "fade_40"),
        (0x84, "fade_84"), (0x90, "fade_90"),
        (0xC4, "fade_c4"), (0xD9, "fade_d9"),
        (0xEE, "fade_ee"), (0xF9, "fade_f9"),
        (0xFE, "fade_fe"), (0xFF, "fade_ff"),
    ):
        a.db(0xFE, value)
        a.absolute(0xCA, target)
    a.absolute(0xC3, "story_normal")

    a.label("mirror_ending")
    a.db(0xF0, 0x47)
    a.label("mirror_ending_value")
    for value, target in (
        (0x00, "fade_00"), (0x40, "fade_40"),
        (0x84, "fade_84"), (0x90, "fade_90"),
        (0xC4, "fade_c4"), (0xD9, "fade_d9"),
        (0xEE, "fade_ee"), (0xF9, "fade_f9"),
        (0xFE, "fade_fe"), (0xFF, "ending_fade_ff"),
    ):
        a.db(0xFE, value)
        a.absolute(0xCA, target)
    a.db(0xFE, 0xE4)
    a.absolute(0xCA, "ending_normal")
    a.db(0xC9)

    # The credits viewport becomes a uniform BG1 page before its first reveal.
    # Its private fade therefore updates only BG1: eight bytes complete early
    # in the same VBlank, avoiding a boundary between a 64-byte preparation
    # and the following BGP publication. The first FE step waits under exact
    # black until the native writer has completed its visible BG1 mask.
    a.label("mirror_credits_value")
    a.db(0xF5, 0xF0, 0xF9, 0xB7)
    a.jr(0x28, "mirror_credits_value_current")
    a.db(0xF1)
    a.absolute(0xC3, "mirror_ending_value")
    a.label("mirror_credits_value_current")
    a.db(0xF1)
    a.db(0xFE, 0xFF)
    a.absolute(0xCA, "credits_fade_ff")
    a.db(0xFE, 0xFE)
    a.absolute(0xCA, "credits_fade_fe")
    a.db(0xFE, 0xF9)
    a.absolute(0xCA, "credits_fade_f9")
    a.absolute(0xC3, "credits_normal")

    a.label("credits_fade_ff")
    a.db(0xFA, STATE & 0xFF, STATE >> 8, 0xFE, CREDITS_BLACK_SETTLED, 0xC8)
    a.db(0xFE, MIRROR_FF, 0xC8, 0x3E, 0x01)
    a.absolute(0x21, "row_ff")
    a.absolute(0xCD, "copy_credit_slot")
    a.db(0x3E, MIRROR_FF, 0xEA, STATE & 0xFF, STATE >> 8, 0xC9)

    a.label("credits_fade_fe")
    a.label("credits_wait_mask")
    a.db(0xFA, ROW & 0xFF, ROW >> 8, 0xFE, CREDITS_REVEAL_ROW)
    a.jr(0x30, "credits_fe_ready")
    a.absolute(0xCD, "wait_vblank")
    a.jr(0x18, "credits_wait_mask")
    a.label("credits_fe_ready")
    a.db(0xFA, STATE & 0xFF, STATE >> 8, 0xFE, MIRROR_FE, 0xC8)
    a.db(0x3E, 0x01)
    a.absolute(0x21, "row_fe")
    a.absolute(0xCD, "copy_credit_slot")
    a.db(0x3E, MIRROR_FE, 0xEA, STATE & 0xFF, STATE >> 8, 0xC9)

    a.label("credits_fade_f9")
    a.db(0xFA, STATE & 0xFF, STATE >> 8, 0xFE, MIRROR_F9, 0xC8)
    a.db(0x3E, 0x01)
    a.absolute(0x21, "row_f9")
    a.absolute(0xCD, "copy_credit_slot")
    a.db(0x3E, MIRROR_F9, 0xEA, STATE & 0xFF, STATE >> 8, 0xC9)

    a.label("credits_normal")
    a.db(0x3E, 0x01)
    a.absolute(0x21, "deck_1")
    a.absolute(0xCD, "copy_credit_slot")
    a.db(0x3E, ENDING_WAIT, 0xEA, STATE & 0xFF, STATE >> 8, 0xC9)

    # A steady fade step is a cheap no-op. During initial post-final page
    # construction, however, the native palette loader can overwrite the
    # already-published black deck without changing BGP. Recheck BG0 color 0
    # from the row-publisher hook and reassert black whenever that occurs.
    a.label("fade_ff")
    a.db(0xFA, STATE & 0xFF, STATE >> 8, 0xFE, MIRROR_FF)
    a.jr(0x20, "fade_ff_fill")
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x1A, 0xC0)
    a.db(0xF0, 0xF9, 0xB7, 0xC0)
    a.db(0xF0, 0x68, 0xF5, 0x3E, 0x01, 0xE0, 0x68)
    a.db(0xF0, 0x69, 0xB7)
    a.jr(0x28, "fade_ff_restore_bcps")
    a.absolute(0xCD, "fill_ff")
    a.label("fade_ff_restore_bcps")
    a.db(0xF1, 0xE0, 0x68, 0xC9)
    a.label("fade_ff_fill")
    a.absolute(0xCD, "fill_ff")
    a.db(0x3E, MIRROR_FF, 0xEA, STATE & 0xFF, STATE >> 8, 0xC9)

    # Other changed steps perform one specialized, sequential 64-byte fill
    # and record their exact owner.
    for label, marker, fill in (
        ("fade_fe", MIRROR_FE, "fill_fe"),
        ("fade_f9", MIRROR_F9, "fill_f9"),
    ):
        a.label(label)
        a.db(0xFA, STATE & 0xFF, STATE >> 8, 0xFE, marker, 0xC8)
        a.absolute(0xCD, fill)
        a.db(0x3E, marker, 0xEA, STATE & 0xFF, STATE >> 8, 0xC9)

    for label, marker, row in (
        ("fade_00", MIRROR_00, "row_00"),
        ("fade_40", MIRROR_40, "row_40"),
        ("fade_84", MIRROR_84, "row_84"),
        ("fade_90", MIRROR_90, "row_90"),
        ("fade_c4", MIRROR_C4, "row_c4"),
        ("fade_d9", MIRROR_D9, "row_d9"),
        ("fade_ee", MIRROR_EE, "row_ee"),
    ):
        a.label(label)
        a.db(0xFA, STATE & 0xFF, STATE >> 8, 0xFE, marker, 0xC8)
        a.absolute(0x21, row)
        a.absolute(0xCD, "copy_repeat")
        a.db(0x3E, marker, 0xEA, STATE & 0xFF, STATE >> 8, 0xC9)

    # The first credits transition begins from the post-final art deck. The
    # native page loader can restore that deck after fade_ff has made CRAM
    # black. Detect the actual overwrite through BG0 color-0's high byte,
    # preserve BCPS, then perform one final black fill. Story fades retain the
    # cheaper shared idempotent handler above.
    a.label("ending_fade_ff")
    a.db(0xFA, STATE & 0xFF, STATE >> 8, 0xFE, CREDITS_BLACK_SETTLED, 0xC8)
    a.db(0xFE, MIRROR_FF)
    a.absolute(0xC2, "fade_ff")
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x16, 0xC0)
    a.db(0xF0, 0xF9, 0xB7, 0xC0)
    a.db(0xF0, 0x68, 0xF5, 0x3E, 0x01, 0xE0, 0x68)
    a.db(0xF0, 0x69, 0x57, 0x7A, 0xB7)
    a.jr(0x28, "ending_fade_ff_restore")
    a.absolute(0xCD, "fill_ff")
    a.db(0x3E, CREDITS_BLACK_SETTLED,
         0xEA, STATE & 0xFF, STATE >> 8)
    a.label("ending_fade_ff_restore")
    a.db(0xF1, 0xE0, 0x68, 0xC9)

    a.label("story_normal")
    a.db(0xFA, STATE & 0xFF, STATE >> 8, 0xFE, STORY_RESTORE)
    a.absolute(0xD2, "story_restore")       # state >= $80
    a.db(0xB7, 0xC8, 0xFE, MIRROR_LIMIT, 0xD0)
    a.db(0xFA, 0xF0, 0xDC, 0xFE, 0x04)
    a.jr(0x28, "story_art4")
    a.db(0xFE, 0x05)
    a.jr(0x28, "story_art56")
    a.db(0xFE, 0x06)
    a.jr(0x28, "story_art56")
    a.db(0xFE, 0x07)
    a.jr(0x28, "story_art7")
    a.db(0xC9)                              # page ID not committed yet

    a.label("story_art4")
    for slot in (0, 3, 4, 5):
        a.db(0x3E, slot)
        a.absolute(0x21, f"deck_{slot}")
        a.absolute(0xCD, "copy_slot")
    a.jr(0x18, "story_alias6")

    a.label("story_art56")
    for slot in (0, 2, 7):
        a.db(0x3E, slot)
        a.absolute(0x21, f"deck_{slot}")
        a.absolute(0xCD, "copy_slot")
    a.label("story_alias6")
    a.db(0x3E, 0x06)
    a.absolute(0x21, "deck_0")              # unfinished cleaner cells are BG0
    a.absolute(0xCD, "copy_slot")
    a.jr(0x18, "story_reveal_done")

    a.label("story_art7")
    for slot in (0, 2, 6, 7):
        a.db(0x3E, slot)
        a.absolute(0x21, f"deck_{slot}")
        a.absolute(0xCD, "copy_slot")
    a.label("story_reveal_done")
    a.db(0x3E, STORY_RESTORE,
         0xEA, STATE & 0xFF, STATE >> 8, 0xC9)

    a.label("story_restore")
    a.db(0xFE, STORY_RESTORE + 8, 0xD0)      # unrelated/finished state
    a.db(0xE6, 0x07, 0x57)                  # D = restore cursor
    a.absolute(0x21, "restore_order")
    a.db(0xD7, 0x5E)                        # E = selected deck slot
    a.db(0x7B, 0xFE, 0x06)
    a.jr(0x20, "story_restore_slot")
    # BG6 is the cleaner's temporary cell value. Arts 4/5/6 never use it, so
    # retain the exact BG0 alias through their complete visible lifetime.
    # Art 7 installs its real BG6 in story_art7 before reaching this cursor.
    a.absolute(0xC3, "clear_state")
    a.label("story_restore_slot")
    a.db(0x7B, 0x07, 0x07, 0x07)
    a.absolute(0x21, "deck")
    a.db(0xD7, 0x7B)
    a.absolute(0xCD, "copy_slot")
    a.db(0x7A, 0xFE, 0x07)
    a.jr(0x28, "clear_state")
    a.db(0x3C, 0xF6, STORY_RESTORE,
         0xEA, STATE & 0xFF, STATE >> 8, 0xC9)

    a.label("ending_normal")
    a.db(0xFA, STATE & 0xFF, STATE >> 8, 0xFE, ENDING_WAIT)
    a.db(0xC8)                              # one-shot page repair is complete
    a.db(0xFE, CREDITS_BLACK_SETTLED)
    a.jr(0x28, "ending_reveal")
    a.db(0xFE, ENDING_RESTORE)
    a.absolute(0xD2, "repair_credits_row")
    a.db(0xB7, 0xC8, 0xFE, MIRROR_LIMIT, 0xD0)
    # D880=$16 chooses credits BG1 or END BG2; D880=$00 chooses
    # epilogue-preamble BG0 or epilogue-text BG3.
    a.label("ending_reveal")
    a.db(0xFA, 0x80, 0xD8, 0xB7)
    a.jr(0x28, "ending_epilogue_row")
    a.db(0xF0, 0xF9, 0xB7, 0x3E, 0x01)
    a.jr(0x28, "ending_have_row")
    a.db(0x3C)                              # END -> BG2
    a.jr(0x18, "ending_have_row")
    a.label("ending_epilogue_row")
    a.db(0xFA, 0xE2, 0xDC, 0xB7, 0x3E, 0x00)
    a.jr(0x28, "ending_have_row")
    a.db(0x3E, 0x03)                        # epilogue text -> BG3
    a.label("ending_have_row")
    a.db(0x07, 0x07, 0x07)
    a.absolute(0x21, "deck")
    a.db(0xD7)
    a.absolute(0xCD, "copy_repeat")
    # Credits inherit a partial story mask. Arm a bounded full-page repair;
    # every other ending page already receives its exact native full mask.
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x16)
    a.jr(0x20, "ending_complete")
    a.db(0xF0, 0xF9, 0xB7)
    a.jr(0x20, "ending_complete")
    a.db(0x3E, ENDING_RESTORE,
         0xEA, STATE & 0xFF, STATE >> 8)
    a.absolute(0xC3, "repair_credits_row")
    a.label("ending_complete")
    a.db(0x3E, ENDING_WAIT,
         0xEA, STATE & 0xFF, STATE >> 8, 0xC9)

    a.label("clear_state")
    a.db(0xAF, 0xEA, STATE & 0xFF, STATE >> 8, 0xC9)

    a.label("repair_credits_row")
    a.db(0xFE, ENDING_RESTORE + 18, 0xD0)
    a.db(0xFA, ROW & 0xFF, ROW >> 8, 0xFE, ENDING_DONE_ROW, 0xC0)
    a.db(0xFA, STATE & 0xFF, STATE >> 8, 0xE6, 0x1F, 0x07)
    a.absolute(0x21, "credits_row_addresses")
    a.db(0xD7, 0x5E, 0x23, 0x56, 0x62, 0x6B)
    a.db(0xF0, 0x4F, 0xF5, 0x3E, 0x01, 0xE0, 0x4F)
    a.db(0x06, 0x0A, 0x3E, 0x01)
    a.label("repair_credits_pair")
    a.absolute(0xCD, "wait_cram_window")
    a.db(0x22, 0x22, 0x05)
    a.jr(0x20, "repair_credits_pair")
    a.db(0xF1, 0xE0, 0x4F)
    a.db(0xFA, STATE & 0xFF, STATE >> 8, 0x3C,
         0xFE, ENDING_RESTORE + 18)
    a.jr(0x38, "repair_credits_store")
    a.db(0x3E, ENDING_WAIT)
    a.label("repair_credits_store")
    a.db(0xEA, STATE & 0xFF, STATE >> 8, 0xC9)

    # Specialized fade fills. BCPS auto-increment is sequential, so no CRAM
    # index is exposed half-old after the service returns. Each two-byte
    # color begins only in LCD mode 0/1, so CGB mode-3 write rejection
    # cannot produce a partially committed visible palette.
    a.label("fill_ff")
    a.absolute(0x21, "row_ff")
    a.absolute(0xC3, "copy_repeat")

    a.label("fill_fe")
    a.absolute(0x21, "row_fe")
    a.absolute(0xC3, "copy_repeat")

    a.label("fill_f9")
    a.absolute(0x21, "row_f9")
    a.absolute(0xC3, "copy_repeat")

    # Credits enter a fresh VBlank before changing their sole visible CRAM
    # row. Catch the last visible line with interrupts enabled, then mask only
    # the final HBlank and short eight-byte VBlank copy so neither the ISR nor
    # a frame callback can expose a partially changed row.
    a.label("copy_credit_slot")
    a.db(0xF5)
    a.absolute(0xCD, "wait_last_visible_mode3")
    a.db(0xF3)
    a.absolute(0xCD, "wait_combined_vblank")
    a.db(0xF1)
    a.db(0x07, 0x07, 0x07, 0xF6, 0x80, 0xE0, 0x68)
    for _ in range(8):
        a.db(0x2A, 0xE0, 0x69)
    a.db(0xFB, 0xC9)

    # A=destination slot, HL=one eight-byte row.
    a.label("copy_slot")
    a.db(0x07, 0x07, 0x07, 0xF6, 0x80, 0xE0, 0x68)
    for index in range(8):
        wait_label = f"copy_slot_wait_{index}"
        a.label(wait_label)
        a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x02)
        a.jr(0x30, wait_label)
        a.db(0x2A, 0xE0, 0x69)
    a.db(0xC9)

    # HL=one eight-byte row; replicate it through BG0..BG7.
    a.label("copy_repeat")
    a.db(0x3E, 0x80, 0xE0, 0x68, 0x06, 0x08)
    a.label("copy_repeat_palette")
    a.db(0x54, 0x5D)
    for index in range(8):
        wait_label = f"copy_repeat_wait_{index}"
        a.label(wait_label)
        a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x02)
        a.jr(0x30, wait_label)
        a.db(0x2A, 0xE0, 0x69)
    a.db(0x62, 0x6B, 0x05)
    a.jr(0x20, "copy_repeat_palette")
    # Reassert the two auto-increment wrap endpoints explicitly. Fine-grained
    # hardware-latch traces showed that an otherwise complete 64-byte pass can
    # retain the previous byte at index 0 or 63 when it lands on a mode edge.
    a.label("copy_repeat_retry_first_wait")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x02)
    a.jr(0x30, "copy_repeat_retry_first_wait")
    a.db(0x3E, 0x80, 0xE0, 0x68, 0x7E, 0xE0, 0x69)
    a.label("copy_repeat_retry_last_wait")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x02)
    a.jr(0x30, "copy_repeat_retry_last_wait")
    a.db(0x3E, 0xFF, 0xE0, 0x68, 0xE5, 0x3E, 0x07, 0xD7,
         0x7E, 0xE0, 0x69, 0xE1)
    a.db(0xC9)

    # Preserve the byte being written while waiting for a palette-accessible
    # LCD phase. Mode 2 is rejected as well, ensuring the following two-byte
    # group cannot run directly into mode 3 on normal-speed CGB hardware.
    a.label("wait_cram_window")
    a.db(0xF5)
    a.label("wait_cram_window_poll")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x02)
    a.jr(0x30, "wait_cram_window_poll")
    a.db(0xF1, 0xC9)

    # Byte-exact copy of bank 1:$406F. The credits trampoline keeps FF99 and
    # the MBC bank coherent at 20, so interrupts safely return to this loop.
    a.label("wait_vblank")
    a.db(0xF5, 0xAF, 0xE0, 0xD4)
    a.label("wait_vblank_poll")
    a.db(0xF0, 0xD4, 0xFE, 0x04)
    a.jr(0x20, "wait_vblank_poll")
    a.db(0xAF, 0xE0, 0xD4, 0xF1, 0xC9)

    # Byte-exact copies of bank 1:$4068 and $407E. The native combined fade
    # uses them to wait 30 display frames between adjacent table entries.
    a.label("wait_30_frames")
    a.absolute(0xCD, "wait_mode3_to_vblank")
    a.db(0x05)
    a.jr(0x20, "wait_30_frames")
    a.db(0xC9)

    a.label("wait_mode3_to_vblank")
    a.label("wait_mode3")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, "wait_mode3")
    a.label("wait_combined_vblank")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0x3D)
    a.jr(0x20, "wait_combined_vblank")
    a.db(0xC9)

    a.label("wait_last_visible_mode3")
    a.label("wait_last_visible_mode3_poll")
    a.db(0xF0, 0x44, 0xFE, 0x8F)
    a.jr(0x20, "wait_last_visible_mode3_poll")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, "wait_last_visible_mode3_poll")
    a.db(0xC9)

    # Bank 13's only 49-byte zero run is part of Angela's live arena LUT, so
    # the palette publisher cannot own a local cave. Each mirrored bank saves
    # its identity at $71DB and CALLs the native mapper, whose return-under-self
    # enters this bank-20 guard at $71E3 with FF99 coherent for interrupts.
    # Native writes map back through a four-byte source-bank stub which restores
    # the live palette pointer before resuming the untouched $71F7 tail.
    a.label("palette_guard")
    a.db(0xF1, 0xC5, 0x47)                  # bank -> B; preserve caller BC
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x16)
    a.jr(0x28, "palette_guard_suppress")
    a.db(0xFE, 0x1A)
    a.jr(0x20, "palette_guard_scene_zero")
    a.db(0xF0, 0x47, 0xFE, 0xE4)
    a.jr(0x20, "palette_guard_suppress")
    a.jr(0x18, "palette_guard_native")
    a.label("palette_guard_scene_zero")
    a.db(0xB7)
    a.jr(0x20, "palette_guard_native")
    a.db(0xFA, 0x89, 0xD8, 0xFE, 0x0C)
    a.jr(0x20, "palette_guard_native")
    a.db(0xF0, 0x47, 0xFE, 0xFF)
    a.jr(0x20, "palette_guard_native")
    a.label("palette_guard_suppress")
    a.db(0x23, 0x23, 0x23, 0x23)
    a.db(0x78, 0xC1, 0xC3, FIXED_SWITCH & 0xFF, FIXED_SWITCH >> 8)
    a.label("palette_guard_native")
    a.db(0xF0, 0x40, 0xE6, 0x80)            # LCD off: no mode wait
    a.jr(0x28, "palette_guard_native_ready")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x01)
    a.jr(0x28, "palette_guard_native_ready")
    a.label("palette_guard_wait_mode3")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, "palette_guard_wait_mode3")
    a.label("palette_guard_wait_hblank")
    a.db(0xF0, 0x41, 0xE6, 0x03)
    a.jr(0x20, "palette_guard_wait_hblank")
    a.label("palette_guard_native_ready")
    a.db(0x78, 0xC1, 0xE5,
         0x21, PALETTE_RESUME_STUB & 0xFF, PALETTE_RESUME_STUB >> 8,
         0xE5, 0xC3, FIXED_SWITCH & 0xFF, FIXED_SWITCH >> 8)

    a.label("restore_order")
    a.db(0, 1, 2, 3, 4, 5, 7, 6)
    a.label("credits_row_addresses")
    for row in range(18):
        address = 0x9800 + row * 32
        a.db(address & 0xFF, address >> 8)
    # Exact DMG rows for the non-E4 values in the other native fade tables.
    for name, row in (
        ("row_ff", "0000000000000000"),
        ("row_fe", "4a29000000000000"),
        ("row_f9", "94524a2900000000"),
        ("row_00", "ff7fff7fff7fff7f"),
        ("row_40", "ff7fff7fff7f9452"),
        ("row_84", "ff7f9452ff7f4a29"),
        ("row_90", "ff7fff7f94524a29"),
        ("row_c4", "ff7f9452ff7f0000"),
        ("row_d9", "94524a2994520000"),
        ("row_ee", "4a2900004a290000"),
    ):
        a.label(name)
        a.db(*bytes.fromhex(row))
    a.label("deck")
    for slot in range(8):
        a.label(f"deck_{slot}")
        a.db(*deck[slot * 8:(slot + 1) * 8])
    return a.finish(), a.labels


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x134:0x14D]:
        header = (header - value - 1) & 0xFF
    rom[0x14D] = header
    rom[0x14E] = rom[0x14F] = 0
    total = sum(rom) & 0xFFFF
    rom[0x14E], rom[0x14F] = total >> 8, total & 0xFF


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    if hashlib.sha256(source).hexdigest() != BASE_SHA256:
        raise ValueError("requires the exact r475 combined base")
    rom = bytearray(source)

    # Save original AF exactly where stock does, switch-under-self into the
    # matching bank-20 entry, and resume each scene setter at its untouched POP.
    postfinal_switch = bytes((0xF5, 0x3E, CAVE_BANK, 0xEA, 0x00, 0x21))
    for site, scene, entry, label in (
        (POSTFINAL_SCENE, 0x1A, POSTFINAL_BANK20_ENTRY, "postfinal_blank"),
    ):
        site_offset = off(1, site)
        assert source[site_offset:site_offset + 6] == bytes(
            (0xF5, 0x3E, scene, 0xEA, 0x80, 0xD8)
        )
        rom[site_offset:site_offset + 6] = postfinal_switch
        entry_offset = off(CAVE_BANK, entry)
        assert set(source[entry_offset:entry_offset + 3]) == {0xFF}
        target = BODY
        rom[entry_offset:entry_offset + 3] = bytes(
            (0xC3, target & 0xFF, target >> 8)
        )

    # The normal deck occupies $6800..$6837. Slot 7 is scene-selected by the
    # production loader; ending/story pages select the tuned row at $68F8.
    deck = bytearray(source[off(13, 0x6800):off(13, 0x6838)])
    deck.extend(source[off(13, 0x68F8):off(13, 0x6900)])
    assert len(deck) == 64
    assert bytes(deck) == (
        source[off(16, 0x6800):off(16, 0x6838)]
        + source[off(16, 0x68F8):off(16, 0x6900)]
    )
    body, labels = build_body(bytes(deck))
    body_offset = off(CAVE_BANK, BODY)
    assert BODY + len(body) <= min(site[3] for site in SITES.values())
    assert set(source[body_offset:body_offset + len(body)]) == {0xFF}
    rom[body_offset:body_offset + len(body)] = body

    # Keep the global/native fade dispatcher byte-exact. The private fixed-bank
    # callers switch coherently into synchronized copies. Preserve live A on
    # the stack; CALL $0061 returns under itself in bank 20, whose four-byte
    # twin restores A and jumps into a return-address dispatcher.
    assert source[CREDITS_FADE_CALL:CREDITS_FADE_CALL + 3] == bytes.fromhex(
        "CD 47 0F"
    )
    rom[CREDITS_FADE_CALL:CREDITS_FADE_CALL + 3] = bytes((
        0xCD, CREDITS_FADE_WRAPPER & 0xFF, CREDITS_FADE_WRAPPER >> 8,
    ))
    wrapper = bytes((
        0xF5, 0x3E, CAVE_BANK, 0xCD, 0x61, 0x00,
    ))
    assert source[
        CREDITS_FADE_WRAPPER:CREDITS_FADE_WRAPPER + len(wrapper)
    ] == bytes(len(wrapper))
    rom[
        CREDITS_FADE_WRAPPER:CREDITS_FADE_WRAPPER + len(wrapper)
    ] = wrapper
    credits_entry_offset = off(CAVE_BANK, CREDITS_FADE_BANK20_CONT)
    assert set(source[credits_entry_offset:credits_entry_offset + 4]) == {0xFF}
    credits_target = labels["credits_fade_dispatch"]
    rom[credits_entry_offset:credits_entry_offset + 4] = bytes((
        0xF1, 0xC3, credits_target & 0xFF, credits_target >> 8,
    ))

    assert source[
        CREDITS_FADE_OUT_CALL:CREDITS_FADE_OUT_CALL + 3
    ] == bytes.fromhex("CD 3D 0F")
    rom[
        CREDITS_FADE_OUT_CALL:CREDITS_FADE_OUT_CALL + 3
    ] = bytes((
        0xCD, CREDITS_FADE_OUT_WRAPPER & 0xFF,
        CREDITS_FADE_OUT_WRAPPER >> 8,
    ))

    # The story fade-out is a CALL, but the paired fade-in is a tail JP. Both
    # enter one second trampoline; their distinct retained return addresses
    # select the correct copied native entry in bank 20.
    assert source[
        STORY_FADE_OUT_CALL:STORY_FADE_OUT_CALL + 3
    ] == bytes.fromhex("CD 33 0F")
    rom[STORY_FADE_OUT_CALL:STORY_FADE_OUT_CALL + 3] = bytes((
        0xCD, STORY_FADE_WRAPPER & 0xFF, STORY_FADE_WRAPPER >> 8,
    ))
    assert source[
        STORY_FADE_IN_JUMP:STORY_FADE_IN_JUMP + 3
    ] == bytes.fromhex("C3 51 0F")
    rom[STORY_FADE_IN_JUMP:STORY_FADE_IN_JUMP + 3] = bytes((
        0xC3, STORY_FADE_WRAPPER & 0xFF, STORY_FADE_WRAPPER >> 8,
    ))
    assert source[
        STORY_COMBINED_FADE_OUT_CALL:STORY_COMBINED_FADE_OUT_CALL + 3
    ] == bytes.fromhex("CD 9D 0F")
    rom[
        STORY_COMBINED_FADE_OUT_CALL:STORY_COMBINED_FADE_OUT_CALL + 3
    ] = bytes((
        0xCD, STORY_FADE_WRAPPER & 0xFF, STORY_FADE_WRAPPER >> 8,
    ))
    assert source[
        EPILOGUE_COMBINED_FADE_OUT_CALL:EPILOGUE_COMBINED_FADE_OUT_CALL + 3
    ] == bytes.fromhex("CD 9D 0F")
    rom[
        EPILOGUE_COMBINED_FADE_OUT_CALL:EPILOGUE_COMBINED_FADE_OUT_CALL + 3
    ] = bytes((
        0xCD, STORY_FADE_WRAPPER & 0xFF, STORY_FADE_WRAPPER >> 8,
    ))
    assert source[
        EPILOGUE_FADE_OUT_CALL:EPILOGUE_FADE_OUT_CALL + 3
    ] == bytes.fromhex("CD 33 0F")
    rom[EPILOGUE_FADE_OUT_CALL:EPILOGUE_FADE_OUT_CALL + 3] = bytes((
        0xCD, STORY_FADE_WRAPPER & 0xFF, STORY_FADE_WRAPPER >> 8,
    ))
    assert source[
        STORY_FADE_WRAPPER:STORY_FADE_WRAPPER + len(wrapper)
    ] == bytes(len(wrapper))
    rom[STORY_FADE_WRAPPER:STORY_FADE_WRAPPER + len(wrapper)] = wrapper
    story_entry_offset = off(CAVE_BANK, STORY_FADE_BANK20_CONT)
    assert set(source[story_entry_offset:story_entry_offset + 4]) == {0xFF}
    story_target = labels["story_fade_dispatch"]
    rom[story_entry_offset:story_entry_offset + 4] = bytes((
        0xF1, 0xC3, story_target & 0xFF, story_target >> 8,
    ))

    # Route the complete publisher entry through bank 20 while retaining the
    # source bank on the stack. Native paths return through a tiny dead-wait
    # stub at $71F0 and execute the untouched source-bank $71F7 tail, so HL
    # still reads palette data from the correct ROM bank. Suppressed paths
    # consume four bytes in bank 20 and return directly. Neither route owns an
    # arena-table byte.
    palette_publisher = bytes.fromhex(
        "F0 40 CB 7F 28 16 F0 41 E6 03 FE 01 28 0E "
        "F0 41 E6 03 FE 03 20 F8 F0 41 E6 03 20 FA "
        "2A E2 2A E2 2A E2 2A E2 C9"
    )
    assert len(palette_publisher) == 37
    palette_stub = bytes((
        0xE1, 0xC3, PALETTE_QUAD_WRITE & 0xFF, PALETTE_QUAD_WRITE >> 8,
    ))
    for bank in (13, 16):
        palette_hook = bytes((
            0x3E, bank, 0xF5, 0x3E, CAVE_BANK,
            0xCD, FIXED_SWITCH & 0xFF, FIXED_SWITCH >> 8,
        ))
        publisher_offset = off(bank, PALETTE_PUBLISHER)
        assert source[
            publisher_offset:publisher_offset + len(palette_publisher)
        ] == palette_publisher
        rom[publisher_offset:publisher_offset + len(palette_hook)] = palette_hook
        stub_offset = off(bank, PALETTE_RESUME_STUB)
        rom[stub_offset:stub_offset + len(palette_stub)] = palette_stub
    palette_entry_offset = off(CAVE_BANK, PALETTE_BANK20_ENTRY)
    assert set(source[palette_entry_offset:palette_entry_offset + 3]) == {0xFF}
    palette_target = labels["palette_guard"]
    rom[palette_entry_offset:palette_entry_offset + 3] = bytes((
        0xC3, palette_target & 0xFF, palette_target >> 8,
    ))

    switch = bytes((0x3E, CAVE_BANK, 0xEA, 0x00, 0x21, 0x00))
    for name, (address, preimage, _continuation, entry) in SITES.items():
        for bank in (13, 16):
            offset = off(bank, address)
            assert source[offset:offset + 6] == preimage
            rom[offset:offset + 6] = switch
        entry_offset = off(CAVE_BANK, entry)
        assert set(source[entry_offset:entry_offset + 3]) == {0xFF}
        target = labels[name.lower()]
        rom[entry_offset:entry_offset + 3] = bytes(
            (0xC3, target & 0xFF, target >> 8)
        )

    update_checksums(rom)
    candidate = bytes(rom)
    changed = [
        hex(index)
        for index, (before, after) in enumerate(zip(source, candidate))
        if before != after
    ]
    return candidate, {
        "schema": "penta-ending-bgp-handoff-r517-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "body": f"{BODY:04X}",
        "body_len": len(body),
        "state": f"{STATE:04X}",
        "story_done_row": STORY_DONE_ROW,
        "ending_done_row": ENDING_DONE_ROW,
        "story_bg7_source": "bank13/16:$68F8",
        "palette_loader_gate": "bank13/16:$6900..$6905 unchanged",
        "postfinal_loader_black": (
            "bank13/16:$71DB mapper handoff -> bank20 guarded publisher; "
            "native path maps back through $71F0 to untouched $71F7 tail"
        ),
        "native_fade_handoff": "fixed:$0F5A..$0F65 unchanged",
        "postfinal_preblank": "bank1:$5513 -> bank20 before scene $1A publication",
        "credits_attr_repair": "18x20 VBK1 rows at $9800, armed after DF4A=$60",
        "credits_black_settle": "BGP=$FF re-fill after native BG0 CRAM overwrite",
        "credits_fade_sync": (
            "fixed:$3E72/$3E84 -> bank20 copies of $0F47/$0F3D; single "
            "BG1 CRAM row prepared immediately before BGP publication"
        ),
        "story_fade_sync": (
            "fixed:$371E/$3735/$5523/$3DD4/$5553 -> bank20 copies of "
            "$0F33/$0F51/$0F9D; routed story/ending CRAM before BGP "
            "publication"
        ),
        "credits_reveal_row": CREDITS_REVEAL_ROW,
        "labels": {name: f"{address:04X}" for name, address in labels.items()},
        "changed_offsets": changed,
    }


def main() -> int:
    source = BASE.read_bytes()
    candidate, receipt = build(source)
    OUT.mkdir(exist_ok=True)
    target = OUT / "candidate.gb"
    if target.exists() and target.read_bytes() != candidate:
        raise ValueError("immutable candidate collision")
    target.write_bytes(candidate)
    payload = json.dumps(receipt, indent=2) + "\n"
    receipt_path = OUT / "build-receipt.json"
    if receipt_path.exists() and receipt_path.read_text() != payload:
        raise ValueError("immutable build receipt collision")
    receipt_path.write_text(payload)
    print(json.dumps({
        key: value for key, value in receipt.items()
        if key not in {"labels", "changed_offsets"}
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
