"""Authenticate the title-port wrapper around Crystal's unchanged rearm ABI."""
import os

from build_v302_title_fix import build_title_transition_service, TITLE_TRANSITION_SERVICE_ADDR
from build_title_nightfall_port import rearm_wrapper_v2
from build_stage1_title_nightfall_r366 import CLEAR_HELPER_ADDR, build_rearm_pads
from build_reload_flag_dealias_r443e import CAVE_SET_F, CAVE_TEST_F


def offset(address):
    return 13 * 0x4000 + address - 0x4000


def verify_transition(rom):
    import release_lock_lineage
    if release_lock_lineage.is_candidate(bytes(rom)):
        # The final continue-miniboss-reload stage moves the scene-02 reload
        # arm from the $7D18 setter into the common hook tail ($7D35 -> $7719
        # -> bank 39) and widens the $7703 gate to scene $0A. Authenticate that
        # exact stage, then hold the inherited title-port/r443e3 contract to
        # the bytes it was built on.
        import build_continue_miniboss_reload_trial as continue_reload
        assert continue_reload.verify_installed(bytes(rom)), "continue-miniboss-reload stage differs"
        rom = release_lock_lineage.revert_owned(bytes(rom), {release_lock_lineage.CONTINUE_OWNER})
    original = build_title_transition_service()
    start = offset(TITLE_TRANSITION_SERVICE_ADDR)
    if rom[start:start + len(original)] == original:
        return "builder"
    # Reconstruct the production handoff from source, then apply the exact
    # reviewed title-port and r443e3 reload-dealias overlays. Never mask bytes.
    keys = ("PENTA_STAGE_CARD_CLEAN_HANDOFF", "PENTA_TED_EXPANDED_PRODUCTION")
    saved = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys:
            os.environ[key] = "1"
        expected = bytearray(build_title_transition_service())
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    call = 0x7D01 - TITLE_TRANSITION_SERVICE_ADDR
    assert expected[call:call + 3] == bytes.fromhex("CD DF 6B")
    expected[call:call + 3] = bytes.fromhex("CD D7 76")
    setter = 0x7D18 - TITLE_TRANSITION_SERVICE_ADDR
    assert expected[setter:setter + 5] == bytes.fromhex("3C E0 E1 18 09")
    expected[setter:setter + 5] = bytes((0xC3, CAVE_SET_F & 255, CAVE_SET_F >> 8, 0, 0))
    assert rom[start:start + len(expected)] == expected, "unknown title-transition implementation"
    fragments = {
        0x76D7: rearm_wrapper_v2(CLEAR_HELPER_ADDR),
        0x6E9D: build_rearm_pads()[1],
        CAVE_SET_F: bytes.fromhex("3C EA 5D DF C3 26 7D"),
        CAVE_TEST_F: bytes.fromhex("FA 80 D8 FE 02 C2 2D 74 FA 5D DF 3D C2 2D 74 AF EA 5D DF C3 0F 74"),
        0x7407: bytes((0xC3, CAVE_TEST_F & 255, CAVE_TEST_F >> 8)) + bytes(5),
    }
    for address, payload in fragments.items():
        assert rom[offset(address):offset(address) + len(payload)] == payload, (
            f"title/Crystal transition dependency differs at ${address:04X}")
    return "title-port-r443e3"
