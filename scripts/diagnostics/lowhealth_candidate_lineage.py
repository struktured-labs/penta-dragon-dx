"""#59/#66 experimental descendant identity, never a readiness decision.

Reconstruction is for unchanged component identification only. Every emulator
must execute the supplied candidate, never the reconstructed parent.
"""
import hashlib

PARENT_SHA = '6c4a9654b5c6dad70c8ea21bfd39b6e53766a3cd1a642153c6085774392ec228'
CANDIDATE_SHA = '3d581fc835e15e0d6df691b566b7e2053e1b8d17783496c2e2fcade54a33d626'
TITLE_CANDIDATE_SHA = 'a1ff1f90018122d84a378d0150a9fcbd0b5da6ffb228462b4f16c8bcd74e6d6d'
TITLE_RETRY_SHA = '126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941'
TITLE_SHAS = {TITLE_CANDIDATE_SHA, TITLE_RETRY_SHA}
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


def title_parent(rom):
    """Authenticate the entire footer extension; no runtime substitution."""
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
    elif hashlib.sha256(rom).hexdigest() == TITLE_RETRY_SHA:
        import build_title_glyph_retry_window as glyph
        image = glyph.build(image)
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
    for start, end in ranges:
        expected = dispatcher_overlay(rom, start, parent[start:end])
        if rom[start:end] != expected:
            raise ValueError('dispatcher component differs from its oracle')
    return parent
