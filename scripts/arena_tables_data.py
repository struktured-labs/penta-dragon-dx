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


# Ted is an armored egg/jellyfish rather than four stacked materials.  Tile
# IDs $02-$76 are laid out in canonical art rows, so broad numeric ranges
# become ruler-straight cyan/purple/orange/green bands.  Give the shell a
# warm Contra/Metroid-like red/gold scale pattern and carry those materials
# vertically through the tendrils.  Palette ownership follows an art tile as
# the native animation shifts whole rows horizontally.
_TED_ROW_WIDTHS = (5, 8, 8, 8, 8, 9, 10, 11, 11, 11, 10, 8, 6, 4)


def _ted_materials() -> dict[int, int]:
    result: dict[int, int] = {}
    tile = 0x02
    for row, width in enumerate(_TED_ROW_WIDTHS):
        for col in range(width):
            if row <= 6:
                # Dark blue edge scales frame interleaved gold/crimson armor;
                # stagger each row so no palette boundary spans the sphere.
                if col in (0, width - 1) and row >= 2:
                    palette = 1
                else:
                    palette = 5 if (row + col) % 3 else 1
            else:
                # Preserve vertical tendril identity across animated rows.
                palette = (1, 5, 2)[col % 3]
            result[tile] = palette
            tile += 1
    assert tile == 0x77
    # Animation-only contour fragments use the adjacent shell materials.
    # $7C/$7E/$7F/$81 are the connector halves of the neighboring contour
    # IDs.  Omitting them left native Ted cells on BG0 in extended poses.
    result.update({
        0x7B: 5, 0x7C: 5,
        # $7E is the middle cell of the observed $85/$7E/$85 upper
        # tendril. Keeping it crimson produced two one-row, ruler-straight
        # BG5/BG1/BG5 seams; gold preserves that contour as one material.
        0x7D: 1, 0x7E: 5, 0x7F: 1,
        0x80: 2, 0x81: 2,
        0x82: 5, 0x83: 1, 0x84: 2, 0x85: 5, 0x86: 1,
    })
    return result


TED_BODY_TILE_PAL = _ted_materials()
TED_BODY_TILE_IDS = frozenset(TED_BODY_TILE_PAL)
TED_FLOOR_TILE_PAL = {0x77: 6, 0x78: 7, 0x79: 7, 0x7A: 6}


# The palette numbers refer to the editable BG rows in palettes.yaml:
# BG1 cherry red/crimson, BG2 purple, BG3 green, BG4 ice cyan,
# BG5 orange/red, BG6 blue-gray, BG7 steel/navy.
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

    # A bounded four-material treatment measured from Ted's actual body. The
    # former $17-$FF red span painted unrelated scrolling terrain and omitted
    # the complete $02-$16 upper contour.
    "ted": TED_BODY_TILE_PAL | TED_FLOOR_TILE_PAL,

    # These four tables previously treated later animation chunks as item
    # pickups.  That was the source of the visible horizontal bands.
    "troop": _span(7, 0x23, 0xFF),
    "faze": _span(2, 0x12, 0xFF, exclude=(0x7A,)),
    "angela": _span(2, 0x20, 0xBA) | {0xFF: 2},
    "penta_dragon": _span(1, 0x20, 0xFF),
}
