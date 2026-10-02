"""Release-lock 2026-10-01 candidate lineage (#14/#34 deferred).

The stream release-lock candidate is source-built by
``scripts/build_stream_regression_candidate.py --release-lock`` from the
qualified restart candidate (c693eafb...) through the Sara atomic pose
(4f5a67b8...) and the re-pinned stream stages documented in
docs/audit/release-lock-20261001-repin.md.

Verifiers that bind reviewed bytes to exact historical ROM hashes may accept
the candidate only for regions this module proves the release-lock delta
leaves byte-identical to 4f5a67b8. ``DELTA_VS_SARA`` lists every changed
file-offset run inside the first 512 KiB (computed from the source build);
banks 32..63 are new. It is a recognition aid, never a byte mask: callers
must still check the bytes they care about.
"""
from __future__ import annotations

import hashlib

SARA_SHA256 = "4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5"
CANDIDATE_SHA256 = (
    "792319cbe9db7d56ae6497018b727c8a0a8737c3c8c7a4a122713054677022db"
)
ROM_SIZE = 0x100000
LEGACY_SIZE = 0x80000
DELTA_VS_SARA = (
    (0x00148, 8), (0x00A81, 9), (0x00A95, 2), (0x00AA0, 2), (0x00AB6, 5),
    (0x00CC7, 1), (0x015DB, 2), (0x02AE1, 1), (0x02B91, 14), (0x02BC6, 20),
    (0x042F6, 1), (0x04355, 4), (0x075F1, 2), (0x1F828, 23), (0x1F920, 3),
    (0x1F930, 3), (0x3563A, 3), (0x3569C, 14), (0x356DE, 16), (0x356FA, 5),
    (0x35830, 12), (0x369C1, 4), (0x36A57, 8), (0x36DAD, 1), (0x36DBD, 67),
    (0x36F98, 103), (0x37082, 2), (0x37092, 2), (0x3718F, 5), (0x37C38, 2),
    (0x37C7A, 3), (0x37FEA, 5), (0x4155D, 12), (0x416A4, 6), (0x416DE, 3),
    (0x41CDA, 5), (0x5004A, 3), (0x5028F, 4), (0x50700, 3362),
    (0x5151C, 1784), (0x51C20, 105), (0x51CDC, 6), (0x52A59, 6),
    (0x52B80, 85), (0x52C21, 7), (0x52C40, 17), (0x52DA7, 31),
    (0x52DE0, 31), (0x52F92, 14), (0x531E7, 5), (0x53320, 3),
    (0x5332F, 42), (0x53C00, 360), (0x53D80, 115), (0x53E50, 8),
    (0x6EC81, 24), (0x70000, 61), (0x72C80, 5), (0x7F1A0, 6),
    (0x7F1CE, 3), (0x7F1E3, 12),
)

# Stage(s) of build_stream_regression_candidate --release-lock that write each
# run (bisected over the re-pinned stage ROMs; see the repin audit).
RUN_OWNERS = {
    0x00a81: ('presentation-composition',),
    0x00a95: ('presentation-composition',),
    0x00aa0: ('presentation-composition',),
    0x00ab6: ('presentation-composition',),
    0x00cc7: ('secret-stock-graphics',),
    0x015db: ('return-cgb-fade',),
    0x02ae1: ('native-projectile-templates',),
    0x02b91: ('presentation-composition',),
    0x02bc6: ('presentation-composition',),
    0x042f6: ('arena-completion-safe',),
    0x04355: ('arena-completion-safe',),
    0x075f1: ('return-cgb-fade',),
    0x1f828: ('five-point-star',),
    0x1f920: ('five-point-star',),
    0x1f930: ('five-point-star',),
    0x3563a: ('arena-graphics-owner', 'arena-completion-safe'),
    0x3569c: ('arena-graphics-owner', 'arena-completion-safe'),
    0x356de: ('arena-completion-safe',),
    0x356fa: ('arena-completion-safe',),
    0x35830: ('arena-completion-safe',),
    0x369c1: ('secret-palette-source',),
    0x36a57: ('title-local-guard',),
    0x36dad: ('title-glyph-window',),
    0x36dbd: ('title-glyph-window',),
    0x36f98: ('arena-alias-fastpath',),
    0x37082: ('five-point-star',),
    0x37092: ('five-point-star',),
    0x3718f: ('continue-input-after-visuals',),
    0x37c38: ('gameover-accent',),
    0x37c7a: ('arena-graphics-owner', 'arena-completion-safe'),
    0x37fea: ('secret-palette-source',),
    0x4155d: ('arena-completion-safe',),
    0x416a4: ('arena-completion-safe',),
    0x416de: ('arena-completion-safe',),
    0x41cda: ('ted-menu-reinstall',),
    0x5004a: ('presentation-composition',),
    0x5028f: ('presentation-composition',),
    0x50700: ('presentation-composition', 'return-cgb-fade', 'return-card-compact'),
    0x5151c: ('return-cgb-fade', 'return-card-deadline'),
    0x51c20: ('return-card-deadline', 'return-card-compact'),
    0x51cdc: ('ted-menu-reinstall',),
    0x52a59: ('title-local-guard',),
    0x52b80: ('title-local-guard',),
    0x52c21: ('title-local-guard',),
    0x52c40: ('ted-menu-reinstall',),
    0x52da7: ('arena-sound-alias',),
    0x52de0: ('arena-alias-fastpath',),
    0x52f92: ('arena-sound-alias', 'arena-alias-fastpath'),
    0x531e7: ('handheld-palette',),
    0x53320: ('handheld-palette',),
    0x5332f: ('palette-window',),
    0x53c00: ('presentation-composition',),
    0x53d80: ('handheld-palette',),
    0x53e50: ('handheld-palette',),
    0x6ec81: ('return-initial-map',),
    0x70000: ('presentation-composition', 'secret-sound-alias-fast', 'secret-alias-chunks'),
    0x72c80: ('presentation-composition',),
    0x7f1a0: ('arena-completion-safe',),
    0x7f1ce: ('arena-completion-safe',),
    0x7f1e3: ('arena-completion-safe',),
    # Header ROM size/checksums: every stage re-normalizes them.
    0x00148: ("header",),
}


# 4f5a67b8 preimage bytes of DELTA_VS_SARA, concatenated, zlib, base64.
SARA_PREIMAGE = (
    "eNpjYWKQYthZNC2U9yybw/uzYlxPHPn1pjqdrTbgreLnFWQ4YCdw9gnnU8XWO8rKDAfBHEWQ"
    "4HVGB4azmzlPfvx4+/B9Y/5D+/7te7DgwgYGhoZ/DnUOdQp2dnZMTCyndpxdwRfxq+EGEMVX"
    "/XPR0K3+J6Chsf7hycPTTRhQwYdd2zVY1j9gPHn4kcDqfLVqPg6tB5m8Cr80ROxyHwTaJTwI"
    "shN/EGz34UGIHcOD0I+HE7I/+H9d/8D/l+usf5UK73/9mf5PQuMFWG0AqlqJS2f/1JT/YzJg"
    "Puyc+09UQw6oUOqfpIbQPykNvn/SQCyjwfVPTIFPgmX9K477dlGvmO4DVV7jsRD4x2kgfawo"
    "XY/BTvysO4eEEMiRzIef169/FXz/Vfh9RYYCQYZjbAxaQsKsCr9Ogrzx8HBPPsPWMKCHMXwF"
    "9/yv/0f/neTjOvrxsFbJ/1EwCkbBKBgFo2AUjIJRMApGwSgYBaNgFIyCUTAKRsEoGAWEQcXB"
    "q2IfHJ8x/2PU4APTzAo/QLTCr6qnio8Lnx5OZBgNpBEEzm3X4Kw5xpwu+OAwH4Md40mqGCq4"
    "4CCfI3wsH3mAHwBiYTGF"
)


def is_candidate(rom: bytes) -> bool:
    return len(rom) == ROM_SIZE and hashlib.sha256(rom).hexdigest() == CANDIDATE_SHA256


def touched(start: int, end: int) -> list[tuple[int, int]]:
    """Return release-lock delta runs intersecting file range [start, end)."""
    if end > LEGACY_SIZE:
        raise ValueError("range extends into the release-lock expansion banks")
    return [
        (offset, length) for offset, length in DELTA_VS_SARA
        if offset < end and start < offset + length
    ]


def untouched(rom: bytes, *ranges: tuple[int, int]) -> bool:
    """True when ``rom`` is the candidate and no range meets the delta."""
    return is_candidate(rom) and not any(touched(s, e) for s, e in ranges)


def sara_ancestor(rom: bytes, *ranges: tuple[int, int]) -> bytes:
    """Return the authenticated 4f5a67b8 ancestor of the candidate.

    Every ``ranges`` entry (file offsets, end exclusive) must lie outside the
    release-lock delta, so verifiers reuse an ancestor ABI only for bytes the
    candidate provably shares with it. The reconstruction is fail-closed on
    the ancestor hash.
    """
    import base64
    import zlib

    if not is_candidate(rom):
        raise ValueError("not the exact release-lock candidate")
    if not ranges:
        raise ValueError("sara_ancestor requires the verifier's byte ranges")
    for start, end in ranges:
        hits = touched(start, end)
        if hits:
            raise ValueError(
                f"range {start:#x}..{end:#x} meets the release-lock delta {hits}"
            )
    blob = zlib.decompress(base64.b64decode("".join(SARA_PREIMAGE)))
    parent = bytearray(rom[:LEGACY_SIZE])
    cursor = 0
    for offset, length in DELTA_VS_SARA:
        parent[offset:offset + length] = blob[cursor:cursor + length]
        cursor += length
    if cursor != len(blob):
        raise ValueError("release-lock preimage table is inconsistent")
    if hashlib.sha256(parent).hexdigest() != SARA_SHA256:
        raise ValueError("release-lock ancestor reconstruction failed")
    return bytes(parent)


def _preimage() -> bytes:
    import base64
    import zlib

    return zlib.decompress(base64.b64decode("".join(SARA_PREIMAGE)))


def overlay(rom: bytes, offset: int, expected: bytes, owners: set[str]) -> bytes:
    """Source-built ``expected`` bytes for ``rom[offset:...]`` plus owned runs.

    Inside delta runs written only by ``owners`` the candidate's bytes are
    accepted, after proving the run's 4f5a preimage equals ``expected`` there
    (so the source contract still describes the ancestor exactly). Any other
    delta run inside the range fails closed.
    """
    if not is_candidate(rom):
        return expected
    end = offset + len(expected)
    result = bytearray(expected)
    blob = _preimage()
    cursor = 0
    for run, length in DELTA_VS_SARA:
        lo, hi = max(run, offset), min(run + length, end)
        if lo < hi:
            if not set(RUN_OWNERS[run]) <= set(owners):
                raise ValueError(
                    f"{offset:#x}..{end:#x} meets release-lock run {run:#x} "
                    f"owned by {RUN_OWNERS[run]}"
                )
            pre = blob[cursor + lo - run:cursor + hi - run]
            if pre != expected[lo - offset:hi - offset]:
                raise ValueError(f"source contract no longer describes 4f5a at {run:#x}")
            result[lo - offset:hi - offset] = rom[lo:hi]
        cursor += length
    return bytes(result)


def ancestor_bytes(rom: bytes, start: int, end: int, owners: set[str]) -> bytes:
    """4f5a67b8 bytes of [start, end) for the candidate.

    Only delta runs written exclusively by ``owners`` may intersect the range;
    the caller then applies its historical contract to the ancestor bytes and
    must qualify the owners' change separately.
    """
    if not is_candidate(rom):
        raise ValueError("not the exact release-lock candidate")
    result = bytearray(rom[start:end])
    blob = _preimage()
    cursor = 0
    for run, length in DELTA_VS_SARA:
        lo, hi = max(run, start), min(run + length, end)
        if lo < hi:
            if not set(RUN_OWNERS[run]) <= set(owners):
                raise ValueError(
                    f"{start:#x}..{end:#x} meets release-lock run {run:#x} "
                    f"owned by {RUN_OWNERS[run]}"
                )
            result[lo - start:hi - start] = blob[cursor + lo - run:cursor + hi - run]
        cursor += length
    return bytes(result)
