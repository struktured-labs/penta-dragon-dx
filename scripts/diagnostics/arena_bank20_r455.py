"""Reconstruct every bank-20 byte from its source owners, not candidate data."""
from functools import lru_cache
import verify_stage1_spike_palettes as stage1
import build_room03_animation_envelope_r440 as envelope
import build_menu_vblank_reveal_r372 as reveal
import build_interrupt_checked_vblank_r373 as wait
import menu_icon_colorization as menu
from arena_semantic_key import HELPER_ENTRY, PENTA_SEAM_ENTRY, build_helper, build_penta_seam_helper
from build_v301_gdma import _bg_table


def expected_bank20() -> bytes:
    table = bytearray(_bg_table())
    for tile in (*range(0x64, 0x6A), *range(0x74, 0x7A)):
        table[tile] = 15
    bank = bytearray([255]) * 0x4000

    def put(address, data):
        offset = address - 0x4000
        if not 0 <= offset <= 0x4000 - len(data):
            raise ValueError('bank-20 owner exceeds bank bounds')
        bank[offset:offset + len(data)] = data

    put(HELPER_ENTRY, build_helper(shalamar_native_exact_class=0))
    put(PENTA_SEAM_ENTRY, build_penta_seam_helper())
    bank[:] = menu.expected_bank20(bytes(table), bytes(bank))
    # Menu LCDC reveal and interrupt-checked VBlank service.
    put(0x4023, bytes.fromhex('F040CB772804CB9F1802CBDFE040'))
    put(0x407C, bytes.fromhex('CD007F000000'))
    # The menu's retained pre-r341 table is not the current gameplay LUT.
    old_table = bytearray(_bg_table())
    for tile in (0x6B, 0x6F, 0x7B, 0x7F):
        old_table[tile] = 6
    put(0x4164, old_table[0x64:0x80])
    helper = stage1.build_semantic_helper()
    lut = stage1.build_semantic_lut(table)
    put(stage1.SEMANTIC_ROOM01_HELPER_ADDR, stage1.build_semantic_room01_helper(helper))
    put(stage1.SEMANTIC_ROOM01_LUT_ADDR, stage1.build_semantic_room01_lut(lut))
    put(stage1.SEMANTIC_HELPER_ENTRY, bytes.fromhex('C3804300') + helper[4:])
    put(0x4380, envelope.helper())
    put(stage1.SEMANTIC_LUT_ADDR, lut)
    for address in stage1.SEMANTIC_CALLER_RETURNS:
        put(address, stage1.SEMANTIC_CONTEXT_TRAMPOLINE)
    put(0x60CD, bytes([0x72]))
    put(0x6CDF, bytes.fromhex('3E13CD6100'))
    put(0x7F00, reveal.CODE.replace(wait.OLD_WAIT, wait.WAIT))
    return bytes(bank)


def expected_boss_repairs_bank20() -> bytes:
    from compose_troop_repeat_r457c import patches
    from compose_shalamar_death_r458b import ENTRY, CAVE, PREIMAGE, guard_code
    image = bytearray(expected_bank20())
    updates = list(patches()) + [
        (ENTRY, PREIMAGE, bytes.fromhex('C30063')),
        (CAVE, b'\xff'*len(guard_code()), guard_code()),
    ]
    for address, before, after in updates:
        offset = address-0x4000
        assert image[offset:offset+len(before)] == before
        assert len(before) == len(after)
        image[offset:offset+len(after)] = after
    return bytes(image)


@lru_cache(maxsize=1)
def expected_penta_seam_rom() -> bytes:
    # r535 also owns menu/reveal code in this bank. Replay its authenticated
    # lineage instead of treating those bytes as erased r455 padding.
    import tempfile
    from pathlib import Path
    import build_r534_candidate as r534
    import build_title_tile_retire_trial_r535 as title
    import build_stage_card_blank_trial_r535 as card
    import build_penta_seam_vram_trial_r536 as seam
    # #61: reconstruct from the original cartridge and current source. The
    # historical r475 scratch ROM is not an input and the ROM under test is
    # never used to derive expected bytes. The builder authenticates its
    # original, double-builds, traces factory reads and checks the exact hash.
    scratch = r534.ROOT / "tmp"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bank20-source-", dir=scratch) as work:
        output = Path(work) / "r534"
        # This historical source stage predates the purple Game Over overlay.
        r534.build(output, r534.ROOT / "palettes/penta_palettes_restart_parent.yaml")
        original = (output / "candidate.gb").read_bytes()
    image = seam.build(card.build(title.build(original)))
    return image


@lru_cache(maxsize=1)
def expected_penta_seam_bank20() -> bytes:
    return expected_penta_seam_rom()[20 * 0x4000:21 * 0x4000]


def matches(rom: bytes) -> bool:
    bank = rom[20 * 0x4000:21 * 0x4000]
    if bank in (expected_bank20(), expected_boss_repairs_bank20()):
        return True
    from build_penta_seam_vram_trial_r536 import HOOK, payloads
    stub, _ = payloads()
    return bank in (expected_penta_seam_bank20(), expected_gameover_row_guard_bank20()) and rom[HOOK:HOOK + len(stub)] == stub


@lru_cache(maxsize=1)
def expected_gameover_row_guard_bank20() -> bytes:
    from build_gameover_row_guard import patches
    image=bytearray(expected_penta_seam_bank20())
    for address,before,after in patches():
        start=address-0x4000
        assert image[start:start+len(before)]==before
        image[start:start+len(after)]=after
    return bytes(image)


def visible_seam_matches(rom: bytes) -> bool:
    from build_penta_seam_vram_trial_r536 import HOOK, HELPER, PREIMAGE, payloads
    stub, helper = payloads()
    import playtest_successor_lineage as successor
    if successor.is_candidate(rom):
        return visible_seam_matches(successor.authenticated_parent(
            rom, (HOOK, HOOK + len(PREIMAGE)),
            (HELPER, HELPER + len(helper)), (20 * 0x4000, 21 * 0x4000)))
    if (rom[HOOK:HOOK + len(PREIMAGE)] == PREIMAGE
            and rom[HELPER:HELPER + len(helper)] == b'\xff' * len(helper)):
        return True
    import release_lock_lineage
    if release_lock_lineage.is_candidate(rom):
        # Release lock: hook and seam helper are outside the delta, and every
        # bank-20 byte outside the reviewed release-lock runs still equals the
        # Game Over row-guard bank (the candidate's 4f5a ancestor bank 20).
        expected = expected_gameover_row_guard_bank20()
        base = 20 * 0x4000
        return (rom[HOOK:HOOK + len(stub)] == stub
                and not release_lock_lineage.touched(HOOK, HOOK + len(stub))
                and not release_lock_lineage.touched(HELPER, HELPER + len(helper))
                and all(
                    rom[base + i] == expected[i]
                    or release_lock_lineage.touched(base + i, base + i + 1)
                    for i in range(0x4000)))
    return (rom[HOOK:HOOK + len(stub)] == stub
            and rom[20 * 0x4000:21 * 0x4000] in
            (expected_penta_seam_bank20(), expected_gameover_row_guard_bank20()))
