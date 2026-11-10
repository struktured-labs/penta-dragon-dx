# #81 menu-open-map-hold

Select pressed two frames after an `FFBD` room-id change published the
inventory to the current window map (`$9800` while LCDC=`8B`/`AB`) and then
the attract-shared VBlank packed-map commit (`0D:7459`, `xor $48`) swapped
LCDC.3/.6. The menu tiles became the BG, and the menu was published again to
the new window map — a persistent double HUD, identical on JP and EN.

The fix is gameplay-only: `14:7F32` (the RET after the menu window-enable
hook sets LCDC.5) now clears `FFC4` so the ISR pretest skips the pending
commit while the menu is up. The ISR itself is not modified; attract timing
is unchanged. Closing the menu uses `RES 5` and later commits resume.

A live gate, `verify_select_roomchange_menu.py`, presses Select two frames
after each starting-area room change on JP and on an EN image rebuilt from
the committed translation delta, and rejects a double HP bar at y=31-33 and
y=131-133.

#82 was measured on the same 3→1 doorway: the large black region on the
right is the settled shaft geometry (black pixel count is stable from the
change frame through +24). It is not this mid-menu map flip and is not
closed by this stage.
