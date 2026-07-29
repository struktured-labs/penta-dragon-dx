# Launch Game

Launch the Penta Dragon DX ROM in mGBA with proper display settings for KDE Wayland + Nvidia.

## Steps

1. Launch through the project-owned single-flight guardian (NO pipes, NO
   redirects — those break Wayland window visibility):
   ```bash
   /home/struktured/projects/penta-dragon-dx-claude/scripts/launch_mgba.sh /home/struktured/projects/penta-dragon-dx-claude/rom/working/penta_dragon_dx_FIXED.gb
   ```
   Keep the command session alive while the window is open. The launcher is
   the emulator's parent-death guardian.

2. Optionally load a save state by passing the state arguments through the
   guarded launcher only after its ROM argument.

3. Verify through the project status script; never use raw `pgrep` patterns:
   ```bash
   scripts/check_emulator_processes.sh
   ```

## Critical Notes
- MUST use `DISPLAY=:0 QT_QPA_PLATFORM=xcb __GLX_VENDOR_LIBRARY_NAME=nvidia` — without these, the GPU display device fails and the game runs poorly
- NEVER pipe stdout/stderr — this breaks window visibility on Wayland
- NEVER invoke raw `mgba-qt`, use `pkill`/`killall`, or launch a second
  emulator. The project lock rejects concurrent instances with status 75.
- If the command session or verifier dies, Linux parent-death cleanup
  terminates its exact emulator and releases the lock.
