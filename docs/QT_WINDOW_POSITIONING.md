# Qt Application Window Positioning Guide

## Overview
This guide covers methods to force Qt applications (like mgba-qt) to launch on a specific monitor/desktop.

## Environment Variables

### Qt-Specific Variables

1. **`QT_QPA_PLATFORM`** - Force Qt platform plugin
   ```bash
   QT_QPA_PLATFORM=xcb mgba-qt rom.gb  # Force X11 backend
   QT_QPA_PLATFORM=wayland mgba-qt rom.gb  # Force Wayland backend
   ```

2. **`QT_SCREEN_SCALE_FACTORS`** - Set per-screen scaling
   ```bash
   QT_SCREEN_SCALE_FACTORS="DP-1=1;DP-2=1;DP-3=1" mgba-qt rom.gb
   ```

3. **`QT_QPA_EGLFS_FORCE888`** - Force 888 color format (embedded)

### Display/Window Manager Variables

1. **`DISPLAY`** - X11 display (for X11 sessions)
   ```bash
   DISPLAY=:0.1 mgba-qt rom.gb  # Use second X screen
   ```

2. **`WAYLAND_DISPLAY`** - Wayland display socket
   ```bash
   WAYLAND_DISPLAY=wayland-1 mgba-qt rom.gb
   ```

## Method 1: Environment Variables + Geometry (X11)

```python
import subprocess
import os

env = os.environ.copy()
env['DISPLAY'] = ':0'  # Or specific X screen

# Get monitor geometry (example: 3rd monitor at x=3840)
cmd = ['mgba-qt', 'rom.gb', '--geometry', '3840x0+800+600']
subprocess.Popen(cmd, env=env)
```

## Method 2: Window Manager Tools (Post-Launch)

### wmctrl (X11 - Workspaces/Desktops)
```bash
# List windows
wmctrl -l

# Move window to desktop 3 (0-indexed, so desktop 2)
wmctrl -r "mGBA" -t 2

# Move and resize window
wmctrl -r "mGBA" -e 0,3840,0,800,600  # gravity,x,y,width,height
```

### xdotool (X11 - Window Positioning)
```bash
# Find window by name
WIN_ID=$(xdotool search --name "mGBA")

# Move window to specific position (3rd monitor at x=3840)
xdotool windowmove $WIN_ID 3840 0

# Or combine search and move
xdotool search --name "mGBA" windowmove -- 3840 0
```

### swaymsg (Sway/i3 - Wayland)
```bash
# Move window to specific workspace
swaymsg '[app_id="mgba-qt"] move workspace 3'

# Move to specific output (monitor)
swaymsg '[app_id="mgba-qt"] move to output DP-3'
```

### wlr-randr (Generic Wayland)
```bash
# List outputs
wlr-randr

# Move window (requires compositor support)
```

## Method 3: Python Script with Post-Launch Positioning

```python
import subprocess
import time
import shutil

def launch_qt_on_monitor(app_cmd, monitor_num=3, wait_time=1.5):
    """Launch Qt app and move to specific monitor"""
    
    # Launch app
    proc = subprocess.Popen(app_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(wait_time)  # Wait for window to appear
    
    # Try wmctrl first (desktop switching)
    wmctrl = shutil.which("wmctrl")
    if wmctrl:
        try:
            result = subprocess.run(
                ["wmctrl", "-l"],
                capture_output=True,
                text=True,
                timeout=2
            )
            for line in result.stdout.splitlines():
                if "mGBA" in line or "mgba" in line.lower():
                    win_id = line.split()[0]
                    # Move to desktop (0-indexed)
                    subprocess.run(
                        ["wmctrl", "-i", "-r", win_id, "-t", str(monitor_num - 1)],
                        timeout=2
                    )
                    return True
        except:
            pass
    
    # Try xdotool (window positioning)
    xdotool = shutil.which("xdotool")
    if xdotool:
        try:
            # Get monitor geometry (you may need to query xrandr)
            # Assuming 1920px wide monitors: Monitor 1=0, Monitor 2=1920, Monitor 3=3840
            x_offset = (monitor_num - 1) * 1920
            
            result = subprocess.run(
                ["xdotool", "search", "--name", "mGBA"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.stdout.strip():
                win_id = result.stdout.strip().split()[0]
                subprocess.run(
                    ["xdotool", "windowmove", win_id, str(x_offset), "0"],
                    timeout=2
                )
                return True
        except:
            pass
    
    # Try swaymsg (Sway/i3)
    swaymsg = shutil.which("swaymsg")
    if swaymsg:
        try:
            subprocess.run(
                ["swaymsg", f'[app_id="mgba-qt"]', "move", "to", "output", f"DP-{monitor_num}"],
                timeout=2
            )
            return True
        except:
            pass
    
    return False

# Usage
launch_qt_on_monitor(["mgba-qt", "rom.gb"], monitor_num=3)
```

## Method 4: Query Monitor Geometry First

```python
import subprocess
import re

def get_monitor_geometry(monitor_num=3):
    """Get geometry of specific monitor using xrandr"""
    result = subprocess.run(
        ["xrandr"],
        capture_output=True,
        text=True
    )
    
    lines = result.stdout.splitlines()
    connected = [l for l in lines if "connected" in l]
    
    if monitor_num <= len(connected):
        monitor_line = connected[monitor_num - 1]
        # Parse: DP-1 connected primary 3440x1440+0+0
        match = re.search(r'(\d+)x(\d+)\+(\d+)\+(\d+)', monitor_line)
        if match:
            width, height, x, y = map(int, match.groups())
            return (x, y, width, height)
    
    return None

# Get 3rd monitor position
geo = get_monitor_geometry(3)
if geo:
    x, y, w, h = geo
    # Use x,y for window positioning
```

## Method 5: Qt Application Arguments

Some Qt apps support geometry arguments:
```bash
mgba-qt --geometry 3840x0+800+600 rom.gb
# Format: WIDTHxHEIGHT+X+Y
```

## Method 6: Wayland-Specific (Sway/i3)

For Sway/i3 compositors on Wayland:
```python
import subprocess

def launch_on_wayland_output(app_cmd, output_name="DP-3"):
    """Launch app and move to specific Wayland output"""
    proc = subprocess.Popen(app_cmd)
    time.sleep(1)
    
    # Use swaymsg to move window
    subprocess.run([
        "swaymsg",
        f'[app_id="mgba-qt"]',
        "move", "to", "output", output_name
    ])
```

## Complete Example for auto_palette_loop.py

```python
def launch_mgba_with_lua(lua_script_path, target_monitor=3):
    """Launch mgba-qt and position on specific monitor"""
    mgba_qt_path = Path("/usr/local/bin/mgba-qt")
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb").resolve()
    
    cmd = [
        str(mgba_qt_path),
        str(rom_path),
        "--fastforward",
        "--script", str(lua_script_path.resolve())
    ]
    
    # Launch
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Wait for window
    time.sleep(1.5)
    
    # Position window
    position_window("mGBA", target_monitor)
    
    return proc

def position_window(window_name, monitor_num=3):
    """Position window on specific monitor using available tools"""
    import shutil
    
    # Get monitor geometry
    geo = get_monitor_geometry(monitor_num)
    if not geo:
        x_offset = (monitor_num - 1) * 1920  # Fallback estimate
    else:
        x_offset = geo[0]
    
    # Try different methods
    methods = [
        lambda: try_wmctrl(window_name, monitor_num),
        lambda: try_xdotool(window_name, x_offset),
        lambda: try_swaymsg(window_name, monitor_num),
    ]
    
    for method in methods:
        if method():
            return True
    
    return False
```

## Notes

- **Wayland Limitations**: Wayland doesn't support arbitrary window positioning. Compositor-specific tools (swaymsg, etc.) are needed.
- **X11**: More flexible with xdotool/wmctrl
- **Timing**: Always wait 1-2 seconds after launching before positioning
- **Window Name Matching**: May need to try variations: "mGBA", "mgba-qt", "mGBA-Qt", etc.

