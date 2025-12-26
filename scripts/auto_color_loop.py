#!/usr/bin/env python3
"""Automated color verification loop for Penta Dragon DX.

Workflow:
1. Inject palettes with VBlank hook (guaranteed execution each frame).
2. Launch mGBA headless or GUI minimized for N frames.
3. After delay, trigger screenshot or savestate (if CLI supports --savestate loading first, we can pre-place player in level 1).
4. Repeat until palette registers produce non-DMG defaults.

Current constraints:
- mGBA Qt binary installed; headless binary may be mgba-sdl or mgba (platform dependent).
- This script focuses on repeated ROM regeneration and simple presence check (CGB flag + stub presence).

Future extension points (TODO markers) for: savestate loading, screenshot extraction, pixel diff.
"""

from __future__ import annotations
import subprocess, shutil, time, sys, pathlib, tempfile
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROM_ORIG = ROOT / "rom" / "Penta Dragon (J).gb"
WORKING = ROOT / "rom" / "working" / "penta_dx.gb"
PALETTES = ROOT / "palettes" / "penta_palettes.yaml"

CLI = ["uv", "run", "penta-colorize", "inject",
       "--rom", str(ROM_ORIG),
       "--palette-file", str(PALETTES),
       "--out", str(WORKING),
       "--vblank"]

EMULATOR_CANDIDATES = ["/usr/local/bin/mgba-headless", "mgba-headless", "mgba", "mgba-sdl", "mgba-qt"]

def find_emulator() -> Optional[str]:
    for exe in EMULATOR_CANDIDATES:
        p = shutil.which(exe)
        if p:
            return p
    return None

def inject_rom() -> bool:
    print("[inject] Running palette injector with VBlank hook...")
    proc = subprocess.run(CLI, capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        return False
    if not WORKING.exists():
        print("[inject] Output ROM missing", file=sys.stderr)
        return False
    # Simple header flag verification (CGB support) at 0x143
    with WORKING.open("rb") as f:
        f.seek(0x143)
        flag = f.read(1)
    print(f"[inject] CGB flag byte: 0x{flag[0]:02X}")
    if flag[0] == 0x00:
        print("[inject] Warning: CGB flag not set; emulator may stay in DMG mode.")
    return True

def launch_headless_with_script(emulator: str, savestate: Optional[pathlib.Path]) -> None:
    args = [emulator, str(WORKING)]
    if savestate and savestate.exists():
        args += ["--savestate", str(savestate)]
    # Use scripting to take screenshot and exit
    script = ROOT / "scripts" / "capture.lua"
    args += ["--script", str(script)]
    print(f"[emu] Launching: {' '.join(args)}")
    subprocess.run(args, check=False)

def main():
    emulator = find_emulator()
    if not emulator:
        print("No mGBA emulator found in PATH.")
        sys.exit(1)
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    savestate = ROOT / "rom" / "stage1.ss0"
    for i in range(iterations):
        print(f"=== Iteration {i+1}/{iterations} ===")
        if not inject_rom():
            print("Injection failed; aborting.")
            break
        launch_headless_with_script(emulator, savestate)
        out_png = ROOT / "rom" / "working" / "frame.png"
        if out_png.exists():
            print(f"[emu] Screenshot captured: {out_png}")
        else:
            print("[emu] Screenshot not found; scripting may not be supported in this emulator build.")
    print("Done.")

if __name__ == "__main__":
    main()
