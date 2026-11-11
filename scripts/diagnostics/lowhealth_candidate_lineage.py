"""#59/#66 experimental descendant identity, never a readiness decision.

Reconstruction is for unchanged component identification only. Every emulator
must execute the supplied candidate, never the reconstructed parent.
"""
import hashlib

PARENT_SHA = '6c4a9654b5c6dad70c8ea21bfd39b6e53766a3cd1a642153c6085774392ec228'
CANDIDATE_SHA = '3d581fc835e15e0d6df691b566b7e2053e1b8d17783496c2e2fcade54a33d626'
TITLE_CANDIDATE_SHA = 'a1ff1f90018122d84a378d0150a9fcbd0b5da6ffb228462b4f16c8bcd74e6d6d'
TITLE_RETRY_SHA = '126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941'
# #54: the title-retry image plus the final native stage-record stage
# (build_native_stage_records). It inherits every title/low-health owner.
NATIVE_RECORDS_SHA = '050209058633e2723a25c4ad60f92e0a3d54d51dbdd27d449b23069d98323ed4'
# Post-ending soft reset rearms the DX cold-boot init (build_soft_reset_cold_init).
SOFT_RESET_SHA = '9642170ac94ebcf8b278eaffd6afea1d3545d851123b33233f08fa69a14fe095'
# #55/#83 transition palette blanking (build_transition_palette_blanking).
TRANSITION_SHA = '91d58599d3df5dde80131ce20d0a639d7056d015dc91cedd2e699b66a141ba18'
# #81 menu-open-map-hold (build_menu_open_map_hold).
MENU_HOLD_SHA = '952f9b9f2b3feafb1882282e8ac7e5d0f462a597b79da49e74587469d8f6888a'
# #74 death-fade-white (build_death_fade_white).
DEATH_FADE_SHA = '23aa5f44f604d120877169f7dfa32186c3b089afbbadae4618b5cd06e7cb7d6c'
TITLE_SHAS = {TITLE_CANDIDATE_SHA, TITLE_RETRY_SHA, NATIVE_RECORDS_SHA, SOFT_RESET_SHA,
              TRANSITION_SHA, MENU_HOLD_SHA, DEATH_FADE_SHA}
COMPILER_HEX = (
    'f0fffe04c28d78f0b7d603fe06d28d783e01e070fa80d8fe0b2807'
    '3e03e070c38d783e03e070f0bafe012004afea7fd43e18e0e0'
    + '1a134f0a22' * 24
    + '3e01e070fb00f33e03e0707dc6086f300124f0e03de0e0c2d478'
      'e5f8043624233643e1afe0e03e01c9'
)
RUNS = (
    (0x14e, 'd8f3', '467f'),
    (0x356ea, '0c', '03'), (0x356ec, '09', '12'),
    (0x356fc, 'ff', '08'), (0x356fe, '0c', '03'),
    (0x3570e, 'fa80d8', 'cde86e'),
    (0x36ee8, '00' * 9, 'fa80d8fe0bc0f0b7c9'),
    (0x5ac80, 'fa80d8', 'cd807f'),
    (0x5acb7, 'f3', 'f0'), (0x5acbe, 'f3', 'f0'),
    (0x5b1da, 'fa80d8', 'cd807f'),
    (0x5b201, 'f3', 'f0'), (0x5b208, 'f3', 'f0'),
    (0x5bf80, 'ff' * 9, 'fa80d8fe0bc0f0b7c9'),
    (0x7ad04, '8d', 'a0'),
    (0x7b8a0, 'ff' * (len(COMPILER_HEX) // 2), COMPILER_HEX),
)


def is_candidate(rom):
    return len(rom) == 0x100000 and hashlib.sha256(rom).hexdigest() in {
        CANDIDATE_SHA, *TITLE_SHAS}


def _original():
    from pathlib import Path
    return (Path(__file__).resolve().parents[2] / 'rom/Penta Dragon (J).gb').read_bytes()


def death_fade_parent(rom):
    """Invert only the final death-fade-white stage (exact rebuild)."""
    if hashlib.sha256(rom).hexdigest() != DEATH_FADE_SHA:
        raise ValueError('not the exact death-fade-white candidate')
    import build_death_fade_white as fade
    return fade.reconstruct_parent(rom, _original())


def menu_hold_parent(rom):
    """Invert only the final menu-open-map-hold stage (exact rebuild)."""
    if hashlib.sha256(rom).hexdigest() != MENU_HOLD_SHA:
        raise ValueError('not the exact menu-open-map-hold candidate')
    import build_menu_open_map_hold as hold
    return hold.reconstruct_parent(rom, _original())


def transition_parent(rom):
    """Invert only the final transition-palette-blanking stage (exact rebuild)."""
    if hashlib.sha256(rom).hexdigest() != TRANSITION_SHA:
        raise ValueError('not the exact transition palette blanking candidate')
    import build_transition_palette_blanking as blanking
    return blanking.reconstruct_parent(rom, _original())


def soft_reset_parent(rom):
    """Invert only the final soft-reset cold-init stage (exact rebuild)."""
    if hashlib.sha256(rom).hexdigest() != SOFT_RESET_SHA:
        raise ValueError('not the exact soft-reset cold-init candidate')
    import build_soft_reset_cold_init as soft
    return soft.reconstruct_parent(rom, _original())


def native_records_parent(rom):
    """#54: invert only the final native stage-record stage (exact rebuild)."""
    if hashlib.sha256(rom).hexdigest() != NATIVE_RECORDS_SHA:
        raise ValueError('not the exact native stage-record candidate')
    import build_native_stage_records as records
    return records.reconstruct_parent(rom, _original())


def native_records_intersects(start, end):
    import build_native_stage_records as records
    import build_soft_reset_cold_init as soft
    import build_transition_palette_blanking as blanking
    import build_menu_open_map_hold as hold
    import build_death_fade_white as fade
    spans = (records.changed_spans(_original()) + soft.changed_spans(_original())
             + blanking.changed_spans(_original()) + hold.changed_spans(_original())
             + fade.changed_spans(_original()))
    # Approved #83 carve-out (2026-11-09): the 6-byte 14:7F1D LY-window change
    # is owned by transition-palette-blanking and is reverted by
    # reconstruct_parent / title_parent before bank-20 components are
    # authenticated. Do not treat those exact bytes as a foreign delta that
    # blocks verify_low_health_flicker, arena_bank20_r455, or
    # verify_stage1_captured_menu.
    # #81: the 4-byte 14:7F32 FFC4 clear is owned by menu-open-map-hold and
    # is similarly inverted before bank-20 authentication.
    wait = (blanking.WAIT_SITE, blanking.WAIT_SITE + 6)
    hold_site = (hold.SITE, hold.SITE + len(hold.NEW))
    spans = [span for span in spans if span not in (wait, hold_site)]
    return any(start < b and a < end for a, b in spans)


def title_parent(rom):
    """Authenticate the entire footer extension; no runtime substitution."""
    identity = hashlib.sha256(rom).hexdigest()
    if identity == DEATH_FADE_SHA:
        rom = death_fade_parent(rom)
        identity = hashlib.sha256(rom).hexdigest()
    if identity == MENU_HOLD_SHA:
        rom = menu_hold_parent(rom)
        identity = hashlib.sha256(rom).hexdigest()
    if identity == TRANSITION_SHA:
        rom = transition_parent(rom)
        identity = hashlib.sha256(rom).hexdigest()
    if identity == SOFT_RESET_SHA:
        rom = soft_reset_parent(rom)
        identity = hashlib.sha256(rom).hexdigest()
    if identity == NATIVE_RECORDS_SHA:
        rom = native_records_parent(rom)
        identity = hashlib.sha256(rom).hexdigest()
    if identity not in TITLE_SHAS:
        raise ValueError('not the exact title-read candidate')
    if identity == TITLE_RETRY_SHA:
        import build_title_glyph_retry_window as glyph
        previous = glyph.old
    else:
        import build_title_glyph_read_window as glyph
        previous = glyph.previous
    parent = bytearray(rom)
    start = previous.offset(previous.ENTRY)
    parent[start:start + previous.SLOT] = previous.helper()
    parent[0x14e:0x150] = ((sum(parent[:0x14e]) + sum(parent[0x150:])) & 65535).to_bytes(2, 'big')
    parent = bytes(parent)
    if hashlib.sha256(parent).hexdigest() != CANDIDATE_SHA or glyph.build(parent) != rom:
        raise ValueError('title-read source replay differs')
    return parent


def authenticated_parent(rom, *ranges):
    if not is_candidate(rom):
        raise ValueError('not the exact low-health candidate')
    if not ranges:
        raise ValueError('explicit component ranges required')
    if hashlib.sha256(rom).hexdigest() in TITLE_SHAS:
        for start, end in ranges:
            if not 0 <= start < end <= len(rom):
                raise ValueError('invalid component range')
            if start < 0x36e00 and 0x36da7 < end:
                raise ValueError('component intersects title-read delta')
            if (hashlib.sha256(rom).hexdigest() in (NATIVE_RECORDS_SHA, SOFT_RESET_SHA, TRANSITION_SHA, MENU_HOLD_SHA, DEATH_FADE_SHA)
                    and native_records_intersects(start, end)):
                raise ValueError('component intersects native stage-record delta')
        return authenticated_parent(title_parent(rom), *ranges)
    for start, end in ranges:
        if not 0 <= start < end <= len(rom):
            raise ValueError('invalid component range')
        if any(start < offset + len(bytes.fromhex(after)) and offset < end
               for offset, before, after in RUNS):
            raise ValueError('component intersects low-health delta')
    parent = bytearray(rom)
    previous_end = 0
    for offset, before_hex, after_hex in RUNS:
        before, after = bytes.fromhex(before_hex), bytes.fromhex(after_hex)
        if len(before) != len(after) or offset < previous_end:
            raise ValueError('invalid low-health delta table')
        if parent[offset:offset + len(after)] != after:
            raise ValueError('low-health delta bytes differ')
        parent[offset:offset + len(before)] = before
        previous_end = offset + len(after)
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA:
        raise ValueError('low-health ancestor reconstruction failed')
    return bytes(parent)


def source_replay(rom):
    """Rebuild new owners from the authenticated parent and checked builders."""
    import build_later_lowhealth_dispatch as dispatch
    import build_later_compile_timer_yield as timer
    import build_stage7_lowhealth_fastpath as fastpath
    import build_stage7_lowhealth_camera as camera
    parent = authenticated_parent(rom, (0x147, 0x149))
    image = camera.build(fastpath.build(timer.build(dispatch.build(parent))))
    if hashlib.sha256(rom).hexdigest() == TITLE_CANDIDATE_SHA:
        import build_title_glyph_read_window as glyph
        image = glyph.build(image)
    elif hashlib.sha256(rom).hexdigest() in (TITLE_RETRY_SHA, NATIVE_RECORDS_SHA, SOFT_RESET_SHA,
                                             TRANSITION_SHA, MENU_HOLD_SHA, DEATH_FADE_SHA):
        import build_title_glyph_retry_window as glyph
        image = glyph.build(image)
        if hashlib.sha256(rom).hexdigest() in (NATIVE_RECORDS_SHA, SOFT_RESET_SHA, TRANSITION_SHA, MENU_HOLD_SHA, DEATH_FADE_SHA):
            import build_native_stage_records as records
            image = records.build(image, _original())
        if hashlib.sha256(rom).hexdigest() in (SOFT_RESET_SHA, TRANSITION_SHA, MENU_HOLD_SHA, DEATH_FADE_SHA):
            import build_soft_reset_cold_init as soft
            image = soft.build(image, _original())
        if hashlib.sha256(rom).hexdigest() in (TRANSITION_SHA, MENU_HOLD_SHA, DEATH_FADE_SHA):
            import build_transition_palette_blanking as blanking
            image = blanking.build(image, _original())
        if hashlib.sha256(rom).hexdigest() in (MENU_HOLD_SHA, DEATH_FADE_SHA):
            import build_menu_open_map_hold as hold
            image = hold.build(image, _original())
        if hashlib.sha256(rom).hexdigest() == DEATH_FADE_SHA:
            import build_death_fade_white as fade
            image = fade.build(image, _original())
    if image != rom:
        raise ValueError('low-health source replay differs from pinned candidate')
    return parent, image


def dispatcher_overlay(rom, offset, payload):
    """Only the four reviewed scene-resolver immediates may change here."""
    if not is_candidate(rom):
        raise ValueError('not the exact low-health candidate')
    if hashlib.sha256(rom).hexdigest() in TITLE_SHAS:
        if offset < 0x36e00 and 0x36da7 < offset + len(payload):
            raise ValueError('unowned title-read change in dispatcher component')
        if (hashlib.sha256(rom).hexdigest() in (NATIVE_RECORDS_SHA, SOFT_RESET_SHA, TRANSITION_SHA, MENU_HOLD_SHA, DEATH_FADE_SHA)
                and native_records_intersects(offset, offset + len(payload))):
            raise ValueError('unowned native stage-record change in dispatcher component')
        return dispatcher_overlay(title_parent(rom), offset, payload)
    allowed = {0x356ea, 0x356ec, 0x356fc, 0x356fe}
    result = bytearray(payload)
    end = offset + len(payload)
    for address, before_hex, after_hex in RUNS:
        before, after = bytes.fromhex(before_hex), bytes.fromhex(after_hex)
        if address < end and offset < address + len(after):
            if address not in allowed or len(after) != 1 or not offset <= address < end:
                raise ValueError('unowned change in dispatcher component')
            i = address - offset
            if result[i:i + 1] != before:
                raise ValueError('dispatcher oracle preimage differs')
            result[i:i + 1] = after
    return bytes(result)



def _transition_wait_reverted(rom):
    """Static oracle view: revert the 6-byte #83 14:7F1D LY-window change.

    Those bytes are owned by transition-palette-blanking and are already
    inverted by reconstruct_parent when peeling the candidate. Bank-20
    components are authenticated against this reverted image so the rest of
    the bank can stay a strict unchanged-inheritance check. #81's 14:7F32
    FFC4 clear is reverted the same way when the tip is menu-open-map-hold.
    """
    identity = hashlib.sha256(rom).hexdigest()
    if identity not in (TRANSITION_SHA, MENU_HOLD_SHA, DEATH_FADE_SHA):
        return rom
    import build_transition_palette_blanking as blanking
    out = bytearray(rom)
    if identity == DEATH_FADE_SHA:
        import build_death_fade_white as fade
        out = bytearray(fade.reconstruct_parent(bytes(out), _original()))
        identity = hashlib.sha256(bytes(out)).hexdigest()
    if identity == MENU_HOLD_SHA:
        import build_menu_open_map_hold as hold
        if out[hold.SITE:hold.SITE + len(hold.NEW)] != hold.NEW:
            raise ValueError('menu-open-map-hold site differs from the owned 4-byte change')
        out[hold.SITE:hold.SITE + len(hold.PRE)] = hold.PRE
    if out[blanking.WAIT_SITE:blanking.WAIT_SITE + 6] != blanking.WAIT_NEW:
        raise ValueError('transition wait site differs from the owned 6-byte change')
    out[blanking.WAIT_SITE:blanking.WAIT_SITE + 6] = blanking.WAIT_PRE
    return bytes(out)


def dispatcher_component_parent(rom, *ranges):
    """Authenticate changed dispatcher components, not unchanged inheritance.

    Only the four reviewed resolver immediates may differ inside these
    components. All remaining bytes and the complete child/parent identities
    are checked. This reconstructed image is a static oracle, not a replay ROM.
    """
    if not ranges:
        raise ValueError('explicit component ranges required')
    for start, end in ranges:
        if not 0 <= start < end <= len(rom):
            raise ValueError('invalid component range')
    parent = authenticated_parent(rom, (0x147, 0x149))
    compared = _transition_wait_reverted(rom)
    for start, end in ranges:
        expected = dispatcher_overlay(rom, start, parent[start:end])
        if compared[start:end] != expected:
            raise ValueError('dispatcher component differs from its oracle')
    return parent
