"""Data-driven tile-to-palette tables for the nine boss arenas.

Boss animation frames reuse large tile-ID ranges.  Splitting those ranges as
if their high IDs were dungeon pickups produced ruler-straight color bands and
animation-dependent palette changes.  Each boss therefore starts from one
coherent material palette.  Only independently traced arena-background IDs
remain neutral; richer accents belong in the position/material pass, where a
tile cannot change semantic meaning when an animation frame changes.
"""

def _span(palette: int, first: int, last: int, *, exclude=()) -> dict[int, int]:
    excluded = set(exclude)
    return {
        tile: palette
        for tile in range(first, last + 1)
        if tile not in excluded
    }


# The palette numbers refer to the editable BG rows in palettes.yaml:
# BG1 cherry red/crimson, BG2 purple, BG4 ice cyan, BG7 steel/navy.
ARENA_TILE_PAL = {
    # Checker background is exactly $00/$01; animation body spans $02-$E9.
    "shalamar": _span(4, 0x02, 0xFF),

    # Riff's traced frame/floor IDs remain neutral.  The rest is one purple
    # material instead of the former green/red split.
    "riff": _span(
        2, 0x01, 0xFB,
        exclude=(
            0xCC, 0xCD, 0xCE, 0xCF, 0xD3,
            0xDC, 0xDD, 0xDE, 0xDF, 0xE9,
            0xEC, 0xED, 0xEE, 0xEF,
        ),
    ),

    # Live-arena inventory separates the animated orb/body IDs from the cave
    # backdrop.  Keep that measured boundary and use one icy material.
    "crystal_dragon": _span(
        4, 0x88, 0xFB,
        exclude=(
            0x94, 0xA0, 0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAB,
            0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBB, 0xBC, 0xBD,
            0xBE, 0xBF, 0xC0, 0xC4, 0xC5, 0xC6, 0xCC, 0xCD, 0xCE,
            0xCF, 0xD0, 0xD4, 0xDC, 0xDD, 0xDE, 0xDF, 0xE0, 0xE1,
            0xE2, 0xE3, 0xE4, 0xE6, 0xF0, 0xF1, 0xF2, 0xF3, 0xF4,
        ),
    ),

    # $0C-$0F are Cameo's traced upper contour. Leaving them on BG0 produced
    # the conspicuous blue-gray cap visible above the otherwise crimson body.
    # The checker field is $04/$05, so extending only to $0C is contained.
    "cameo": _span(1, 0x0C, 0xFF),

    "ted": _span(
        1, 0x17, 0xFF,
        exclude=(0x77, 0x78, 0x79, 0x7A, 0x7C, 0x7E, 0x7F, 0x81),
    ),

    # These four tables previously treated later animation chunks as item
    # pickups.  That was the source of the visible horizontal bands.
    "troop": _span(7, 0x23, 0xFF),
    "faze": _span(2, 0x12, 0xFF, exclude=(0x7A,)),
    "angela": _span(2, 0x20, 0xBA) | {0xFF: 2},
    "penta_dragon": _span(1, 0x20, 0xFF),
}
