; Minimal GBC palette init stub (RGBDS syntax)
; Assumes running on CGB. Writes BG and OBJ palettes via auto-increment.
; Hook this after hardware init and VBlank enable.

SECTION "GbcPaletteStub", ROM0

GbcInitPalettes:
    ; Set BG palette write with auto-increment
    ld a, $80           ; bit7=1 -> auto-increment
    ldh [rBCPS], a      ; FF68
    ld hl, BgPaletteData
    ld de, BgPaletteDataEnd - BgPaletteData
.bg_loop:
    ld a, [hl+]
    ldh [rBCPD], a      ; FF69
    dec de
    ld a, d | a         ; quick check if de==0 (not exact; replace with proper)
    jr nz, .bg_loop

    ; Set OBJ palette write with auto-increment
    ld a, $80
    ldh [rOCPS], a      ; FF6A
    ld hl, ObjPaletteData
    ld de, ObjPaletteDataEnd - ObjPaletteData
.obj_loop:
    ld a, [hl+]
    ldh [rOCPD], a      ; FF6B
    dec de
    ld a, d | a
    jr nz, .obj_loop
    ret

; Data blocks (to be filled by patcher)
BgPaletteData:
    ; 8 palettes * 4 colors * 2 bytes = 64 bytes (optional; use as many as needed)
    ; .db <lo>, <hi>, ... for each color in BGR555 LE
BgPaletteDataEnd:

ObjPaletteData:
    ; Similar layout for OBJ palettes
ObjPaletteDataEnd:

; I/O register aliases (for readability)
DEF rBCPS EQU $FF68
DEF rBCPD EQU $FF69
DEF rOCPS EQU $FF6A
DEF rOCPD EQU $FF6B
